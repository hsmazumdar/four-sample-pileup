"""Isolated Fe-55 snippets for constructed pile-up.

    python -m sparse_pileup.real_pulse_lib

Loads the 61 measured segments, keeps pulses that are isolated by
≥ 8 µs on both sides, stores a peak-aligned ADC window, and writes
``real_data/isolated_fe55_snippets.npz``.

This archive is not a pile-up dataset. It is a library of real singles
used later to (a) emit isolated events as-is and (b) add two singles
at a chosen delay.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import numpy as np

from sparse_pileup.constants import (
    ADC_CHANNELS,
    REAL_ISO_DT_SAMPLES,
    REAL_LIBRARY_TRAIN_FRAC,
    REAL_LIBRARY_VAL_FRAC,
    REAL_SNIPPET_PRE,
    REAL_SNIPPETS_NPZ,
    WAVEFORM_LEN,
)
from sparse_pileup.real_sdd import (
    FE55_AMP_HI,
    FE55_AMP_LO,
    SAMPLES_PER_SEGMENT,
    find_pulses,
    load_all_samples,
    repo_root,
)

BASELINE_N = 8


@dataclass(frozen=True)
class IsolatedSnippet:
    pulse_id: int
    segment_index: int
    adc: np.ndarray  # int16, length WAVEFORM_LEN, peak at REAL_SNIPPET_PRE
    baseline_ch: float
    amplitude_ch: float


@dataclass
class PulseLibrary:
    snippets: list[IsolatedSnippet]

    def __len__(self) -> int:
        return len(self.snippets)

    def split(self, seed: int) -> tuple["PulseLibrary", "PulseLibrary", "PulseLibrary"]:
        """Disjoint unique-pulse libraries so train snippets never sit in test."""
        n = len(self.snippets)
        rng = np.random.default_rng(seed)
        order = rng.permutation(n)
        n_train = int(round(REAL_LIBRARY_TRAIN_FRAC * n))
        n_val = int(round(REAL_LIBRARY_VAL_FRAC * n))
        tr = [self.snippets[i] for i in order[:n_train]]
        va = [self.snippets[i] for i in order[n_train : n_train + n_val]]
        te = [self.snippets[i] for i in order[n_train + n_val :]]
        if not tr or not va or not te:
            raise RuntimeError(f"library split too small: {n} snippets")
        return PulseLibrary(tr), PulseLibrary(va), PulseLibrary(te)


def snippets_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / REAL_SNIPPETS_NPZ


def _dt_next(pulses, i: int) -> int | None:
    if i + 1 >= len(pulses):
        return None
    return int(pulses[i + 1].global_peak - pulses[i].global_peak)


def extract_isolated(
    root: Path | None = None,
    *,
    progress=None,
) -> PulseLibrary:
    """Scan the measured stream and keep isolated Fe-55 windows."""
    root = root or repo_root()
    x, segments = load_all_samples(root, progress=progress)
    pulses = find_pulses(x, segments)
    pre = REAL_SNIPPET_PRE
    post = WAVEFORM_LEN - pre
    out: list[IsolatedSnippet] = []
    for i, p in enumerate(pulses):
        if p.kind != "fe55":
            continue
        if p.dt_prev is not None and p.dt_prev < REAL_ISO_DT_SAMPLES:
            continue
        nxt = _dt_next(pulses, i)
        if nxt is not None and nxt < REAL_ISO_DT_SAMPLES:
            continue
        if p.local_peak - pre < 0 or p.local_peak + post > SAMPLES_PER_SEGMENT:
            continue
        g0 = int(p.global_peak - pre)
        g1 = int(p.global_peak + post)
        if g0 < 0 or g1 > x.size:
            continue
        adc = x[g0:g1].astype(np.int16)
        if adc.size != WAVEFORM_LEN:
            continue
        baseline = float(np.mean(adc[:BASELINE_N]))
        peak = float(adc[pre])
        amp = peak - baseline
        if not (FE55_AMP_LO <= peak <= FE55_AMP_HI):
            continue
        if amp < 200:
            continue
        out.append(
            IsolatedSnippet(
                pulse_id=int(p.pulse_id),
                segment_index=int(p.segment_index),
                adc=adc,
                baseline_ch=baseline,
                amplitude_ch=amp,
            )
        )
    if len(out) < 50:
        raise RuntimeError(f"only {len(out)} isolated Fe-55 snippets — check real_data/")
    return PulseLibrary(out)


def save_library(lib: PulseLibrary, path: Path | None = None) -> Path:
    path = path or snippets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    adc = np.stack([s.adc for s in lib.snippets], axis=0)
    np.savez_compressed(
        path,
        adc=adc,
        pulse_id=np.array([s.pulse_id for s in lib.snippets], dtype=np.int32),
        segment_index=np.array([s.segment_index for s in lib.snippets], dtype=np.int32),
        baseline_ch=np.array([s.baseline_ch for s in lib.snippets], dtype=np.float64),
        amplitude_ch=np.array([s.amplitude_ch for s in lib.snippets], dtype=np.float64),
        peak_rel=np.int32(REAL_SNIPPET_PRE),
        waveform_len=np.int32(WAVEFORM_LEN),
        iso_dt_samples=np.int32(REAL_ISO_DT_SAMPLES),
        adc_channels=np.int32(ADC_CHANNELS),
    )
    meta = {
        "n_isolated": len(lib.snippets),
        "peak_rel": REAL_SNIPPET_PRE,
        "waveform_len": WAVEFORM_LEN,
        "iso_dt_us": REAL_ISO_DT_SAMPLES * 0.1,
        "note": (
            "Isolated measured Fe-55 singles. Not a pile-up set. "
            "Constructed pile-up adds two of these at a controlled delay."
        ),
    }
    side = path.with_suffix(".json")
    side.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def load_library(root: Path | None = None, path: Path | None = None) -> PulseLibrary:
    path = path or snippets_path(root)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} missing. Run: python -m sparse_pileup.real_pulse_lib"
        )
    z = np.load(path)
    adc = z["adc"]
    snippets = [
        IsolatedSnippet(
            pulse_id=int(z["pulse_id"][i]),
            segment_index=int(z["segment_index"][i]),
            adc=adc[i],
            baseline_ch=float(z["baseline_ch"][i]),
            amplitude_ch=float(z["amplitude_ch"][i]),
        )
        for i in range(adc.shape[0])
    ]
    return PulseLibrary(snippets)


def load_or_build(root: Path | None = None, *, rebuild: bool = False) -> PulseLibrary:
    path = snippets_path(root)
    if path.is_file() and not rebuild:
        return load_library(root, path)
    lib = extract_isolated(root)
    save_library(lib, path)
    return lib


def main(argv: list[str] | None = None) -> None:
    import argparse

    p = argparse.ArgumentParser(description="Build isolated Fe-55 snippet library.")
    p.add_argument("--rebuild", action="store_true")
    args = p.parse_args(argv)
    root = repo_root()

    def progress(i, n, name):
        if i == 1 or i == n or i % 10 == 0:
            print(f"  segment {i}/{n}  {name}")

    print("Extracting isolated Fe-55 pulses from real_data/sdd_fe55 …")
    if args.rebuild or not snippets_path(root).is_file():
        lib = extract_isolated(root, progress=progress)
        path = save_library(lib, snippets_path(root))
        print(f"Wrote {path}")
    else:
        lib = load_library(root)
        print(f"Loaded cache {snippets_path(root)}")
    amps = np.array([s.amplitude_ch for s in lib.snippets], dtype=np.float64)
    print(f"Isolated Fe-55 snippets: {len(lib)}")
    print(
        f"  amplitude (peak-baseline): mean {amps.mean():.1f}  "
        f"min {amps.min():.1f}  max {amps.max():.1f} ch"
    )


if __name__ == "__main__":
    main()
