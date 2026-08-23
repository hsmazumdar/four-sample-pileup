# Generated synthetic events

Produced by `python synthesize_data.py` (engine: `sparse_pileup/pulse_sim.py`).

The pulse shape is a **CR–RC⁸** kernel fitted to isolated Fe-55 SDD
traces (`config/sdd_shape.json`). Pile-up is still **software-injected**.
This folder is not a real-detector dump.

| File | Rows | Contents |
|------|------|----------|
| `synth_train.csv` | 4000 | 4 samples + labels, seed 42 |
| `synth_val.csv` | 1000 | seed 43 |
| `synth_test.csv` | 1000 | seed 44 (held-out) |
| `example_isolated.csv` | 160 samples | one full waveform |
| `example_pileup.csv` | 160 samples | one full piled waveform |

Columns in `synth_*.csv`:

`split, is_pileup, A1_ch, A2_ch, t_start, gap, trig, s0, s1, s2, s3`

- `A1_ch` / `A2_ch` — first / second pulse peak in 4096-channel units
- `t_start` — first-pulse **peak** sample
- `gap` — peak-to-peak samples (0 if isolated)
- `s0…s3` — FPGA inputs, quantized to 1/4096, at `trig + k*4`
- `is_pileup` — 1 if a second CR–RC⁸ kernel was added

Re-generate:

```bash
python synthesize_data.py --seed 42
```
