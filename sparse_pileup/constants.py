"""Magic numbers, each tied to the WinForms C# trainer where it still applies.

FPGA: only N_SAMPLES, N_HIDDEN, SAMPLE_STRIDE, TRIGGER_CHANNEL, CLIP_PRE,
ADC_CHANNELS matter on the chip. The rest is the testbench pulse generator.
"""

from __future__ import annotations

# --- ADC / MCA scale (MCA4096 + trainer) ---
ADC_CHANNELS = 4096
TRIGGER_CHANNEL = 100  # PileupNNBPTrainer.cs timer1_Tick, 100.0/4096.0

# --- Sparse sampler (RTL) ---
N_SAMPLES = 4  # ii in nnBP.cs; SetII is never called
N_HIDDEN = 5  # jj default
N_OUTPUT = 1  # one logit / one height; C# used kk=2 for radio-button modes
SAMPLE_STRIDE = 15  # sw in timer1_Tick
CLIP_PRE = 10.0  # nnBP.UpdateNet saturates pre-activations at ±10
ETA = 0.5  # nnBP.eta
WEIGHT_INIT_HALF = 0.5  # load_random_weight: 0.5 - Random.NextDouble()

# --- Shaped pulse testbench (not RTL) ---
WAVEFORM_LEN = 500  # timer1_Tick pulseDt length
PULSE_WIDTH = 15  # tw1
RC_ALPHA = 0.01  # Array2ShapeDbl res
RC_INNER_STEPS = 10
RC_GAIN = 1.1  # applied to each output sample, not to the integrator state
RC_PASSES = 3
START_OFFSET = 2  # tx = 2 + rnd.Next(10)
START_SPAN = 10  # rnd.Next(10) -> 0..9
PILEUP_PERIOD = 10  # pileUpPro; rnd.Next(10)==0 => ~10% pile-up
GAP_LOW = 2  # rnd.Next(2, 10) -> 2..9
GAP_HIGH = 10  # exclusive, matching Random.Next(min, max)

# --- PoC training protocol (not in C#; C# had no split) ---
DEFAULT_SEED = 42
DEFAULT_EPOCHS = 40
N_TRAIN = 4000
N_VAL = 1000
N_TEST = 1000
