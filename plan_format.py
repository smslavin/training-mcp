"""On-disk training plan format.

A plan is a template: workouts sit on day offsets from a start date chosen at
push time. Files are JSON written one step per line, so a diff between the
coach's original and an edited copy shows exactly which steps changed.

    {
      "format_version": 1,
      "name": "RECREATIONAL OFF SEASON 8-Weeks",
      "source": {"platform": "trainingpeaks", "plan_id": "459451", ...},
      "workouts": [
        {
          "day": 0,
          "sport": "Ride",
          "title": "B BASIC ENDURANCE",
          "planned_minutes": 71.0,
          "planned_tss": 47.3,
          "target_unit": "lthr",
          "blocks": [
            {
              "steps": [
                {"kind": "warmup", "name": "Warmup", "seconds": 1800, "target": [50, 75], "cadence": [80, 100]}
              ]
            },
            {
              "reps": 7,
              "steps": [
                {"name": "MAIN SET #1", "seconds": 30, "target": [75, 86]},
                {"kind": "rest", "name": "Rest", "seconds": 30, "target": [69, 69]}
              ]
            }
          ]
        }
      ]
    }

Targets are percent of threshold in the workout's target_unit (ftp, lthr or
pace); [lo, hi] with lo == hi for a single value; omitted for a plain rest.
"""

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, model_validator

# intervals.icu event types, since intervals.icu is where plans end up.
# "Note" is a day off or other text-only calendar entry.
Sport = Literal[
    "Swim",
    "Ride",
    "Run",
    "MountainBikeRide",
    "WeightTraining",
    "NordicSki",
    "Rowing",
    "Walk",
    "Note",
    "Other",
]
TargetUnit = Literal["ftp", "lthr", "pace"]
Number = int | float  # keeps whole-number targets like 75 from rendering as 75.0
StepKind = Literal["warmup", "active", "rest", "cooldown"]


class Step(BaseModel):
    kind: StepKind = "active"
    name: Optional[str] = None
    seconds: Optional[int] = None
    meters: Optional[int] = None
    target: Optional[tuple[Number, Number]] = None
    cadence: Optional[tuple[Number, Number]] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _one_length(self):
        if (self.seconds is None) == (self.meters is None):
            raise ValueError("a step needs exactly one of seconds or meters")
        return self


class Block(BaseModel):
    reps: int = 1
    steps: list[Step]


class Workout(BaseModel):
    day: int
    sport: Sport
    title: str
    description: Optional[str] = None
    coach_comments: Optional[str] = None
    planned_minutes: Optional[float] = None
    planned_tss: Optional[float] = None
    planned_if: Optional[float] = None
    target_unit: Optional[TargetUnit] = None
    blocks: list[Block] = []
    # Workout id on the source platform; keeps pushes idempotent after edits.
    source_id: Optional[str] = None

    @model_validator(mode="after")
    def _unit_when_structured(self):
        if self.blocks and self.target_unit is None:
            raise ValueError(
                f"day {self.day} '{self.title}': structured workouts need a target_unit"
            )
        return self


class PlanSource(BaseModel):
    platform: Literal["trainingpeaks"]
    plan_id: str
    title: str
    fetched: date


class Plan(BaseModel):
    format_version: Literal[1]
    name: str
    source: Optional[PlanSource] = None
    workouts: list[Workout]


# --- TrainingPeaks → plan -------------------------------------------------

TP_SPORTS: dict[int, Sport] = {
    1: "Swim",
    2: "Ride",
    3: "Run",
    4: "Other",
    5: "Other",
    7: "Note",
    8: "MountainBikeRide",
    9: "WeightTraining",
    11: "NordicSki",
    12: "Rowing",
    13: "Walk",
    100: "Other",
}
TP_TARGET_UNITS: dict[str, TargetUnit] = {
    "percentOfFtp": "ftp",
    "percentOfThresholdHr": "lthr",
    "percentOfThresholdPace": "pace",
}
TP_STEP_KINDS: dict[str, StepKind] = {
    "warmUp": "warmup",
    "active": "active",
    "rest": "rest",
    "coolDown": "cooldown",
}
TP_CADENCE_UNIT = "roundOrStridePerMinute"


def _tp_range(t: dict) -> Optional[tuple[Number, Number]]:
    lo, hi = t.get("minValue"), t.get("maxValue")
    lo, hi = (lo if lo is not None else hi), (hi if hi is not None else lo)
    if lo is None or (lo == 0 and hi == 0):  # TP writes plain rests as a 0% target
        return None
    return (_whole(lo), _whole(hi))


def _whole(v: Number) -> Number:
    # TP sends some targets (cadence) as 80.0; keep the file free of ".0" noise.
    return int(v) if float(v).is_integer() else v


