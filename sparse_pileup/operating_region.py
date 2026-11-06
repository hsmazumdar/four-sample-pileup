"""Historical V5 operating-region experiments on constructed Fe-55 pile-up.

    python -m sparse_pileup.operating_region

Pulse-level 60/20/20 snippet split (not a segment split). The CR–RC^8
template is the campaign-wide fit in ``config/sdd_shape.json``. The MLP
threshold stays 0.5. The ``v5_poisson.csv`` column is a conditional
two-pulse draw with an exponential gap, not an unconditional stream.

The stricter protocol is ``python -m sparse_pileup.strict_validation``.
Pile-up here remains constructed. Not a measured high-rate F1.
"""

from __future__ import annotations

from pathlib import Path
import csv
import json

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

from sparse_pileup.constants import (
    ADC_CHANNELS,
    DEFAULT_EPOCHS,
    DEFAULT_SEED,
    N_HIDDEN,
    PEDESTAL_CH,
    REAL_SNIPPET_PRE,
    SAMPLE_STRIDE,
    START_OFFSET,
    WAVEFORM_LEN,
)
from sparse_pileup.dataset import _to_event
from sparse_pileup.dual_head import DualHeadDetector
from sparse_pileup.flex_mlp import FlexMLP
from sparse_pileup.ls_peak import LsPeakEstimator, unit_kernel_at
from sparse_pileup.metrics import roc_auc, wilson_interval
from sparse_pileup.real_pulse_lib import IsolatedSnippet, PulseLibrary
from sparse_pileup.real_superpose import compose_waveform, library_for_split, simulate_real_event
from sparse_pileup.sampler import extract_frame, extract_n_taps, find_trigger, quantize_4096

GAPS = (3, 4, 5, 6, 8, 10, 12, 16, 20)  # samples = 0.3 … 2.0 µs
RATIOS = (0.25, 0.5, 1.0, 2.0, 4.0)
N_GRID = (
    (4, 4, "N=4 stride 4"),
    (8, 2, "N=8 stride 2"),
    (16, 1, "N=16 stride 1"),
    (32, 1, "N=32 stride 1"),
    (48, 1, "N=48 full window"),
)
SNR_EXTRA_CH = (0.0, 10.0, 20.0, 40.0)
N_PER_CELL = 120
N_NSWEEP_TRAIN = 2000
N_NSWEEP_TEST = 400
NSWEEP_EPOCHS = 20


def _f1(tp, fp, fn) -> float:
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0


def _scores_frozen(model: DualHeadDetector, waves: list[np.ndarray]) -> np.ndarray:
    out = []
    for w in waves:
        fr = extract_frame(w)
        if fr is None:
            out.append(0.0)
            continue
        out.append(model.infer(fr.samples).pileup_prob)
    return np.array(out, dtype=np.float64)


def make_balanced(
    lib: PulseLibrary,
    rng: np.random.Generator,
    n_each: int,
    *,
    gap: int | None = None,
    guest_scale: float = 1.0,
    target_ratio: float | None = None,
    extra_noise_ch: float = 0.0,
) -> tuple[list[np.ndarray], np.ndarray]:
    waves: list[np.ndarray] = []
    labels: list[int] = []
    for piled in (False, True):
        for _ in range(n_each):
            ev = simulate_real_event(
                lib,
                rng,
                force_pileup=piled,
                gap=gap if piled else None,
                guest_scale=guest_scale if piled else 1.0,
                target_ratio=target_ratio if piled else None,
                extra_noise_ch=extra_noise_ch,
            )
            if extract_frame(ev.waveform) is None:
                continue
            waves.append(ev.waveform)
            labels.append(1 if piled else 0)
    return waves, np.array(labels, dtype=np.int32)


def eval_threshold(scores: np.ndarray, labels: np.ndarray, thr: float = 0.5) -> dict:
    pred = scores >= thr
    y = labels.astype(bool)
    tp = int(np.sum(pred & y))
    fp = int(np.sum(pred & ~y))
    tn = int(np.sum(~pred & ~y))
    fn = int(np.sum(~pred & y))
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "n": int(labels.size),
        "n_pileup": int(y.sum()),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": prec,
        "recall": rec,
        "f1": _f1(tp, fp, fn),
        "accuracy": (tp + tn) / labels.size if labels.size else 0.0,
    }


