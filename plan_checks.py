"""Sanity checks for plan files.

Coach plans carry data-entry errors that TrainingPeaks happily computes with,
e.g. a technique swim entered as 50000 m reps, which TP turned into a 705-hour,
TSS 42983 session. The same checks catch slips in hand-edited plans.
"""
from plan_format import Plan, Workout

MAX_SWIM_STEP_METERS = 5000
MAX_STEP_SECONDS = 6 * 3600
MAX_WORKOUT_MINUTES = 8 * 60
MAX_WORKOUT_TSS = 400
MAX_TARGET_PCT = 200


def _label(w: Workout) -> str:
    return f"day {w.day} {w.sport} '{w.title}'"


def _fix_thousandfold_swim(w: Workout) -> bool:
    """Divide 1000x swim distances back down; True if anything changed.

    Only applies when every distance step is a whole multiple of 1000 and at
    least one is implausible, which is what a meters-vs-kilometers slip looks
    like. TP's planned time and TSS were computed from the bad distances, so
    scale them by the corrected swim time (rest steps are unaffected).
    """
    dist = [s for b in w.blocks for s in b.steps if s.meters]
    if not dist or not any(s.meters > MAX_SWIM_STEP_METERS for s in dist):
        return False
    if any(s.meters % 1000 for s in dist):
        return False
    for s in dist:
        s.meters //= 1000
    if w.planned_minutes:
        rest_min = sum(b.reps * (s.seconds or 0) for b in w.blocks for s in b.steps) / 60
        old = w.planned_minutes
        w.planned_minutes = round((old - rest_min) / 1000 + rest_min, 1)
        if w.planned_tss:
            w.planned_tss = round(w.planned_tss * w.planned_minutes / old, 1)
    return True


def check_plan(plan: Plan, fix: bool = False) -> list[str]:
    """Warnings for implausible values; with fix, repair 1000x swim distances in place."""
    warnings = []
    for w in plan.workouts:
        if fix and w.sport == "Swim" and _fix_thousandfold_swim(w):
            warnings.append(f"{_label(w)}: swim distances were 1000x too large; divided by 1000 "
                            f"(now {w.planned_minutes} min, TSS {w.planned_tss})")
        steps = [s for b in w.blocks for s in b.steps]
        long_swims = [s.meters for s in steps if w.sport == "Swim" and s.meters and s.meters > MAX_SWIM_STEP_METERS]
        if long_swims:
            warnings.append(f"{_label(w)}: {len(long_swims)} swim steps over {MAX_SWIM_STEP_METERS} m "
                            f"(up to {max(long_swims)} m)")
        long_steps = [s.seconds for s in steps if s.seconds and s.seconds > MAX_STEP_SECONDS]
        if long_steps:
            warnings.append(f"{_label(w)}: {len(long_steps)} steps over {MAX_STEP_SECONDS // 3600} h "
                            f"(up to {max(long_steps) / 3600:.1f} h)")
        high = [max(s.target) for s in steps if s.target and max(s.target) > MAX_TARGET_PCT]
        if high:
            warnings.append(f"{_label(w)}: {len(high)} steps target over {MAX_TARGET_PCT}% of threshold "
                            f"(up to {max(high)}%)")
        if w.planned_minutes and w.planned_minutes > MAX_WORKOUT_MINUTES:
            warnings.append(f"{_label(w)}: planned {w.planned_minutes / 60:.1f} h")
        if w.planned_tss and w.planned_tss > MAX_WORKOUT_TSS:
            warnings.append(f"{_label(w)}: planned TSS {w.planned_tss}")
        if w.planned_minutes and steps and not any(s.meters for s in steps):
            step_min = sum(b.reps * s.seconds for b in w.blocks for s in b.steps) / 60
            if abs(step_min - w.planned_minutes) > max(10, 0.25 * w.planned_minutes):
                warnings.append(f"{_label(w)}: steps add up to {step_min:.0f} min "
                                f"but planned time is {w.planned_minutes:.0f} min")
    return warnings
