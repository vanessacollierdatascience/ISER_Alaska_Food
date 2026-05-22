#!/usr/bin/env python3

from pathlib import Path
from typing import List

VALID_SUFFIXES = {".csv", ".json", ".txt"}

def discover_raw_files(store_raw_root: Path) -> List[Path]:
    """
    Recursively discover all compliant raw data files
    under a store's RAW directory.
    """
    files = []
    for p in store_raw_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in VALID_SUFFIXES:
            files.append(p)
    return sorted(files)
