#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from frequency_estimation.datasets import prepare_real_world_dataset


def main() -> None:
    pcap_path = REPO_ROOT / "data" / "network" / "200002091359.dump"
    cache_path = REPO_ROOT / "data" / "network" / "flow_distribution.json"
    prepare_real_world_dataset(pcap_path=pcap_path, cache_path=cache_path, vocabulary_size=1024)
    print(cache_path)


if __name__ == "__main__":
    main()
