# Generated events (V4 default: real-pulse superposition)

Produced by `python synthesize_data.py` (default `--engine real`).

**Isolated events** are measured Fe-55 SDD snippets.
**Pile-up events** are a linear sum of two isolated measured pulses at a
controlled peak-to-peak delay. They are **constructed**, not a measured
high-rate recording. Unique pulses are split 60/20/20 so a test snippet
never appears in training.

`--engine kernel` rebuilds the V3 CR–RC⁸ formula table.

| File | Rows | Contents |
|------|------|----------|
| `synth_train.csv` | 4000 | 4 samples + labels, seed 42 |
| `synth_val.csv` | 1000 | seed 43 |
| `synth_test.csv` | 1000 | seed 44 (held-out) |
| `example_isolated.csv` | 160 samples | one full waveform |
| `example_pileup.csv` | 160 samples | one constructed pile-up |

Columns in `synth_*.csv`:

`split, is_pileup, A1_ch, A2_ch, t_start, gap, trig, s0, s1, s2, s3`

- `A1_ch` / `A2_ch` — conventional peak-minus-baseline of each snippet
- `t_start` — first-pulse **peak** sample on the 160-sample canvas
- `gap` — peak-to-peak samples (0 if isolated)
- `s0…s3` — FPGA inputs, quantized to 1/4096, at `trig + k*4`
- `is_pileup` — 1 if a second measured snippet was added

Snippet library: `real_data/isolated_fe55_snippets.npz`

```bash
python -m sparse_pileup.real_pulse_lib
python synthesize_data.py --seed 42
python synthesize_data.py --engine kernel   # V3 baseline
```
