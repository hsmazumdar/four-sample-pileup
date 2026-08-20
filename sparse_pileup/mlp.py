"""4-5-1 MLP. ``forward`` is the only routine that belongs on the FPGA.

Training (``train_step``) stays on the PC. Arithmetic matches nnBP.cs:
sigmoid, ±10 clip, online SGD with η = 0.5.

Weight layout (same as C# wij / wjk):
    wij[i, j]  i = 0..N_IN (last row = input bias)
    wjk[j, 0]  j = 0..N_HIDDEN (last row = hidden bias)
Fully parallel MAC count: (4+1)*5 + (5+1)*1 = 31 multiplies.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sparse_pileup.constants import (
    CLIP_PRE,
    ETA,
    N_HIDDEN,
    N_OUTPUT,
    N_SAMPLES,
    WEIGHT_INIT_HALF,
)

N_IN = N_SAMPLES
N_HID = N_HIDDEN
N_OUT = N_OUTPUT


def sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    """FPGA: saturate then LUT of 1/(1+exp(-x)). Software uses exp."""
    z = np.clip(x, -CLIP_PRE, CLIP_PRE)
    return 1.0 / (1.0 + np.exp(-z))


@dataclass
class ForwardCache:
    yi: np.ndarray  # (N_IN+1,) including bias 1
    yj: np.ndarray  # (N_HID+1,) including bias 1
    yk: float


class SmallMLP:
    """One 4-5-1 head."""

    def __init__(self, wij: np.ndarray, wjk: np.ndarray, eta: float = ETA) -> None:
        if wij.shape != (N_IN + 1, N_HID):
            raise ValueError(f"wij expected {(N_IN + 1, N_HID)}, got {wij.shape}")
        if wjk.shape != (N_HID + 1, N_OUT):
            raise ValueError(f"wjk expected {(N_HID + 1, N_OUT)}, got {wjk.shape}")
        self.wij = np.array(wij, dtype=np.float64, copy=True)
        self.wjk = np.array(wjk, dtype=np.float64, copy=True)
        self.eta = float(eta)

    @classmethod
    def random(cls, rng: np.random.Generator, eta: float = ETA) -> "SmallMLP":
        # C# : 0.5 - NextDouble()  →  (-0.5, 0.5]
        wij = WEIGHT_INIT_HALF - rng.random((N_IN + 1, N_HID))
        wjk = WEIGHT_INIT_HALF - rng.random((N_HID + 1, N_OUT))
        return cls(wij, wjk, eta=eta)

    def forward(self, samples: np.ndarray) -> tuple[float, ForwardCache]:
        """FPGA infer: 31 MACs + 6 sigmoids (5 hidden + 1 output).

        RTL:
            yi[0..3] = sample_reg; yi[4] = 1;
            for j in 0..4:
                acc = 0
                for i in 0..4: acc += yi[i] * wij[i,j]
                yj[j] = sigmoid_lut(clip(acc))
            yj[5] = 1
            acc = 0
            for j in 0..5: acc += yj[j] * wjk[j,0]
            yk = sigmoid_lut(clip(acc))
        """
        x = np.asarray(samples, dtype=np.float64).reshape(N_IN)
        yi = np.empty(N_IN + 1, dtype=np.float64)
        yi[:N_IN] = x
        yi[N_IN] = 1.0

        yj = np.empty(N_HID + 1, dtype=np.float64)
        for j in range(N_HID):
            acc = 0.0
            for i in range(N_IN + 1):
                acc += yi[i] * self.wij[i, j]
            yj[j] = float(sigmoid(acc))
        yj[N_HID] = 1.0

        acc_o = 0.0
        for j in range(N_HID + 1):
            acc_o += yj[j] * self.wjk[j, 0]
        yk = float(sigmoid(acc_o))
        return yk, ForwardCache(yi=yi, yj=yj, yk=yk)

    def train_step(self, samples: np.ndarray, target: float) -> float:
        """Offline back-prop. Uses *pre-update* wjk for the hidden layer
        (standard SGD). C# updated wjk first, then used the new values —
        a small bug we do not copy.
        """
        yk, cache = self.forward(samples)
        t = float(target)
        delta_k = (yk - t) * yk * (1.0 - yk)
        wjk_old = self.wjk.copy()

        eta = self.eta
        for j in range(N_HID + 1):
            self.wjk[j, 0] -= eta * delta_k * cache.yj[j]

        for j in range(N_HID):
            r = delta_k * wjk_old[j, 0]
            r = r * eta * cache.yj[j] * (1.0 - cache.yj[j])
            for i in range(N_IN + 1):
                self.wij[i, j] -= r * cache.yi[i]
        return abs(yk - t)

    def to_lists(self) -> dict:
        return {
            "wij": self.wij.tolist(),
            "wjk": self.wjk.tolist(),
            "eta": self.eta,
        }

    @classmethod
    def from_lists(cls, data: dict) -> "SmallMLP":
        return cls(
            np.array(data["wij"], dtype=np.float64),
            np.array(data["wjk"], dtype=np.float64),
            eta=float(data.get("eta", ETA)),
        )
