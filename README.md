# Four-sample pile-up MLP and OT-LS peak height

Repository: https://github.com/hsmazumdar/four-sample-pileup

Lab proof of concept for a **resource-constrained radiation source counting
front-end**. After a leading-edge trigger, **four** uniformly spaced ADC
samples are latched. A tiny MLP tags pile-up; height is a frozen-shape
least-squares fit on the same four numbers:

| Head | Size | Output | Role |
|------|------|--------|------|
| Pile-up | 4-5-1 (31 weights) | flag in (0,1), threshold 0.5 | veto / tag the event |
| Peak | OT-LS (frozen CR–RC⁸) | first-pulse height A1, 0..1 FS | MCA channel |

This repository is meant for **code review and reproduction**, not as a
finished IEEE TNS / NIM A paper. Pile-up training is offline. FPGA/HLS
needs `SmallMLP.forward`, the OT-LS Φ table in `ls_peak.py`, and the
four sample registers.

```
                 sample_reg[0..3]          ← 4 ADC taps, stride 4 (400 ns @ 10 MSPS)
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
   MLP_pileup  4-5-1              OT-LS height
          │                           ▼
     pileup_flag                 peak_height (A1)
```

## Reproduce (reviewer)

```bash
python -m pip install -r requirements.txt
python tests/test_sanity.py
python synthesize_data.py          # data synthesizer → data/*.csv
python run_poc.py                  # train pile-up head, refresh RESULTS.md
python -m sparse_pileup.ls_peak    # OT-LS smoke on data/synth_test.csv
python -m sparse_pileup.report     # rebuild tables from frozen weights
python real_data_viewer.py         # step / scan measured SDD + Fe-55 pulses
real_data_viewer.bat               # Windows double-click launcher
```

Tabulated numbers: **[RESULTS.md](RESULTS.md)**  
Machine-readable: `artifacts/pileup_confusion.csv`, `artifacts/peak_metrics.csv`

## Measured SDD + Fe-55 data

`real_data/sdd_fe55/` holds 61 time-ordered ASCII traces from a silicon
drift detector and an Fe-55 source (12-bit ADC, 10 MSPS, 1 µs peaking).
See [real_data/README.md](real_data/README.md). Open the reviewer GUI:

```bash
python real_data_viewer.py
```

Windows: double-click `real_data_viewer.bat` (installs `requirements.txt` if needed).

The held-out tables in RESULTS.md are **synthetic** but **shape-calibrated**
to these traces (CR–RC⁸, 1.01 µs peaking). Pile-up in the tables is still
injected in software. Real pile-up is scarce in the SDD drop.

## Data synthesizer

Synthetic events are generated in software so a reviewer can rebuild
the exact train/val/test files. The kernel is a **CR–RC⁸** fit to
2 898 isolated Fe-55 pulses (`config/sdd_shape.json`).

| File | What it is |
|------|------------|
| `sparse_pileup/pulse_sim.py` | Pulse engine: fitted CR–RC⁸ + measured noise |
| `sparse_pileup/synthesize.py` | CLI that writes CSVs |
| `synthesize_data.py` | Root entry point (`python synthesize_data.py`) |
| `config/sdd_shape.json` | Frozen n, τ, peaking time, noise |
| `config/sdd_fe55_lines.csv` | Si escape / Mn Kα / Mn Kβ tables |
| `config/mca_lines.csv` | 2016 trainer lines (reference only) |
| `data/synth_*.csv` | Labelled events: `is_pileup`, `A1_ch`, `A2_ch`, four samples `s0…s3` |
| `data/example_isolated.csv` | Full 160-sample waveform, isolated pulse |
| `data/example_pileup.csv` | Full 160-sample waveform, pile-up |

Pulse model: CR–RC⁸ (τ = 1.2606 samples, T_peak = 1.01 µs) at 10 MSPS,
pedestal 7.1 ch, Gaussian noise σ = 9.86 ch, trigger at channel 100/4096,
taps at +0 / +4 / +8 / +12. Pile-up probability 1/10, peak-to-peak gap
3–20 samples (0.3–2.0 µs). Amplitudes from the Fe-55 line table. This is
**not** measured pile-up.

```bash
python synthesize_data.py --n-train 4000 --n-val 1000 --n-test 1000 --seed 42
```

Seeds 42 / 43 / 44 are independent streams for train / val / test.

## Held-out results (seed 42; pile-up 40 epochs, height OT-LS)

Full tables and the confusion matrix are in [RESULTS.md](RESULTS.md). Summary:

### Pile-up

