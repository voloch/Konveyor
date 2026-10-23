#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))

from checks import Checks
from fakepointer import move
from kwinsession import activate, active_title, frame, frames, intersects, konveyor, konveyor_action, konveyor_windows, managed_now, open_client, qdbus, wait_for

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


def main():
    Checks().run(arrange, reload_keeps_parked)


if __name__ == "__main__":
    main()
