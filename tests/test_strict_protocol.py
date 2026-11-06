"""Leakage, threshold, and superposition checks. No full campaign."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sparse_pileup.constants import REAL_SNIPPET_PRE, WAVEFORM_LEN  # noqa: E402
from sparse_pileup.segment_protocol import (  # noqa: E402
    FOOTPRINT_POST,
    FOOTPRINT_PRE,
    Snippet,
    _apply_footprint,
    compose_conditional,
    historical_pulse_leakage,
    rate_grid,
    select_threshold,
    split_segment_ids,
)


def _snip(baseline: float, peak: float, segment: int = 1) -> Snippet:
    adc = np.full(WAVEFORM_LEN, baseline, dtype=np.float64)
    adc[REAL_SNIPPET_PRE - 2 : REAL_SNIPPET_PRE + 3] = np.linspace(baseline, peak, 5)
    adc[REAL_SNIPPET_PRE] = peak
    return Snippet(
        segment_index=segment,
        local_peak=1000,
        adc=adc.astype(np.int16),
        baseline_ch=baseline,
        amplitude_ch=peak - baseline,
    )


class SplitTests(unittest.TestCase):
    def test_blocked_and_random_are_disjoint_covers(self) -> None:
        for mode, seed in (("blocked", 42), ("random", 42), ("random", 44)):
            tr, va, te = split_segment_ids(mode, seed)
            self.assertEqual(len(tr) + len(va) + len(te), 61)
            self.assertFalse(set(tr) & set(va))
            self.assertFalse(set(tr) & set(te))
            self.assertFalse(set(va) & set(te))
        tr, va, te = split_segment_ids("blocked", 99)
        self.assertEqual(tr[0], 1)
        self.assertEqual(te[-1], 61)
        self.assertEqual(split_segment_ids("blocked", 1), split_segment_ids("blocked", 99))

    def test_historical_pulse_split_shares_every_test_segment(self) -> None:
        report = historical_pulse_leakage(ROOT, 42)
        self.assertEqual(report["n_test"], 575)
        self.assertEqual(report["n_test_snippets_whose_segment_is_in_train"], 575)
        self.assertEqual(report["n_test_segments_also_in_train"], 61)


class SynthesisTests(unittest.TestCase):
    def test_guest_excess_does_not_add_a_second_baseline(self) -> None:
        host = _snip(10, 1000)
        guest = _snip(10, 800)
        gap = 30
        wave, n_high, n_low = compose_conditional(host, t1=40, guest=guest, gap=gap, guest_scale=1.0)
        self.assertEqual(n_high, 0)
        self.assertEqual(n_low, 0)
        counts = wave * 4096
        guest_peak = 40 + gap
        # Host baseline plus guest excess. A second copy of the guest baseline
        # would land near 810.
        self.assertAlmostEqual(float(counts[guest_peak]), 10 + (800 - 10), delta=1.5)
        self.assertLess(float(counts[guest_peak]), 809)

    def test_no_extra_noise_on_default_path(self) -> None:
        host = _snip(7, 1200)
        wave, _high, _low = compose_conditional(host, t1=32)
        counts = wave * 4096
        self.assertAlmostEqual(float(counts[10]), 7, delta=1.0)

    def test_stream_footprint_keeps_one_baseline(self) -> None:
        sn = _snip(7, 1500)
        canvas = np.full(400, 7.0)
        occupied = np.zeros(400, dtype=bool)
        origin = 0
        peak_abs = 200
        _apply_footprint(canvas, occupied, origin, peak_abs, sn)
        di_peak = peak_abs
        self.assertAlmostEqual(float(canvas[di_peak]), 1500, delta=1.5)
        # Outside the footprint the pool is untouched (still 7, not 14).
        self.assertAlmostEqual(float(canvas[10]), 7.0, delta=1e-6)
        self.assertAlmostEqual(float(canvas[350]), 7.0, delta=1e-6)
        si0 = REAL_SNIPPET_PRE - FOOTPRINT_PRE
        di0 = peak_abs - REAL_SNIPPET_PRE + si0
        self.assertAlmostEqual(float(canvas[di0]), float(sn.adc[si0]), delta=1e-6)
        self.assertGreater(FOOTPRINT_POST, 0)

    def test_second_pulse_adds_excess_only(self) -> None:
        a = _snip(7, 1000)
        b = _snip(7, 900)
        # Widen the peaks so the footprints actually overlap on a large sample.
        a.adc[REAL_SNIPPET_PRE : REAL_SNIPPET_PRE + 8] = 1000
        b.adc[REAL_SNIPPET_PRE : REAL_SNIPPET_PRE + 8] = 900
        canvas = np.full(400, 7.0)
        occupied = np.zeros(400, dtype=bool)
        _apply_footprint(canvas, occupied, 0, 100, a)
        before = float(canvas[104])
        _apply_footprint(canvas, occupied, 0, 104, b)
        # A's sample stays, then B's excess (900-7) is added. Not A's sample + 900.
        self.assertAlmostEqual(before, 1000, delta=1.5)
        self.assertAlmostEqual(float(canvas[104]), before + (900 - 7), delta=2.0)


class OrThresholdTests(unittest.TestCase):
    def test_binary_or_uses_validation_cut_not_a_second_mlp_threshold(self) -> None:
        from sparse_pileup.metrics import roc_auc  # noqa: F401
        from sparse_pileup.segment_protocol import prf_counts
        from sparse_pileup.strict_validation import _or_scores

        mlp = np.array([0.20, 0.80, 0.05, 0.40])
        retrigger = np.array([0.0, 0.0, 1.0, 0.0])
        fused = _or_scores(mlp, retrigger, 0.11)
        # 0.20 is above 0.11 and below 0.5, retrigger is off: validation OR fires.
        self.assertEqual(fused.tolist(), [1.0, 1.0, 1.0, 1.0])
        labels = np.array([1, 1, 1, 0])
        at_half = prf_counts(fused, labels, 0.5)
        at_validation = prf_counts(fused, labels, 0.11)
        self.assertEqual(at_half["tp"], at_validation["tp"])
        self.assertEqual(at_half["fp"], at_validation["fp"])
        raw_at_half = prf_counts(mlp, labels, 0.5)
        self.assertNotEqual(raw_at_half["tp"], at_half["tp"])


class AggregateTests(unittest.TestCase):
    def test_three_runs_produce_a_mean(self) -> None:
        from sparse_pileup.strict_validation import _aggregate

        rows = []
        for run_id, f1 in (("blocked-42", 0.2), ("blocked-43", 0.4), ("blocked-44", 0.6)):
            rows.append({"run_id": run_id, "method": "mlp", "study": "mix", "f1": f1, "recall": f1})
        out = _aggregate(rows, "blocked_init", {"blocked-42", "blocked-43", "blocked-44"}, ["method", "study"])
        f1 = next(r for r in out if r["metric"] == "f1")
        self.assertEqual(f1["n_runs"], 3)
        self.assertAlmostEqual(f1["mean"], 0.4)


class ThresholdAndRateTests(unittest.TestCase):
    def test_threshold_uses_only_the_array_it_is_given(self) -> None:
        rng = np.random.default_rng(0)
        scores = rng.random(200)
        labels = (scores > 0.6).astype(np.int32)
        thr, _ = select_threshold(scores, labels)
        decoy = np.zeros_like(scores)
        thr2, _ = select_threshold(scores, labels)
        self.assertEqual(thr, thr2)
        self.assertNotEqual(select_threshold(decoy, labels)[0], thr)

    def test_rate_grid_labels_the_poisson_assumption(self) -> None:
        rows = rate_grid(900.0)
        self.assertGreaterEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["modelling_assumption"], "poisson_exponential_interarrival")
            self.assertIn("poisson", row["modelling_assumption"])
            self.assertTrue(row["rate_source"])
        self.assertAlmostEqual(rows[0]["rate_hz"], 900.0)
        self.assertLess(rows[0]["modelling_p_forward_within_2us"], 0.01)


if __name__ == "__main__":
    unittest.main()
