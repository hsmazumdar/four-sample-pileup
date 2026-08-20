"""Sanity checks that do not require a 40-epoch train. Run:

    python tests/test_sanity.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sparse_pileup.constants import (  # noqa: E402
    ADC_CHANNELS,
    N_HIDDEN,
    N_SAMPLES,
    PULSE_WIDTH,
    SAMPLE_STRIDE,
    TRIGGER_CHANNEL,
    WAVEFORM_LEN,
)
from sparse_pileup.dataset import make_split  # noqa: E402
from sparse_pileup.dual_head import DualHeadDetector  # noqa: E402
from sparse_pileup.mlp import SmallMLP, sigmoid  # noqa: E402
from sparse_pileup.pulse_sim import array2shape_dbl, load_mca_lines, simulate_pulse  # noqa: E402
from sparse_pileup.sampler import extract_frame, quantize_4096  # noqa: E402

CSV = ROOT / "config" / "mca_lines.csv"


class SigmoidTests(unittest.TestCase):
    def test_clip_and_midpoint(self) -> None:
        self.assertAlmostEqual(float(sigmoid(0.0)), 0.5, places=6)
        self.assertGreater(float(sigmoid(10.0)), 0.99)
        self.assertEqual(float(sigmoid(10.0)), float(sigmoid(50.0)))


class PulseTests(unittest.TestCase):
    def test_mca_lines(self) -> None:
        lines = load_mca_lines(CSV)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0].height, 100)
        self.assertGreater(len(lines[0].profile), 10)

    def test_shape_is_causal_and_positive(self) -> None:
        rect = np.zeros(64)
        rect[8:8 + PULSE_WIDTH] = 0.5
        y = array2shape_dbl(rect)
        self.assertTrue(np.all(y >= -1e-12))
        self.assertGreater(y[8 + PULSE_WIDTH - 1], y[8])

    def test_waveform_length(self) -> None:
        lines = load_mca_lines(CSV)
        rng = np.random.default_rng(0)
        p = simulate_pulse(lines, rng, force_pileup=False)
        self.assertEqual(p.waveform.shape, (WAVEFORM_LEN,))
        self.assertFalse(p.is_pileup)
        p2 = simulate_pulse(lines, rng, force_pileup=True)
        self.assertTrue(p2.is_pileup)
        self.assertIsNotNone(p2.amplitude_second)


class SamplerTests(unittest.TestCase):
    def test_quantize(self) -> None:
        self.assertEqual(quantize_4096(0.5), 2048 / 4096)
        self.assertEqual(quantize_4096(0.0), 0.0)

    def test_four_taps(self) -> None:
        lines = load_mca_lines(CSV)
        rng = np.random.default_rng(1)
        for _ in range(40):
            pulse = simulate_pulse(lines, rng, force_pileup=False)
            # boost so trigger always fires
            pulse.waveform = np.maximum(pulse.waveform, pulse.waveform)
            if pulse.waveform.max() < TRIGGER_CHANNEL / ADC_CHANNELS:
                continue
            frame = extract_frame(pulse.waveform)
            if frame is None:
                continue
            self.assertEqual(frame.samples.shape, (N_SAMPLES,))
            self.assertEqual(int(frame.indices[1] - frame.indices[0]), SAMPLE_STRIDE)
            return
        self.fail("could not extract a frame")


class MlpTests(unittest.TestCase):
    def test_shapes_and_range(self) -> None:
        rng = np.random.default_rng(2)
        net = SmallMLP.random(rng)
        y, cache = net.forward(np.array([0.1, 0.2, 0.3, 0.4]))
        self.assertTrue(0.0 < y < 1.0)
        self.assertEqual(cache.yi.shape, (N_SAMPLES + 1,))
        self.assertEqual(cache.yj.shape, (N_HIDDEN + 1,))
        self.assertEqual(cache.yi[-1], 1.0)
        self.assertEqual(cache.yj[-1], 1.0)

    def test_train_step_reduces_error_on_easy_target(self) -> None:
        rng = np.random.default_rng(3)
        net = SmallMLP.random(rng)
        x = np.array([0.2, 0.4, 0.3, 0.1])
        e0 = net.train_step(x, 0.0)
        for _ in range(80):
            net.train_step(x, 0.0)
        e1 = abs(net.forward(x)[0] - 0.0)
        self.assertLess(e1, e0)


class DualHeadTests(unittest.TestCase):
    def test_infer_and_json_roundtrip(self, tmp=None) -> None:
        rng = np.random.default_rng(4)
        model = DualHeadDetector.random(rng)
        x = np.array([0.05, 0.4, 0.35, 0.1])
        r = model.infer(x)
        self.assertTrue(0.0 < r.pileup_prob < 1.0)
        path = ROOT / "artifacts" / "_roundtrip_test.json"
        path.parent.mkdir(exist_ok=True)
        model.save_json(path)
        model2 = DualHeadDetector.load_json(path)
        r2 = model2.infer(x)
        self.assertAlmostEqual(r.pileup_prob, r2.pileup_prob, places=9)
        path.unlink(missing_ok=True)

    def test_tiny_split(self) -> None:
        split = make_split(CSV, n_train=8, n_val=4, n_test=4, seed=7)
        self.assertEqual(len(split.train), 8)
        self.assertEqual(split.train[0].samples.shape, (4,))
        self.assertTrue(0.0 <= split.train[0].amplitude_first < 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