def _tp_step(s: dict) -> Step:
    length = s["length"]
    if length["unit"] not in ("second", "meter"):
        raise ValueError(f"unsupported step length unit {length['unit']!r}")
    main = next((t for t in s.get("targets", []) if t.get("unit") is None), None)
    cadence = next(
        (t for t in s.get("targets", []) if t.get("unit") == TP_CADENCE_UNIT), None
    )
    return Step(
        kind=TP_STEP_KINDS.get(s.get("intensityClass"), "active"),
        name=s.get("name") or None,
        seconds=int(length["value"]) if length["unit"] == "second" else None,
        meters=int(length["value"]) if length["unit"] == "meter" else None,
        target=_tp_range(main) if main else None,
        cadence=_tp_range(cadence) if cadence else None,
        notes=(s.get("notes") or "").strip() or None,
    )


def _tp_blocks(structure: dict) -> list[Block]:
    blocks = []
    for b in structure["structure"]:
        if b["type"] not in ("step", "repetition", "rampUp", "rampDown"):
            raise ValueError(f"unsupported block type {b['type']!r}")
        length = b.get("length") or {}
        reps = int(length["value"]) if length.get("unit") == "repetition" else 1
        blocks.append(Block(reps=reps, steps=[_tp_step(s) for s in b["steps"]]))
    return blocks


def _round(v: Optional[float], digits: int) -> Optional[float]:
    return round(v, digits) if v is not None else None


def plan_from_tp(
    tp_workouts: list[dict], plan_id: str, title: str, start: date
) -> tuple[Plan, list[str]]:
    """Map TrainingPeaks calendar workouts from an applied plan to a Plan.

    Returns the plan plus a warning per workout whose structure could not be
    mapped; those keep their description but lose their steps.
    """
    warnings = []
    workouts = []
    ordered = sorted(
        tp_workouts, key=lambda w: (w["workoutDay"], w.get("orderOnDay") or 0)
    )
    for w in ordered:
        day = (datetime.fromisoformat(w["workoutDay"]).date() - start).days
        title_ = (w.get("title") or "").strip() or "Workout"
        target_unit, blocks = None, []
        structure = w.get("structure") or {}
        if structure.get("structure"):
            try:
                metric = structure.get("primaryIntensityMetric")
                if metric not in TP_TARGET_UNITS:
                    raise ValueError(f"unsupported intensity metric {metric!r}")
                target_unit, blocks = TP_TARGET_UNITS[metric], _tp_blocks(structure)
            except (ValueError, KeyError) as e:
                warnings.append(f"day {day} '{title_}': steps dropped ({e})")
                target_unit, blocks = None, []
        hours = w.get("totalTimePlanned")
        workouts.append(
            Workout(
                day=day,
                sport=TP_SPORTS.get(w.get("workoutTypeValueId"), "Other"),
                title=title_,
                description=(w.get("description") or "").strip() or None,
                coach_comments=(w.get("coachComments") or "").strip() or None,
                planned_minutes=_round(hours * 60 if hours else None, 1),
                planned_tss=_round(w.get("tssPlanned"), 1),
                planned_if=_round(w.get("ifPlanned"), 3),
                target_unit=target_unit,
                blocks=blocks,
                source_id=str(w["workoutId"]),
            )
        )
    plan = Plan(
        format_version=1,
        name=title,
        source=PlanSource(
            platform="trainingpeaks",
            plan_id=str(plan_id),
            title=title,
            fetched=date.today(),
        ),
        workouts=workouts,
    )
    return plan, warnings


# --- Files ----------------------------------------------------------------


def plans_dir() -> Path:
    """Where plan files live. Coach plans are licensed content, so the default
    sits inside the repo but is git-ignored; point TP_PLANS_DIR at a private
    repo to keep edit history."""
    return Path(
        os.getenv("TP_PLANS_DIR") or Path(__file__).parent / "plans"
    ).expanduser()


def load_plan(path: str | Path) -> Plan:
    return Plan.model_validate_json(Path(path).read_text())


def _render(value, level: int = 0, items_inline: bool = False) -> str:
    """Indented JSON, except scalar lists and step objects stay on one line."""
    compact = json.dumps(value, ensure_ascii=False)
    if not isinstance(value, (dict, list)) or (
        isinstance(value, list) and all(not isinstance(v, (dict, list)) for v in value)
    ):
        return compact
    pad, close = "  " * (level + 1), "  " * level
    if isinstance(value, dict):
        # Steps are the unit of editing, so each step renders as one line.
        items = [
            f"{pad}{json.dumps(k)}: {_render(v, level + 1, items_inline=(k == 'steps'))}"
            for k, v in value.items()
        ]
        return "{\n" + ",\n".join(items) + "\n" + close + "}"
    items = [
        f"{pad}{json.dumps(v, ensure_ascii=False) if items_inline else _render(v, level + 1)}"
        for v in value
    ]
    return "[\n" + ",\n".join(items) + "\n" + close + "]"


def dump_plan(plan: Plan) -> str:
    return (
        _render(plan.model_dump(mode="json", exclude_none=True, exclude_defaults=True))
        + "\n"
    )


def save_plan(plan: Plan, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_plan(plan))
    return path
