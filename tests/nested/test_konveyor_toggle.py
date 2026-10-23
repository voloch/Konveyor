#!/usr/bin/env python3
"""Press the Kontrol Panel's Meta+Shift+Backspace to turn Konveyor off and on again, and check the windows and the layout come through."""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "harness"))

from test_kontrol_panel import SETUP, stage

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

    with tempfile.TemporaryDirectory(prefix="konveyor-kontrol-panel-") as temporary:
        panel, imports, _ = stage(Path(temporary))
        return run_runner(HERE / "runners" / "konveyor_toggle.py", clients=(), timeout=420, setup=SETUP.format(imports=imports, panel=panel),
                          global_shortcuts=True, output_count=2, extra_kwinrc=DESKTOPS)


if __name__ == "__main__":
    sys.exit(main())
