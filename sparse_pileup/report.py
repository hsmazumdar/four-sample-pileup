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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sparse_pileup.constants import ADC_CHANNELS, DEFAULT_LINES_CSV, DEFAULT_SEED, N_TEST
from sparse_pileup.dataset import generate_events
from sparse_pileup.dual_head import DualHeadDetector
from sparse_pileup.metrics import format_report, peak_metrics, pileup_metrics


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

    hist_iso = _peak_hist(model, rows, isolated_only=True)
    hist_all = _peak_hist(model, rows, isolated_only=False)
    bins = sorted(set(hist_iso) | set(hist_all))
    with (artifacts / "peak_error_hist.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["abs_error_ch_rounded", "count_isolated", "count_all"])
        for b in bins:
            w.writerow([b, hist_iso.get(b, 0), hist_all.get(b, 0)])

    md = f"""# Held-out results (seed 42 protocol)

Synthetic **CR–RC⁸** pulses fitted to isolated Fe-55 SDD traces
(`config/sdd_shape.json`, fs = 10 MSPS, peaking 1.01 µs, stride 4).
Pile-up is still **injected in software**. These numbers are not a
measured pile-up F1 and not HPGe/NaI data. Reproduce with
`python synthesize_data.py` then `python run_poc.py`.

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

The C# trainer reported ~0.89 channel MAE on **same-set** files against
**shaped max(waveform)**, isolated pulses only. That is a different target
and is not comparable to the A1 columns above.

Error histogram (rounded |err|): `artifacts/peak_error_hist.csv`.

## How these numbers were produced

1. Fit isolated Fe-55 pulses → `config/sdd_shape.json` (CR–RC⁸, τ = 1.2606 samples).
2. `python synthesize_data.py` — 4000/1000/1000 events, seeds 42/43/44,
   lines in `config/sdd_fe55_lines.csv`, measured baseline noise.
3. `python run_poc.py` — train both 4–5–1 heads 40 epochs, η = 0.5.
4. Evaluate `infer()` on the held-out test seed.

The 2016 C# same-set MAE (~0.89 ch vs shaped max) used a different
pulse, stride 15, and a different label. Do not compare it to the A1
columns above.
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
    args = p.parse_args(argv)

    model = DualHeadDetector.load_json(args.weights)
    rows = generate_events(args.n_test, args.config, args.seed + 2)
    write_tables(model, rows, args.artifacts, args.results)


if __name__ == "__main__":
    main()
