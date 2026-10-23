#!/usr/bin/env python3
"""Park a window past the right edge of the right output, then reload the effect and check it stays parked."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "harness"))

DESKTOPS = """
[Desktops]
Number=4
Name_1=Mail
Name_2=Web
Name_3=Chat
Name_4=Music
"""


def main():
    from nested import run_runner

    return run_runner(HERE / "runners" / "konveyor_disable.py", timeout=300, clients=(), output_count=2, extra_kwinrc=DESKTOPS)


if __name__ == "__main__":
    sys.exit(main())
