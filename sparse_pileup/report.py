"""Write reviewer tables: pile-up confusion matrix + peak-height errors.

    python -m sparse_pileup.report
    python -m sparse_pileup.report --weights weights/dual_head.json

Uses the frozen test seed (DEFAULT_SEED+2) so numbers match run_poc.py.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sparse_pileup.constants import (
    ADC_CHANNELS,
    DEFAULT_ENGINE,
    DEFAULT_LINES_CSV,
    DEFAULT_SEED,
    N_TEST,
)
from sparse_pileup.dataset import generate_events
from sparse_pileup.dual_head import DualHeadDetector
from sparse_pileup.ls_peak import OFFSETS_N8, estimate_offsets, latch_offsets
from sparse_pileup.metrics import PeakMetrics, format_report, peak_metrics, pileup_metrics


def _peak_hist(model: DualHeadDetector, rows, isolated_only: bool) -> Counter:
    c: Counter = Counter()
    for row in rows:
        if isolated_only and row.is_pileup:
            continue
        pred = model.infer(row.samples).peak_height
        err = abs(pred - row.amplitude_first) * ADC_CHANNELS
        c[int(round(err))] += 1
    return c


def write_tables(
    model: DualHeadDetector,
    rows,
    artifacts: Path,
    results_md: Path,
) -> None:
    artifacts.mkdir(parents=True, exist_ok=True)
    pile = pileup_metrics(model, rows)
    peak_all = peak_metrics(model, rows)
    peak_iso = peak_metrics(model, rows, isolated_only=True)
    report = format_report(pile, peak_all, peak_iso)
    (artifacts / "test_report.txt").write_text(report + "\n", encoding="utf-8")

    with (artifacts / "pileup_confusion.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["", "pred_single", "pred_pileup", "row_total"])
        w.writerow(["true_single", pile.tn, pile.fp, pile.tn + pile.fp])
        w.writerow(["true_pileup", pile.fn, pile.tp, pile.fn + pile.tp])
        w.writerow(["col_total", pile.tn + pile.fn, pile.fp + pile.tp, pile.n])

    with (artifacts / "pileup_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in [
            ("n", pile.n),
            ("n_pileup", pile.n_pileup),
            ("tp", pile.tp),
            ("fp", pile.fp),
            ("tn", pile.tn),
            ("fn", pile.fn),
            ("accuracy", f"{pile.accuracy:.6f}"),
            ("precision", f"{pile.precision:.6f}"),
            ("recall", f"{pile.recall:.6f}"),
            ("f1", f"{pile.f1:.6f}"),
        ]:
            w.writerow([k, v])

    with (artifacts / "peak_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subset", "n", "MAE_ch", "RMSE_ch", "max_ch"])
        w.writerow(
            ["isolated", peak_iso.n, f"{peak_iso.mae_ch:.4f}",
             f"{peak_iso.rmse_ch:.4f}", f"{peak_iso.max_ch:.4f}"]
        )
        w.writerow(
            ["all_events", peak_all.n, f"{peak_all.mae_ch:.4f}",
             f"{peak_all.rmse_ch:.4f}", f"{peak_all.max_ch:.4f}"]
        )

    n8_err: list[float] = []
    for row in rows:
        if row.is_pileup:
            continue
        taps = latch_offsets(row.waveform, int(row.frame.indices[0]), OFFSETS_N8)
        if taps is None:
            continue
        pred = estimate_offsets(taps, OFFSETS_N8).amplitude
        n8_err.append(abs(pred - row.amplitude_first) * ADC_CHANNELS)
    n8_arr = np.array(n8_err, dtype=np.float64)
    peak_n8 = PeakMetrics(
        n=int(n8_arr.size),
        mae_ch=float(n8_arr.mean()) if n8_arr.size else 0.0,
        rmse_ch=float(np.sqrt((n8_arr**2).mean())) if n8_arr.size else 0.0,
        max_ch=float(n8_arr.max()) if n8_arr.size else 0.0,
    )
    with (artifacts / "peak_n8_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subset", "n", "MAE_ch", "RMSE_ch", "max_ch"])
        w.writerow(
            ["isolated_n8_T/2", peak_n8.n, f"{peak_n8.mae_ch:.4f}",
             f"{peak_n8.rmse_ch:.4f}", f"{peak_n8.max_ch:.4f}"]
        )

    hist_iso = _peak_hist(model, rows, isolated_only=True)
    hist_all = _peak_hist(model, rows, isolated_only=False)
    bins = sorted(set(hist_iso) | set(hist_all))
    with (artifacts / "peak_error_hist.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["abs_error_ch_rounded", "count_isolated", "count_all"])
        for b in bins:
            w.writerow([b, hist_iso.get(b, 0), hist_all.get(b, 0)])

    md = f"""# Held-out results (seed 42 protocol)

**Engine = real-pulse superposition (V4).** Isolated events are
measured Fe-55 SDD snippets. Pile-up events are a **linear sum of
two isolated measured pulses** at a controlled peak-to-peak delay.
They are **constructed**, not Poisson arrivals recorded at high rate,
and this is **not** a measured pile-up F1.

