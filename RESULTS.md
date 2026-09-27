# Held-out results (seed 42 protocol)

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

Test set: n = 1000 events, independent RNG seed `42+2`.
Peak target = true first-pulse amplitude A1 (4096-channel units).

## Pile-up classification

| Metric | Value |
|--------|------:|
| Events | 1000 |
| True pile-up | 95 |
| Accuracy | 0.955 |
| Precision | 1.000 |
| Recall | 0.526 |
| F1 | 0.690 |

### Confusion matrix

| | Predicted single | Predicted pile-up |
|--|--:|--:|
| True single | 905 | 0 |
| True pile-up | 45 | 50 |

Threshold: `pileup_prob >= 0.5`. Machine-readable copy:
`artifacts/pileup_confusion.csv`.

## Peak height vs A1

| Subset | n | MAE (ch) | RMSE (ch) | Max (ch) |
|--------|--:|---------:|----------:|---------:|
| Isolated pulses | 905 | 21.9 | 24.4 | 61.1 |
| All events (incl. pile-up) | 1000 | 52.2 | 165.8 | 1286.3 |

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
| Isolated, N = 4 (device) | 905 | 21.9 | 24.4 | 61.1 |
| Isolated, N = 8 (T/2) | 905 | 20.8 | 23.2 | 54.8 |

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

## V5 operating region (no Am-241)

Reproduce: `python -m sparse_pileup.operating_region`.
All pile-up here is still **constructed**. Tables: `artifacts/v5_*.csv`.

Held-out 4–5–1 (same 1000-event file as above):

| Metric | Value |
|--------|------:|
| ROC-AUC | 0.835 |
| Recall 95% Wilson CI | 0.427 – 0.624 |
| Precision 95% Wilson CI | 0.929 – 1.000 |

### Detection vs Δt (equal-ish Fe-55 pairs)

Four taps span 1.2 µs. Recall of the frozen 4–5–1 is **1.00 for Δt ≤ 1.0 µs**
and **0 for Δt ≥ 1.6 µs**. A retrigger inspector is the opposite: ~0 on
unresolved pairs, ~1 once the peaks separate. They are complementary.

| Δt (µs) | 4–5–1 recall | Retrigger recall | Residual recall |
|--------:|-------------:|-----------------:|----------------:|
| 0.3–1.0 | 1.00 | ~0 | 1.00 |
| 1.2 | 0.15 | 0.99 | 0.93 |
| 1.6–2.0 | 0.00 | 1.00 | ~0 |

### A2/A1 × Δt

Guest amplitude is scaled (measured shape, constructed ratio). Hard cell:
small guest (A2/A1 = 0.25) even at Δt = 0.4 µs (F1 0.28). Ratios 0.5–2 at
Δt ≤ 0.8 µs stay near F1 1.0. See `artifacts/v5_operating_region.png`.

### Sample count (20-epoch balanced ablation, not the device weights)

| Inputs | Weights | F1 | Recall | AUC |
|--------|--------:|---:|-------:|----:|
| 4 | 31 | 0.566 | 0.395 | 0.771 |
| 8 | 51 | 0.722 | 0.565 | 0.835 |
| 16 | 91 | 0.738 | 0.585 | 0.860 |
| 32 | 171 | 1.000 | 1.000 | 1.000 |
| 48 | 251 | 1.000 | 1.000 | 1.000 |

More taps recover the large-gap seconds that four taps miss.

### Four-tap baselines (balanced constructed mix)

| Method | F1 | Recall | AUC |
|--------|---:|-------:|----:|
| 4–5–1 MLP (frozen) | 0.662 | 0.495 | 0.791 |
| Logistic regression | 0.684 | 0.530 | 0.770 |
| Template residual | 0.712 | 0.552 | 0.804 |
| Retrigger | 0.722 | 0.565 | 0.782 |
| Slope / 2nd rise | 0.005 | 0.003 | 0.501 |

On a **random-gap** mix, retrigger and residual match or beat the MLP.
The MLP’s advantage is the **close-overlap** slice (Δt ≤ 1.0 µs), where
retrigger is blind.

### Complementary OR (frozen 4–5–1 **or** retrigger)

Same official 1000-event mix. Still constructed. Not Am-241.

| Method | TP / 95 | FP | Recall | F1 |
|--------|--------:|---:|-------:|---:|
| 4–5–1 MLP | 50 | 0 | 0.526 | 0.690 |
| Retrigger | 51 | 0 | 0.537 | 0.699 |
| MLP OR retrigger | 95 | 0 | 1.000 | 1.000 |

OR recall Wilson 95% CI: 0.961–1.000. The same OR has recall **1.00 at
every tested Δt** from 0.3 to 2.0 µs on equal-ish Fe-55 guests, and
F1 1.00 on the balanced random-gap mix (0 false positives). The hard
A2/A1 = 0.25 cell was **not** part of this OR test.

Reproduce the extra column without retraining:
`python -m sparse_pileup.operating_region --fusion`.

### SNR and empirical height

Added noise σ = 0 / 10 / 20 / 40 ch → F1 0.72 / 0.69 / 0.68 / 0.61.
Isolated OT-LS MAE: CR–RC⁸ template **21.1 ch**; empirical mean pulse **11.2 ch**.

Am-241 / measured high-rate F1 is still absent.
