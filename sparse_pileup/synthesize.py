"""Data synthesizer — the public generator a reviewer should run.

This module *is* the synthetic radiation source counter dataset. It does not read
real digitizer files. It writes labelled events so training is reproducible
without the 2016 WinForms GUI.

    python synthesize_data.py
    python synthesize_data.py --n-train 4000 --n-val 1000 --n-test 1000

Output (default ``data/``):
    synth_train.csv / synth_val.csv / synth_test.csv
        split, is_pileup, A1_ch, A2_ch, t_start, gap, trig, s0, s1, s2, s3
    example_isolated.csv / example_pileup.csv
        full 500-sample shaped waveforms for two typical events

Physics (testbench, not HPGe/NaI):
    rectangle width 15 → three discrete RC passes (α=0.01, ×1.1) → trigger
    at channel 100/4096 → four taps at +0, +15, +30, +45. Amplitudes are
    drawn from config/mca_lines.csv Gaussian photopeak tables. Pile-up is
    Bernoulli 1/10 with a 2–9 sample gap. Both pulses use the same MCA lines.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from sparse_pileup.constants import DEFAULT_SEED, N_TEST, N_TRAIN, N_VAL, WAVEFORM_LEN
from sparse_pileup.dataset import make_split, write_events_csv


def _write_waveform_csv(path: Path, waveform: np.ndarray, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# {title}\n")
        f.write("sample_index,amplitude_fs\n")
        for i, v in enumerate(waveform):
            f.write(f"{i},{float(v):.8f}\n")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description="Synthesize labelled 4-sample radiation source counter events."
    )
    p.add_argument("--config", type=Path, default=ROOT / "config" / "mca_lines.csv")
    p.add_argument("--out", type=Path, default=ROOT / "data")
    p.add_argument("--n-train", type=int, default=N_TRAIN)
    p.add_argument("--n-val", type=int, default=N_VAL)
    p.add_argument("--n-test", type=int, default=N_TEST)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = p.parse_args(argv)

    split = make_split(
        args.config,
        n_train=args.n_train,
        n_val=args.n_val,
        n_test=args.n_test,
        seed=args.seed,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    write_events_csv(args.out / "synth_train.csv", split.train, "train")
    write_events_csv(args.out / "synth_val.csv", split.val, "val")
    write_events_csv(args.out / "synth_test.csv", split.test, "test")

    iso = next(r for r in split.test if not r.is_pileup)
    piled = next(r for r in split.test if r.is_pileup)
    _write_waveform_csv(
        args.out / "example_isolated.csv",
        iso.waveform,
        f"isolated A1={iso.amplitude_first:.4f} trig={int(iso.frame.indices[0])}",
    )
    _write_waveform_csv(
        args.out / "example_pileup.csv",
        piled.waveform,
        f"pile-up A1={piled.amplitude_first:.4f} A2={piled.amplitude_second:.4f} "
        f"gap={piled.gap} trig={int(piled.frame.indices[0])}",
    )

    n_pu = sum(r.is_pileup for r in split.train)
    print("Data synthesizer")
    print(f"  seed={args.seed}  waveform_len={WAVEFORM_LEN}")
    print(f"  train={len(split.train)} (pile-up {n_pu})  "
          f"val={len(split.val)}  test={len(split.test)}")
    print(f"  wrote {args.out / 'synth_train.csv'}")
    print(f"  wrote {args.out / 'synth_val.csv'}")
    print(f"  wrote {args.out / 'synth_test.csv'}")
    print(f"  wrote {args.out / 'example_isolated.csv'}")
    print(f"  wrote {args.out / 'example_pileup.csv'}")


if __name__ == "__main__":
    main()
