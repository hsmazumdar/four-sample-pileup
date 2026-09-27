"""N-5-1 perceptron with the same sigmoid / clip / η = 0.5 rule as SmallMLP.

Used for the sample-count ablation. The FPGA paper claim stays 4-5-1.
"""

from __future__ import annotations

import numpy as np

from sparse_pileup.constants import CLIP_PRE, ETA, N_HIDDEN, WEIGHT_INIT_HALF
from sparse_pileup.mlp import sigmoid


class FlexMLP:
    def __init__(self, wij: np.ndarray, wjk: np.ndarray, eta: float = ETA) -> None:
        self.wij = np.array(wij, dtype=np.float64, copy=True)
        self.wjk = np.array(wjk, dtype=np.float64, copy=True)
        self.n_in = int(self.wij.shape[0] - 1)
        self.n_hid = int(self.wij.shape[1])
        self.eta = float(eta)

    @classmethod
    def random(
        cls,
        n_in: int,
        rng: np.random.Generator,
        n_hid: int = N_HIDDEN,
        eta: float = ETA,
    ) -> "FlexMLP":
        wij = WEIGHT_INIT_HALF - rng.random((n_in + 1, n_hid))
        wjk = WEIGHT_INIT_HALF - rng.random((n_hid + 1, 1))
        return cls(wij, wjk, eta=eta)

    def forward(self, samples: np.ndarray) -> float:
        x = np.asarray(samples, dtype=np.float64).reshape(self.n_in)
        yi = np.empty(self.n_in + 1, dtype=np.float64)
        yi[: self.n_in] = x
        yi[-1] = 1.0
        hj = sigmoid(np.clip(yi @ self.wij, -CLIP_PRE, CLIP_PRE))
        yj = np.empty(self.n_hid + 1, dtype=np.float64)
        yj[: self.n_hid] = hj
        yj[-1] = 1.0
        acc = float(yj @ self.wjk[:, 0])
        return float(sigmoid(acc))

    def train_step(self, samples: np.ndarray, target: float) -> float:
        x = np.asarray(samples, dtype=np.float64).reshape(self.n_in)
        yi = np.empty(self.n_in + 1, dtype=np.float64)
        yi[: self.n_in] = x
        yi[-1] = 1.0
        pre_h = np.clip(yi @ self.wij, -CLIP_PRE, CLIP_PRE)
        hj = 1.0 / (1.0 + np.exp(-pre_h))
        yj = np.empty(self.n_hid + 1, dtype=np.float64)
        yj[: self.n_hid] = hj
        yj[-1] = 1.0
        yk = float(sigmoid(float(yj @ self.wjk[:, 0])))
        t = float(target)
        delta_k = (yk - t) * yk * (1.0 - yk)
        wjk_old = self.wjk.copy()
        self.wjk[:, 0] -= self.eta * delta_k * yj
        for j in range(self.n_hid):
            r = delta_k * wjk_old[j, 0] * self.eta * yj[j] * (1.0 - yj[j])
            self.wij[:, j] -= r * yi
        return abs(yk - t)
