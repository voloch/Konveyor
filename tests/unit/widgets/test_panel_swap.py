#!/usr/bin/env python3
import fcntl
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from appletsrc_harness import SERVICE


STOCK = """[Containments][1]
plugin=org.kde.panel

[Containments][1][Applets][2]
plugin=org.kde.plasma.kickoff

[Containments][1][Applets][3]
plugin=org.kde.plasma.pager

[Containments][1][Applets][4]
immutability=1
plugin=org.kde.plasma.icontasks

[Containments][1][Applets][4][Configuration][General]
launchers=applications:org.kde.dolphin.desktop,applications:firefox.desktop
groupingStrategy=0

[Containments][1][Applets][5]
plugin=org.kde.plasma.systemtray

[Containments][1][General]
AppletOrder=2;3;4;5

[Containments][6]
plugin=org.kde.desktopcontainment
"""

FAKE_SYSTEMCTL = """#!/bin/sh
echo "$*" >> "$FAKE_SYSTEMCTL_LOG"
case "$2" in
    stop|start) cp "$XDG_CONFIG_HOME/plasma-org.kde.plasma.desktop-appletsrc" "$FAKE_SYSTEMCTL_LOG.$2" ;;
esac
"""

STOP = "--user stop plasma-plasmashell.service"
RESET = "--user reset-failed plasma-plasmashell.service"
START = "--user start plasma-plasmashell.service"


