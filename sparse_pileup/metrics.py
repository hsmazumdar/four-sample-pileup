"""Held-out pile-up F1 and peak MAE in 4096-channel units."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sparse_pileup.constants import ADC_CHANNELS
from sparse_pileup.dataset import Event
from sparse_pileup.dual_head import DualHeadDetector


@dataclass
class PileupMetrics:
    n: int
    n_pileup: int
    tp: int
    fp: int
    tn: int
    fn: int
    accuracy: float
    precision: float
    recall: float
    f1: float


@dataclass
class PeakMetrics:
    n: int
    mae_ch: float
    rmse_ch: float
    max_ch: float


def pileup_metrics(model: DualHeadDetector, rows: list[Event]) -> PileupMetrics:
    tp = fp = tn = fn = 0
    for row in rows:
        pred = model.infer(row.samples).is_pileup
        if row.is_pileup and pred:
            tp += 1
        elif row.is_pileup and not pred:
            fn += 1
        elif (not row.is_pileup) and pred:
            fp += 1
        else:
            tn += 1
    n = len(rows)
    acc = (tp + tn) / n if n else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    return PileupMetrics(
        n=n,
        n_pileup=tp + fn,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        accuracy=acc,
        precision=prec,
        recall=rec,
        f1=f1,
    )


def peak_metrics(
    model: DualHeadDetector,
    rows: list[Event],
    isolated_only: bool = False,
) -> PeakMetrics:
    err: list[float] = []
    for row in rows:
        if isolated_only and row.is_pileup:
            continue
        pred = model.infer(row.samples).peak_height
        err.append(abs(pred - row.amplitude_first) * ADC_CHANNELS)
    arr = np.array(err, dtype=np.float64)
    if arr.size == 0:
        return PeakMetrics(n=0, mae_ch=0.0, rmse_ch=0.0, max_ch=0.0)
    return PeakMetrics(
        n=int(arr.size),
        mae_ch=float(arr.mean()),
        rmse_ch=float(np.sqrt((arr**2).mean())),
        max_ch=float(arr.max()),
    )


def format_report(
    pile: PileupMetrics,
    peak_all: PeakMetrics,
    peak_iso: PeakMetrics,
) -> str:
    lines = [
        "Held-out report (not a paper claim; SDD-fitted CR–RC^8, synthetic pile-up)",
        f"  Pile-up  n={pile.n}  (true pile-up {pile.n_pileup})",
        f"           acc={pile.accuracy:.3f}  F1={pile.f1:.3f}  "
        f"precision={pile.precision:.3f}  recall={pile.recall:.3f}",
        f"           tp={pile.tp}  fp={pile.fp}  tn={pile.tn}  fn={pile.fn}",
        f"  Peak vs A1, isolated  n={peak_iso.n}  "
        f"MAE={peak_iso.mae_ch:.1f} ch  RMSE={peak_iso.rmse_ch:.1f} ch  "
        f"max={peak_iso.max_ch:.1f} ch",
        f"  Peak vs A1, all events n={peak_all.n}  "
        f"MAE={peak_all.mae_ch:.1f} ch  RMSE={peak_all.rmse_ch:.1f} ch  "
        f"max={peak_all.max_ch:.1f} ch",
        "  Peak target is true first-pulse amplitude A1, not shaped max(waveform).",
    ]
    return "\n".join(lines)
