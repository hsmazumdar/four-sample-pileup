"""Pile-up 4-5-1 MLP + OT-LS height on the same four taps.

``infer`` is the FPGA contract: one sigmoid net for the veto, then
closed-form A with a 1-D walk search. The old peak 4-5-1 is not used.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import numpy as np

from sparse_pileup.constants import ADC_CHANNELS, N_HIDDEN, N_SAMPLES
from sparse_pileup.ls_peak import LsPeakEstimator
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
    """Python runs the heads back-to-back; FPGA can issue the pile-up MAC
    pipeline and the LS search once sample_reg[0..3] is full.
    """

    def __init__(self, pileup: SmallMLP, peak: LsPeakEstimator | None = None) -> None:
        self.pileup = pileup
        self.peak = peak if peak is not None else LsPeakEstimator()

    @classmethod
    def random(cls, rng: np.random.Generator) -> "DualHeadDetector":
        return cls(SmallMLP.random(rng), LsPeakEstimator())

    def infer(self, samples: np.ndarray) -> InferResult:
        assert_fpga_width(np.asarray(samples, dtype=np.float64))
        p, _ = self.pileup.forward(samples)
        h = self.peak.estimate(samples)
        return InferResult(pileup_prob=float(p), peak_height=float(h.amplitude))

    def train_event(
        self,
        samples: np.ndarray,
        is_pileup: bool,
        amplitude_first: float | None = None,
    ) -> tuple[float, float]:
        """Update the pile-up head only. Height is the frozen OT-LS model."""
        _ = amplitude_first
        t_p = 1.0 if is_pileup else 0.0
        e_p = self.pileup.train_step(samples, t_p)
        return e_p, 0.0

    def save_json(self, path: Path) -> None:
        payload = {
            "n_samples": N_SAMPLES,
            "n_hidden": N_HIDDEN,
            "adc_channels": ADC_CHANNELS,
            "height": "ot_ls",
            "pileup": self.pileup.to_lists(),
            "ls_peak": self.peak.to_dict(),
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: Path) -> "DualHeadDetector":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            SmallMLP.from_lists(data["pileup"]),
            LsPeakEstimator.from_dict(data.get("ls_peak")),
        )
