# Segment-first validation

Historical V5 numbers stay in [RESULTS.md](RESULTS.md) and `artifacts/v5_*`.
This file is the later protocol. It does not replace those files.

Pile-up below is still a linear sum of measured isolated Fe-55 pulses.
It is not a high-rate recording and not a spectrometer claim.

## Reproduce

```bash
python -m pip install -r requirements.txt
python tests/test_sanity.py
python tests/test_strict_protocol.py
python -m sparse_pileup.strict_validation --out artifacts/v6
```

One command writes `artifacts/v6/summary.json`, the CSV tables, and the
plots. The run records Python, NumPy, code SHA-256, and per-buffer
SHA-256 in `summary.json`. Seeds and split counts are in `runs.csv`.

Primary run: `blocked-42`.
Blocked buffers follow acquisition order: segments 1–37 train, 38–49
validation, 50–61 test.
Blocked init/synthesis seeds: 42, 43, 44 (same buffers).
Random buffer assignments: seeds 42, 43, 44.
Train / validation / test event seeds: `seed`, `seed+1`, `seed+2`.
Weight init: `seed+99`. Logistic init: `seed+123`.
Conditional draws: `seed+7`. Streams: `seed+11`.
MLP: 4–5–1, 40 epochs, η = 0.5, pile-up period 10, 4000 / 1000 / 1000 events.
Threshold: maximize F1 on the validation prevalence mix. Ties take the
higher threshold. Probability scores use 0.05–0.95 step 0.02. The
template-residual score uses validation quantiles, because it is not a
probability. Retrigger and slope are hard decisions.
Logistic regression is fit on the train mix only, with inverse-frequency
weights, 400 steps, step size 0.05.

## What the historical split did

`tests/test_strict_protocol.py` locks this in. The V5 unique-pulse shuffle
(seed 42) puts all 575 test snippets into buffers that also appear in
training (61/61 buffers). The CR–RC⁸ coefficients in `config/sdd_shape.json`
were fit on the campaign (`fit_n_isolated` 2898), not on a train split.

Per-buffer extraction reproduces the published library count of 2878
isolated Fe-55 pulses. Zero buffer-edge pulses were dropped, and zero
adjacent buffers have pulses closer than 8 µs, so the leak is the shuffle,
not a boundary cut. Live time 3.1981568 s. Fe-55 rate 912.4 Hz. The ~69 Hz
family near 3650 channels is 221 pulses and is not used as a shape.

## Two studies, two denominators

`conditional_two_pulse` places one measured host and, when piled, one
guest excess at a controlled gap. Class counts are balanced in the gap
and ratio cells (160 per class). That F1 is not a rate.

`unconditional_stream` draws 3000 pulses onto one measured baseline taken
from the train buffers. Inter-arrival times are i.i.d. exponential.
`modelling_assumption` is `poisson_exponential_interarrival` on every
stream row. The measured Fe-55 rate is one row. The other rates are set
so that a Poisson process would put the next pulse inside 2.0 µs with
probability 0.02, 0.05, 0.10, 0.20, or 0.35. Those probabilities are
modelling targets. The metric denominator is the empirical trigger count.

The host keeps its measured samples. A second pulse adds
baseline-subtracted excess only. No second pedestal and no extra
Gaussian are added, except the labelled SNR stress test. The footprint
written into a stream is 16 samples before the peak through 24 after, so
snippet-wing noise is not laid on the baseline trace. Ratio 4 saturates
the ADC (160/160 piled events on the primary 0.4 µs cell). Ratio 0.25
does not.

## Historical file, replayed

Frozen weights, pulse-level split, test seed 44, threshold 0.5:

| Item | Value |
|---|---:|
| Events | 1000 |
| Pile-up | 95 (TP 50, FN 45, FP 0) |
| F1 | 0.690 |
| Isolated OT-LS MAE | 21.940 ch (n = 905) |

Manuscript text that says 103 pile-up events does not match this file.
95 does.