# --- baselines on four taps / full wave ------------------------------------


def score_or_fuse(mlp_prob: float, retrigger: float, mlp_thr: float = 0.5) -> float:
    """Complementary veto: close overlaps from the MLP, resolved seconds from retrigger."""
    return 1.0 if (float(mlp_prob) >= mlp_thr or float(retrigger) >= 0.5) else 0.0


def score_retrigger(wave: np.ndarray) -> float:
    """Second leading-edge after the first peak. 1 if found."""
    trig = find_trigger(wave)
    if trig is None:
        return 0.0
    peak = trig + int(np.argmax(wave[trig : min(trig + 16, len(wave))]))
    start = peak + 4
    level = 100 / ADC_CHANNELS
    for i in range(start, min(len(wave) - 1, peak + 40)):
        if wave[i] < level <= wave[i + 1] or (
            wave[i + 1] - wave[i] > 80 / ADC_CHANNELS and wave[i + 1] > level
        ):
            return 1.0
    return 0.0


def score_slope(samples: np.ndarray) -> float:
    """Rise–fall–rise on the four taps."""
    d = np.diff(np.asarray(samples, dtype=np.float64))
    if d.size < 2:
        return 0.0
    saw_down = False
    for v in d:
        if v < -0.02:
            saw_down = True
        elif saw_down and v > 0.03:
            return 1.0
    return 0.0


def score_residual(samples: np.ndarray, est: LsPeakEstimator) -> float:
    return float(est.estimate(samples).residual)


def fit_logistic(x: np.ndarray, y: np.ndarray, rng: np.random.Generator, epochs: int = 80) -> np.ndarray:
    """x (n,4) in 0..1, y in {0,1}. Returns weights including bias."""
    xb = np.column_stack([x, np.ones(len(x))])
    w = rng.normal(0.0, 0.2, size=xb.shape[1])
    eta = 0.4
    for _ in range(epochs):
        z = np.clip(xb @ w, -20, 20)
        p = 1.0 / (1.0 + np.exp(-z))
        w -= eta * (xb.T @ (p - y)) / len(y)
    return w


def score_logistic(samples: np.ndarray, w: np.ndarray) -> float:
    xb = np.append(np.asarray(samples, dtype=np.float64), 1.0)
    z = float(np.clip(xb @ w, -20, 20))
    return float(1.0 / (1.0 + np.exp(-z)))


def tune_threshold(scores: np.ndarray, labels: np.ndarray) -> float:
    best_t, best_f1 = 0.5, -1.0
    for t in np.unique(np.quantile(scores, np.linspace(0.05, 0.95, 19))):
        m = eval_threshold(scores, labels, float(t))
        if m["f1"] > best_f1:
            best_f1, best_t = m["f1"], float(t)
    return best_t


# --- empirical template ----------------------------------------------------


def empirical_unit_pulse(lib: PulseLibrary) -> np.ndarray:
    acc = np.zeros(WAVEFORM_LEN, dtype=np.float64)
    n = 0
    for s in lib.snippets:
        y = s.adc.astype(np.float64) - s.baseline_ch
        peak = float(y[REAL_SNIPPET_PRE])
        if peak <= 50:
            continue
        acc += y / peak
        n += 1
    if n == 0:
        raise RuntimeError("no snippets for empirical template")
    p = acc / n
    p = np.clip(p, 0.0, None)
    if p.max() > 0:
        p = p / p.max()
    return p


