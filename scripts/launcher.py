#!/usr/bin/env python3
"""Absolute-path launcher that does not import Python modules from the target repo."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jev_approval.cli import main
raise SystemExit(main())
