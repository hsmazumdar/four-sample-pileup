"""Construct events from measured isolated Fe-55 snippets.

Isolated: one real snippet placed on the 160-sample canvas.
Pile-up: host snippet kept as measured (baseline + noise + pulse);
the guest is baseline-subtracted and added at a controlled peak-to-peak
gap. Linear superposition — not a Poisson high-rate recording.

A1 / A2 labels are each snippet's conventional peak-minus-baseline.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from sparse_pileup.constants import (
    ADC_CHANNELS,
    GAP_HIGH,
    GAP_LOW,
    PILEUP_PERIOD,
    REAL_SNIPPET_PRE,
    START_OFFSET,
    START_SPAN,
    WAVEFORM_LEN,
)
from sparse_pileup.pulse_sim import SimulatedPulse
from sparse_pileup.real_pulse_lib import IsolatedSnippet, PulseLibrary


def _place(canvas: np.ndarray, src: np.ndarray, peak_dst: int, peak_src: int = REAL_SNIPPET_PRE) -> None:
    """Add src onto canvas so src[peak_src] lands at peak_dst."""
    shift = int(peak_dst - peak_src)
    src_lo = max(0, -shift)
    src_hi = min(src.size, WAVEFORM_LEN - shift)
    if src_lo >= src_hi:
        return
    dst_lo = src_lo + shift
    dst_hi = src_hi + shift
    canvas[dst_lo:dst_hi] += src[src_lo:src_hi].astype(np.float64)


def compose_waveform(
    host: IsolatedSnippet,
    *,
    t1: int,
    guest: IsolatedSnippet | None = None,
    gap: int = 0,
    guest_scale: float = 1.0,
    extra_noise_ch: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Return a 0..1 full-scale waveform, clipped to the 12-bit range.

    The host is the measured snippet (one baseline, one noise draw).
    The guest contributes only its baseline-subtracted excess, scaled by
    ``guest_scale``. No second pedestal is added. ``extra_noise_ch`` is
    off unless a caller explicitly requests an SNR stress test; the
    default path does not add ``NOISE_SIGMA_CH`` on top of measured noise.
    """
    canvas = np.zeros(WAVEFORM_LEN, dtype=np.float64)
    _place(canvas, host.adc.astype(np.float64), t1)
    if guest is not None and gap > 0:
        excess = (guest.adc.astype(np.float64) - guest.baseline_ch) * float(guest_scale)
        _place(canvas, excess, t1 + int(gap))
    if extra_noise_ch > 0.0:
        if rng is None:
            rng = np.random.default_rng()
        canvas = canvas + rng.normal(0.0, float(extra_noise_ch), size=WAVEFORM_LEN)
    canvas = np.clip(canvas, 0.0, float(ADC_CHANNELS - 1))
    return canvas / float(ADC_CHANNELS)


def simulate_real_event(
    lib: PulseLibrary,
    rng: np.random.Generator,
    *,
    force_pileup: bool | None = None,
    gap: int | None = None,
    guest_scale: float = 1.0,
    target_ratio: float | None = None,
    extra_noise_ch: float = 0.0,
) -> SimulatedPulse:
    n = len(lib.snippets)
    if n < 2:
        raise RuntimeError("need at least two isolated snippets")
    i_host = int(rng.integers(0, n))
    host = lib.snippets[i_host]
    t1 = START_OFFSET + int(rng.integers(0, START_SPAN))
    is_pileup = bool(rng.integers(0, PILEUP_PERIOD) == 0)
    if force_pileup is not None:
        is_pileup = force_pileup
    a2 = None
    used_gap = 0
    guest = None
    scale = float(guest_scale)
    if is_pileup:
        i_guest = int(rng.integers(0, n))
        while i_guest == i_host and n > 1:
            i_guest = int(rng.integers(0, n))
        guest = lib.snippets[i_guest]
        used_gap = int(gap) if gap is not None else int(rng.integers(GAP_LOW, GAP_HIGH))
        if target_ratio is not None and guest.amplitude_ch > 1.0:
            scale = float(target_ratio) * host.amplitude_ch / guest.amplitude_ch
        a2 = guest.amplitude_ch * scale / float(ADC_CHANNELS)
    wave = compose_waveform(
        host,
        t1=t1,
        guest=guest,
        gap=used_gap,
        guest_scale=scale,
        extra_noise_ch=extra_noise_ch,
        rng=rng,
    )
    return SimulatedPulse(
        waveform=wave,
        amplitude_first=host.amplitude_ch / float(ADC_CHANNELS),
        amplitude_second=a2,
        is_pileup=is_pileup,
        t_start=t1,
        gap=used_gap,
    )


def generate_real_pulses(
    n: int,
    lib: PulseLibrary,
    seed: int,
    *,
    force_pileup: bool | None = None,
) -> list[SimulatedPulse]:
    rng = np.random.default_rng(seed)
    return [simulate_real_event(lib, rng, force_pileup=force_pileup) for _ in range(n)]


def library_for_split(split_name: str, seed: int, root: Path | None = None) -> PulseLibrary:
    from sparse_pileup.real_pulse_lib import load_or_build

    full = load_or_build(root)
    train, val, test = full.split(seed)
    if split_name == "train":
        return train
    if split_name == "val":
        return val
    if split_name == "test":
        return test
    raise ValueError(split_name)
