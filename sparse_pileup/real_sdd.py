"""Load and segment the measured SDD + Fe-55 traces under real_data/."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import json

import numpy as np

SAMPLES_PER_SEGMENT = 524288
FS_HZ = 10_000_000.0
SAMPLE_PERIOD_US = 0.1
ADC_CHANNELS = 4096
NOISE_FLOOR_CH = 50
DEFAULT_PULSE_THR = 200
DEFAULT_LEAVE_CH = 40
FE55_AMP_LO = 1100
FE55_AMP_HI = 1400
HIGH_ARTIFACT_CH = 3000
CLOSE_PAIR_SAMPLES = 80  # 8 us at 10 MSPS


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def real_data_root(root: Path | None = None) -> Path:
    return (root or repo_root()) / "real_data"


def sdd_dir(root: Path | None = None) -> Path:
    return real_data_root(root) / "sdd_fe55"


def load_metadata(root: Path | None = None) -> dict:
    path = real_data_root(root) / "metadata.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@dataclass(frozen=True)
class Segment:
    index: int
    name: str
    path: Path
    original_name: str
    n_samples: int


@dataclass
class Pulse:
    pulse_id: int
    segment_index: int
    segment_name: str
    local_start: int
    local_peak: int
    local_end: int
    global_peak: int
    amplitude: int
    width: int
    rise_10_90: int
    dt_prev: int | None
    kind: str

    @property
    def width_us(self) -> float:
        return self.width * SAMPLE_PERIOD_US

    @property
    def rise_us(self) -> float:
        return self.rise_10_90 * SAMPLE_PERIOD_US


def load_manifest(root: Path | None = None) -> list[Segment]:
    path = real_data_root(root) / "manifest.csv"
    rows: list[Segment] = []
    with path.open(encoding="utf-8", newline="") as f:
        for rec in csv.DictReader(f):
            rows.append(
                Segment(
                    index=int(rec["segment"]),
                    name=rec["filename"],
                    path=sdd_dir(root) / rec["filename"],
                    original_name=rec["original_name"],
                    n_samples=int(rec["n_samples"]),
                )
            )
    return rows


def load_segment(path: Path) -> np.ndarray:
    return np.loadtxt(path, dtype=np.int32)


def load_all_samples(root: Path | None = None, progress=None) -> tuple[np.ndarray, list[Segment]]:
    segments = load_manifest(root)
    blocks = []
    for i, seg in enumerate(segments, start=1):
        blocks.append(load_segment(seg.path))
        if progress is not None:
            progress(i, len(segments), seg.name)
    x = np.concatenate(blocks)
    return x, segments


def _rise_10_90(seg: np.ndarray, amp: int, peak_rel: int) -> int:
    if amp <= 0:
        return 0
    i10 = next((k for k, v in enumerate(seg) if v >= 0.1 * amp), 0)
    i90 = next((k for k, v in enumerate(seg) if v >= 0.9 * amp), peak_rel)
    return max(0, i90 - i10)


def classify_amplitude(amp: int) -> str:
    if amp >= HIGH_ARTIFACT_CH:
        return "high"
    if FE55_AMP_LO <= amp <= FE55_AMP_HI:
        return "fe55"
    return "other"


def find_pulses(
    x: np.ndarray,
    segments: list[Segment],
    *,
    threshold: int = DEFAULT_PULSE_THR,
    leave: int = DEFAULT_LEAVE_CH,
    min_width: int = 5,
) -> list[Pulse]:
    """Leading-edge pulses on the concatenated stream."""
    n = int(x.size)
    pulses: list[Pulse] = []
    i = 0
    last_peak: int | None = None
    seg_starts = np.arange(len(segments), dtype=np.int64) * SAMPLES_PER_SEGMENT

    while i < n:
        if x[i] < threshold:
            i += 1
            continue
        start = i
        while start > 0 and x[start] > leave:
            start -= 1
        end = i
        while end < n and x[end] > leave:
            end += 1
        width = end - start
        if width >= min_width:
            rel = int(np.argmax(x[start:end]))
            peak = start + rel
            amp = int(x[peak])
            seg_i = int(np.searchsorted(seg_starts, peak, side="right") - 1)
            seg_i = max(0, min(seg_i, len(segments) - 1))
            origin = int(seg_starts[seg_i])
            dt = None if last_peak is None else int(peak - last_peak)
            pulses.append(
                Pulse(
                    pulse_id=len(pulses),
                    segment_index=segments[seg_i].index,
                    segment_name=segments[seg_i].name,
                    local_start=start - origin,
                    local_peak=peak - origin,
                    local_end=end - origin,
                    global_peak=peak,
                    amplitude=amp,
                    width=width,
                    rise_10_90=_rise_10_90(x[start:end], amp, rel),
                    dt_prev=dt,
                    kind=classify_amplitude(amp),
                )
            )
            last_peak = peak
        i = max(end, i + 1)
    return pulses


def filter_pulses(pulses: list[Pulse], mode: str) -> list[Pulse]:
    if mode == "all":
        return list(pulses)
    if mode == "fe55":
        return [p for p in pulses if p.kind == "fe55"]
    if mode == "high":
        return [p for p in pulses if p.kind == "high"]
    if mode == "other":
        return [p for p in pulses if p.kind == "other"]
    if mode == "close":
        return [
            p
            for p in pulses
            if p.kind == "fe55" and p.dt_prev is not None and p.dt_prev < CLOSE_PAIR_SAMPLES
        ]
    raise ValueError(f"unknown filter {mode!r}")


def four_taps(x: np.ndarray, trigger_index: int, stride: int, n: int = 4) -> tuple[np.ndarray, np.ndarray]:
    idx = trigger_index + np.arange(n, dtype=np.int64) * int(stride)
    idx = np.clip(idx, 0, len(x) - 1)
    return idx, x[idx].astype(np.int32)


def find_trigger(x: np.ndarray, start: int, end: int, level: int = 100) -> int | None:
    sl = x[start:end]
    hits = np.flatnonzero(sl >= level)
    if hits.size == 0:
        return None
    return int(start + hits[0])
