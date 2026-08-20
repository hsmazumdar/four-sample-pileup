"""Two 4-5-1 heads on the same four taps. ``infer`` is the FPGA contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import numpy as np

from sparse_pileup.constants import ADC_CHANNELS, N_HIDDEN, N_SAMPLES
from sparse_pileup.mlp import SmallMLP
from sparse_pileup.sampler import assert_fpga_width


@dataclass
class InferResult:
    pileup_prob: float
    peak_height: float  # 0..1 full scale = A1 estimate

    @property
    def is_pileup(self) -> bool:
        return self.pileup_prob >= 0.5

    @property
    def peak_channel(self) -> float:
        return self.peak_height * ADC_CHANNELS


class DualHeadDetector:
    """Python runs the heads back-to-back; FPGA can issue both MAC pipelines
    once sample_reg[0..3] is full (or one DSP, twice the latency).
    """

    def __init__(self, pileup: SmallMLP, peak: SmallMLP) -> None:
        self.pileup = pileup
        self.peak = peak

    @classmethod
    def random(cls, rng: np.random.Generator) -> "DualHeadDetector":
        return cls(SmallMLP.random(rng), SmallMLP.random(rng))

    def infer(self, samples: np.ndarray) -> InferResult:
        assert_fpga_width(np.asarray(samples, dtype=np.float64))
        p, _ = self.pileup.forward(samples)
        h, _ = self.peak.forward(samples)
        return InferResult(pileup_prob=float(p), peak_height=float(h))

    def train_event(
        self,
        samples: np.ndarray,
        is_pileup: bool,
        amplitude_first: float,
    ) -> tuple[float, float]:
        """Update both heads. Peak target is true A1, including piled events."""
        t_p = 1.0 if is_pileup else 0.0
        e_p = self.pileup.train_step(samples, t_p)
        e_h = self.peak.train_step(samples, float(amplitude_first))
        return e_p, e_h

    def save_json(self, path: Path) -> None:
        payload = {
            "n_samples": N_SAMPLES,
            "n_hidden": N_HIDDEN,
            "adc_channels": ADC_CHANNELS,
            "pileup": self.pileup.to_lists(),
            "peak": self.peak.to_lists(),
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: Path) -> "DualHeadDetector":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            SmallMLP.from_lists(data["pileup"]),
            SmallMLP.from_lists(data["peak"]),
        )
