#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from appletsrc_harness import SERVICE
from test_panel_swap import FAKE_SYSTEMCTL, RESET, START, STOCK, STOP


WIDGETS = SERVICE.parent
TAKE_OVER = r"""
set -euo pipefail
say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
source "$WIDGETS_DIR/lib.sh"
take_over_launcher_and_restart
"""


class TestInstallPanelSwap(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.config = root / "config"
        self.state = root / "state" / "konveyor"
        self.log = root / "systemctl.log"
        bin_dir = root / "bin"
        bin_dir.mkdir()
        self.config.mkdir()
        fake = bin_dir / "systemctl"
        fake.write_text(FAKE_SYSTEMCTL)
        fake.chmod(0o755)
        self.environment = {**os.environ, "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(self.config),
                            "XDG_STATE_HOME": str(root / "state"), "WIDGETS_DIR": str(WIDGETS),
                            "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_SYSTEMCTL_LOG": str(self.log)}
        self.appletsrc = self.config / "plasma-org.kde.plasma.desktop-appletsrc"
        self.panel_off = self.state / "panel-off"
        self.taskbarrc = self.config / "konveyor" / "taskbarrc"
        self.state.mkdir(parents=True)
        for marker in ("launcher-set-up", "taskbar-set-up"):
            (self.state / marker).touch()

    def konveyor_panel(self):
        self.appletsrc.write_text(STOCK)
        for tool in ("panel-launcher", "panel-taskbar"):
            subprocess.run([sys.executable, str(SERVICE / tool), "install", str(self.appletsrc)], check=True, capture_output=True)
        subprocess.run([sys.executable, str(SERVICE / "panel-taskbar"), "settings", str(self.appletsrc), str(self.taskbarrc)], check=True, capture_output=True)
        return self.appletsrc.read_text()

    def swap_off(self):
        result = subprocess.run([str(SERVICE / "panel-swap"), "off", "--no-restart"], capture_output=True, text=True, env=self.environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.appletsrc.read_text()

    def take_over(self):
        result = subprocess.run(["bash", "-c", TAKE_OVER], capture_output=True, text=True, env=self.environment)
        self.assertEqual(result.returncode, 0, result.stderr)

    def calls(self):
        return self.log.read_text().splitlines()

    def snapshot(self, verb):
        return Path(f"{self.log}.{verb}").read_text()

    def test_install_while_konveyor_is_off_gives_the_konveyor_widgets_back(self):
        self.konveyor_panel()
        self.swap_off()
        self.take_over()
        text = self.appletsrc.read_text()
        self.assertIn("plugin=org.devl0rd.portal.launcher", text)
        self.assertIn("plugin=org.devl0rd.taskbar", text)
        self.assertNotIn("plugin=org.kde.plasma.kickoff", text)
        self.assertNotIn("plugin=org.kde.plasma.icontasks", text)

    def test_install_while_konveyor_is_off_restores_inside_one_plasma_stop(self):
        self.konveyor_panel()
        native = self.swap_off()
        self.take_over()
        self.assertFalse(self.panel_off.exists(), "panel-off is still there")
        self.assertEqual(self.calls(), [STOP, RESET, START])
        self.assertEqual(self.snapshot("stop"), native)
        self.assertEqual(self.snapshot("start"), self.appletsrc.read_text())

    def test_install_with_no_state_file_leaves_a_settled_panel_alone(self):
        self.konveyor_panel()
        self.take_over()
        settled = self.appletsrc.read_text()
        self.take_over()
        self.assertEqual(self.appletsrc.read_text(), settled)


if __name__ == "__main__":
    unittest.main()
