#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))

from checks import Checks
from fakepointer import move
from kwinsession import activate, frames, intersects, konveyor, konveyor_windows, managed_titles, open_client, run_script, wait_for
from nested import build_dir

ROOT = Path(os.environ["KONVEYOR_TEST_ROOT"])
EVENTS = ROOT / "output-events.txt"
HOME = "Virtual-0"
OTHER = "Virtual-1"
TITLE = "A"
SETTLE_SECONDS = 1
WATCH_SECONDS = 3
trackers = []


def outputs():
    return {entry["name"]: (entry["logical"]["x"], entry["logical"]["y"], entry["logical"]["width"], entry["logical"]["height"])
            for entry in json.loads(konveyor("Outputs"))}


def scales():
    return [int(line.split()[1]) for line in EVENTS.read_text().splitlines() if line.startswith("SCALE ")] if EVENTS.exists() else []


def settled():
    targets = {window["title"]: window["layout"]["tile_size"] for window in konveyor_windows()}
    return all(abs(frame[2] - targets[title][0]) < 1 for title, frame in frames().items() if title in targets)


def entered():
    return [line.split()[1] for line in EVENTS.read_text().splitlines() if line.startswith("ENTER ")] if EVENTS.exists() else []


def on_screen(frame):
    return any(intersects(frame, rect) for rect in outputs().values())


def inside(frame, rect):
    return frame[0] >= rect[0] and frame[1] >= rect[1] and frame[0] + frame[2] <= rect[0] + rect[2] and frame[1] + frame[3] <= rect[1] + rect[3]


def off_every_output():
    return not on_screen(frames()[TITLE])


def geometry_trail(seconds):
    """Every frame geometry TITLE had at the start of the window and took on during it."""
    watch = ('const w = workspace.windowList().find(w => !w.deleted && w.caption == "' + TITLE + '");'
             'const show = () => print("MARK|" + w.frameGeometry.x + "|" + w.frameGeometry.y + "|" + w.frameGeometry.width + "|" + w.frameGeometry.height);'
             'show(); w.frameGeometryChanged.connect(show);')
    return [tuple(float(value) for value in line.split("|")) for line in run_script(watch, seconds)]


def two_monitors(checks):
    """The real laptop layout: a scale 2 screen left of a scale 1.5 one, overlapping its tile rows vertically."""
    result = subprocess.run(["kscreen-doctor", f"output.{HOME}.scale.1.5", f"output.{OTHER}.scale.2"], capture_output=True, text=True)
    checks.expect(result.returncode == 0, f"{HOME} is scaled to 1.5 and {OTHER} to 2 ({result.stderr.strip()})")
    checks.expect(wait_for(lambda: outputs().get(HOME, (0, 0, 0, 0))[2] == 1280 and outputs().get(OTHER, (0, 0, 0, 0))[2] == 960),
                  f"{HOME} is 1280 and {OTHER} is 960 logical pixels wide ({outputs()})")
    result = subprocess.run(["kscreen-doctor", f"output.{HOME}.position.960,0", f"output.{OTHER}.position.0,360"], capture_output=True, text=True)
    checks.expect(result.returncode == 0, f"{OTHER} sits left of {HOME} ({result.stderr.strip()})")
    checks.expect(wait_for(lambda: outputs().get(HOME, (0, 0, 0, 0))[:2] == (960, 0) and outputs().get(OTHER, (0, 0, 0, 0))[:2] == (0, 360)),
                  f"{HOME} starts at x 960 and {OTHER} at y 360 ({outputs()})")


def open_row(checks):
    x, y, width, height = outputs()[HOME]
    move(x + width / 2, y + height / 2, settle=False)
    with EVENTS.open("w") as log:
        trackers.append(subprocess.Popen([str(build_dir() / "bin" / "output_tracking_client"), TITLE], stdout=log, stderr=subprocess.STDOUT))
    checks.expect(wait_for(lambda: TITLE in managed_titles(), 30), f"{TITLE} is managed")
    checks.expect(wait_for(lambda: "READY" in EVENTS.read_text().split(), 30), f"{TITLE} is mapped")
    for title in ("B", "C", "D"):
        open_client(title)
    checks.expect(wait_for(settled), "the layout settles with D focused")


def parked_window_stays_parked(checks):
    checks.expect(wait_for(off_every_output), f"{TITLE} is parked off every output ({frames()[TITLE]}, {outputs()})")
    parked_at = len(scales())
    entered_at = len(entered())
    time.sleep(SETTLE_SECONDS)
    trail = geometry_trail(WATCH_SECONDS)
    pulled_back = [frame for frame in trail if on_screen(frame)]
    checks.equal(pulled_back, [], f"{TITLE} stays off every output once parked ({len(trail)} frames in {WATCH_SECONDS}s, outputs {outputs()})")
    flips = scales()[parked_at:]
    checks.expect(len(flips) <= 1, f"parking {TITLE} changes its preferred scale at most once ({len(flips)} changes: {flips[:6]})")
    checks.equal(entered()[entered_at:], [], f"{TITLE}'s surface enters no output while it is parked")


def unparked_window_returns_to_its_tile(checks):
    checks.expect(activate(TITLE), f"{TITLE} is focused")
    checks.expect(wait_for(settled), f"the layout settles with {TITLE} focused")
    checks.expect(wait_for(lambda: inside(frames()[TITLE], outputs()[HOME])), f"{TITLE} is back on {HOME} ({frames()[TITLE]}, {outputs()[HOME]})")
    tile = next(window["layout"]["tile_size"] for window in konveyor_windows() if window["title"] == TITLE)
    trail = geometry_trail(WATCH_SECONDS)
    wandering = [frame for frame in trail if not inside(frame, outputs()[HOME]) or abs(frame[2] - tile[0]) >= 1]
    checks.equal(wandering, [], f"{TITLE} keeps its {tile[0]:.0f}px tile on {HOME} once unparked ({len(trail)} frames in {WATCH_SECONDS}s)")


def main():
    checks = Checks()
    try:
        checks.run(two_monitors, open_row, parked_window_stays_parked, unparked_window_returns_to_its_tile)
    finally:
        for tracker in trackers:
            tracker.terminate()


if __name__ == "__main__":
    main()