def empirical_ls_mae(template: np.ndarray, lib: PulseLibrary, rng: np.random.Generator, n: int = 400) -> float:
    err = []
    for _ in range(n):
        ev = simulate_real_event(lib, rng, force_pileup=False)
        fr = extract_frame(ev.waveform)
        if fr is None:
            continue
        trig = int(fr.indices[0])
        best_a, best_j = 0.0, 1e9
        for d in np.arange(-10.0, 2.1, 0.2):
            # taps relative to peak: (trig - t_peak) + k*stride; t_peak unknown
            # template is peak-aligned at REAL_SNIPPET_PRE on its own axis.
            # We search phase: template index of tap0 = REAL_SNIPPET_PRE + d
            idxs = REAL_SNIPPET_PRE + d + np.array([0, 4, 8, 12], dtype=np.float64)
            phi = np.array(
                [
                    float(np.interp(i, np.arange(WAVEFORM_LEN), template, left=0.0, right=0.0))
                    for i in idxs
                ],
                dtype=np.float64,
            )
            y = fr.samples - PEDESTAL_CH / ADC_CHANNELS
            den = float(np.dot(phi, phi))
            if den < 1e-12:
                continue
            a = float(np.dot(phi, y) / den)
            j = float(np.dot(y - a * phi, y - a * phi))
            if j < best_j:
                best_j, best_a = j, a
        err.append(abs(best_a * ADC_CHANNELS - ev.amplitude_first * ADC_CHANNELS))
        _ = trig
    return float(np.mean(err)) if err else float("nan")


# --- N-sweep ---------------------------------------------------------------


def _tap_spec(n: int, stride: int):
    return n, stride


def train_flex(
    lib: PulseLibrary,
    n: int,
    stride: int,
    rng: np.random.Generator,
    n_train: int = N_NSWEEP_TRAIN,
    epochs: int = NSWEEP_EPOCHS,
) -> FlexMLP:
    net = FlexMLP.random(n, rng)
    xs, ys = [], []
    for _ in range(n_train * 3):
        if len(xs) >= n_train:
            break
        ev = simulate_real_event(lib, rng)
        fr = extract_n_taps(ev.waveform, n, stride)
        if fr is None:
            continue
        xs.append(fr.samples)
        ys.append(1.0 if ev.is_pileup else 0.0)
    order = np.arange(len(xs))
    for _ in range(epochs):
        rng.shuffle(order)
        for i in order:
            net.train_step(xs[i], ys[i])
    return net


