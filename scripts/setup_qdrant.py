#!/usr/bin/env python3
"""
CLI: Setup Qdrant collection với 11 payload indexes.
Usage:
    python scripts/setup_qdrant.py
    python scripts/setup_qdrant.py --recreate
"""
import sys, argparse
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.core.indexing.qdrant_setup import setup

parser = argparse.ArgumentParser()
parser.add_argument("--recreate", action="store_true")
args = parser.parse_args()
print("\n  Qdrant Setup v2")
setup(recreate=args.recreate)
