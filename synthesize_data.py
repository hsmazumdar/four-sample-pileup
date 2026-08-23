#!/usr/bin/env python3
"""Data synthesizer (reviewer entry point).

    python synthesize_data.py

Writes labelled train/val/test CSVs under data/. Engine:
sparse_pileup.pulse_sim (SDD-fitted CR–RC^8 + Fe-55 lines + measured
noise). Pile-up is still synthetic.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sparse_pileup.synthesize import main

if __name__ == "__main__":
    main()
