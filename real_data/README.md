# Measured SDD + Fe-55 traces

Real silicon-drift-detector (SDD) waveforms for the four-sample
radiation source counting front-end. These traces are **not** the synthetic CR–RC⁸ events in `data/`.

## Acquisition

| Item | Value |
|------|--------|
| Detector | Silicon drift detector (SDD) |
| Source | Fe-55 (Mn Kα / Kβ) |
| ADC | 12-bit, 0…4095 channels |
| Sample rate | 10 MSPS (\(T_s = 100\) ns) |
| Shaping peaking time | 1 µs |
| Samples per segment | 524 288 (\(2^{19}\)) |
| Segments | 61 |
| Live time | 3.198 s |
| File format | One unsigned ADC integer per line, CRLF, ASCII `.txt` |

Acquired by **Arpit Patel**, Senior Engineer, Physical Research
Laboratory (PRL), Ahmedabad. Contact: arpitp@prl.res.in
(mail to H. S. Mazumdar, 21 August 2026).

Operator notes used as-is: count rate is low; full traces show
Gaussian-like pulses; amplitude is around 1000 ADC channels; below
50 channels is noise; baseline noise is present; multiple files
because of acquisition-setup limits. Am-241 pile-up traces were not
included in this drop.

## Files

| Path | Role |
|------|------|
| `metadata.json` | Machine-readable acquisition record |
| `manifest.csv` | Segment index, new name, original lab name, sample count |
| `sdd_fe55/sdd_fe55_12bit_10msps_seg001.txt` … `seg061.txt` | Time-ordered ADC streams |

Original lab names (`1.xls`, `2`…`9`, `a`…`z`, `aa`…`zz`) had no
extension, or a misleading `.xls`. The mapping is in `manifest.csv`.
The local folder `SDD data 10us` is the un-renamed lab drop; do not
treat that folder name as a peaking time. The operator’s peaking
time is **1 µs**.

## Reviewer viewer

```bash
python real_data_viewer.py
```

Step **Up** / **Dn** through pulses, **Scan** / **Pause**, filter
Fe-55 vs periodic high pulses, and overlay four post-trigger taps.

## Honest use

- Isolated-pulse shape, noise floor, and physical units (\(f_s = 10\) MHz).
- Fe-55 Kα ≈ 1197 ch, Kβ ≈ 1317 ch on this gain.
- A periodic ~69 Hz family near 3650 channels is **not** a photopeak;
  hide it with the viewer’s “Fe-55 window” filter.
- Pile-up events are scarce (low source rate). Do not quote a pile-up
  F1 from this set.
