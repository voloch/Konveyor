#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))

from checks import Checks
from dragging import dragging, grab_point
from fakepointer import move
from kwinsession import activate, frames, intersects, konveyor, konveyor_action, konveyor_windows, managed_titles, open_client, wait_for
from nested import build_dir

ROOT = Path(os.environ["KONVEYOR_TEST_ROOT"])
EVENTS = ROOT / "output-events.txt"
HOME = "Virtual-0"
OTHER = "Virtual-1"
TITLE = "A"
QUIET_SECONDS = 5
trackers = []


def outputs():
    return {entry["name"]: (entry["logical"]["x"], entry["logical"]["y"], entry["logical"]["width"], entry["logical"]["height"])
            for entry in json.loads(konveyor("Outputs"))}


def events():
    return [line for line in EVENTS.read_text().splitlines() if line.startswith(("ENTER ", "LEAVE "))] if EVENTS.exists() else []


def entered():
    names = set()
    for event, name in (line.split(" ", 1) for line in events()):
        if event == "ENTER":
            names.add(name)
        else:
            names.discard(name)
    return names


def settled():
    targets = {window["title"]: window["layout"]["tile_size"] for window in konveyor_windows()}
    return all(abs(frame[2] - targets[title][0]) < 1 for title, frame in frames().items() if title in targets)


def off_every_output():
    frame = frames()[TITLE]
    return not any(intersects(frame, rect) for rect in outputs().values())


def inside(frame, rect):
    return rect[0] <= frame[0] and rect[1] <= frame[1] and frame[0] + frame[2] <= rect[0] + rect[2] and frame[1] + frame[3] <= rect[1] + rect[3]


def still():
    samples = []

    def unchanged():
        samples.append(frames()[TITLE])
        return len(samples) >= 4 and len(set(samples[-4:])) == 1

    return wait_for(unchanged, 20, 0.3)


def reports(names):
    return wait_for(lambda: entered() == names, 3)


def two_monitors(checks):
    result = subprocess.run(["kscreen-doctor", f"output.{HOME}.scale.1.5", f"output.{OTHER}.scale.2"], capture_output=True, text=True)
    checks.expect(result.returncode == 0, f"{HOME} is scaled to 1.5 and {OTHER} to 2 ({result.stderr.strip()})")
    checks.expect(wait_for(lambda: outputs().get(HOME, (0, 0, 0, 0))[2] == 1280 and outputs().get(OTHER, (0, 0, 0, 0))[2] == 960),
                  f"{HOME} is 1280 and {OTHER} is 960 logical pixels wide ({outputs()})")
    result = subprocess.run(["kscreen-doctor", f"output.{OTHER}.position.1280,0"], capture_output=True, text=True)
    checks.expect(result.returncode == 0, f"{OTHER} sits right of {HOME} ({result.stderr.strip()})")
    checks.expect(wait_for(lambda: outputs().get(OTHER, (0, 0, 0, 0))[:2] == (1280, 0)), f"{OTHER} starts at x 1280 ({outputs()})")


def open_row(checks):
    x, y, width, height = outputs()[HOME]
    move(x + width / 2, y + height / 2, settle=False)
    with EVENTS.open("w") as log:
        trackers.append(subprocess.Popen([str(build_dir() / "bin" / "output_tracking_client"), TITLE], stdout=log, stderr=subprocess.STDOUT))
    checks.expect(wait_for(lambda: TITLE in managed_titles(), 30), f"{TITLE} is managed")
    checks.expect(wait_for(lambda: "READY" in EVENTS.read_text().split(), 30), f"{TITLE} is mapped")
    reports({HOME})
    checks.equal(entered(), {HOME}, f"{TITLE} on screen reports being on {HOME} only")
    for title in ("B", "C", "D"):
        open_client(title)
    checks.expect(wait_for(settled), "the layout settles with D focused")


def parked_window_keeps_its_home_output(checks):
    checks.expect(wait_for(off_every_output), f"{TITLE} is parked off every output ({frames()[TITLE]}, {outputs()})")
    checks.expect(still(), f"{TITLE} stops moving while parked")
    time.sleep(1)
    checks.equal(entered(), {HOME}, f"parked {TITLE} reports being on {HOME} only")
    count = len(events())
    time.sleep(QUIET_SECONDS)
    checks.equal(events()[count:], [], f"parked {TITLE} gets no leave or enter for {QUIET_SECONDS} seconds")


def scrolling_back_restores_tracking(checks):
    checks.expect(activate(TITLE), f"{TITLE} gets focus")
    checks.expect(wait_for(settled), f"the layout settles with {TITLE} focused")
    checks.expect(wait_for(lambda: inside(frames()[TITLE], outputs()[HOME])), f"{TITLE} is fully on {HOME} ({frames()[TITLE]})")
    checks.expect(still(), f"{TITLE} stops moving")
    reports({HOME})
    checks.equal(entered(), {HOME}, f"{TITLE} scrolled back reports being on {HOME} only")


def floating_window_across_both_monitors(checks):
    error = konveyor_action("toggle-window-floating")
    checks.expect(not error, f"{TITLE} turns floating ({error})")
    checks.expect(still(), f"floating {TITLE} stops moving")
    home = outputs()[HOME]
    start = grab_point(TITLE)
    with dragging(TITLE, (home[0] + home[2], start[1]), grab=start):
        pass
    checks.expect(wait_for(lambda: all(intersects(frames()[TITLE], rect) for rect in outputs().values())),
                  f"{TITLE} spans both outputs ({frames()[TITLE]}, {outputs()})")
    reports({HOME, OTHER})
    checks.equal(entered(), {HOME, OTHER}, f"floating {TITLE} reports being on {HOME} and {OTHER}")


def main():
    checks = Checks()
    try:
        checks.run(two_monitors, open_row, parked_window_keeps_its_home_output, scrolling_back_restores_tracking,
                   floating_window_across_both_monitors)
    finally:
        for tracker in trackers:
            tracker.terminate()


if __name__ == "__main__":
    main()
