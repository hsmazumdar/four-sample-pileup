"""Segment-first protocol for constructed Fe-55 pile-up.

Historical V5 draws train and test snippets from the same recording
buffers, and it fits the CR–RC^8 template on the whole campaign. This
module assigns buffers first, then extracts, fits, trains, and scores.

Two constructions are kept separate:

* ``conditional_two_pulse`` — exactly one host, and optionally one guest
  at a controlled peak-to-peak gap. This is not a count rate.
* ``unconditional_stream`` — many pulses on one measured baseline.
  Inter-arrival times are i.i.d. exponential. That Poisson process is a
  modelling assumption, labelled on every stream row. It is not a
  high-rate recording.

No second pedestal and no extra Gaussian are added unless a caller passes
``extra_noise_ch`` for the labelled SNR stress test.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np

from sparse_pileup.constants import (
    ADC_CHANNELS,
    CR_RC_N,
    CR_RC_TAU_SAMPLES,
    GAP_HIGH,
    GAP_LOW,
    PEDESTAL_CH,
    PILEUP_PERIOD,
    REAL_ISO_DT_SAMPLES,
    REAL_SNIPPET_PRE,
    SAMPLE_STRIDE,
    START_OFFSET,
    START_SPAN,
    WAVEFORM_LEN,
)
from sparse_pileup.ls_peak import LsPeakEstimator, estimate_offsets
from sparse_pileup.metrics import wilson_interval
from sparse_pileup.real_sdd import (
    DEFAULT_LEAVE_CH,
    DEFAULT_PULSE_THR,
    FE55_AMP_HI,
    FE55_AMP_LO,
    SAMPLES_PER_SEGMENT,
    classify_amplitude,
    load_manifest,
    load_metadata,
    repo_root,
)
from sparse_pileup.sampler import extract_frame, extract_n_taps, quantize_4096

# Pre-specified. Not tuned on a test score.
COINCIDENCE_SAMPLES = 20  # 2.0 µs, the upper gap of the V5 conditional study
COINCIDENCE_S = COINCIDENCE_SAMPLES / 10_000_000.0
TAP_APERTURE_SAMPLES = 12  # 1.2 µs latch
FOOTPRINT_PRE = 16
FOOTPRINT_POST = 24
FORWARD_P_TARGETS = (0.02, 0.05, 0.10, 0.20, 0.35)
N_TRAIN = 4000
N_VAL = 1000
N_TEST_PREV = 1000
N_STREAM_PULSES = 3000
N_CELL = 160
EPOCHS = 40
GAPS = (3, 4, 5, 6, 8, 10, 12, 16, 20)
RATIOS = (0.25, 0.5, 1.0, 2.0, 4.0)
EXTRA_NOISE_CH = (0.0, 10.0, 20.0, 40.0)
PRIMARY_RUN = "blocked-42"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_file(path)


@dataclass
class Snippet:
    segment_index: int
    local_peak: int
    adc: np.ndarray
    baseline_ch: float
    amplitude_ch: float


@dataclass
class SegmentRecord:
    index: int
    name: str
    sha256: str
    n_pulses: int
    n_fe55: int
    n_high: int
    n_isolated: int
    n_edge_dropped: int
    first_peak: int | None
    last_peak: int | None
    snippets: list[Snippet]
    baseline: np.ndarray


@dataclass
class Campaign:
    records: list[SegmentRecord]
    live_time_s: float
    n_cross_boundary_close: int
    metadata_sha256: str
    manifest_sha256: str

    def by_index(self) -> dict[int, SegmentRecord]:
        return {r.index: r for r in self.records}


@dataclass
class TemplateFit:
    segment_ids: tuple[int, ...]
    n_snippets: int
    tau_samples: float
    tau_grid_step: float
    fit_mse: float
    pedestal_ch: float
    baseline_sigma_ch: float
    support_pre_samples: int
    support_post_samples: int
    mean_unit: np.ndarray
    published_tau_samples: float = CR_RC_TAU_SAMPLES
    published_pedestal_ch: float = PEDESTAL_CH


@dataclass
class PreparedSplit:
    run_id: str
    mode: str
    seed: int
    train_ids: tuple[int, ...]
    val_ids: tuple[int, ...]
    test_ids: tuple[int, ...]
    train: list[Snippet]
    val: list[Snippet]
    test: list[Snippet]
    template: TemplateFit
    baseline_pool: np.ndarray


def _find_pulses_one(x: np.ndarray) -> list[tuple[int, int, int]]:
    """Return (local_peak, amplitude, kind_code) inside one buffer.

    kind_code: 2 high artifact, 1 Fe-55 window, 0 other.
    """
    n = int(x.size)
    out: list[tuple[int, int, int]] = []
    i = 0
    while i < n:
        if x[i] < DEFAULT_PULSE_THR:
            i += 1
            continue
        start = i
        while start > 0 and x[start] > DEFAULT_LEAVE_CH:
            start -= 1
        end = i
        while end < n and x[end] > DEFAULT_LEAVE_CH:
            end += 1
        if end - start >= 5:
            rel = int(np.argmax(x[start:end]))
            peak = start + rel
            amp = int(x[peak])
            kind = classify_amplitude(amp)
            code = 2 if kind == "high" else 1 if kind == "fe55" else 0
            out.append((peak, amp, code))
        i = max(end, i + 1)
    return out


def _isolate(x: np.ndarray, pulses: list[tuple[int, int, int]], segment_index: int) -> tuple[list[Snippet], int]:
    """Keep Fe-55 pulses isolated inside this buffer and clear of both edges."""
    pre = REAL_SNIPPET_PRE
    post = WAVEFORM_LEN - pre
    n = int(x.size)
    kept: list[Snippet] = []
    edge_dropped = 0
    for i, (peak, amp, code) in enumerate(pulses):
        if code != 1:
            continue
        if not (FE55_AMP_LO <= amp <= FE55_AMP_HI):
            continue
        if peak < REAL_ISO_DT_SAMPLES or peak + REAL_ISO_DT_SAMPLES > n:
            edge_dropped += 1
            continue
        if peak - pre < 0 or peak + post > n:
            edge_dropped += 1
            continue
        prev_dt = None if i == 0 else peak - pulses[i - 1][0]
        next_dt = None if i + 1 == len(pulses) else pulses[i + 1][0] - peak
        if prev_dt is not None and prev_dt < REAL_ISO_DT_SAMPLES:
            continue
        if next_dt is not None and next_dt < REAL_ISO_DT_SAMPLES:
            continue
        adc = x[peak - pre : peak + post].astype(np.int16)
        baseline = float(np.mean(adc[:8]))
        height = float(adc[pre]) - baseline
        if height < 200:
            continue
        kept.append(
            Snippet(
                segment_index=int(segment_index),
                local_peak=int(peak),
                adc=adc,
                baseline_ch=baseline,
                amplitude_ch=height,
            )
        )
    return kept, edge_dropped


def _quiet_baseline(x: np.ndarray, pulses: list[tuple[int, int, int]]) -> np.ndarray:
    """Samples far from every detected pulse. One noise realization, no pulses."""
    mask = np.ones(x.size, dtype=bool)
    for peak, _amp, _code in pulses:
        a = max(0, peak - REAL_ISO_DT_SAMPLES)
        b = min(x.size, peak + REAL_ISO_DT_SAMPLES)
        mask[a:b] = False
    mask &= x < 80
    return x[mask].astype(np.float32)


def scan_campaign(root: Path | None = None) -> Campaign:
    root = root or repo_root()
    meta_path = root / "real_data" / "metadata.json"
    man_path = root / "real_data" / "manifest.csv"
    meta = load_metadata(root)
    records: list[SegmentRecord] = []
    manifest = load_manifest(root)
    for n_done, seg in enumerate(manifest, start=1):
        raw = np.loadtxt(seg.path, dtype=np.int32)
        if raw.size != SAMPLES_PER_SEGMENT:
            raise RuntimeError(f"{seg.name} has {raw.size} samples, expected {SAMPLES_PER_SEGMENT}")
        pulses = _find_pulses_one(raw)
        snippets, n_edge = _isolate(raw, pulses, seg.index)
        n_fe = sum(1 for p in pulses if p[2] == 1)
        n_hi = sum(1 for p in pulses if p[2] == 2)
        records.append(
            SegmentRecord(
                index=seg.index,
                name=seg.name,
                sha256=sha256_file(seg.path),
                n_pulses=len(pulses),
                n_fe55=n_fe,
                n_high=n_hi,
                n_isolated=len(snippets),
                n_edge_dropped=n_edge,
                first_peak=None if not pulses else int(pulses[0][0]),
                last_peak=None if not pulses else int(pulses[-1][0]),
                snippets=snippets,
                baseline=_quiet_baseline(raw, pulses),
            )
        )
        if n_done == 1 or n_done == len(manifest) or n_done % 10 == 0:
            print(f"  scanned {n_done}/{len(manifest)} {seg.name} isolated={len(snippets)}", flush=True)
    n_cross = 0
    for a, b in zip(records, records[1:]):
        if a.last_peak is None or b.first_peak is None:
            continue
        gap = (SAMPLES_PER_SEGMENT - a.last_peak) + b.first_peak
        if gap < REAL_ISO_DT_SAMPLES:
            n_cross += 1
    return Campaign(
        records=records,
        live_time_s=float(meta["live_time_s"]),
        n_cross_boundary_close=n_cross,
        metadata_sha256=sha256_file(meta_path),
        manifest_sha256=sha256_file(man_path),
    )


def split_segment_ids(mode: str, seed: int, n_segments: int = 61) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """60/20/20 of recording buffers. ``blocked`` follows acquisition order."""
    ids = np.arange(1, n_segments + 1)
    if mode == "blocked":
        order = ids
    elif mode == "random":
        rng = np.random.default_rng(seed)
        order = rng.permutation(ids)
    else:
        raise ValueError(mode)
    n_train = int(round(0.60 * n_segments))
    n_val = int(round(0.20 * n_segments))
    train = tuple(int(i) for i in order[:n_train])
    val = tuple(int(i) for i in order[n_train : n_train + n_val])
    test = tuple(int(i) for i in order[n_train + n_val :])
    if set(train) & set(val) or set(train) & set(test) or set(val) & set(test):
        raise RuntimeError("segment split is not disjoint")
    if len(train) + len(val) + len(test) != n_segments:
        raise RuntimeError("segment split does not cover every buffer")
    return train, val, test


def _snippets_for(campaign: Campaign, ids: tuple[int, ...]) -> list[Snippet]:
    table = campaign.by_index()
    out: list[Snippet] = []
    for i in ids:
        out.extend(table[i].snippets)
    return out


def _baseline_pool(campaign: Campaign, ids: tuple[int, ...]) -> np.ndarray:
    table = campaign.by_index()
    parts = [table[i].baseline for i in ids if table[i].baseline.size]
    if not parts:
        raise RuntimeError("train buffers produced no quiet baseline")
    return np.concatenate(parts).astype(np.float32)


def fit_template(snippets: list[Snippet], segment_ids: tuple[int, ...]) -> TemplateFit:
    """CR–RC^8 tau and the empirical mean, from these snippets only."""
    if len(snippets) < 20:
        raise RuntimeError(f"need >= 20 train snippets to fit a template, got {len(snippets)}")
    bad = sorted({s.segment_index for s in snippets} - set(segment_ids))
    if bad:
        raise RuntimeError(f"template saw segments outside the train split: {bad[:8]}")
    acc = np.zeros(WAVEFORM_LEN, dtype=np.float64)
    n = 0
    for s in snippets:
        y = s.adc.astype(np.float64) - s.baseline_ch
        peak = float(y[REAL_SNIPPET_PRE])
        if peak <= 50:
            continue
        acc += y / peak
        n += 1
    mean = acc / n
    mean = np.clip(mean, 0.0, None)
    if mean.max() <= 0:
        raise RuntimeError("empirical mean pulse is empty")
    mean = mean / mean.max()
    peak_at = REAL_SNIPPET_PRE
    i0 = max(0, peak_at - 20)
    i1 = min(WAVEFORM_LEN, peak_at + 31)
    target = mean[i0:i1]
    step = 0.002
    best_tau, best_mse = float(CR_RC_TAU_SAMPLES), 1e9
    grid = np.arange(0.6, 2.4 + 0.5 * step, step)
    tt = np.arange(WAVEFORM_LEN, dtype=np.float64) - float(peak_at)
    for tau in grid:
        u = (tt + CR_RC_N * tau) / tau
        kern = np.zeros(WAVEFORM_LEN, dtype=np.float64)
        m = u >= 0.0
        uu = u[m]
        kern[m] = (uu / CR_RC_N) ** CR_RC_N * np.exp(CR_RC_N - uu)
        sl = kern[i0:i1]
        mse = float(np.mean((sl - target) ** 2))
        if mse < best_mse:
            best_mse = mse
            best_tau = float(tau)
    above = np.flatnonzero(mean > 0.02)
    if above.size:
        support_pre = int(peak_at - above[0])
        support_post = int(above[-1] - peak_at)
    else:
        support_pre, support_post = 0, 0
    bases = np.array([s.baseline_ch for s in snippets], dtype=np.float64)
    wings = np.concatenate([s.adc[:8].astype(np.float64) - s.baseline_ch for s in snippets])
    return TemplateFit(
        segment_ids=tuple(segment_ids),
        n_snippets=int(n),
        tau_samples=best_tau,
        tau_grid_step=step,
        fit_mse=best_mse,
        pedestal_ch=float(bases.mean()),
        baseline_sigma_ch=float(wings.std()),
        support_pre_samples=support_pre,
        support_post_samples=support_post,
        mean_unit=mean,
    )


def assert_no_leakage(prep: PreparedSplit) -> None:
    tr, va, te = set(prep.train_ids), set(prep.val_ids), set(prep.test_ids)
    if tr & va or tr & te or va & te:
        raise AssertionError("segment ids overlap across splits")
    for name, rows, allowed in (
        ("train", prep.train, tr),
        ("val", prep.val, va),
        ("test", prep.test, te),
    ):
        seen = {s.segment_index for s in rows}
        if not seen <= allowed:
            raise AssertionError(f"{name} snippets leave their segment split")
    if set(prep.template.segment_ids) != tr:
        raise AssertionError("template segment ids are not the train split")
    used = {s.segment_index for s in prep.train}
    if not used <= tr:
        raise AssertionError("template snippets are not train-only")


def historical_pulse_leakage(root: Path | None = None, seed: int = 42) -> dict:
    """V5 unique-pulse split. Expected to share every buffer across splits."""
    root = root or repo_root()
    path = root / "real_data" / "isolated_fe55_snippets.npz"
    z = np.load(path)
    seg = z["segment_index"]
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(seg))
    n_train = int(round(0.60 * len(seg)))
    n_val = int(round(0.20 * len(seg)))
    tr = seg[order[:n_train]]
    va = seg[order[n_train : n_train + n_val]]
    te = seg[order[n_train + n_val :]]
    tr_s, va_s, te_s = set(tr.tolist()), set(va.tolist()), set(te.tolist())
    return {
        "protocol": "v5_pulse_level_split",
        "seed": seed,
        "n_snippets": int(len(seg)),
        "n_train": int(len(tr)),
        "n_val": int(len(va)),
        "n_test": int(len(te)),
        "n_train_segments": len(tr_s),
        "n_val_segments": len(va_s),
        "n_test_segments": len(te_s),
        "n_test_segments_also_in_train": len(te_s & tr_s),
        "n_test_snippets_whose_segment_is_in_train": int(np.isin(te, list(tr_s)).sum()),
        "n_val_segments_also_in_train": len(va_s & tr_s),
    }


def prepare_split(campaign: Campaign, mode: str, seed: int) -> PreparedSplit:
    train_ids, val_ids, test_ids = split_segment_ids(mode, seed, n_segments=len(campaign.records))
    train = _snippets_for(campaign, train_ids)
    val = _snippets_for(campaign, val_ids)
    test = _snippets_for(campaign, test_ids)
    if min(len(train), len(val), len(test)) < 30:
        raise RuntimeError(
            f"split {mode}-{seed} is too small: {len(train)}/{len(val)}/{len(test)} snippets"
        )
    template = fit_template(train, train_ids)
    prep = PreparedSplit(
        run_id=f"{mode}-{seed}",
        mode=mode,
        seed=int(seed),
        train_ids=train_ids,
        val_ids=val_ids,
        test_ids=test_ids,
        train=train,
        val=val,
        test=test,
        template=template,
        baseline_pool=_baseline_pool(campaign, train_ids),
    )
    assert_no_leakage(prep)
    return prep


def _place_excess(canvas: np.ndarray, src: np.ndarray, peak_dst: int, peak_src: int = REAL_SNIPPET_PRE) -> None:
    shift = int(peak_dst - peak_src)
    src_lo = max(0, -shift)
    src_hi = min(src.size, canvas.size - shift)
    if src_lo >= src_hi:
        return
    dst_lo = src_lo + shift
    dst_hi = src_hi + shift
    canvas[dst_lo:dst_hi] += src[src_lo:src_hi]


def compose_conditional(
    host: Snippet,
    *,
    t1: int,
    guest: Snippet | None = None,
    gap: int = 0,
    guest_scale: float = 1.0,
    extra_noise_ch: float = 0.0,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, int]:
    """Host ADC plus optional guest excess.

    Returns the full-scale wave, the count of samples above 4095 before
    clipping, and the count below 0. Sub-zero samples are baseline
    mismatch of a few channels, not spectroscopic saturation.
    """
    canvas = np.zeros(WAVEFORM_LEN, dtype=np.float64)
    _place_excess(canvas, host.adc.astype(np.float64), t1)
    if guest is not None and gap > 0:
        excess = (guest.adc.astype(np.float64) - guest.baseline_ch) * float(guest_scale)
        _place_excess(canvas, excess, t1 + int(gap))
    if extra_noise_ch > 0.0:
        if rng is None:
            raise ValueError("extra_noise_ch requires an explicit rng")
        canvas = canvas + rng.normal(0.0, float(extra_noise_ch), size=WAVEFORM_LEN)
    n_high = int(np.sum(canvas > float(ADC_CHANNELS - 1)))
    n_low = int(np.sum(canvas < 0.0))
    canvas = np.clip(canvas, 0.0, float(ADC_CHANNELS - 1))
    return canvas / float(ADC_CHANNELS), n_high, n_low


def _draw_pair(snippets: list[Snippet], rng: np.random.Generator, piled: bool) -> tuple[Snippet, Snippet | None]:
    n = len(snippets)
    host = snippets[int(rng.integers(0, n))]
    if not piled:
        return host, None
    guest = snippets[int(rng.integers(0, n))]
    guard = 0
    while guest is host and n > 1 and guard < 8:
        guest = snippets[int(rng.integers(0, n))]
        guard += 1
    return host, guest


def make_conditional_events(
    snippets: list[Snippet],
    rng: np.random.Generator,
    n: int,
    *,
    force_pileup: bool | None = None,
    gap: int | None = None,
    target_ratio: float | None = None,
    extra_noise_ch: float = 0.0,
    pileup_period: int = PILEUP_PERIOD,
) -> list[dict]:
    """Conditional two-pulse (or single) records. Not a Poisson stream."""
    out: list[dict] = []
    attempts = 0
    limit = max(n * 30, n + 10)
    while len(out) < n and attempts < limit:
        attempts += 1
        if force_pileup is None:
            piled = bool(rng.integers(0, pileup_period) == 0)
        else:
            piled = bool(force_pileup)
        host, guest = _draw_pair(snippets, rng, piled)
        t1 = START_OFFSET + int(rng.integers(0, START_SPAN))
        used_gap = 0
        scale = 1.0
        if piled and guest is not None:
            used_gap = int(gap) if gap is not None else int(rng.integers(GAP_LOW, GAP_HIGH))
            if target_ratio is not None and guest.amplitude_ch > 1.0:
                scale = float(target_ratio) * host.amplitude_ch / guest.amplitude_ch
        wave, n_high, n_low = compose_conditional(
            host,
            t1=t1,
            guest=guest if piled else None,
            gap=used_gap,
            guest_scale=scale,
            extra_noise_ch=extra_noise_ch,
            rng=rng,
        )
        frame = extract_frame(wave)
        if frame is None:
            continue
        a2 = None
        if piled and guest is not None:
            a2 = guest.amplitude_ch * scale
        out.append(
            {
                "study": "conditional_two_pulse",
                "waveform": wave,
                "samples": frame.samples,
                "indices": frame.indices,
                "is_pileup": piled,
                "a1_ch": host.amplitude_ch,
                "a2_ch": a2,
                "gap": used_gap,
                "guest_scale": scale if piled else 0.0,
                "n_saturated_high": n_high,
                "n_below_zero": n_low,
                "host_segment": host.segment_index,
                "guest_segment": None if guest is None or not piled else guest.segment_index,
                "extra_noise_ch": float(extra_noise_ch),
            }
        )
    if len(out) < n:
        raise RuntimeError(f"conditional synthesis produced {len(out)}/{n}")
    return out


def make_balanced(
    snippets: list[Snippet],
    rng: np.random.Generator,
    n_each: int,
    **kwargs,
) -> list[dict]:
    singles = make_conditional_events(snippets, rng, n_each, force_pileup=False, **kwargs)
    piled = make_conditional_events(snippets, rng, n_each, force_pileup=True, **kwargs)
    return singles + piled


def rate_grid(measured_hz: float) -> list[dict]:
    """Measured Fe-55 rate, plus Poisson rates at pre-specified forward probabilities."""
    rows = [
        {
            "tag": "measured_fe55_rate",
            "rate_hz": float(measured_hz),
            "modelling_assumption": "poisson_exponential_interarrival",
            "modelling_p_forward_within_2us": float(1.0 - np.exp(-measured_hz * COINCIDENCE_S)),
            "rate_source": (
                "lambda equals the measured Fe-55 pulse rate. "
                "Arrival times are still i.i.d. exponential, not the measured timestamps."
            ),
        }
    ]
    for p in FORWARD_P_TARGETS:
        lam = float(-np.log(1.0 - p) / COINCIDENCE_S)
        rows.append(
            {
                "tag": f"model_p_forward_{p:.2f}",
                "rate_hz": lam,
                "modelling_assumption": "poisson_exponential_interarrival",
                "modelling_p_forward_within_2us": float(p),
                "rate_source": (
                    "lambda set so that 1-exp(-lambda*2us) equals the target "
                    "under a homogeneous Poisson process. Modelling assumption."
                ),
            }
        )
    return rows


def _apply_footprint(
    canvas: np.ndarray,
    occupied: np.ndarray,
    origin: int,
    peak_abs: int,
    snip: Snippet,
) -> None:
    """First writer copies measured samples. A later pulse adds excess only."""
    si0 = REAL_SNIPPET_PRE - FOOTPRINT_PRE
    si1 = REAL_SNIPPET_PRE + FOOTPRINT_POST
    for si in range(si0, si1):
        di = int(peak_abs - origin - REAL_SNIPPET_PRE + si)
        if di < 0 or di >= canvas.size:
            continue
        sample = float(snip.adc[si])
        if not occupied[di]:
            canvas[di] = sample
            occupied[di] = True
        else:
            canvas[di] += sample - snip.baseline_ch


def synthesize_stream(
    snippets: list[Snippet],
    baseline_pool: np.ndarray,
    rng: np.random.Generator,
    *,
    rate_hz: float,
    n_pulses: int,
) -> tuple[list[dict], dict]:
    """Unconditional stream under an exponential-arrival model.

    The baseline pool is quiet measured samples from the train buffers.
    Each pulse footprint is written once. Overlap adds baseline-subtracted
    excess only. No synthetic Gaussian and no second pedestal.
    """
    if rate_hz <= 0:
        raise ValueError("rate_hz must be positive")
    if baseline_pool.size < 500:
        raise RuntimeError("baseline pool is too short")
    mean_gap = 10_000_000.0 / float(rate_hz)
    gaps = rng.exponential(mean_gap, size=n_pulses)
    # Keep a pulse from landing on sample 0. Gaps are still exponential.
    peaks = np.cumsum(gaps)
    peaks = peaks - peaks[0] + 80.0
    peaks_i = np.rint(peaks).astype(np.int64)
    # Split where consecutive pulses cannot share a footprint or a 2 µs label.
    cuts = np.flatnonzero(np.diff(peaks_i) > 200)
    starts = np.concatenate([[0], cuts + 1])
    ends = np.concatenate([cuts + 1, [n_pulses]])
    records: list[dict] = []
    n_saturated_high = 0
    n_below_zero = 0
    n_tiled = 0
    for a, b in zip(starts, ends):
        cluster_peaks = peaks_i[a:b]
        pad_l, pad_r = 40, 90
        origin = int(cluster_peaks[0] - pad_l)
        length = int(cluster_peaks[-1] + pad_r - origin)
        if baseline_pool.size >= length:
            start = int(rng.integers(0, baseline_pool.size - length + 1))
            canvas = baseline_pool[start : start + length].astype(np.float64)
        else:
            reps = int(np.ceil(length / baseline_pool.size)) + 1
            tiled = np.tile(baseline_pool, reps)
            start = int(rng.integers(0, tiled.size - length + 1))
            canvas = tiled[start : start + length].astype(np.float64)
            n_tiled += 1
        occupied = np.zeros(length, dtype=bool)
        chosen = [snippets[int(rng.integers(0, len(snippets)))] for _ in range(b - a)]
        for pk, sn in zip(cluster_peaks, chosen):
            _apply_footprint(canvas, occupied, origin, int(pk), sn)
        n_saturated_high += int(np.sum(canvas > float(ADC_CHANNELS - 1)))
        n_below_zero += int(np.sum(canvas < 0.0))
        canvas = np.clip(canvas, 0.0, float(ADC_CHANNELS - 1))
        local_peaks = [int(pk - origin) for pk in cluster_peaks]
        above = canvas >= 100.0
        prev = np.concatenate([[False], above[:-1]])
        rises = np.flatnonzero(above & ~prev)
        next_ok = 0
        accepted: list[int] = []
        for r in rises:
            if r < next_ok or r + (4 - 1) * SAMPLE_STRIDE >= length:
                continue
            accepted.append(int(r))
            next_ok = int(r) + TAP_APERTURE_SAMPLES + 1
        for trig in accepted:
            cands = [p for p in local_peaks if trig - 2 <= p <= trig + 18]
            if not cands:
                records.append(
                    {
                        "study": "unconditional_stream",
                        "matched": False,
                        "trig": trig,
                    }
                )
                continue
            primary = min(cands, key=lambda p: (0 if p >= trig else 1, abs(p - trig)))
            idx = local_peaks.index(primary)
            later = [p for p in local_peaks if p > primary]
            earlier = [p for p in local_peaks if p < primary]
            dt_next = int(later[0] - primary) if later else None
            dt_prev = int(primary - earlier[-1]) if earlier else None
            n_other = 0
            if dt_next is not None and dt_next <= COINCIDENCE_SAMPLES:
                n_other += sum(1 for p in later if p - primary <= COINCIDENCE_SAMPLES)
            if dt_prev is not None and dt_prev <= COINCIDENCE_SAMPLES:
                n_other += sum(1 for p in earlier if primary - p <= COINCIDENCE_SAMPLES)
            sl = canvas[trig : trig + 80]
            wave = sl / float(ADC_CHANNELS)
            frame = extract_frame(wave)
            frame8 = extract_n_taps(wave, 8, 2)
            if frame is None:
                continue
            records.append(
                {
                    "study": "unconditional_stream",
                    "matched": True,
                    "samples": frame.samples,
                    "samples8": None if frame8 is None else frame8.samples,
                    "waveform": wave,
                    "a1_ch": chosen[idx].amplitude_ch,
                    "dt_next": dt_next,
                    "dt_prev": dt_prev,
                    "label_either_2us": bool(
                        (dt_next is not None and 0 < dt_next <= COINCIDENCE_SAMPLES)
                        or (dt_prev is not None and 0 < dt_prev <= COINCIDENCE_SAMPLES)
                    ),
                    "label_either_4us": bool(
                        (dt_next is not None and 0 < dt_next <= 40)
                        or (dt_prev is not None and 0 < dt_prev <= 40)
                    ),
                    "label_forward_2us": bool(dt_next is not None and 0 < dt_next <= COINCIDENCE_SAMPLES),
                    "backward_only": bool(
                        (dt_prev is not None and 0 < dt_prev <= COINCIDENCE_SAMPLES)
                        and not (dt_next is not None and 0 < dt_next <= COINCIDENCE_SAMPLES)
                    ),
                    "n_other_within_2us": int(n_other),
                    "host_segment": chosen[idx].segment_index,
                }
            )
    meta = {
        "study": "unconditional_stream",
        "modelling_assumption": "poisson_exponential_interarrival",
        "rate_hz": float(rate_hz),
        "n_pulses_drawn": int(n_pulses),
        "mean_gap_samples_requested": float(mean_gap),
        "n_triggers_matched": int(sum(1 for r in records if r.get("matched"))),
        "n_triggers_unmatched": int(sum(1 for r in records if not r.get("matched"))),
        "n_saturated_high_samples": int(n_saturated_high),
        "n_below_zero_samples": int(n_below_zero),
        "n_clusters_tiled_baseline": int(n_tiled),
        "coincidence_samples": COINCIDENCE_SAMPLES,
        "latch_dead_samples": TAP_APERTURE_SAMPLES + 1,
        "noise": "one measured baseline trace; pulse footprint copied from the snippet; overlap adds excess only",
    }
    return records, meta


def prf_counts(scores: np.ndarray, labels: np.ndarray, thr: float) -> dict:
    scores = np.asarray(scores, dtype=np.float64)
    y = np.asarray(labels, dtype=bool)
    pred = scores >= thr
    tp = int(np.sum(pred & y))
    fp = int(np.sum(pred & ~y))
    tn = int(np.sum(~pred & ~y))
    fn = int(np.sum(~pred & y))
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    n_pos = int(y.sum())
    n_neg = int((~y).sum())
    return {
        "n": int(y.size),
        "n_pos": n_pos,
        "n_neg": n_neg,
        "prevalence": (n_pos / y.size) if y.size else 0.0,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "fpr": (fp / n_neg) if n_neg else 0.0,
        "threshold": float(thr),
        "recall_ci95_lo": wilson_interval(tp, n_pos)[0],
        "recall_ci95_hi": wilson_interval(tp, n_pos)[1],
        "precision_ci95_lo": wilson_interval(tp, tp + fp)[0],
        "precision_ci95_hi": wilson_interval(tp, tp + fp)[1],
    }


def select_threshold(
    scores: np.ndarray,
    labels: np.ndarray,
    *,
    mode: str = "probability",
) -> tuple[float, float]:
    """Max F1 on this set only. Ties take the higher threshold.

    ``probability`` is the 0.05–0.95 grid for sigmoid scores.
    ``quantile`` is for raw residual scores, whose scale is not a probability.
    """
    if mode == "quantile":
        grid = np.unique(np.quantile(np.asarray(scores, dtype=np.float64), np.linspace(0.02, 0.98, 49)))
    elif mode == "probability":
        grid = np.round(np.arange(0.05, 0.9501, 0.02), 2)
    else:
        raise ValueError(mode)
    best_t, best_f1 = 0.5, -1.0
    for t in grid:
        f1 = prf_counts(scores, labels, float(t))["f1"]
        if f1 > best_f1 + 1e-15 or (abs(f1 - best_f1) <= 1e-15 and float(t) >= best_t):
            best_f1 = f1
            best_t = float(t)
    return best_t, best_f1


def fit_logistic(x: np.ndarray, y: np.ndarray, rng: np.random.Generator, epochs: int = 400) -> np.ndarray:
    """Train-only logistic on four taps.

    Inverse-frequency weights keep the 1-in-10 pile-up mix from collapsing
    the fit. Step size 0.05. This replaces an unweighted step of 0.4 that
    left scores stuck near the base rate and slightly anti-ranked.
    """
    xb = np.column_stack([x, np.ones(len(x))])
    w = rng.normal(0.0, 0.05, size=xb.shape[1])
    y = np.asarray(y, dtype=np.float64)
    pos = max(float(y.mean()), 1e-6)
    sw = np.where(y > 0.5, 0.5 / pos, 0.5 / (1.0 - pos))
    eta = 0.05
    for _ in range(epochs):
        z = np.clip(xb @ w, -20, 20)
        p = 1.0 / (1.0 + np.exp(-z))
        grad = (xb.T @ (sw * (p - y))) / max(len(y), 1)
        w -= eta * grad
    return w


def score_logistic(samples: np.ndarray, w: np.ndarray) -> float:
    xb = np.append(np.asarray(samples, dtype=np.float64), 1.0)
    z = float(np.clip(xb @ w, -20, 20))
    return float(1.0 / (1.0 + np.exp(-z)))


def estimate_empirical(
    samples: np.ndarray,
    template: np.ndarray,
    *,
    pedestal_ch: float,
    offsets: tuple[int, ...] = (0, 4, 8, 12),
    delta_step: float = 0.1,
) -> float:
    """Four-or-more-tap LS against a train-only unit pulse. Returns full-scale amplitude."""
    y = np.asarray(samples, dtype=np.float64) - pedestal_ch / float(ADC_CHANNELS)
    axis = np.arange(template.size, dtype=np.float64)
    best_a, best_j = 0.0, 1e9
    offs = np.asarray(offsets, dtype=np.float64)
    for d in np.arange(-10.0, 2.0 + 0.5 * delta_step, delta_step):
        idx = REAL_SNIPPET_PRE + float(d) + offs
        phi = np.interp(idx, axis, template, left=0.0, right=0.0)
        den = float(np.dot(phi, phi))
        if den < 1e-12:
            continue
        a = float(np.dot(phi, y) / den)
        resid = y - a * phi
        j = float(np.dot(resid, resid))
        if j < best_j:
            best_j, best_a = j, a
    return best_a


def height_errors(
    snippets: list[Snippet],
    rng: np.random.Generator,
    *,
    estimator: LsPeakEstimator | None = None,
    template: np.ndarray | None = None,
    pedestal_ch: float = PEDESTAL_CH,
    offsets: tuple[int, ...] = (0, 4, 8, 12),
    empirical_step: float = 0.1,
) -> dict:
    """One official-style random placement per snippet. Signed error is pred − label."""
    err: list[float] = []
    n_clip = 0
    for sn in snippets:
        t1 = START_OFFSET + int(rng.integers(0, START_SPAN))
        wave, n_high, _n_low = compose_conditional(sn, t1=t1)
        n_clip += n_high
        if offsets == (0, 4, 8, 12) and estimator is not None and template is None:
            frame = extract_frame(wave)
            if frame is None:
                continue
            pred = estimator.estimate(frame.samples).amplitude * ADC_CHANNELS
        else:
            trig = None
            level = 100 / ADC_CHANNELS
            for i, v in enumerate(wave):
                if v >= level:
                    trig = i
                    break
            if trig is None:
                continue
            if estimator is not None and template is None:
                from sparse_pileup.ls_peak import latch_offsets

                latched = latch_offsets(wave, trig, offsets)
                if latched is None:
                    continue
                pred = estimate_offsets(
                    latched,
                    offsets,
                    pedestal=estimator.pedestal,
                    tau=estimator.tau,
                    n=estimator.n_shape,
                ).amplitude * ADC_CHANNELS
            else:
                if template is None:
                    raise ValueError("template required")
                latched_idx = [trig + off for off in offsets]
                if max(latched_idx) >= len(wave):
                    continue
                samples = np.array([quantize_4096(float(wave[i])) for i in latched_idx])
                pred = estimate_empirical(
                    samples,
                    template,
                    pedestal_ch=pedestal_ch,
                    offsets=offsets,
                    delta_step=empirical_step,
                ) * ADC_CHANNELS
        err.append(pred - sn.amplitude_ch)
    arr = np.array(err, dtype=np.float64)
    if arr.size == 0:
        return {"n": 0}
    abs_err = np.abs(arr)
    return {
        "n": int(arr.size),
        "mae_ch": float(abs_err.mean()),
        "rmse_ch": float(np.sqrt(np.mean(arr ** 2))),
        "bias_ch": float(arr.mean()),
        "max_abs_ch": float(abs_err.max()),
        "mae_se_ch": float(abs_err.std(ddof=1) / np.sqrt(arr.size)) if arr.size > 1 else 0.0,
        "n_saturated_high_samples": int(n_clip),
    }


def campaign_rates(campaign: Campaign) -> dict:
    live = campaign.live_time_s
    n_pulses = sum(r.n_pulses for r in campaign.records)
    n_fe = sum(r.n_fe55 for r in campaign.records)
    n_iso = sum(r.n_isolated for r in campaign.records)
    n_high = sum(r.n_high for r in campaign.records)
    n_edge = sum(r.n_edge_dropped for r in campaign.records)
    return {
        "live_time_s": live,
        "n_segments": len(campaign.records),
        "n_pulses": n_pulses,
        "n_fe55": n_fe,
        "n_high_artifact": n_high,
        "n_isolated_fe55": n_iso,
        "n_edge_uncertified_dropped": n_edge,
        "n_cross_boundary_pairs_closer_than_8us": campaign.n_cross_boundary_close,
        "rate_all_pulses_hz": n_pulses / live,
        "rate_fe55_hz": n_fe / live,
        "rate_isolated_fe55_hz": n_iso / live,
        "rate_high_artifact_hz": n_high / live,
    }


def amp_summary(snippets: list[Snippet]) -> dict:
    if not snippets:
        return {"n": 0}
    a = np.array([s.amplitude_ch for s in snippets], dtype=np.float64)
    return {
        "n": int(a.size),
        "mean_ch": float(a.mean()),
        "std_ch": float(a.std(ddof=1)) if a.size > 1 else 0.0,
        "min_ch": float(a.min()),
        "max_ch": float(a.max()),
        "p10_ch": float(np.percentile(a, 10)),
        "p50_ch": float(np.percentile(a, 50)),
        "p90_ch": float(np.percentile(a, 90)),
    }


# Re-exported constants used by the runner and tests.
PROTOCOL_PUBLIC = {
    "name": "segment-first-v6",
    "segment_fractions": [0.60, 0.20, 0.20],
    "blocked_order": "segment index ascending, seg001 through seg061",
    "isolation_us": REAL_ISO_DT_SAMPLES * 0.1,
    "edge_rule": "drop a pulse within 8 us of either buffer edge",
    "coincidence_window_us": COINCIDENCE_SAMPLES * 0.1,
    "tap_aperture_us": TAP_APERTURE_SAMPLES * 0.1,
    "footprint_pre_samples": FOOTPRINT_PRE,
    "footprint_post_samples": FOOTPRINT_POST,
    "pileup_period": PILEUP_PERIOD,
    "epochs": EPOCHS,
    "eta": 0.5,
    "n_train": N_TRAIN,
    "n_val": N_VAL,
    "n_test_prevalence": N_TEST_PREV,
    "n_stream_pulses": N_STREAM_PULSES,
    "n_per_class_conditional_cell": N_CELL,
    "threshold_rule": "maximize F1 on the validation prevalence mix; ties take the higher threshold",
    "threshold_grid": "0.05 to 0.95 step 0.02",
    "primary_run": PRIMARY_RUN,
    "forward_probability_targets": list(FORWARD_P_TARGETS),
    "gaps_samples": list(GAPS),
    "ratios": list(RATIOS),
    "extra_noise_ch_stress": list(EXTRA_NOISE_CH),
    "poisson": "modelling assumption, stream inter-arrivals only",
        "logistic": "inverse-frequency weights, 400 steps, eta 0.05, fit on train prevalence mix",
        "residual_threshold": "quantile grid on validation residual scores",
        "double_baseline_noise": False,
}
