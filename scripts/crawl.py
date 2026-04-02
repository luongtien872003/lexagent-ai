#!/usr/bin/env python3
"""
CLI: Crawl văn bản từ thuvienphapluat.vn.
Usage:
    python scripts/crawl.py               # Tất cả
    python scripts/crawl.py --law bhxh   # 1 luật
    python scripts/crawl.py --list       # Liệt kê
"""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Proxy to crawler module
import subprocess
result = subprocess.run([sys.executable, str(ROOT / "crawler/tvpl_crawler.py")] + sys.argv[1:])
sys.exit(result.returncode)