Height is **OT-LS** (frozen CR–RC⁸ template + four-tap least squares).
A1 / A2 labels are conventional peak-minus-baseline of each snippet.
Unique pulses are partitioned so a test snippet is never used in
training. Reproduce: `python -m sparse_pileup.real_pulse_lib`
then `python synthesize_data.py` then `python run_poc.py`.
The V3 formula injector remains as `--engine kernel`.

Test set: n = {pile.n} events, independent RNG seed `{DEFAULT_SEED}+2`.
Peak target = true first-pulse amplitude A1 (4096-channel units).

## Pile-up classification

| Metric | Value |
|--------|------:|
| Events | {pile.n} |
| True pile-up | {pile.n_pileup} |
| Accuracy | {pile.accuracy:.3f} |
| Precision | {pile.precision:.3f} |
| Recall | {pile.recall:.3f} |
| F1 | {pile.f1:.3f} |

### Confusion matrix

| | Predicted single | Predicted pile-up |
|--|--:|--:|
| True single | {pile.tn} | {pile.fp} |
| True pile-up | {pile.fn} | {pile.tp} |

Threshold: `pileup_prob >= 0.5`. Machine-readable copy:
`artifacts/pileup_confusion.csv`.

## Peak height vs A1

| Subset | n | MAE (ch) | RMSE (ch) | Max (ch) |
|--------|--:|---------:|----------:|---------:|
| Isolated pulses | {peak_iso.n} | {peak_iso.mae_ch:.1f} | {peak_iso.rmse_ch:.1f} | {peak_iso.max_ch:.1f} |
| All events (incl. pile-up) | {peak_all.n} | {peak_all.mae_ch:.1f} | {peak_all.rmse_ch:.1f} | {peak_all.max_ch:.1f} |

Isolated MAE is the OT-LS four-tap result. Quote that row for
spectroscopy. The all-event row applies OT-LS even when a second
pulse is present; it is not A1 unfolding and is why the pile-up
veto exists. The retired peak 4–5–1 scored 34.9 ch MAE / −20 ch
bias on the same isolated file. The C# trainer
reported ~0.89 channel MAE on **same-set** files against
**shaped max(waveform)**, isolated pulses only. That is a different
target and is not comparable to the A1 columns above.

Error histogram (rounded |err|): `artifacts/peak_error_hist.csv`.

## Offline N = 8 at T/2 (ablation, not the FPGA claim)

Same isolated events, same OT-LS equation, eight taps at 200 ns
(ADC1 at 0, T, 2T, 3T and ADC2 at T/2… or one 10 MSPS stream).
Extra points are redundant for the frozen shape; they reduce noise.
Do not pick “best of two” N = 4 heads — average / one 8-tap LS.

| Subset | n | MAE (ch) | RMSE (ch) | Max (ch) |
|--------|--:|---------:|----------:|---------:|
| Isolated, N = 4 (device) | {peak_iso.n} | {peak_iso.mae_ch:.1f} | {peak_iso.rmse_ch:.1f} | {peak_iso.max_ch:.1f} |
| Isolated, N = 8 (T/2) | {peak_n8.n} | {peak_n8.mae_ch:.1f} | {peak_n8.rmse_ch:.1f} | {peak_n8.max_ch:.1f} |

Machine-readable: `artifacts/peak_n8_metrics.csv`.

## How these numbers were produced

1. Extract isolated Fe-55 pulses → `real_data/isolated_fe55_snippets.npz`.
2. Partition unique snippets 60/20/20 (seed 42).
3. `python synthesize_data.py` — 4000/1000/1000 events, seeds 42/43/44.
   Isolated = one snippet. Pile-up = host as measured + guest excess at Δt.
4. `python run_poc.py` — train the 4–5–1 pile-up head 40 epochs, η = 0.5.
   Height is the frozen OT-LS estimator (`sparse_pileup/ls_peak.py`).
5. Evaluate `infer()` on the held-out test seed.

The 2016 C# same-set MAE (~0.89 ch vs shaped max) used a different
pulse, stride 15, and a different label. Do not compare it to the A1
columns above.

V3 used a CR–RC⁸ formula for both pulses (F1 0.671, isolated MAE 6.1 ch).
V4 isolated events are real singles; pile-up is still constructed.
`--engine kernel` rebuilds the V3 table.
"""
    results_md.write_text(md, encoding="utf-8")
    print(report)
    print(f"Wrote {results_md}")
    print(f"Wrote {artifacts / 'pileup_confusion.csv'}")
    print(f"Wrote {artifacts / 'peak_metrics.csv'}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Rebuild RESULTS.md from frozen weights.")
    p.add_argument("--weights", type=Path, default=ROOT / "weights" / "dual_head.json")
    p.add_argument("--config", type=Path, default=ROOT / DEFAULT_LINES_CSV)
    p.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
    p.add_argument("--results", type=Path, default=ROOT / "RESULTS.md")
    p.add_argument("--n-test", type=int, default=N_TEST)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--engine", choices=("real", "kernel"), default=DEFAULT_ENGINE)
    args = p.parse_args(argv)

    model = DualHeadDetector.load_json(args.weights)
    rows = generate_events(
        args.n_test,
        args.config,
        args.seed + 2,
        engine=args.engine,
        split_name="test",
    )
    write_tables(model, rows, args.artifacts, args.results)


if __name__ == "__main__":
    main()
