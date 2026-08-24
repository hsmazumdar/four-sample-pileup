"""Four-sample pile-up MLP + OT-LS peak PoC (FPGA-oriented, training is offline)."""

from sparse_pileup.dual_head import DualHeadDetector, InferResult
from sparse_pileup.ls_peak import LsPeakEstimator

__all__ = ["DualHeadDetector", "InferResult", "LsPeakEstimator"]
