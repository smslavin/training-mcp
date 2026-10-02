"""Plan workouts → intervals.icu workout text.

intervals.icu parses a workout from the event description, one step per line:

    Warmup
    - Warmup 30m 50-75% LTHR 80-100rpm

    MAIN SET 7x
    - MAIN SET 30s 75-86% LTHR 110-115rpm
    - Rest 30s 69% LTHR

Verified live for Ride, Run and Swim (spike tm-cgg.3). "m" means minutes, so
distances are written as "400mtr", and a rest step with no target is a plain rest.
"""
import re
from bisect import bisect_right

from plan_format import Block, Step, Workout

UNIT_SUFFIX = {"ftp": "%", "lthr": "% LTHR", "pace": "% Pace"}
RIDE_SPORTS = {"Ride", "MountainBikeRide"}

# Bike %LTHR → %FTP, matching Friel heart-rate zone edges to Coggan power zone
# edges (Z1/Z2 at 81% LTHR ≈ 56% FTP, Z2/Z3 89% ≈ 75%, Z3/Z4 93% ≈ 90%,
# threshold 100% ≈ 105% top of Z4, 106% ≈ 120% top of Z5). Heart rate lags and
# drifts, so this is an approximation; it exists because Zwift only takes
# power-based workouts.
_LTHR_TO_FTP = [(0, 0), (50, 40), (81, 56), (89, 75), (93, 90), (100, 105), (106, 120), (130, 150)]


def lthr_to_ftp(pct: float) -> int:
    xs = [x for x, _ in _LTHR_TO_FTP]
    i = min(max(bisect_right(xs, pct), 1), len(xs) - 1)
    (x0, y0), (x1, y1) = _LTHR_TO_FTP[i - 1], _LTHR_TO_FTP[i]
    return round(y0 + (y1 - y0) * (pct - x0) / (x1 - x0))


def _length(step: Step) -> str:
    if step.meters is not None:
        return f"{step.meters}mtr"
    h, rem = divmod(step.seconds, 3600)
    m, s = divmod(rem, 60)
    return "".join(f"{n}{u}" for n, u in ((h, "h"), (m, "m"), (s, "s")) if n) or "0s"


# A number glued to a unit ("4x50m", "25s", "90%") in cue text would be read as
# the step's duration or target, so split the number from the unit.
_UNIT_TOKEN = re.compile(r"(\d)(mtr|km|mi|m|s|h|w|%|rpm|bpm)\b", re.I)


def _clean(text: str | None) -> str:
    return _UNIT_TOKEN.sub(r"\1 \2", " ".join((text or "").split())).strip(" -")


def _cue(step: Step) -> str:
    name, notes = _clean(step.name), _clean(step.notes)
    return f"{name}: {notes}" if name and notes else name or notes


def _fmt(v: float) -> str:
    return f"{v:g}"


def _step_line(step: Step, unit: str, convert) -> str:
    parts = ["-", _cue(step), _length(step)]
    if step.target:
        lo, hi = (convert(v) for v in step.target)
        parts.append((_fmt(lo) if lo == hi else f"{_fmt(lo)}-{_fmt(hi)}") + UNIT_SUFFIX[unit])
    if step.cadence:
        lo, hi = step.cadence
        parts.append(f"{_fmt(lo)}rpm" if lo == hi else f"{_fmt(lo)}-{_fmt(hi)}rpm")
    return " ".join(p for p in parts if p)


def _block_header(block: Block) -> str:
    first = block.steps[0]
    if block.reps > 1:
        return f"{_clean(first.name) or 'Set'} {block.reps}x"
    return {"warmup": "Warmup", "cooldown": "Cooldown"}.get(first.kind, "")


def effective_unit(workout: Workout, run_pace_as_power: bool, bike_hr_as_power: bool):
    """Target unit to write, plus a function mapping plan values into it."""
    unit = workout.target_unit
    if workout.sport == "Run" and unit == "pace" and run_pace_as_power:
        # Running power tracks speed on the flat, so % threshold pace ≈ % FTP.
        return "ftp", lambda v: v
    if workout.sport in RIDE_SPORTS and unit == "lthr" and bike_hr_as_power:
        return "ftp", lthr_to_ftp
    return unit, lambda v: v


def workout_text(workout: Workout, run_pace_as_power: bool = False, bike_hr_as_power: bool = False) -> str:
    """intervals.icu description for a workout: steps first, then the coach's notes."""
    sections = []
    if workout.blocks:
        unit, convert = effective_unit(workout, run_pace_as_power, bike_hr_as_power)
        for block in workout.blocks:
            lines = [_block_header(block)] if _block_header(block) else []
            lines += [_step_line(s, unit, convert) for s in block.steps]
            sections.append("\n".join(lines))
    notes = "\n\n".join(t for t in (workout.description, workout.coach_comments) if t)
    if notes:
        sections.append(_as_plain_text(notes))
    return "\n\n".join(sections)


def _as_plain_text(text: str) -> str:
    """Keep free text from being parsed as workout steps or repeat headers."""
    out = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("-"):
            line = "• " + stripped.lstrip("- ")
        # Numbered lines ("1. 25m drill") are parsed as steps when they hold
        # a duration, so renumber them and split numbers from units.
        line = re.sub(r"^(\s*\d+)\.(\s)", r"\1)\2", line)
        line = _UNIT_TOKEN.sub(r"\1 \2", line)
        if re.search(r"\d+\s*x\s*$", line, re.I):  # "Main set 4x" would start a repeat
            line += "."
        out.append(line)
    return "\n".join(out)


def planned_seconds(workout: Workout) -> int | None:
    return round(workout.planned_minutes * 60) if workout.planned_minutes else None
