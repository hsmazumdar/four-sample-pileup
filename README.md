# Four-sample MLP for radiation pulse pile-up and peak height

Repository: https://github.com/hsmazumdar/four-sample-pileup

Lab proof of concept for a **resource-constrained radiation source counter
front-end**. After a leading-edge trigger, **four** uniformly spaced ADC
samples are latched. Two tiny MLPs run on those four numbers:

| Head | Size | Output | Role |
|------|------|--------|------|
| Pile-up | 4-5-1 (31 weights) | flag in (0,1), threshold 0.5 | veto / tag the event |
| Peak | 4-5-1 (31 weights) | first-pulse height A1, 0..1 FS | MCA channel |

This repository is meant for **code review and reproduction**, not as a
finished IEEE TNS / NIM A paper. Training is offline. FPGA/HLS only needs
`SmallMLP.forward` + the four sample registers.

```
                 sample_reg[0..3]          ← 4 ADC taps, stride 15
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
   MLP_pileup  4-5-1           MLP_peak  4-5-1
          │                           ▼
     pileup_flag                 peak_height (A1)
```

## Reproduce (reviewer)

```bash
python -m pip install -r requirements.txt
python tests/test_sanity.py
python synthesize_data.py          # data synthesizer → data/*.csv
python run_poc.py                  # train both heads, refresh RESULTS.md
python -m sparse_pileup.report     # rebuild tables from frozen weights
```

Tabulated numbers: **[RESULTS.md](RESULTS.md)**  
Machine-readable: `artifacts/pileup_confusion.csv`, `artifacts/peak_metrics.csv`

## Data synthesizer

There is **no real detector dump** in this PoC. Events are generated in
software so a reviewer can rebuild the exact train/val/test files.

| File | What it is |
|------|------------|
| `sparse_pileup/pulse_sim.py` | Pulse engine: rectangle → 3× discrete RC, MCA Gaussian heights |
| `sparse_pileup/synthesize.py` | CLI that writes CSVs |
| `synthesize_data.py` | Root entry point (`python synthesize_data.py`) |
| `config/mca_lines.csv` | Four photopeak lines (from `PileupNNBPTrainer/configMca.csv`) |
| `data/synth_*.csv` | Labelled events: `is_pileup`, `A1_ch`, `A2_ch`, four samples `s0…s3` |
| `data/example_isolated.csv` | Full 500-sample waveform, isolated pulse |
| `data/example_pileup.csv` | Full 500-sample waveform, pile-up |

Pulse model (testbench, not HPGe/NaI physics): width-15 rectangle, three
passes of `Array2ShapeDbl` (α = 0.01, 10 inner steps, ×1.1), trigger at
channel 100/4096, taps at +0 / +15 / +30 / +45. Pile-up probability 1/10,
gap 2–9 samples. **Both** amplitudes are drawn from the MCA Gaussian tables
(the WinForms trainer used Uniform(0.1, 1) for the second pulse).

```bash
python synthesize_data.py --n-train 4000 --n-val 1000 --n-test 1000 --seed 42
```

Seeds 42 / 43 / 44 are independent streams for train / val / test.

## Held-out results (seed 42, 40 epochs)

Full tables and the confusion matrix are in [RESULTS.md](RESULTS.md). Summary:

### Pile-up

| Metric | Value |
|--------|------:|
| Test events | 1000 (122 pile-up) |
| Accuracy | 0.969 |
| Precision | 1.000 |
| Recall | 0.746 |
| F1 | 0.854 |
| Confusion | TN 878, FP 0, FN 31, TP 91 |

### Peak vs true A1 (4096-channel units)

| Subset | n | MAE (ch) | RMSE (ch) |
|--------|--:|---------:|----------:|
| Isolated pulses | 878 | 93.7 | 95.6 |
| All events | 1000 | 143.5 | 391.8 |

Peak-vs-A1 is harder than the C# GUI figure (~0.89 ch), which was
**same-set**, **shaped max(waveform)**, isolated pulses only.

## What matches the WinForms C# trainer

| | C# `PileupNNBPTrainer` | this PoC |
|--|--|--|
| Pulse | width-15 rectangle, 3× RC | same |
| Samples | trigger ch 100, stride 15 | same |
| Network | one 4-5-2, Peak **or** Pileup | **two** 4-5-1, **both** every event |
| Peak label | `max(waveform)`, isolated only | true **A1**, all events |
| 2nd piled pulse | `Uniform(0.1, 1)` | same MCA lines as pulse 1 |
| Train/test | same array | independent seeds |
| Pile-up metric | mean \|yk − target\| | accuracy / precision / recall / F1 |

The original idea was “3–4 samples, or 3–6 if pile-up”. The trainer and this
PoC keep **four** (fixed FPGA input width). Sweeping 4 / 8 / 16 / 32 is a
**paper** figure, not required to review this repo.

## FPGA port (what to synthesise)

**Do synthesise:** trigger vs channel 100; four sample registers; two 4-5-1
forwards in `sparse_pileup/mlp.py` (`SmallMLP.forward`); sigmoid clip ±10 then
LUT; pile-up bit = `p >= 0.5`; peak word = `height * 4096`.

**Do not synthesise:** `pulse_sim.py`, `train_step`, matplotlib.

**Do not publish invented DSP/LUT/ns.** Count them from a synthesis of
`weights/dual_head_weights.h`. Fully parallel MACs: 31 per head, 62 both.

## Repository map

```
synthesize_data.py         data synthesizer (reviewer entry)
run_poc.py                 train + RESULTS.md
RESULTS.md                 tabulated pile-up + peak
sparse_pileup/pulse_sim.py    synthesizer engine (not RTL)
sparse_pileup/sampler.py      trigger + 4 taps (RTL)
sparse_pileup/mlp.py          4-5-1 MAC + sigmoid (RTL = forward)
sparse_pileup/dual_head.py    both heads (RTL = infer)
config/mca_lines.csv       MCA Gaussian lines
data/                      generated labelled CSVs
weights/                   frozen JSON + C header
artifacts/                 confusion matrix, histograms, plot
PileupNNBPTrainer/         WinForms trainer GUI (reference)
MCA4096/                   4096-channel spectrum GUI
```

## Claim this repo is allowed to make

A 62-parameter dual-head MLP can tag pile-up and estimate A1 from four
post-trigger samples on **synthetic** RC-smoothed rectangles, with a
held-out split. It is **not** a novel “neural pile-up detector”, **not**
measured FPGA latency, and **not** HPGe/NaI physics.

Journal experiments still missing (do these before TNS/NIM A, not before
pushing this PoC): F1 vs sample count, Pd vs Δt, A2/A1 map, SNR +
conventional baselines.

## License

MIT. See [LICENSE](LICENSE).