def eval_flex(net: FlexMLP, lib: PulseLibrary, n: int, stride: int, rng: np.random.Generator) -> dict:
    waves, labels = make_balanced(lib, rng, N_NSWEEP_TEST // 2)
    scores = []
    keep = []
    for w, y in zip(waves, labels):
        fr = extract_n_taps(w, n, stride)
        if fr is None:
            continue
        scores.append(net.forward(fr.samples))
        keep.append(y)
    scores = np.array(scores)
    labels = np.array(keep)
    m = eval_threshold(scores, labels, 0.5)
    m["auc"] = roc_auc(scores, labels)
    m["n_in"] = n
    m["stride"] = stride
    m["n_weights"] = (n + 1) * N_HIDDEN + (N_HIDDEN + 1)
    return m


# --- main ------------------------------------------------------------------


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def make_figures(art: Path, dt_rows, heat_rows, n_rows, base_rows, snr_rows) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Pd vs Δt
    fig, ax = plt.subplots(figsize=(6.2, 3.4), dpi=160)
    xs = [r["gap_us"] for r in dt_rows]
    ax.plot(xs, [r["mlp_recall"] for r in dt_rows], "o-", color="#1F4E79", label="4-5-1 MLP")
    ax.plot(xs, [r["retrigger_recall"] for r in dt_rows], "s--", color="#7F8C8D", label="Retrigger")
    ax.plot(xs, [r["residual_recall"] for r in dt_rows], "d--", color="#C0392B", label="Template residual")
    ax.plot(xs, [r["logistic_recall"] for r in dt_rows], "^--", color="#27AE60", label="Logistic 4-tap")
    if dt_rows and "fusion_recall" in dt_rows[0]:
        ax.plot(
            xs,
            [r["fusion_recall"] for r in dt_rows],
            "k-.",
            label="MLP OR retrigger",
        )
    ax.set_xlabel("Peak-to-peak Δt (µs)")
    ax.set_ylabel("Recall (constructed pile-up)")
    ax.set_title("Detection vs separation — measured Fe-55 shapes")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(art / "v5_pd_vs_dt.png", bbox_inches="tight")
    plt.close(fig)

    # heatmap F1
    gaps = sorted({r["gap_us"] for r in heat_rows})
    ratios = sorted({r["ratio"] for r in heat_rows})
    z = np.full((len(ratios), len(gaps)), np.nan)
    gi = {g: i for i, g in enumerate(gaps)}
    ri = {a: i for i, a in enumerate(ratios)}
    for r in heat_rows:
        z[ri[r["ratio"]], gi[r["gap_us"]]] = r["f1"]
    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=160)
    im = ax.imshow(z, origin="lower", aspect="auto", vmin=0, vmax=1, cmap="viridis")
    ax.set_xticks(range(len(gaps)), [f"{g:.1f}" for g in gaps])
    ax.set_yticks(range(len(ratios)), [f"{a:g}" for a in ratios])
    ax.set_xlabel("Δt (µs)")
    ax.set_ylabel("A2/A1 (guest scaled)")
    ax.set_title("4-5-1 F1 operating region (constructed)")
    fig.colorbar(im, ax=ax, fraction=0.046, label="F1")
    fig.tight_layout()
    fig.savefig(art / "v5_operating_region.png", bbox_inches="tight")
    plt.close(fig)

    # N sweep
    fig, ax = plt.subplots(figsize=(6.2, 3.4), dpi=160)
    ax.bar(range(len(n_rows)), [r["f1"] for r in n_rows], color="#1F4E79", width=0.6)
    ax.set_xticks(range(len(n_rows)), [r["label"] for r in n_rows], rotation=20, ha="right")
    ax.set_ylabel("Held-out F1")
    ax.set_title("Pile-up F1 vs number of post-trigger samples")
    ax.set_ylim(0, 1.05)
    for i, r in enumerate(n_rows):
        ax.text(i, r["f1"] + 0.03, f"{r['f1']:.2f}", ha="center", fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(art / "v5_f1_vs_n.png", bbox_inches="tight")
    plt.close(fig)

    # baselines
    fig, ax = plt.subplots(figsize=(6.2, 3.4), dpi=160)
    names = [r["method"] for r in base_rows]
    ax.bar(range(len(base_rows)), [r["f1"] for r in base_rows], color="#1F4E79", width=0.55)
    ax.set_xticks(range(len(base_rows)), names, rotation=15, ha="right")
    ax.set_ylabel("F1 on held-out mix")
    ax.set_title("Four-tap baselines vs 4-5-1 (same constructed test)")
    ax.set_ylim(0, 1.05)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(art / "v5_baselines.png", bbox_inches="tight")
    plt.close(fig)

    # SNR
    fig, ax = plt.subplots(figsize=(6.2, 3.2), dpi=160)
    ax.plot(
        [r["extra_sigma_ch"] for r in snr_rows],
        [r["f1"] for r in snr_rows],
        "o-",
        color="#C0392B",
    )
    ax.set_xlabel("Added noise σ (ADC channels)")
    ax.set_ylabel("4-5-1 F1")
    ax.set_title("SNR sweep — extra Gaussian on measured snippets")
    ax.set_ylim(0, 1.05)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(art / "v5_snr.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    art = ROOT / "artifacts"
    art.mkdir(exist_ok=True)
    rng = np.random.default_rng(DEFAULT_SEED + 7)
    train_lib = library_for_split("train", DEFAULT_SEED, ROOT)
    val_lib = library_for_split("val", DEFAULT_SEED, ROOT)
    test_lib = library_for_split("test", DEFAULT_SEED, ROOT)
    model = DualHeadDetector.load_json(ROOT / "weights" / "dual_head.json")
    est = LsPeakEstimator()

    print("V5 operating-region experiments (constructed Fe-55 pile-up)")
    print(f"  library train/val/test = {len(train_lib)}/{len(val_lib)}/{len(test_lib)}")

    # --- ROC + CI on the official test mix (regenerate with test seed) ---
    from sparse_pileup.dataset import generate_events

    test_rows = generate_events(
        1000, ROOT / "config" / "sdd_fe55_lines.csv", DEFAULT_SEED + 2,
        engine="real", split_name="test",
    )
    scores, labels = [], []
    for ev in test_rows:
        r = model.infer(ev.samples)
        scores.append(r.pileup_prob)
        labels.append(1 if ev.is_pileup else 0)
    scores = np.array(scores)
    labels = np.array(labels, dtype=np.int32)
    held = eval_threshold(scores, labels, 0.5)
    auc = roc_auc(scores, labels)
    rec_lo, rec_hi = wilson_interval(held["tp"], held["n_pileup"])
    f1_lo, f1_hi = wilson_interval(held["tp"], held["tp"] + held["fn"] + held["fp"])
    # F1 CI is approximate via treating harmonic; also report recall CI primarily
    held.update({
        "auc": auc,
        "recall_ci95": [rec_lo, rec_hi],
        "precision_ci95": list(wilson_interval(held["tp"], held["tp"] + held["fp"])),
    })
    print(f"  held-out  F1={held['f1']:.3f}  recall={held['recall']:.3f} "
          f"[{rec_lo:.3f},{rec_hi:.3f}]  AUC={auc:.3f}")

    # --- tune residual / logistic on val ---
    val_w, val_y = make_balanced(val_lib, rng, 250)
    val_taps = [extract_frame(w).samples for w in val_w]
    resid_s = np.array([score_residual(t, est) for t in val_taps])
    resid_thr = tune_threshold(resid_s, val_y)
    log_w = fit_logistic(np.stack(val_taps), val_y.astype(np.float64), rng)

    # --- Δt sweep ---
    dt_rows = []
    for gap in GAPS:
        waves, y = make_balanced(test_lib, rng, N_PER_CELL, gap=gap)
        taps = []
        keep_w, keep_y = [], []
        for w, lab in zip(waves, y):
            fr = extract_frame(w)
            if fr is None:
                continue
            taps.append(fr.samples)
            keep_w.append(w)
            keep_y.append(lab)
        y = np.array(keep_y)
        mlp_s = np.array([model.infer(t).pileup_prob for t in taps])
        ret_s = np.array([score_retrigger(w) for w in keep_w])
        sl_s = np.array([score_slope(t) for t in taps])
        rs_s = np.array([score_residual(t, est) for t in taps])
        lg_s = np.array([score_logistic(t, log_w) for t in taps])
        fuse_s = np.array([score_or_fuse(a, b) for a, b in zip(mlp_s, ret_s)])
        mlp = eval_threshold(mlp_s, y)
        ret = eval_threshold(ret_s, y, 0.5)
        sl = eval_threshold(sl_s, y, 0.5)
        rs = eval_threshold(rs_s, y, resid_thr)
        lg = eval_threshold(lg_s, y, 0.5)
        fuse = eval_threshold(fuse_s, y, 0.5)
        dt_rows.append({
            "gap_samples": gap,
            "gap_us": gap * 0.1,
            "n": mlp["n"],
            "mlp_recall": mlp["recall"],
            "mlp_f1": mlp["f1"],
            "mlp_precision": mlp["precision"],
            "retrigger_recall": ret["recall"],
            "slope_recall": sl["recall"],
            "residual_recall": rs["recall"],
            "logistic_recall": lg["recall"],
            "fusion_recall": fuse["recall"],
            "fusion_f1": fuse["f1"],
        })
        print(f"  dT={gap*0.1:.1f} us  MLP recall={mlp['recall']:.2f} F1={mlp['f1']:.2f}")

    # --- A2/A1 × Δt heatmap ---
    heat_rows = []
    heat_gaps = (4, 8, 12, 16, 20)
    for gap in heat_gaps:
        for ratio in RATIOS:
            waves, y = make_balanced(
                test_lib, rng, 80, gap=gap, target_ratio=float(ratio)
            )
            s = _scores_frozen(model, waves)
            m = eval_threshold(s, y)
            heat_rows.append({
                "gap_us": gap * 0.1,
                "ratio": ratio,
                "f1": m["f1"],
                "recall": m["recall"],
                "precision": m["precision"],
                "n": m["n"],
            })
    print(f"  heatmap cells {len(heat_rows)}")

    # --- N sweep ---
    n_rows = []
    for n, stride, label in N_GRID:
        print(f"  training {label} ...")
        net = train_flex(train_lib, n, stride, rng)
        m = eval_flex(net, test_lib, n, stride, rng)
        n_rows.append({
            "label": label,
            "n_in": m["n_in"],
            "stride": m["stride"],
            "n_weights": m["n_weights"],
            "f1": m["f1"],
            "recall": m["recall"],
            "precision": m["precision"],
            "auc": m["auc"],
        })
        print(f"    F1={m['f1']:.3f}  recall={m['recall']:.3f}  AUC={m['auc']:.3f}")

    # --- baselines on official-like balanced test ---
    tw, ty = make_balanced(test_lib, rng, 400)
    taps = []
    keep_w, keep_y = [], []
    for w, lab in zip(tw, ty):
        fr = extract_frame(w)
        if fr is None:
            continue
        taps.append(fr.samples)
        keep_w.append(w)
        keep_y.append(lab)
    ty = np.array(keep_y)
    mlp_bal = np.array([model.infer(t).pileup_prob for t in taps])
    ret_bal = np.array([score_retrigger(w) for w in keep_w])
    methods = [
        ("4-5-1 MLP", mlp_bal, 0.5),
        ("Logistic 4-tap", np.array([score_logistic(t, log_w) for t in taps]), 0.5),
        ("Template residual", np.array([score_residual(t, est) for t in taps]), resid_thr),
        ("Slope / 2nd rise", np.array([score_slope(t) for t in taps]), 0.5),
        ("Retrigger", ret_bal, 0.5),
        ("MLP OR retrigger", np.array([score_or_fuse(a, b) for a, b in zip(mlp_bal, ret_bal)]), 0.5),
    ]
    base_rows = []
    for name, sc, thr in methods:
        m = eval_threshold(sc, ty, thr)
        m["method"] = name
        m["auc"] = roc_auc(sc, ty)
        base_rows.append(m)
        print(f"  baseline {name:20s} F1={m['f1']:.3f}  rec={m['recall']:.3f}  AUC={m['auc']:.3f}")

    # --- SNR ---
    snr_rows = []
    for sig in SNR_EXTRA_CH:
        waves, y = make_balanced(test_lib, rng, 200, extra_noise_ch=sig)
        s = _scores_frozen(model, waves)
        m = eval_threshold(s, y)
        snr_rows.append({
            "extra_sigma_ch": sig,
            "f1": m["f1"],
            "recall": m["recall"],
            "precision": m["precision"],
        })
        print(f"  SNR extra sigma={sig:.0f} ch  F1={m['f1']:.3f}")

    # --- Poisson-like rate: P(pile-up) via exponential gap, pulse width 1.7 µs ---
    width_s = 1.7e-6
    poisson_rows = []
    for kcps in (1.0, 10.0, 50.0, 100.0):
        lam = kcps * 1000.0
        n_ok = n_pu = tp = 0
        for _ in range(400):
            dt = rng.exponential(1.0 / lam)
            piled = dt < width_s
            gap = max(3, min(20, int(round(dt / 1e-7)))) if piled else None
            ev = simulate_real_event(test_lib, rng, force_pileup=piled, gap=gap)
            fr = extract_frame(ev.waveform)
            if fr is None:
                continue
            pred = model.infer(fr.samples).is_pileup
            n_ok += 1
            if piled:
                n_pu += 1
                if pred:
                    tp += 1
        rec = tp / n_pu if n_pu else 0.0
        poisson_rows.append({
            "rate_kcps": kcps,
            "n": n_ok,
            "n_pileup": n_pu,
            "recall": rec,
        })
        print(f"  Poisson {kcps:.0f} kcps  P_overlap~{n_pu/max(n_ok,1):.2f}  recall={rec:.2f}")

    # --- empirical template height ---
    tmpl = empirical_unit_pulse(train_lib)
    emp_mae = empirical_ls_mae(tmpl, test_lib, rng, n=400)
    kernel_mae = []
    for _ in range(400):
        ev = simulate_real_event(test_lib, rng, force_pileup=False)
        fr = extract_frame(ev.waveform)
        if fr is None:
            continue
        pred = est.estimate(fr.samples).amplitude * ADC_CHANNELS
        kernel_mae.append(abs(pred - ev.amplitude_first * ADC_CHANNELS))
    kern_mae = float(np.mean(kernel_mae))
    print(f"  isolated MAE  CR-RC8={kern_mae:.1f} ch  empirical Phi={emp_mae:.1f} ch")

    write_csv(art / "v5_dt_sweep.csv", dt_rows)
    write_csv(art / "v5_heatmap.csv", heat_rows)
    write_csv(art / "v5_n_sweep.csv", n_rows)
    write_csv(art / "v5_baselines.csv", [
        {k: r[k] for k in ("method", "f1", "recall", "precision", "auc", "tp", "fp", "tn", "fn")}
        for r in base_rows
    ])
    write_csv(art / "v5_snr.csv", snr_rows)
    write_csv(art / "v5_poisson.csv", poisson_rows)
    summary = {
        "held_out": {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                     for k, v in held.items() if k != "recall_ci95"},
        "held_out_recall_ci95": held["recall_ci95"],
        "held_out_auc": float(auc),
        "empirical_mae_ch": emp_mae,
        "kernel_mae_ch": kern_mae,
        "note": "Constructed pile-up from measured Fe-55 singles. Not Am-241.",
    }
    # json-safe held
    summary["held_out"] = {
        "n": held["n"],
        "n_pileup": held["n_pileup"],
        "tp": held["tp"],
        "fp": held["fp"],
        "tn": held["tn"],
        "fn": held["fn"],
        "precision": held["precision"],
        "recall": held["recall"],
        "f1": held["f1"],
        "auc": float(auc),
        "recall_ci95": held["recall_ci95"],
        "precision_ci95": held["precision_ci95"],
    }
    (art / "v5_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    make_figures(art, dt_rows, heat_rows, n_rows, base_rows, snr_rows)
    print("Wrote artifacts/v5_*.csv png json")


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    def _num(v: str):
        try:
            if v == "" or v is None:
                return v
            if any(ch in v for ch in ".eE"):
                return float(v)
            return int(v)
        except ValueError:
            return v

    return [{k: _num(v) for k, v in r.items()} for r in rows]


def figures_from_csv(art: Path) -> None:
    make_figures(
        art,
        _read_csv(art / "v5_dt_sweep.csv"),
        _read_csv(art / "v5_heatmap.csv"),
        _read_csv(art / "v5_n_sweep.csv"),
        _read_csv(art / "v5_baselines.csv"),
        _read_csv(art / "v5_snr.csv"),
    )
    print("Rewrote artifacts/v5_*.png from existing CSV tables")


def run_fusion(art: Path) -> dict:
    """Complementary OR on the official mix + merge fusion into existing maps.

    Does not retrain. Does not overwrite MLP / retrigger columns already quoted.
    """
    from sparse_pileup.dataset import generate_events

    rng = np.random.default_rng(DEFAULT_SEED + 11)
    test_lib = library_for_split("test", DEFAULT_SEED, ROOT)
    model = DualHeadDetector.load_json(ROOT / "weights" / "dual_head.json")

    test_rows = generate_events(
        1000, ROOT / "config" / "sdd_fe55_lines.csv", DEFAULT_SEED + 2,
        engine="real", split_name="test",
    )
    mlp_s, ret_s, labels = [], [], []
    for ev in test_rows:
        mlp_s.append(model.infer(ev.samples).pileup_prob)
        ret_s.append(score_retrigger(ev.waveform))
        labels.append(1 if ev.is_pileup else 0)
    mlp_s = np.array(mlp_s)
    ret_s = np.array(ret_s)
    labels = np.array(labels, dtype=np.int32)
    fuse_s = np.array([score_or_fuse(a, b) for a, b in zip(mlp_s, ret_s)])
    held_mlp = eval_threshold(mlp_s, labels, 0.5)
    held_ret = eval_threshold(ret_s, labels, 0.5)
    held_fuse = eval_threshold(fuse_s, labels, 0.5)
    held_fuse["auc"] = roc_auc(fuse_s, labels)
    rec_lo, rec_hi = wilson_interval(held_fuse["tp"], held_fuse["n_pileup"])
    held_fuse["recall_ci95"] = [rec_lo, rec_hi]
    print(
        f"  fusion held-out  MLP F1={held_mlp['f1']:.3f}  retrigger F1={held_ret['f1']:.3f}  "
        f"OR F1={held_fuse['f1']:.3f}  rec={held_fuse['recall']:.3f}  fp={held_fuse['fp']}"
    )

    # Per-gap fusion on a fresh draw; merge only fusion_* into the quoted table.
    fuse_by_gap = {}
    for gap in GAPS:
        waves, y = make_balanced(test_lib, rng, N_PER_CELL, gap=gap)
        scores = []
        keep_y = []
        for w, lab in zip(waves, y):
            fr = extract_frame(w)
            if fr is None:
                continue
            scores.append(score_or_fuse(model.infer(fr.samples).pileup_prob, score_retrigger(w)))
            keep_y.append(lab)
        m = eval_threshold(np.array(scores), np.array(keep_y), 0.5)
        fuse_by_gap[gap] = m
        print(f"  fusion dT={gap * 0.1:.1f} us  recall={m['recall']:.2f} F1={m['f1']:.2f}")

    dt_rows = _read_csv(art / "v5_dt_sweep.csv")
    for r in dt_rows:
        gap = int(r["gap_samples"])
        if gap in fuse_by_gap:
            r["fusion_recall"] = fuse_by_gap[gap]["recall"]
            r["fusion_f1"] = fuse_by_gap[gap]["f1"]
    write_csv(art / "v5_dt_sweep.csv", dt_rows)

    tw, ty = make_balanced(test_lib, rng, 400)
    fuse_bal = []
    keep_y = []
    for w, lab in zip(tw, ty):
        fr = extract_frame(w)
        if fr is None:
            continue
        fuse_bal.append(score_or_fuse(model.infer(fr.samples).pileup_prob, score_retrigger(w)))
        keep_y.append(lab)
    bal = eval_threshold(np.array(fuse_bal), np.array(keep_y), 0.5)
    bal["method"] = "MLP OR retrigger"
    bal["auc"] = roc_auc(np.array(fuse_bal), np.array(keep_y))
    print(f"  fusion balanced  F1={bal['f1']:.3f}  rec={bal['recall']:.3f}  fp={bal['fp']}")

    base_rows = _read_csv(art / "v5_baselines.csv")
    base_rows = [r for r in base_rows if r.get("method") != "MLP OR retrigger"]
    base_rows.append({
        "method": "MLP OR retrigger",
        "f1": bal["f1"],
        "recall": bal["recall"],
        "precision": bal["precision"],
        "auc": bal["auc"],
        "tp": bal["tp"],
        "fp": bal["fp"],
        "tn": bal["tn"],
        "fn": bal["fn"],
    })
    write_csv(art / "v5_baselines.csv", base_rows)

    fusion = {
        "held_out_mlp": {k: held_mlp[k] for k in ("f1", "recall", "precision", "tp", "fp", "fn")},
        "held_out_retrigger": {k: held_ret[k] for k in ("f1", "recall", "precision", "tp", "fp", "fn")},
        "held_out_or": {
            "f1": held_fuse["f1"],
            "recall": held_fuse["recall"],
            "precision": held_fuse["precision"],
            "tp": held_fuse["tp"],
            "fp": held_fuse["fp"],
            "tn": held_fuse["tn"],
            "fn": held_fuse["fn"],
            "auc": held_fuse["auc"],
            "recall_ci95": held_fuse["recall_ci95"],
        },
        "balanced_or_f1": bal["f1"],
        "balanced_or_recall": bal["recall"],
        "note": "Constructed pile-up. OR of frozen 4-5-1 and retrigger. Not Am-241.",
    }
    (art / "v5_fusion.json").write_text(json.dumps(fusion, indent=2), encoding="utf-8")
    summary_path = art / "v5_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    summary["fusion"] = fusion
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    figures_from_csv(art)
    return fusion


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="V5 operating-region maps (constructed pile-up)")
    p.add_argument("--from-csv", action="store_true", help="Redraw PNG files from existing CSV tables")
    p.add_argument("--fusion", action="store_true", help="Add MLP OR retrigger without retraining")
    args = p.parse_args()
    if args.from_csv:
        figures_from_csv(ROOT / "artifacts")
    elif args.fusion:
        run_fusion(ROOT / "artifacts")
    else:
        main()