The same frozen estimator on every historical test snippet (n = 575),
one trigger-relative placement each: MAE 21.849 ch, SE 0.436, bias
+21.64 ch. The archived operating-region figure 21.144 ch is a draw of
up to 400 events after that script’s RNG had already been used. It is
not a second estimator. The archived empirical 11.205 ch is the same
kind of draw. On all 575 snippets the leaky train-split empirical
template gives 10.56 ch (phase step 0.2, published pedestal) and 10.44 ch
(step 0.1, train pedestal).

## Strict height

Trigger-relative four-tap OT-LS. Blocked test snippets are identical
across init seeds, and the taps do not depend on the absolute start
index, so those three seeds share one MAE. Random buffer splits move it.

| Estimator | Blocked n = 555 | Random splits (n = 553, 548, 520) |
|---|---:|---|
| Published CR–RC⁸, pedestal 7.1, τ = 1.2606 | 21.42 ch (bias +21.33, SE 0.45) | 21.09, 21.28, 22.02 |
| Train-only CR–RC⁸, τ = 1.264, pedestal 7.36 | 19.60 ch (bias +19.45) | 19.99, 19.23, 19.98 |
| Train-only empirical mean | 10.15 ch (bias +6.64, SE 0.35) | 9.45, 9.53, 10.25 |

Eight taps at 200 ns do not remove the bias (blocked refit 18.47 ch,
empirical 9.76 ch). Train baseline σ on the pre-peak wings is 6.54
channels. The published 9.86-channel noise figure was not added again.

The 21.9-channel headline stays within about one channel under the
segment split. The 21.1-channel headline does not name a different
result. The empirical template still cuts the error to about 10
channels; 11.2 is the smaller archived draw.

## Strict detection, prevalence mix

Same 1-in-10 mix as V5, but buffers are disjoint and the threshold is
frozen from validation. Primary blocked-42, n = 1000, 96 pile-up:

| Method | Threshold | Precision | Recall | F1 | ROC-AUC | FP |
|---|---:|---:|---:|---:|---:|---:|
| 4–5–1 | 0.11 (validation) | 1.000 | 0.510 | 0.676 | 0.797 | 0 |
| 4–5–1 | 0.50 (historical) | 1.000 | 0.458 | 0.629 | 0.797 | 0 |
| Retrigger | hard | 0.968 | 0.625 | 0.759 | 0.811 | 2 |
| Template residual | validation quantile | 0.857 | 0.562 | 0.679 | 0.805 | 9 |
| Logistic, 4 taps | 0.51 | 1.000 | 0.448 | 0.619 | 0.784 | 0 |
| Slope / second rise | hard | 1.000 | 0.010 | 0.021 | 0.505 | 0 |
| MLP OR retrigger | MLP at 0.11, or retrigger | 0.980 | 1.000 | 0.990 | — | 2 |

The combined detector is positive when the 4–5–1 probability is at least
that run’s validation threshold or the retrigger hard decision fires.
For `blocked-42` the MLP leg is 0.11. The same pair of cuts is used for
the prevalence mix, every conditional gap and ratio cell, the noise
stress, and every stream rate. Stream thresholds are not reselected per
rate. The `threshold` cell on `mlp_or_retrigger` rows remains 0.5 because
that is the cut on a score that is already 0 or 1. It is not the MLP
probability cut. `mlp_leg_threshold` stores the validation cut (0.11 on
the primary run). Where retrigger recall is zero, OR recall equals the
MLP at its validation threshold and does not equal the MLP at 0.5. On
the primary A2/A1 = 0.25 cell at 0.4 µs those recalls are 0.975 and
0.181.

Wilson 95% CI, primary MLP recall 0.412–0.608, precision 0.927–1.000.
OR recall 0.962–1.000. Six-run MLP F1 values: 0.676, 0.709, 0.658,
0.685, 0.708, 0.662 (mean 0.683). The historical 0.690 sits inside that
range. AUC 0.835 does not.

## Conditional gaps, natural Fe-55 amplitudes

