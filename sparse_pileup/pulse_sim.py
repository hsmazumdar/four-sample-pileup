"""Synthetic shaped pulses. Testbench only — do not synthesise to FPGA.

Default engine: unit-height CR–RC^n kernel fitted to isolated Fe-55 SDD
pulses (config/sdd_shape.json), at fs = 10 MHz, plus measured baseline
noise. Pile-up is a second kernel at a controlled peak-to-peak gap.

The 2016 WinForms path (rectangle + three leaky integrators) is kept as
array2shape_dbl / shape_pulse_legacy. It is not used by simulate_pulse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

import numpy as np

from sparse_pileup.constants import (
    ADC_CHANNELS,
    CR_RC_N,
    CR_RC_TAU_SAMPLES,
    GAP_HIGH,
    GAP_LOW,
    NOISE_SIGMA_CH,
    PEDESTAL_CH,
    PILEUP_PERIOD,
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
        sz = int(1000.0 * yy[idx])
        if sz < 0:
            sz = 0
        al.extend([j] * sz)
    if not al:
        return np.array([0], dtype=np.int16)
    return np.array(al, dtype=np.int16) - np.int16(span // 2)


def load_mca_lines(csv_path: Path) -> list[McaLine]:
    text = Path(csv_path).read_text(encoding="utf-8").strip().splitlines()
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
    """Uniform line, then profile offset, /4096."""
    chn = int(rng.integers(0, len(lines)))
    line = lines[chn]
    sel = int(rng.integers(0, len(line.profile)))
    hgt = int(line.height) + int(line.profile[sel])
    hgt = max(0, min(ADC_CHANNELS - 1, hgt))
    return hgt / float(ADC_CHANNELS)


def load_shape_params(path: Path | None = None) -> dict:
    if path is None:
        path = Path(__file__).resolve().parents[1] / "config" / "sdd_shape.json"
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def cr_rc_n_kernel(
    length: int,
    peak_at: float,
    *,
    n: int = CR_RC_N,
    tau: float = CR_RC_TAU_SAMPLES,
) -> np.ndarray:
    """Unit-height causal CR–RC^n. Peak of (u^n e^{-u}) is at u = n."""
    t = np.arange(length, dtype=np.float64) - float(peak_at)
    u = (t + n * tau) / tau
    y = np.zeros(length, dtype=np.float64)
    m = u >= 0.0
    y[m] = (u[m] ** n) * np.exp(-u[m])
    peak = float(y.max())
    if peak > 0.0:
        y /= peak
    return y


def array2shape_dbl(pts: np.ndarray) -> np.ndarray:
    """2016 Array2ShapeDbl — leaky integrator, 10 inner steps, then *1.1."""
    vc = 0.0
    out = np.empty_like(pts, dtype=np.float64)
    for i in range(pts.shape[0]):
        x = float(pts[i])
        for _ in range(RC_INNER_STEPS):
            vc += (x - vc) * RC_ALPHA
        out[i] = vc * RC_GAIN
    return out


def shape_pulse_legacy(rect: np.ndarray) -> np.ndarray:
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
    """One record: A1 p(n−t1) [+ A2 p(n−t2)] + pedestal + measured noise.

    p(·) is the fitted CR–RC^n kernel. t_start is the first-pulse *peak*
    sample. gap is peak-to-peak samples when piled.
    """
    t1 = START_OFFSET + int(rng.integers(0, START_SPAN))
    a1 = draw_amplitude(lines, rng)
    waveform = a1 * cr_rc_n_kernel(WAVEFORM_LEN, t1)

    is_pileup = bool(rng.integers(0, PILEUP_PERIOD) == 0)
    if force_pileup is not None:
        is_pileup = force_pileup

    a2: float | None = None
    gap = 0
    if is_pileup:
        gap = int(rng.integers(GAP_LOW, GAP_HIGH))
        a2 = draw_amplitude(lines, rng)
        t2 = t1 + gap
        if 0 <= t2 < WAVEFORM_LEN:
            waveform = waveform + a2 * cr_rc_n_kernel(WAVEFORM_LEN, t2)

    pedestal = PEDESTAL_CH / float(ADC_CHANNELS)
    noise = rng.normal(0.0, NOISE_SIGMA_CH / float(ADC_CHANNELS), size=WAVEFORM_LEN)
    waveform = np.clip(waveform + pedestal + noise, 0.0, 1.0)
    return SimulatedPulse(
        waveform=waveform,
        amplitude_first=a1,
        amplitude_second=a2,
        is_pileup=is_pileup,
        t_start=t1,
        gap=gap,
    )