| Metric | Value |
|--------|------:|
| Test events | 1000 (103 pile-up) |
| Accuracy | 0.949 |
| Precision | 1.000 |
| Recall | 0.505 |
| F1 | 0.671 |
| Confusion | TN 897, FP 0, FN 51, TP 52 |

F1 is lower than the old cartoon-RC run (0.854). That is expected: the
fitted 1 µs pulse is short, so four taps miss more of the second event.
Precision stayed 1.000 (no false positives).

### Peak vs true A1 (4096-channel units)

| Subset | n | MAE (ch) | RMSE (ch) |
|--------|--:|---------:|----------:|
| Isolated pulses | 897 | 6.1 | 7.7 |
| All events | 1000 | 32.5 | 140.1 |

Isolated MAE is OT-LS on the frozen CR–RC⁸ kernel. Quote the isolated
row for height. The all-event row is OT-LS without the veto (not
unfolding). The retired peak 4–5–1 scored 34.9 ch on the same isolated
file. This is still not the C# GUI figure (~0.89 ch), which was
same-set against shaped max(waveform).

## What matches the WinForms C# trainer

| | C# `PileupNNBPTrainer` | this PoC |
|--|--|--|
| Pulse | width-15 rectangle, 3× RC | **CR–RC⁸ fitted to SDD Fe-55** |
| Time base | samples only | **10 MSPS**, peaking 1.01 µs |
| Samples | trigger ch 100, stride 15 | trigger ch 100, **stride 4** |
| Network | one 4-5-2, Peak **or** Pileup | **4-5-1 pile-up** + **OT-LS height** |
| Peak label | `max(waveform)`, isolated only | true **A1** (LS on four taps) |
| 2nd piled pulse | `Uniform(0.1, 1)` | same Fe-55 lines as pulse 1 |
| Train/test | same array | independent seeds |
| Pile-up metric | mean \|yk − target\| | accuracy / precision / recall / F1 |

The original idea was “3–4 samples, or 3–6 if pile-up”. The trainer and this
PoC keep **four** (fixed FPGA input width). Sweeping 4 / 8 / 16 / 32 is a
**paper** figure, not required to review this repo.

## FPGA port (what to synthesise)

**Do synthesise:** trigger vs channel 100; four sample registers;
`SmallMLP.forward` for the pile-up veto; the OT-LS Φ table + A search
in `sparse_pileup/ls_peak.py`; pile-up bit = `p >= 0.5`; peak word =
`height * 4096`.

**Do not synthesise:** `pulse_sim.py`, `train_step`, matplotlib.

**Do not publish invented DSP/LUT/ns.** Count them from a synthesis of
`weights/dual_head_weights.h`. Arithmetic budget: 31 pile-up MACs plus
about 120 phases on a 0.1-sample δ grid. Do not quote a measured latency.

## Repository map

```
synthesize_data.py         data synthesizer (reviewer entry)
run_poc.py                 train + RESULTS.md
RESULTS.md                 tabulated pile-up + peak
sparse_pileup/pulse_sim.py    synthesizer engine (not RTL)
sparse_pileup/sampler.py      trigger + 4 taps (RTL)
sparse_pileup/mlp.py          4-5-1 pile-up MAC + sigmoid (RTL = forward)
sparse_pileup/ls_peak.py      OT-LS height (RTL = estimate)
sparse_pileup/dual_head.py    infer = pile-up MLP + OT-LS
config/sdd_shape.json      fitted CR–RC⁸ + noise
config/sdd_fe55_lines.csv  Fe-55 amplitude table
config/mca_lines.csv       2016 trainer lines (reference)
data/                      generated labelled CSVs
real_data/                 measured SDD + Fe-55 traces + manifest
real_data_viewer.py        reviewer GUI (Up / Dn / Scan / Pause)
real_data_viewer.bat       Windows double-click launcher
weights/                   frozen JSON + C header
artifacts/                 confusion matrix, histograms, plot
PileupNNBPTrainer/         WinForms trainer GUI (reference)
MCA4096/                   4096-channel spectrum GUI
```

## Claim this repo is allowed to make

A 31-parameter pile-up MLP plus a frozen CR–RC⁸ four-tap least-squares
height can tag pile-up and estimate isolated A1 from four post-trigger
samples on **synthetic CR–RC⁸ pulses fitted to measured SDD + Fe-55
traces**, with a held-out split. It is **not** a measured pile-up F1,
**not** a novel “neural pile-up detector”, **not** piled-up energy
recovery, **not** measured FPGA latency, and **not** HPGe/NaI physics.

Journal experiments still missing (do these before TNS/NIM A, not before
pushing this PoC): F1 vs sample count, Pd vs Δt, A2/A1 map, SNR +
conventional baselines.

## License

MIT. See [LICENSE](LICENSE).
