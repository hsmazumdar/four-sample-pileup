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


def extract_frame(waveform: np.ndarray) -> SampleFrame | None:
    """Four amplitudes at n_trig + k*15, k=0..3. None if no trigger or window overruns."""
    trig = find_trigger(waveform)
    if trig is None:
        return None
    last = trig + (N_SAMPLES - 1) * SAMPLE_STRIDE
    if last >= len(waveform):
        return None
    indices = np.array(
        [trig + k * SAMPLE_STRIDE for k in range(N_SAMPLES)], dtype=np.int32
    )
    samples = np.array(
        [quantize_4096(float(waveform[i])) for i in indices], dtype=np.float64
    )
    return SampleFrame(indices=indices, samples=samples)


def assert_fpga_width(samples: np.ndarray) -> None:
    if samples.shape != (N_SAMPLES,):
        raise ValueError(f"FPGA input is {N_SAMPLES} samples, got {samples.shape}")
    _ = WAVEFORM_LEN  # kept so the constant stays imported for testbench users
