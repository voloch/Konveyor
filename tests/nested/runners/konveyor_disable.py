#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))

from checks import Checks, default_config, load_config
from fakepointer import move
from kwinsession import (activate, active_title, for_window, frame, frames, intersects, konveyor, konveyor_action, konveyor_windows, managed_now,
                         open_client, qdbus, run_script, wait_for)

EFFECTS = ("org.kde.KWin", "/Effects")
TITLES = ("A", "B", "C")
BEFORE = {}


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


def arrange(checks):
    BEFORE["screens"] = screens()
    screen = max(BEFORE["screens"].values())
    move(screen[0] + screen[2] / 2, screen[1] + screen[3] / 2, settle=False)
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


def reload_keeps_parked(checks):
    qdbus(*EFFECTS, "org.kde.kwin.Effects.unloadEffect", "konveyor_effect")
    checks.expect(not wait_for(lambda: on_screen("C"), 3), f"C stays out of view while the effect is unloaded ({frame('C')})")
    checks.equal(qdbus(*EFFECTS, "org.kde.kwin.Effects.loadEffect", "konveyor_effect"), "true", "the effect loads again")
    checks.expect(wait_for(lambda: set(TITLES) <= managed_now(), 60), "the reloaded effect manages the open windows")
    checks.expect(wait_for(lambda: layout() == BEFORE["layout"], 10), f"the layout is unchanged ({BEFORE['layout']} -> {layout()})")
    checks.expect(not wait_for(lambda: on_screen("C"), 3), f"C stays out of view after the reload ({frame('C')})")


def opacity(title):
    printed = run_script(for_window(title, 'print("MARK|" + w.opacity);'))
    return float(printed[0]) if printed else None


def opacity_rule(checks):
    rule = '\nwindow-rule {\n    match title="^B$"\n    opacity 0.8\n}\n'
    checks.expect(load_config(default_config() + rule), "a config with an opacity rule for B loads")
    checks.expect(wait_for(lambda: opacity("B") == 0.8, 10), f"the rule makes B translucent while the effect runs ({opacity('B')})")


def disable_call():
    return subprocess.run(["qdbus6", "org.kde.Konveyor", "/Konveyor", "org.kde.Konveyor.Disable"], capture_output=True, text=True)


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


def disable(checks):
    result = disable_call()
    checks.equal(result.returncode, 0, f"Disable is accepted ({(result.stdout + result.stderr).strip()})")
    checks.expect(wait_for(lambda: not effect_loaded(), 10), "the effect unloads itself")
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
    checks.equal(opacity("B"), 1.0, "B is opaque again, plain KDE has no rule opacity")
    checks.equal(plugin_enabled(), "true", "kwinrc still enables the effect, so it is on again after logging in")


def main():
    Checks().run(arrange, reload_keeps_parked, opacity_rule, disable)


if __name__ == "__main__":
    main()
