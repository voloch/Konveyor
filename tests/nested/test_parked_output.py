#!/usr/bin/env python3
"""Keep the client of a window parked off every monitor on its home output so a mixed-scale setup never flips its scale."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "harness"))


def main():
    from nested import run_runner

    return run_runner(HERE / "runners" / "parked_output.py", timeout=300, clients=(), output_count=2)


if __name__ == "__main__":
    sys.exit(main())
