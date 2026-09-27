"""Data synthesizer — the public generator a reviewer should run.

    python synthesize_data.py
    python synthesize_data.py --n-train 4000 --n-val 1000 --n-test 1000

Output (default ``data/``):
    synth_train.csv / synth_val.csv / synth_test.csv
        split, is_pileup, A1_ch, A2_ch, t_start, gap, trig, s0, s1, s2, s3
    example_isolated.csv / example_pileup.csv
        full shaped waveforms (WAVEFORM_LEN samples)

Physics (default engine=real):
    Isolated events are measured Fe-55 snippets. Pile-up is a linear
    sum of two isolated snippets at a controlled peak-to-peak delay —
    constructed, not a Poisson high-rate recording.
    engine=kernel keeps the V3 CR–RC^8 formula injector.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from sparse_pileup.constants import (
    DEFAULT_ENGINE,
    DEFAULT_LINES_CSV,
    DEFAULT_SEED,
    N_TEST,
    N_TRAIN,
    N_VAL,
    SAMPLE_STRIDE,
    WAVEFORM_LEN,
)
from sparse_pileup.dataset import make_split, write_events_csv


def _write_waveform_csv(path: Path, waveform: np.ndarray, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# {title}\n")
        f.write("sample_index,amplitude_fs,time_us\n")
        for i, v in enumerate(waveform):
            f.write(f"{i},{float(v):.8f},{i * 0.1:.1f}\n")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description="Synthesize labelled 4-sample events (real-pulse superposition by default)."
    )
    p.add_argument("--config", type=Path, default=ROOT / DEFAULT_LINES_CSV)
    p.add_argument("--out", type=Path, default=ROOT / "data")
    p.add_argument("--n-train", type=int, default=N_TRAIN)
    p.add_argument("--n-val", type=int, default=N_VAL)
    p.add_argument("--n-test", type=int, default=N_TEST)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument(
        "--engine",
        choices=("real", "kernel"),
        default=DEFAULT_ENGINE,
        help="real = measured singles + constructed pile-up; kernel = V3 CR–RC⁸",
    )
    args = p.parse_args(argv)

    split = make_split(
        args.config,
        n_train=args.n_train,
        n_val=args.n_val,
        n_test=args.n_test,
        seed=args.seed,
        engine=args.engine,
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
        f"isolated A1={iso.amplitude_first:.4f} trig={int(iso.frame.indices[0])} "
        f"stride={SAMPLE_STRIDE} engine={args.engine}",
    )
    _write_waveform_csv(
        args.out / "example_pileup.csv",
        piled.waveform,
        f"pile-up A1={piled.amplitude_first:.4f} A2={piled.amplitude_second:.4f} "
        f"gap={piled.gap} trig={int(piled.frame.indices[0])}",
    )

    n_pu = sum(r.is_pileup for r in split.train)
    print(f"Data synthesizer (engine={args.engine}, 10 MSPS)")
    print(f"  seed={args.seed}  waveform_len={WAVEFORM_LEN}  stride={SAMPLE_STRIDE}")
    print(f"  isolated = measured Fe-55; pile-up = constructed sum" if args.engine == "real"
          else f"  lines={args.config}")
    print(f"  train={len(split.train)} (pile-up {n_pu})  "
          f"val={len(split.val)}  test={len(split.test)}")
    print(f"  wrote {args.out / 'synth_train.csv'}")
    print(f"  wrote {args.out / 'synth_val.csv'}")
    print(f"  wrote {args.out / 'synth_test.csv'}")
    print(f"  wrote {args.out / 'example_isolated.csv'}")
    print(f"  wrote {args.out / 'example_pileup.csv'}")


if __name__ == "__main__":
    main()
