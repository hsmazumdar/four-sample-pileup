# Held-out results (seed 42 protocol)

Synthetic RC-smoothed rectangles. **Not** HPGe/NaI data and **not** a journal
claim. Reproduce with `python run_poc.py` or `python -m sparse_pileup.report`.

Test set: n = 1000 events, independent RNG seed `42+2`.
Peak target = true first-pulse amplitude A1 (4096-channel units).

## Pile-up classification

| Metric | Value |
|--------|------:|
| Events | 1000 |
| True pile-up | 122 |
| Accuracy | 0.969 |
| Precision | 1.000 |
| Recall | 0.746 |
| F1 | 0.854 |

### Confusion matrix

| | Predicted single | Predicted pile-up |
|--|--:|--:|
| True single | 878 | 0 |
| True pile-up | 31 | 91 |

Threshold: `pileup_prob >= 0.5`. Machine-readable copy:
`artifacts/pileup_confusion.csv`.

## Peak height vs A1

| Subset | n | MAE (ch) | RMSE (ch) | Max (ch) |
|--------|--:|---------:|----------:|---------:|
| Isolated pulses | 878 | 93.7 | 95.6 | 210.8 |
| All events (incl. pile-up) | 1000 | 143.5 | 391.8 | 3737.5 |

The C# trainer reported ~0.89 channel MAE on **same-set** files against
**shaped max(waveform)**, isolated pulses only. That is a different target
and is not comparable to the A1 columns above.

Error histogram (rounded |err|): `artifacts/peak_error_hist.csv`.

## How these numbers were produced

1. `python synthesize_data.py` — 4000/1000/1000 events, seeds 42/43/44.
2. `python run_poc.py` — train both 4–5–1 heads 40 epochs, η = 0.5.
3. Evaluate `infer()` on the held-out test CSV / regenerated test seed.
