"""Trigger + four post-trigger taps. This is the FPGA sample path.

RTL sketch
----------
if (adc >= TRIGGER) firing <= 1;
if (firing) begin
    if (stride_cnt == 0) sample_reg[k] <= adc;
    ...
end
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sparse_pileup.constants import (
    ADC_CHANNELS,
    N_SAMPLES,
    SAMPLE_STRIDE,
    TRIGGER_CHANNEL,
    WAVEFORM_LEN,
)

TRIGGER_LEVEL = TRIGGER_CHANNEL / float(ADC_CHANNELS)


@dataclass
class SampleFrame:
    indices: np.ndarray  # int, shape (N_SAMPLES,)
    samples: np.ndarray  # float 0..1 after 4096-channel quantisation


def quantize_4096(value: float) -> float:
    """C# nnIn: ((int)(v * 4096)) / 4096.0  (truncates toward 0)."""
    return int(value * ADC_CHANNELS) / float(ADC_CHANNELS)


def find_trigger(waveform: np.ndarray, level: float = TRIGGER_LEVEL) -> int | None:
    for i, v in enumerate(waveform):
        if v >= level:
            return int(i)
    return None


def extract_n_taps(
    waveform: np.ndarray,
    n: int,
    stride: int,
) -> SampleFrame | None:
    """n amplitudes at n_trig + k*stride. None if no trigger or overrun."""
    trig = find_trigger(waveform)
    if trig is None:
        return None
    last = trig + (int(n) - 1) * int(stride)
    if last >= len(waveform) or last < 0:
        return None
    indices = np.array(
        [trig + k * int(stride) for k in range(int(n))], dtype=np.int32
    )
    samples = np.array(
        [quantize_4096(float(waveform[i])) for i in indices], dtype=np.float64
    )
    return SampleFrame(indices=indices, samples=samples)


def extract_frame(waveform: np.ndarray) -> SampleFrame | None:
    """Four amplitudes at n_trig + k*SAMPLE_STRIDE. None if no trigger or overrun."""
    return extract_n_taps(waveform, N_SAMPLES, SAMPLE_STRIDE)


def assert_fpga_width(samples: np.ndarray) -> None:
    if samples.shape != (N_SAMPLES,):
        raise ValueError(f"FPGA input is {N_SAMPLES} samples, got {samples.shape}")
    _ = WAVEFORM_LEN  # kept so the constant stays imported for testbench users
