"""Synthetic shaped pulses. Testbench only — do not synthesise.

Ports timer1_Tick + Array2ShapeDbl + Get8ChnlGaussianPulses from
PileupNNBPTrainer.cs. The second piled pulse is drawn from the same MCA
Gaussian lines as the first (C# used Uniform(0.1, 1) for pulse 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from sparse_pileup.constants import (
    ADC_CHANNELS,
    GAP_HIGH,
    GAP_LOW,
    PILEUP_PERIOD,
    PULSE_WIDTH,
    RC_ALPHA,
    RC_GAIN,
    RC_INNER_STEPS,
    RC_PASSES,
    START_OFFSET,
    START_SPAN,
    WAVEFORM_LEN,
)


@dataclass
class McaLine:
    name: str
    height: int
    count: int
    span: int
    profile: np.ndarray = field(repr=False)


def _gaussian_yy(channels: int = ADC_CHANNELS) -> np.ndarray:
    # LoadParameters / FillChannelConfig:
    #   yy[i] = exp(-(i - N/2)^2 / (N^2 * 0.05))
    i = np.arange(channels, dtype=np.float64)
    mid = channels / 2.0
    return np.exp(-((i - mid) ** 2) / (channels * channels * 0.05))


def build_profile(span: int, channels: int = ADC_CHANNELS) -> np.ndarray:
    """Discrete Gaussian lookup used as a random-draw table (C# ArrayList)."""
    yy = _gaussian_yy(channels)
    yk = channels / (span + 1)
    al: list[int] = []
    for j in range(span):
        idx = int((j + 1) * yk)
        if idx >= channels:
            idx = channels - 1
        sz = int(1000.0 * yy[idx])  # C# (short)(1000 * yy[...])
        if sz < 0:
            sz = 0
        al.extend([j] * sz)
    if not al:
        return np.array([0], dtype=np.int16)
    return np.array(al, dtype=np.int16) - np.int16(span // 2)


def load_mca_lines(csv_path: Path) -> list[McaLine]:
    """config/mca_lines.csv — same layout as configMca.csv."""
    text = Path(csv_path).read_text(encoding="utf-8").strip().splitlines()
    # skip header; row 1 is MaxVals
    lines: list[McaLine] = []
    for raw in text[2:]:
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 4 or not parts[0]:
            continue
        name, height, count, span = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
        lines.append(
            McaLine(
                name=name,
                height=height,
                count=count,
                span=span,
                profile=build_profile(span),
            )
        )
    if not lines:
        raise ValueError(f"no MCA lines in {csv_path}")
    return lines


def draw_amplitude(lines: list[McaLine], rng: np.random.Generator) -> float:
    """Get8ChnlGaussianPulses: uniform line, then profile offset, /4096."""
    chn = int(rng.integers(0, len(lines)))
    line = lines[chn]
    sel = int(rng.integers(0, len(line.profile)))
    hgt = int(line.height) + int(line.profile[sel])
    hgt = max(0, min(ADC_CHANNELS - 1, hgt))
    return hgt / float(ADC_CHANNELS)


def array2shape_dbl(pts: np.ndarray) -> np.ndarray:
    """Array2ShapeDbl — leaky integrator, 10 inner steps, then *1.1 on the output."""
    vc = 0.0
    out = np.empty_like(pts, dtype=np.float64)
    for i in range(pts.shape[0]):
        x = float(pts[i])
        for _ in range(RC_INNER_STEPS):
            vc += (x - vc) * RC_ALPHA
        out[i] = vc * RC_GAIN
    return out


def shape_pulse(rect: np.ndarray) -> np.ndarray:
    y = rect
    for _ in range(RC_PASSES):
        y = array2shape_dbl(y)
    return y


@dataclass
class SimulatedPulse:
    waveform: np.ndarray
    amplitude_first: float
    amplitude_second: float | None
    is_pileup: bool
    t_start: int
    gap: int


def simulate_pulse(
    lines: list[McaLine],
    rng: np.random.Generator,
    *,
    force_pileup: bool | None = None,
) -> SimulatedPulse:
    """One 500-sample record: rectangle(s) then three RC passes."""
    rect = np.zeros(WAVEFORM_LEN, dtype=np.float64)
    t_start = START_OFFSET + int(rng.integers(0, START_SPAN))
    a1 = draw_amplitude(lines, rng)
    tw = PULSE_WIDTH
    rect[t_start : t_start + tw] = a1

    is_pileup = bool(rng.integers(0, PILEUP_PERIOD) == 0)
    if force_pileup is not None:
        is_pileup = force_pileup

    a2: float | None = None
    gap = 0
    if is_pileup:
        gap = int(rng.integers(GAP_LOW, GAP_HIGH))
        a2 = draw_amplitude(lines, rng)
        t2 = t_start + tw + gap
        t2e = min(WAVEFORM_LEN, t2 + tw)
        if t2 < WAVEFORM_LEN:
            rect[t2:t2e] = a2

    waveform = shape_pulse(rect)
    return SimulatedPulse(
        waveform=waveform,
        amplitude_first=a1,
        amplitude_second=a2,
        is_pileup=is_pileup,
        t_start=t_start,
        gap=gap,
    )
