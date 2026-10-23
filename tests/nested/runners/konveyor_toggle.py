#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))

import dbus
import dbus.lowlevel
from checks import Checks
from fakepointer import move, tap
from keycodes import KEY_CODES, MODIFIER_CODES
from kwinsession import (activate, active_title, frame, frames, intersects, konveyor, konveyor_action, konveyor_windows, managed_now, open_client, qdbus,
                         run_script, wait_for)
from nested import build_dir
from shortcuts import shortcut

EFFECTS = ("org.kde.KWin", "/Effects")
PANEL = ("org.devl0rd.KontrolPanel", "/KontrolPanel")
TITLES = ("A", "B", "C")
BEFORE = {}
META_SHIFT_BACKSPACE = 0x10000000 | 0x02000000 | 0x01000003


def layout():
    workspaces = {workspace["id"]: workspace for workspace in json.loads(konveyor("Workspaces"))}
    return {window["title"]: (workspaces[window["workspace_id"]]["idx"], window["is_floating"], window["layout"]["pos_in_scrolling_layout"],
                              window["layout"]["tile_size"][0],
                              None if window["is_floating"] else workspaces[window["workspace_id"]]["column_displays"][
                                  window["layout"]["pos_in_scrolling_layout"][0] - 1]) for window in konveyor_windows()}


def screens():
    return {entry["name"]: (entry["logical"]["x"], entry["logical"]["y"], entry["logical"]["width"], entry["logical"]["height"])
            for entry in json.loads(konveyor("Outputs"))}


def on_screen(title):
    return any(intersects(frame(title), screen) for screen in BEFORE["screens"].values())


def settled_frames():
    last = []

    def unchanged():
        current = frames()
        stable = bool(last) and current == last[0]
        last[:] = [current]
        return current if stable else None

    return wait_for(unchanged, 20)


def effect_loaded():
    return qdbus(*EFFECTS, "org.kde.kwin.Effects.isEffectLoaded", "konveyor_effect") == "true"


def desktop_names():
    return run_script('for (const d of workspace.desktops) print("MARK|" + d.name);')


def plugin_enabled():
    section = None
    for line in (Path(os.environ["XDG_CONFIG_HOME"]) / "kwinrc").read_text().splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[Plugins]" and line.startswith("konveyor_effectEnabled="):
            return line.split("=", 1)[1]
    return None


def inside(frame_, screen):
    return screen[0] <= frame_[0] and screen[1] <= frame_[1] and frame_[0] + frame_[2] <= screen[0] + screen[2] and frame_[1] + frame_[3] <= screen[1] + screen[3]


def press_toggle():
    tap([MODIFIER_CODES["Super"], MODIFIER_CODES["Shift"]], KEY_CODES["BackSpace"])


def right_output_centre():
    screen = max(BEFORE["screens"].values())
    move(screen[0] + screen[2] / 2, screen[1] + screen[3] / 2, settle=False)


def arrange(checks):
    BEFORE["screens"] = screens()
    right_output_centre()
    for title in TITLES:
        open_client(title)
    for title in ("A", "B"):
        activate(title)
        checks.equal(konveyor_action("set-column-width", "90%"), "", f"set-column-width 90% on {title}")
    activate("A")
    checks.expect(wait_for(lambda: not on_screen("C"), 20), f"C is scrolled past the edge and intersects no output ({frame('C')})")
    BEFORE["frames"] = settled_frames()
    BEFORE["layout"] = layout()
    BEFORE["active"] = active_title()
    checks.expect(BEFORE["frames"] and not on_screen("C"), f"the arrangement settles with C parked ({BEFORE['frames']})")
    checks.equal(BEFORE["active"], "A", "A has focus")