Balanced, 160 per class, primary run. MLP recall is 1.00 from 0.3 µs
through 1.0 µs on all three blocked seeds, 0.61–0.71 at 1.2 µs, and 0
at 1.6–2.0 µs (one seed has recall 0.006 at 2.0 µs). At the historical
threshold 0.5 the 1.2 µs recall is 0.131, close to the V5 value 0.15.
Retrigger is near 0 until the peaks separate and is 1.00 at 1.6 and
2.0 µs. The OR of those two rules is the complementarity statement.
It is not a license to quote F1 = 1 as a rate.

Measured Fe-55 amplitude ratios span roughly 0.80–1.25. Cells outside
that range scale the guest excess, noise included.

Hard cell A2/A1 = 0.25, primary, balanced:

| Δt | MLP @ 0.11 F1 (recall) | MLP @ 0.50 F1 (recall) | OR @ validation rule |
|---:|---|---|---|
| 0.4 µs | 0.987 (0.975) | 0.307 (0.181) | 0.987 |
| 1.0 µs | 0.877 (0.781) | 0.012 (0.006) | 0.877 |
| 1.2 µs | both MLP and retrigger are near zero; OR does not fill the hole | | |
| 1.6 µs | MLP 0 | retrigger carries the OR (F1 0.991, 3 FP) | 0.991 |

V5’s F1 0.28 at 0.4 µs matches the threshold-0.5 column, not the
validation-chosen threshold. The validation threshold detects that
balanced cell and does not create a large false-positive rate on
ordinary isolated pulses in the stream (below). Ratio 4 is clipped and
is not a linear-superposition result.

Added Gaussian on top of measured noise, balanced random gaps, frozen
clean threshold, primary MLP F1: 0.715, 0.735, 0.727, 0.652 at σ = 0,
10, 20, 40 channels.

Eight-tap ablation, 40 epochs, validation threshold 0.09, primary
prevalence F1 0.792 (recall 0.656, precision 1.000). Recall stays 1
through 1.2 µs and is 0 at 1.6 and 2.0 µs. The old N = 32 / 48 F1 = 1
sweep was not repeated.

## Unconditional stream

Label `either_neighbor_within_2us` is the pre-specified coincidence,
matching the conditional study’s upper gap. Retrigger searches about
4 µs past the peak, so a neighbor at 2–4 µs is a true retrigger hit and
a false positive under the 2 µs label. Both denominators are in
`stream.csv`. Recall with fewer than 30 positives is marked unstable.
At the measured 912 Hz rate the 2 µs overlap count is 6. No recall is
claimed there.

Primary MLP, 2 µs label, stable rows (3000 pulses drawn):

| Modelling forward probability | Rate | Triggers | Positives | Prevalence | Recall | Precision | F1 | FP |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.02 | 10.1 kHz | 2951 | 68 | 0.023 | 0.574 | 0.975 | 0.722 | 1 |
| 0.05 | 25.6 kHz | 2882 | 169 | 0.059 | 0.521 | 0.957 | 0.674 | 4 |
| 0.10 | 52.7 kHz | 2758 | 336 | 0.122 | 0.524 | 0.941 | 0.673 | 11 |
| 0.20 | 112 kHz | 2522 | 633 | 0.251 | 0.496 | 0.978 | 0.658 | 7 |
| 0.35 | 215 kHz | 2118 | 887 | 0.419 | 0.526 | 0.967 | 0.682 | 16 |

MLP recall on this stream stays near one half because many overlaps
fall outside the four taps. Precision stays high. The OR is not F1 = 1
on either label. At modelling probability 0.10, OR F1 is 0.627 under
the 2 µs label (precision 0.490, retrigger FPR 0.122) and 0.769 under
the 4 µs label (precision 0.889, retrigger FPR 0.031). Triples inside
2 µs are 25 and 207 matched triggers at the 0.10 and 0.35 rows. They
are counted, not unfolded.

## Limits

Linear superposition. No ballistic deficit, reset, baseline wander, or
analog dead time. The latch holdoff is 1.3 µs of digital logic, not a
measured shaper dead time. Wings outside the footprint are zero.
Poisson arrivals are a model. The shape library is isolated singles, so
the stream reuses those shapes with replacement. This is a controlled
feasibility check of four samples, not a high-count-rate spectrometer.
