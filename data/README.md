# Generated synthetic events

Produced by `python synthesize_data.py` (engine: `sparse_pileup/pulse_sim.py`).

| File | Rows | Contents |
|------|------|----------|
| `synth_train.csv` | 4000 | 4 samples + labels, seed 42 |
| `synth_val.csv` | 1000 | seed 43 |
| `synth_test.csv` | 1000 | seed 44 (held-out) |
| `example_isolated.csv` | 500 samples | one full waveform |
| `example_pileup.csv` | 500 samples | one full piled waveform |

Columns in `synth_*.csv`:

`split, is_pileup, A1_ch, A2_ch, t_start, gap, trig, s0, s1, s2, s3`

- `A1_ch` / `A2_ch` — amplitudes in 4096-channel units (`A2_ch` empty if isolated)
- `s0…s3` — FPGA inputs, quantized to 1/4096, at `trig + k*15`
- `is_pileup` — 1 if a second rectangle was injected before shaping

Re-generate:

```bash
python synthesize_data.py --seed 42
```