def turn_off(checks):
    press_toggle()
    checks.expect(wait_for(lambda: not effect_loaded(), 10), "the key unloads the effect")
    print("active window right after turning Konveyor off:", active_title())
    names = subprocess.run(["qdbus6"], capture_output=True, text=True).stdout.split()
    checks.expect("org.kde.Konveyor" not in names, "org.kde.Konveyor is gone from the session bus")
    checks.equal(desktop_names(), ["Mail", "Web", "Chat", "Music"], "KDE's four desktops are back with their names")
    now = settled_frames()
    checks.expect(now and all(any(intersects(window, screen) for screen in BEFORE["screens"].values()) for window in now.values()),
                  f"every window intersects an output ({now})")
    parked = BEFORE["frames"]["C"]
    checks.expect(now and inside(now["C"], max(BEFORE["screens"].values())), f"C is on the right output ({now and now['C']})")
    checks.expect(now and all(abs(now["C"][index] - parked[index]) < 1 for index in (2, 3)), f"C has its tiled size ({parked[2:]} -> {now and now['C'][2:]})")
    checks.expect(now and all(now[title] == BEFORE["frames"][title] for title in ("A", "B")), f"A and B have not moved ({now})")
    checks.equal(plugin_enabled(), "true", "kwinrc still enables the effect")


def turn_on(checks):
    right_output_centre()
    open_client("D", managed=False)
    checks.expect(wait_for(lambda: active_title() == "D", 10), f"D has focus while Konveyor is off ({active_title()})")
    activate("B")
    checks.expect(wait_for(lambda: active_title() == "B", 10), f"B has focus while Konveyor is off ({active_title()})")
    press_toggle()
    checks.expect(wait_for(effect_loaded, 10), "the second press loads the effect")
    checks.expect(wait_for(lambda: {*TITLES, "D"} <= managed_now(), 60), "the effect manages A, B, C and D")
    kept = {title: BEFORE["layout"][title] for title in TITLES}
    checks.expect(wait_for(lambda: {title: layout().get(title) for title in TITLES} == kept, 10),
                  f"A, B and C are in the same columns, workspace and display as before ({kept} -> {layout()})")
    new = layout()["D"]
    columns = {layout()[title][2][0] for title in TITLES}
    checks.expect(not new[1] and new[2][1] == 1 and new[2][0] not in columns, f"D is tiled as a new column ({new})")
    checks.equal(active_title(), "B", "the window focused just before turning Konveyor back on keeps focus, and it is not the newest window")
    checks.equal(json.loads(konveyor("FocusedWindow")).get("title"), "B", "and it is the layout's focused window")


def double_press(checks):
    bus = dbus.SessionBus()
    for _ in range(2):
        call = dbus.lowlevel.MethodCallMessage(PANEL[0], PANEL[1], PANEL[0], "ToggleKonveyor")
        call.set_no_reply(True)
        bus.send_message(call)
    bus.flush()
    checks.expect(wait_for(lambda: not effect_loaded(), 10), "two presses together unload the effect")
    time.sleep(3)
    checks.expect(not effect_loaded(), "and the second press does not bring it back")


def reconfigure_record(checks):
    qdbus("org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure")
    print("effect loaded after /KWin reconfigure with Konveyor off:", bool(wait_for(effect_loaded, 5)))
    if not effect_loaded():
        checks.equal(qdbus(*EFFECTS, "org.kde.kwin.Effects.loadEffect", "konveyor_effect"), "true", "the effect loads again to end clean")


def main():
    checks = Checks()
    log = open(os.environ["KONVEYOR_KWIN_LOG"], "a")
    process = subprocess.Popen([str(build_dir() / "bin" / "konveyor-kontrol-panel"), os.environ["KONVEYOR_KONTROL_PANEL_DIR"]],
                               stdout=log, stderr=subprocess.STDOUT)
    bound = checks.expect(wait_for(lambda: dbus.SessionBus().name_has_owner(PANEL[0]), 60), "the Kontrol Panel takes its bus name")
    registered = bound and checks.expect(
        wait_for(lambda: shortcut("konveyor-kontrol-panel", "toggle-konveyor") == [META_SHIFT_BACKSPACE], 30),
        f"KGlobalAccel binds Meta+Shift+Backspace to toggle-konveyor ({bound and shortcut('konveyor-kontrol-panel', 'toggle-konveyor')})")
    if registered:
        checks.run(arrange, turn_off, turn_on, double_press, reconfigure_record)
    else:
        checks.run()
    process.terminate()
    process.wait(timeout=30)


if __name__ == "__main__":
    main()
