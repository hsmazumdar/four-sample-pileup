"""Train both heads, evaluate on a held-out set, export FPGA-facing weights.

    python run_poc.py

Python runs the two nets back-to-back. The *arithmetic* is what the FPGA
will do in parallel after the four sample registers are filled.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

# Allow `python run_poc.py` from the repo root without installing the package.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sparse_pileup.constants import (  # noqa: E402
    ADC_CHANNELS,
    DEFAULT_EPOCHS,
    DEFAULT_LINES_CSV,
    DEFAULT_SEED,
    N_HIDDEN,
    N_SAMPLES,
    SAMPLE_STRIDE,
    WAVEFORM_LEN,
)
from sparse_pileup.dataset import make_split  # noqa: E402
from sparse_pileup.dual_head import DualHeadDetector  # noqa: E402
from sparse_pileup.export_fpga import save_c_header  # noqa: E402
from sparse_pileup.metrics import format_report, peak_metrics, pileup_metrics  # noqa: E402


def train(model: DualHeadDetector, rows, epochs: int, rng: np.random.Generator) -> None:
    order = np.arange(len(rows))
    for ep in range(1, epochs + 1):
        rng.shuffle(order)
        acc_p = 0.0
        for i in order:
            row = rows[i]
            e_p, _ = model.train_event(row.samples, row.is_pileup, row.amplitude_first)
            acc_p += e_p
        n = len(rows)
        if ep == 1 or ep % 5 == 0 or ep == epochs:
            print(
                f"  epoch {ep:3d}/{epochs}   "
                f"pileup L1={acc_p/n:.4f}   (height is OT-LS, not trained)"
            )


def maybe_plot(split, model: DualHeadDetector, out: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    # One isolated and one piled event from the test set.
    iso = next(r for r in split.test if not r.is_pileup)
    piled = next(r for r in split.test if r.is_pileup)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, row, title in (
        (axes[0], iso, "isolated"),
        (axes[1], piled, "pile-up"),
    ):
        ax.plot(row.waveform, color="0.2", lw=1.2, label="shaped pulse")
        ax.axhline(100 / 4096, color="0.6", ls="--", lw=0.8, label="trigger ch 100")
        xs = row.frame.indices
        ys = row.samples
        ax.scatter(xs, ys, c="C3", s=36, zorder=3, label="4 FPGA samples")
        pred = model.infer(row.samples)
        ax.set_title(
            f"{title}  true A1={row.amplitude_first*4096:.0f} ch\n"
            f"net: pileup={pred.pileup_prob:.2f}  peak={pred.peak_channel:.0f} ch"
        )
        ax.set_xlabel("sample index (10 MSPS)")
        ax.set_xlim(0, WAVEFORM_LEN)
    axes[0].set_ylabel("amplitude (full scale)")
    axes[0].legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def main() -> None:
    artifacts = ROOT / "artifacts"
    weights = ROOT / "weights"
    artifacts.mkdir(exist_ok=True)
    weights.mkdir(exist_ok=True)

    print("Four-sample pile-up MLP + OT-LS peak PoC")
    print("  engine=real (measured singles + constructed pile-up), stride", SAMPLE_STRIDE)
    print("  4 post-trigger samples -> 4-5-1 pile-up veto + LS height")
    print(f"  pile-up inputs={N_SAMPLES}  hidden={N_HIDDEN}  (31 weights)")
    print()

    csv_path = ROOT / DEFAULT_LINES_CSV
    print("Generating train/val/test (independent seeds)...")
    split = make_split(csv_path)
    n_pu = sum(r.is_pileup for r in split.train)
    print(
        f"  train={len(split.train)} (pile-up {n_pu})  "
        f"val={len(split.val)}  test={len(split.test)}"
    )

    rng = np.random.default_rng(DEFAULT_SEED + 99)
    model = DualHeadDetector.random(rng=rng)
    print(f"\nTraining pile-up head for {DEFAULT_EPOCHS} epochs (OT-LS height is frozen)...")
    train(model, split.train, DEFAULT_EPOCHS, rng)

    print("\nHeld-out test:")
    pile = pileup_metrics(model, split.test)
    peak_a1 = peak_metrics(model, split.test)
    peak_iso = peak_metrics(model, split.test, isolated_only=True)
    report = format_report(pile, peak_a1, peak_iso)
    print(report)

    json_path = weights / "dual_head.json"
    hdr_path = weights / "dual_head_weights.h"
    model.save_json(json_path)
    save_c_header(model, hdr_path)
    (artifacts / "test_report.txt").write_text(report + "\n", encoding="utf-8")
    from sparse_pileup.report import write_tables

    write_tables(model, split.test, artifacts, ROOT / "RESULTS.md")
    print(f"\nWrote {json_path.relative_to(ROOT)}")
    print(f"Wrote {hdr_path.relative_to(ROOT)}  (HLS/C paste-in)")

    fig_path = artifacts / "sparse_samples.png"
    maybe_plot(split, model, fig_path)
    if fig_path.exists():
        print(f"Wrote {fig_path.relative_to(ROOT)}")

    # One raw inference so a reader sees the FPGA I/O contract.
    demo = split.test[0]
    r = model.infer(demo.samples)
    print("\nExample FPGA I/O")
    print(f"  in : samples = {np.round(demo.samples, 4).tolist()}")
    print(f"  out: pileup_flag = {int(r.is_pileup)}  (p={r.pileup_prob:.3f})")
    print(f"       peak_ch     = {r.peak_channel:.1f}   "
          f"(true A1 = {demo.amplitude_first * ADC_CHANNELS:.1f})")


if __name__ == "__main__":
    main()
