"""Magic numbers for the four-sample PoC.

The pulse *shape* is a CR–RC^n kernel fitted to measured SDD + Fe-55
traces (config/sdd_shape.json). The 2016 WinForms trainer used a
width-15 rectangle and three leaky integrators; that path remains in
pulse_sim.array2shape_dbl for comparison only.

FPGA: N_SAMPLES, N_HIDDEN, SAMPLE_STRIDE, TRIGGER_CHANNEL, CLIP_PRE,
ADC_CHANNELS. SAMPLE_STRIDE is 4 (400 ns at 10 MSPS), not the 2016
value of 15, which sits off a 1 µs pulse.
"""

from __future__ import annotations

# --- ADC / MCA scale ---
ADC_CHANNELS = 4096
TRIGGER_CHANNEL = 100  # leading-edge, same threshold as the 2016 trainer

# --- Sparse sampler (RTL) ---
N_SAMPLES = 4
N_HIDDEN = 5
N_OUTPUT = 1
SAMPLE_STRIDE = 4  # 400 ns at 10 MSPS; 2016 trainer used 15
CLIP_PRE = 10.0
ETA = 0.5
WEIGHT_INIT_HALF = 0.5

# --- Physical units (measured SDD campaign) ---
FS_HZ = 10_000_000.0
SAMPLE_PERIOD_US = 0.1

# --- CR–RC^n testbench (fitted; see config/sdd_shape.json) ---
WAVEFORM_LEN = 160  # 16 µs at 10 MSPS
CR_RC_N = 8
CR_RC_TAU_SAMPLES = 1.2606
PEAKING_SAMPLES = CR_RC_N * CR_RC_TAU_SAMPLES
NOISE_SIGMA_CH = 9.86
PEDESTAL_CH = 7.1
START_OFFSET = 24
START_SPAN = 16
PILEUP_PERIOD = 10  # Bernoulli ~1/10
GAP_LOW = 3  # peak-to-peak samples (0.3 µs)
GAP_HIGH = 21  # exclusive; 3…20 samples (0.3–2.0 µs)

# --- Legacy 2016 rectangle + 3× leaky integrator (not the default synth) ---
PULSE_WIDTH = 15
RC_ALPHA = 0.01
RC_INNER_STEPS = 10
RC_GAIN = 1.1
RC_PASSES = 3

# --- PoC training protocol ---
DEFAULT_SEED = 42
DEFAULT_EPOCHS = 40
N_TRAIN = 4000
N_VAL = 1000
N_TEST = 1000
DEFAULT_LINES_CSV = "config/sdd_fe55_lines.csv"

# --- Real-pulse superposition (default V4 engine) ---
# Isolated events are measured Fe-55 snippets. Pile-up is a linear sum of
# two isolated snippets at a controlled Δt — constructed, not measured.
DEFAULT_ENGINE = "real"
REAL_ISO_DT_SAMPLES = 80  # 8 µs isolation on both sides
REAL_SNIPPET_PRE = 48  # samples stored before the peak
REAL_LIBRARY_TRAIN_FRAC = 0.60
REAL_LIBRARY_VAL_FRAC = 0.20
REAL_SNIPPETS_NPZ = "real_data/isolated_fe55_snippets.npz"
