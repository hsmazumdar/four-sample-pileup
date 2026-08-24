# Held-out results (seed 42 protocol)

Synthetic **CR–RC⁸** pulses fitted to isolated Fe-55 SDD traces
(`config/sdd_shape.json`, fs = 10 MSPS, peaking 1.01 µs, stride 4).
Pile-up is still **injected in software**. Height is **OT-LS**
(frozen CR–RC⁸ template + four-tap least squares), not the old
peak 4–5–1 MLP. These numbers are not a measured pile-up F1 and
not HPGe/NaI data. Reproduce with `python synthesize_data.py`
then `python run_poc.py`.

Test set: n = 1000 events, independent RNG seed `42+2`.
Peak target = true first-pulse amplitude A1 (4096-channel units).

## Pile-up classification

| Metric | Value |
|--------|------:|
| Events | 1000 |
| True pile-up | 103 |
| Accuracy | 0.949 |
| Precision | 1.000 |
| Recall | 0.505 |
| F1 | 0.671 |

### Confusion matrix

| | Predicted single | Predicted pile-up |
|--|--:|--:|
| True single | 897 | 0 |
| True pile-up | 51 | 52 |

Threshold: `pileup_prob >= 0.5`. Machine-readable copy:
`artifacts/pileup_confusion.csv`.

## Peak height vs A1

| Subset | n | MAE (ch) | RMSE (ch) | Max (ch) |
|--------|--:|---------:|----------:|---------:|
| Isolated pulses | 897 | 6.1 | 7.7 | 35.4 |
| All events (incl. pile-up) | 1000 | 32.5 | 140.1 | 1146.1 |

Isolated MAE is the OT-LS four-tap result. Quote that row for
spectroscopy. The all-event row applies OT-LS even when a second
pulse is present; it is not A1 unfolding and is why the pile-up
veto exists. The retired peak 4–5–1 scored 34.9 ch MAE / −20 ch
bias on the same isolated file. The C# trainer
reported ~0.89 channel MAE on **same-set** files against
**shaped max(waveform)**, isolated pulses only. That is a different
target and is not comparable to the A1 columns above.

Error histogram (rounded |err|): `artifacts/peak_error_hist.csv`.

## How these numbers were produced

1. Fit isolated Fe-55 pulses → `config/sdd_shape.json` (CR–RC⁸, τ = 1.2606 samples).
2. `python synthesize_data.py` — 4000/1000/1000 events, seeds 42/43/44,
   lines in `config/sdd_fe55_lines.csv`, measured baseline noise.
3. `python run_poc.py` — train the 4–5–1 pile-up head 40 epochs, η = 0.5.
   Height is the frozen OT-LS estimator (`sparse_pileup/ls_peak.py`).
4. Evaluate `infer()` on the held-out test seed.

The 2016 C# same-set MAE (~0.89 ch vs shaped max) used a different
pulse, stride 15, and a different label. Do not compare it to the A1
columns above.

Versus the previous cartoon synthesizer (3× leaky integrator, stride 15):
pile-up F1 fell from 0.854 to 0.671 (recall 0.505; precision still 1.000).
Isolated A1 MAE is now OT-LS (~6 ch), not the old peak-MLP 34.9 ch.
Both pile-up and height numbers are still synthetic.
