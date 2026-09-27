#!/usr/bin/env python3
"""Data synthesizer (reviewer entry point).

    python synthesize_data.py

Writes labelled train/val/test CSVs under data/. Default engine is
real-pulse superposition: isolated = measured Fe-55 snippets; pile-up
= linear sum of two snippets (constructed, not measured). Use
--engine kernel for the V3 CR–RC⁸ injector.
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