class TestPanelSwap(unittest.TestCase):
    script = SERVICE / "panel-swap"

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
        self.environment = {**os.environ, "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(self.config), "XDG_STATE_HOME": str(root / "state"),
                            "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_SYSTEMCTL_LOG": str(self.log)}
        self.appletsrc = self.config / "plasma-org.kde.plasma.desktop-appletsrc"
        self.taskbarrc = self.config / "konveyor" / "taskbarrc"
        self.panel_off = self.state / "panel-off"

    def konveyor_panel(self, settings=True):
        self.appletsrc.write_text(STOCK)
        for tool, command in (("panel-launcher", "install"), ("panel-taskbar", "install")):
            subprocess.run([sys.executable, str(SERVICE / tool), command, str(self.appletsrc)], check=True, capture_output=True)
        if settings:
            subprocess.run([sys.executable, str(SERVICE / "panel-taskbar"), "settings", str(self.appletsrc), str(self.taskbarrc)], check=True, capture_output=True)
        return self.appletsrc.read_text()

    def swap(self, *arguments, code=0):
        result = subprocess.run([str(self.script), *arguments], capture_output=True, text=True, env=self.environment)
        self.assertEqual(result.returncode, code, result.stderr)
        return result

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def snapshot(self, verb):
        return Path(f"{self.log}.{verb}").read_text()

    def applet(self, text, applet):
        return text.split(f"[Containments][1][Applets][{applet}]\n", 1)[1].split("\n[", 1)[0].rstrip("\n") + "\n"

    def test_the_helper_is_executable(self):
        self.assertTrue(os.access(self.script, os.X_OK))

    def test_off_brings_back_kickoff_and_the_task_manager_where_they_were(self):
        self.konveyor_panel()
        self.swap("off")
        text = self.appletsrc.read_text()
        self.assertEqual(self.applet(text, 2), "plugin=org.kde.plasma.kickoff\n")
        self.assertEqual(self.applet(text, 4), "immutability=1\nplugin=org.kde.plasma.icontasks\n")
        self.assertIn("AppletOrder=2;3;4;5", text)
        self.assertNotIn("org.devl0rd", text)
        self.assertIn("[Containments][1][Applets][4][Configuration][General]\n"
                      "launchers=applications:org.kde.dolphin.desktop,applications:firefox.desktop\n", text)

    def test_off_records_which_widgets_it_swapped(self):
        self.konveyor_panel()
        self.swap("off")
        self.assertEqual(self.panel_off.read_text(), "launcher\ntaskbar\n")

    def test_off_stops_plasma_before_the_edits_and_starts_it_after(self):
        before = self.konveyor_panel()
        self.swap("off")
        self.assertEqual(self.calls(), [STOP, RESET, START])
        self.assertEqual(self.snapshot("stop"), before)
        self.assertEqual(self.snapshot("start"), self.appletsrc.read_text())
        self.assertNotEqual(self.snapshot("start"), before)

    def test_off_keeps_the_current_taskbar_settings_for_the_task_manager(self):
        self.konveyor_panel(settings=False)
        self.swap("off")
        pins = "launchers=applications:org.kde.dolphin.desktop,applications:firefox.desktop\n"
        self.assertIn(pins, self.taskbarrc.read_text())
        self.assertIn("[Containments][1][Applets][4][Configuration][General]\n" + pins, self.appletsrc.read_text())

    def test_on_gives_back_the_konveyor_widgets_where_they_were(self):
        before = self.konveyor_panel()
        self.swap("off")
        self.swap("on")
        self.assertEqual(self.appletsrc.read_text(), before)
        self.assertFalse(self.panel_off.exists())
        self.assertEqual(self.calls(), [STOP, RESET, START] * 2)
        self.assertEqual(self.snapshot("start"), before)

    def test_on_stops_plasma_before_the_edits_and_starts_it_after(self):
        before = self.konveyor_panel()
        self.swap("off")
        off = self.appletsrc.read_text()
        self.swap("on")
        self.assertEqual(self.snapshot("stop"), off)
        self.assertEqual(self.snapshot("start"), before)

    def test_a_widget_removed_before_turning_off_stays_removed(self):
        self.konveyor_panel()
        text = re.sub(r"\[Containments\]\[1\]\[Applets\]\[4\]\n.*?\n\n", "", self.appletsrc.read_text(), flags=re.S).replace("AppletOrder=2;4;3;5", "AppletOrder=2;3;5")
        self.appletsrc.write_text(text)
        self.swap("off")
        self.assertEqual(self.panel_off.read_text(), "launcher\n")
        self.swap("on")
        text = self.appletsrc.read_text()
        self.assertIn("plugin=org.devl0rd.portal.launcher", text)
        self.assertNotIn("org.devl0rd.taskbar", text)
        self.assertNotIn("icontasks", text)
        self.assertNotIn("taskmanager", text)
        self.assertIn("AppletOrder=2;3;5", text)

    def test_off_without_konveyor_widgets_does_nothing(self):
        self.appletsrc.write_text(STOCK)
        self.swap("off")
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.appletsrc.read_text(), STOCK)
        self.assertFalse(self.panel_off.exists())

    def test_off_with_a_missing_appletsrc_does_nothing(self):
        self.swap("off")
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.appletsrc.exists())

    def test_on_without_a_state_file_does_nothing(self):
        before = self.konveyor_panel()
        self.swap("on")
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.appletsrc.read_text(), before)

    def test_off_twice_is_idempotent(self):
        self.konveyor_panel()
        self.swap("off")
        after = self.appletsrc.read_text()
        self.swap("off")
        self.assertEqual(self.appletsrc.read_text(), after)
        self.assertEqual(self.panel_off.read_text(), "launcher\ntaskbar\n")
        self.assertEqual(self.calls(), [STOP, RESET, START])

    def test_no_restart_edits_the_panel_without_touching_plasma(self):
        before = self.konveyor_panel()
        self.swap("off", "--no-restart")
        self.assertNotIn("org.devl0rd", self.appletsrc.read_text())
        self.assertEqual(self.panel_off.read_text(), "launcher\ntaskbar\n")
        self.swap("on", "--no-restart")
        self.assertEqual(self.appletsrc.read_text(), before)
        self.assertFalse(self.panel_off.exists())
        self.assertEqual(self.calls(), [])

    def break_the_taskbar_settings(self):
        self.konveyor_panel(settings=False)
        (self.config / "konveyor").write_text("not a directory\n")

    def test_plasma_is_started_again_when_a_step_fails(self):
        self.break_the_taskbar_settings()
        result = subprocess.run([str(self.script), "off"], capture_output=True, text=True, env=self.environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [STOP, RESET, START])

    def test_plasma_is_not_started_when_this_run_did_not_stop_it(self):
        self.break_the_taskbar_settings()
        result = subprocess.run([str(self.script), "off", "--no-restart"], capture_output=True, text=True, env=self.environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_the_set_up_markers_are_left_alone(self):
        self.konveyor_panel()
        self.state.mkdir(parents=True)
        markers = [self.state / "launcher-set-up", self.state / "taskbar-set-up"]
        for marker in markers:
            marker.write_text("marker\n")
        self.swap("off")
        self.swap("on")
        self.assertEqual([marker.read_text() for marker in markers], ["marker\n", "marker\n"])
        self.assertEqual(sorted(path.name for path in self.state.iterdir()), ["launcher-set-up", "panel-swap.lock", "taskbar-set-up"])

    def test_a_quick_second_toggle_waits_for_the_first(self):
        self.konveyor_panel()
        self.state.mkdir(parents=True)
        with open(self.state / "panel-swap.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            waiting = subprocess.Popen([str(self.script), "off"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.environment)
            time.sleep(0.5)
            self.assertIsNone(waiting.poll())
            self.assertEqual(self.calls(), [])
            fcntl.flock(lock, fcntl.LOCK_UN)
            waiting.communicate(timeout=30)
        self.assertEqual(waiting.returncode, 0)
        self.assertEqual(self.calls(), [STOP, RESET, START])

    def test_usage(self):
        self.konveyor_panel()
        for arguments in ((), ("toggle",), ("off", "--bogus"), ("on", "off"), ("off", "--no-restart", "extra"), ("--no-restart",)):
            with self.subTest(arguments=arguments):
                self.assertIn("usage: panel-swap off|on [--no-restart]", self.swap(*arguments, code=2).stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.panel_off.exists())


if __name__ == "__main__":
    unittest.main()
