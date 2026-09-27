"""Train / val / test splits with independent RNG seeds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from sparse_pileup.constants import (
    ADC_CHANNELS,
    DEFAULT_ENGINE,
    DEFAULT_SEED,
    N_TEST,
    N_TRAIN,
    N_VAL,
)
from sparse_pileup.pulse_sim import SimulatedPulse, load_mca_lines, simulate_pulse
from sparse_pileup.sampler import SampleFrame, extract_frame


@dataclass
class Event:
    waveform: np.ndarray
    samples: np.ndarray
    frame: SampleFrame
    is_pileup: bool
    amplitude_first: float
    amplitude_second: float | None
    t_start: int = 0
    gap: int = 0


@dataclass
class Split:
    train: list[Event]
    val: list[Event]
    test: list[Event]


def _to_event(pulse: SimulatedPulse) -> Event | None:
    frame = extract_frame(pulse.waveform)
    if frame is None:
        return None
    return Event(
        waveform=pulse.waveform,
        samples=frame.samples,
        frame=frame,
        is_pileup=pulse.is_pileup,
        amplitude_first=pulse.amplitude_first,
        amplitude_second=pulse.amplitude_second,
        t_start=pulse.t_start,
        gap=pulse.gap,
    )


def generate_events(
    n: int,
    csv_path: Path,
    seed: int,
    *,
    engine: str | None = None,
    split_name: str = "train",
) -> list[Event]:
    engine = engine or DEFAULT_ENGINE
    rng = np.random.default_rng(seed)
    out: list[Event] = []
    attempts = 0
    limit = n * 20
    if engine == "real":
        from sparse_pileup.real_superpose import library_for_split, simulate_real_event

        lib = library_for_split(split_name, DEFAULT_SEED)
        sim = lambda: simulate_real_event(lib, rng)
    elif engine == "kernel":
        lines = load_mca_lines(csv_path)
        sim = lambda: simulate_pulse(lines, rng)
    else:
        raise ValueError(f"unknown engine {engine!r} (use 'real' or 'kernel')")
    while len(out) < n and attempts < limit:
        attempts += 1
        ev = _to_event(sim())
        if ev is not None:
            out.append(ev)
    if len(out) < n:
        raise RuntimeError(f"only generated {len(out)}/{n} triggered events ({engine})")
    return out


def make_split(
    csv_path: Path,
    n_train: int = N_TRAIN,
    n_val: int = N_VAL,
    n_test: int = N_TEST,
    seed: int = DEFAULT_SEED,
    *,
    engine: str | None = None,
) -> Split:
    """Independent streams: train seed, val seed+1, test seed+2.

    engine='real' (default): isolated = measured Fe-55 snippets;
    pile-up = linear sum of two snippets. Unique pulses are partitioned
    so a test snippet is never used in training.
    engine='kernel': CR–RC⁸ formula (V3 baseline).
    """
    engine = engine or DEFAULT_ENGINE
    return Split(
        train=generate_events(n_train, csv_path, seed, engine=engine, split_name="train"),
        val=generate_events(n_val, csv_path, seed + 1, engine=engine, split_name="val"),
        test=generate_events(n_test, csv_path, seed + 2, engine=engine, split_name="test"),
    )


def events_to_csv_rows(rows: list[Event], split_name: str) -> list[dict]:
    """One row per triggered event: labels + four FPGA samples (no full waveform)."""
    out = []
    for ev in rows:
        a2 = "" if ev.amplitude_second is None else f"{ev.amplitude_second * ADC_CHANNELS:.4f}"
        out.append(
            {
                "split": split_name,
                "is_pileup": int(ev.is_pileup),
                "A1_ch": round(ev.amplitude_first * ADC_CHANNELS, 4),
                "A2_ch": a2,
                "t_start": ev.t_start,
                "gap": ev.gap,
                "trig": int(ev.frame.indices[0]),
                "s0": f"{ev.samples[0]:.8f}",
                "s1": f"{ev.samples[1]:.8f}",
                "s2": f"{ev.samples[2]:.8f}",
                "s3": f"{ev.samples[3]:.8f}",
            }
        )
    return out


def write_events_csv(path: Path, rows: list[Event], split_name: str) -> None:
    import csv

    records = events_to_csv_rows(rows, split_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "split",
                "is_pileup",
                "A1_ch",
                "A2_ch",
                "t_start",
                "gap",
                "trig",
                "s0",
                "s1",
                "s2",
                "s3",
            ],
        )
        w.writeheader()
        w.writerows(records)
