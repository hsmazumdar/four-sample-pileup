"""Offline-frozen CR–RC^n template + four-tap least-squares height.

Online: closed-form A for each walk δ, 1-D search over δ.
Do not synthesise train_offline to FPGA — only estimate().

    python -m sparse_pileup.ls_peak
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sparse_pileup.constants import (  # noqa: E402
    ADC_CHANNELS,
    CR_RC_N,
    CR_RC_TAU_SAMPLES,
    N_SAMPLES,
    PEDESTAL_CH,
    SAMPLE_STRIDE,
)
from sparse_pileup.sampler import assert_fpga_width, quantize_4096  # noqa: E402

PEDESTAL = PEDESTAL_CH / float(ADC_CHANNELS)
DELTA_LO = -10.0
DELTA_HI = 2.0
DELTA_STEP = 0.1
# FPGA / paper claim: four taps at stride T = 4 (400 ns).
OFFSETS_N4 = (0, 4, 8, 12)
# Offline / 2-ADC ablation: second bank starts at T/2; eight samples at T/2.
OFFSETS_N8 = (0, 2, 4, 6, 8, 10, 12, 14)


def unit_kernel_at(
    tau: float,
    *,
    n: int = CR_RC_N,
    rc_tau: float = CR_RC_TAU_SAMPLES,
) -> float:
    """Unit-height CR–RC^n at ``tau`` samples relative to the peak (peak = 0)."""
    u = (float(tau) + n * rc_tau) / rc_tau
    if u < 0.0:
        return 0.0
    return float((u / n) ** n * np.exp(n - u))


def phi_taps(delta: float, stride: int = SAMPLE_STRIDE) -> np.ndarray:
    return np.array(
        [unit_kernel_at(delta + k * stride) for k in range(N_SAMPLES)],
        dtype=np.float64,
    )


def phi_offsets(delta: float, offsets: tuple[int, ...] | list[int]) -> np.ndarray:
    return np.array([unit_kernel_at(delta + off) for off in offsets], dtype=np.float64)


def latch_offsets(waveform: np.ndarray, trig: int, offsets: tuple[int, ...] | list[int]) -> np.ndarray | None:
    idxs = int(trig) + np.asarray(offsets, dtype=np.int32)
    if int(idxs.min()) < 0 or int(idxs.max()) >= len(waveform):
        return None
    return np.array([quantize_4096(float(waveform[i])) for i in idxs], dtype=np.float64)


def estimate_offsets(
    samples: np.ndarray,
    offsets: tuple[int, ...] | list[int],
    *,
    pedestal: float = PEDESTAL,
    delta_lo: float = DELTA_LO,
    delta_hi: float = DELTA_HI,
    delta_step: float = DELTA_STEP,
) -> LsPeakResult:
    y_hat = np.asarray(samples, dtype=np.float64) - float(pedestal)
    best_a, best_j, best_d = 0.0, 1e9, 0.0
    for d in np.arange(delta_lo, delta_hi + 0.5 * delta_step, delta_step):
        a, j = _solve_a(y_hat, phi_offsets(float(d), offsets))
        if j < best_j:
            best_a, best_j, best_d = a, j, float(d)
    return LsPeakResult(amplitude=best_a, delta=best_d, residual=best_j)


def _solve_a(y_hat: np.ndarray, phi: np.ndarray, weights: np.ndarray | None = None) -> tuple[float, float]:
    if weights is None:
        num = float(np.dot(phi, y_hat))
        den = float(np.dot(phi, phi))
    else:
        w = np.asarray(weights, dtype=np.float64)
        num = float(np.dot(w * phi, y_hat))
        den = float(np.dot(w * phi, phi))
    if den < 1e-12:
        return 0.0, 1e9
    a = num / den
    resid = y_hat - a * phi
    if weights is None:
        j = float(np.dot(resid, resid))
    else:
        j = float(np.dot(weights * resid, resid))
    return a, j


@dataclass
class LsPeakResult:
    amplitude: float
    delta: float
    residual: float

    @property
    def amplitude_ch(self) -> float:
        return self.amplitude * ADC_CHANNELS


class LsPeakEstimator:
    """Frozen-shape four-tap height. ``estimate`` is the online path."""

    def __init__(
        self,
        *,
        pedestal: float = PEDESTAL,
        delta_lo: float = DELTA_LO,
        delta_hi: float = DELTA_HI,
        delta_step: float = DELTA_STEP,
        stride: int = SAMPLE_STRIDE,
    ) -> None:
        self.pedestal = float(pedestal)
        self.stride = int(stride)
        self.delta_lo = float(delta_lo)
        self.delta_hi = float(delta_hi)
        self.delta_step = float(delta_step)
        self.deltas = np.arange(delta_lo, delta_hi + 0.5 * delta_step, delta_step)
        self._phi = np.stack([phi_taps(d, self.stride) for d in self.deltas])

    def to_dict(self) -> dict:
        return {
            "pedestal": self.pedestal,
            "delta_lo": self.delta_lo,
            "delta_hi": self.delta_hi,
            "delta_step": self.delta_step,
            "stride": self.stride,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "LsPeakEstimator":
        if not data:
            return cls()
        return cls(
            pedestal=float(data.get("pedestal", PEDESTAL)),
            delta_lo=float(data.get("delta_lo", DELTA_LO)),
            delta_hi=float(data.get("delta_hi", DELTA_HI)),
            delta_step=float(data.get("delta_step", DELTA_STEP)),
            stride=int(data.get("stride", SAMPLE_STRIDE)),
        )

    def estimate_known_delta(self, samples: np.ndarray, delta: float) -> LsPeakResult:
        assert_fpga_width(np.asarray(samples, dtype=np.float64))
        y_hat = np.asarray(samples, dtype=np.float64) - self.pedestal
        phi = phi_taps(float(delta), self.stride)
        a, j = _solve_a(y_hat, phi)
        return LsPeakResult(amplitude=a, delta=float(delta), residual=j)

    def estimate(self, samples: np.ndarray) -> LsPeakResult:
        assert_fpga_width(np.asarray(samples, dtype=np.float64))
        y_hat = np.asarray(samples, dtype=np.float64) - self.pedestal
        best_a, best_j, best_d = 0.0, 1e9, 0.0
        for d, phi in zip(self.deltas, self._phi):
            a, j = _solve_a(y_hat, phi)
            if j < best_j:
                best_a, best_j, best_d = a, j, float(d)
        return LsPeakResult(amplitude=best_a, delta=best_d, residual=best_j)


def _line_of(a1_ch: float) -> str:
    if a1_ch < 1000:
        return "SiEscape"
    if a1_ch < 1260:
        return "MnKa"
    return "MnKb"


def _stats(err_ch: np.ndarray) -> dict[str, float]:
    if err_ch.size == 0:
        return {"n": 0, "mae": 0.0, "rmse": 0.0, "bias": 0.0, "max": 0.0}
    return {
        "n": float(err_ch.size),
        "mae": float(np.mean(np.abs(err_ch))),
        "rmse": float(np.sqrt(np.mean(err_ch**2))),
        "bias": float(np.mean(err_ch)),
        "max": float(np.max(np.abs(err_ch))),
    }


def smoke_from_csv(path: Path) -> dict:
    """Held-out isolated events in the reviewer synth_test.csv."""
    est = LsPeakEstimator()
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for rec in csv.DictReader(f):
            if int(rec["is_pileup"]):
                continue
            samples = np.array(
                [float(rec["s0"]), float(rec["s1"]), float(rec["s2"]), float(rec["s3"])],
                dtype=np.float64,
            )
            a1 = float(rec["A1_ch"])
            delta_true = float(rec["trig"]) - float(rec["t_start"])
            known = est.estimate_known_delta(samples, delta_true)
            searched = est.estimate(samples)
            rows.append(
                {
                    "a1": a1,
                    "line": _line_of(a1),
                    "known_ch": known.amplitude_ch,
                    "search_ch": searched.amplitude_ch,
                }
            )

    a1 = np.array([r["a1"] for r in rows], dtype=np.float64)
    known = np.array([r["known_ch"] for r in rows], dtype=np.float64)
    search = np.array([r["search_ch"] for r in rows], dtype=np.float64)
    out: dict = {
        "n_isolated": len(rows),
        "known": _stats(known - a1),
        "search": _stats(search - a1),
        "centroids": {},
    }
    for name in ("SiEscape", "MnKa", "MnKb"):
        m = np.array([r["line"] == name for r in rows])
        if not np.any(m):
            continue
        out["centroids"][name] = {
            "n": int(m.sum()),
            "true": float(a1[m].mean()),
            "known": float(known[m].mean()),
            "search": float(search[m].mean()),
        }

    mlp_path = ROOT / "weights" / "dual_head.json"
    if mlp_path.is_file():
        from sparse_pileup.dual_head import DualHeadDetector

        mlp = DualHeadDetector.load_json(mlp_path)
        pred = []
        with path.open(encoding="utf-8", newline="") as f:
            for rec in csv.DictReader(f):
                if int(rec["is_pileup"]):
                    continue
                samples = np.array(
                    [float(rec["s0"]), float(rec["s1"]), float(rec["s2"]), float(rec["s3"])],
                    dtype=np.float64,
                )
                pred.append(mlp.infer(samples).peak_channel)
        pred_a = np.array(pred, dtype=np.float64)
        out["mlp"] = _stats(pred_a - a1)
    return out


def _fmt(s: dict) -> str:
    return (
        f"n={int(s['n'])}  MAE={s['mae']:.2f} ch  RMSE={s['rmse']:.2f} ch  "
        f"bias={s['bias']:+.2f} ch  max={s['max']:.1f} ch"
    )


def main() -> int:
    csv_path = ROOT / "data" / "synth_test.csv"
    print("OT-LS smoke  (frozen CR-RC^8, four taps, stride 4)")
    print(f"  file  {csv_path.relative_to(ROOT)}")
    print(f"  delta grid  [{DELTA_LO}, {DELTA_HI}] step {DELTA_STEP}")
    print()
    out = smoke_from_csv(csv_path)
    print(f"Isolated events: {out['n_isolated']}")
    print(f"  LS, known t0     {_fmt(out['known'])}")
    print(f"  LS, t0 from taps {_fmt(out['search'])}")
    if "mlp" in out:
        print(f"  Peak MLP 4-5-1   {_fmt(out['mlp'])}")
    print()
    print("Line centroids (true vs LS-search)")
    for name, c in out["centroids"].items():
        print(
            f"  {name:10s} n={c['n']:4d}  true={c['true']:.1f}  "
            f"LS={c['search']:.1f}  shift={c['search']-c['true']:+.1f} ch"
        )
    mae = out["search"]["mae"]
    ok = mae <= 8.0
    print()
    print(f"SMOKE  isolated LS MAE {mae:.2f} ch   {'PASS' if ok else 'FAIL'}  (pass <= 8 ch)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
