"""Plan load analysis: weekly volume and intensity, and fitness projection.

Pure functions over plan files and daily fitness numbers; the plan_analyze
tool fetches the athlete data and calls these.

Load uses the plan's planned TSS (TrainingPeaks' numbers), because most coach
bike sessions target heart rate and %FTP-derived TSS doesn't exist for them.
Strength sessions carry no planned TSS, so totals understate load slightly.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from plan_format import Plan, Step

ENDURANCE_SPORTS = ("Swim", "Ride", "Run")
CTL_DAYS, ATL_DAYS = 42, 7

# Upper bounds (% of threshold) for "easy" and "moderate"; anything above is hard.
# Heart rate: below LTHR zone 3 is easy; power: below Coggan tempo; pace: below
# ~88% of threshold speed.
INTENSITY_BANDS = {"lthr": (90, 100), "ftp": (76, 91), "pace": (88, 97)}

VOLUME_JUMP = 0.20       # week-on-week increase in endurance hours worth flagging
RUN_JUMP = 0.30          # same, for run time alone
RECOVERY_DROP = 0.20     # a recovery week is at least this far below the block's peak
MAX_WEEKS_WITHOUT_RECOVERY = 4
DEEP_TSB = -30
STEEP_RAMP = 5.0         # CTL points per week


@dataclass
class Week:
    number: int
    hours: dict = field(default_factory=lambda: defaultdict(float))
    sessions: dict = field(default_factory=lambda: defaultdict(int))
    longest: dict = field(default_factory=lambda: defaultdict(float))
    tss: float = 0.0
    intensity_hours: dict = field(default_factory=lambda: defaultdict(float))
    ctl: float = 0.0
    atl: float = 0.0

    @property
    def endurance_hours(self) -> float:
        return sum(self.hours[s] for s in ENDURANCE_SPORTS)

    def to_dict(self) -> dict:
        total = sum(self.intensity_hours.values()) or 1
        return {
            "week": self.number,
            "hours": {s: round(self.hours[s], 1) for s in (*ENDURANCE_SPORTS, "WeightTraining") if self.hours[s]},
            "endurance_hours": round(self.endurance_hours, 1),
            "sessions": dict(self.sessions),
            "longest_hours": {s: round(self.longest[s], 1) for s in ("Ride", "Run") if self.longest[s]},
            "planned_tss": round(self.tss),
            "intensity_pct": {k: round(100 * self.intensity_hours[k] / total) for k in ("easy", "moderate", "hard")},
            "ctl_end": round(self.ctl, 1),
            "tsb_end": round(self.ctl - self.atl, 1),
        }


def _band(unit: str, pct: float | None) -> str:
    if pct is None:
        return "easy"
    easy, hard = INTENSITY_BANDS[unit]
    return "easy" if pct < easy else ("moderate" if pct < hard else "hard")


def _step_hours(step: Step, swim_threshold_mps: float, pct: float | None) -> float:
    if step.seconds is not None:
        return step.seconds / 3600
    return step.meters / (swim_threshold_mps * (pct or 80) / 100) / 3600


def weekly_stats(plan: Plan, swim_threshold_mps: float = 1.0) -> list[Week]:
    last_day = max((w.day for w in plan.workouts), default=0)
    weeks = [Week(number=i + 1) for i in range(last_day // 7 + 1)]
    for w in plan.workouts:
        wk = weeks[w.day // 7]
        hours = (w.planned_minutes or 0) / 60
        if w.sport == "Note" or not hours:
            continue
        wk.hours[w.sport] += hours
        wk.sessions[w.sport] += 1
        wk.longest[w.sport] = max(wk.longest[w.sport], hours)
        wk.tss += w.planned_tss or 0
        for b in w.blocks:
            for s in b.steps:
                pct = sum(s.target) / 2 if s.target else None
                wk.intensity_hours[_band(w.target_unit, pct)] += b.reps * _step_hours(s, swim_threshold_mps, pct)
    return weeks


def daily_load(plan: Plan) -> dict[int, float]:
    load = defaultdict(float)
    for w in plan.workouts:
        load[w.day] += w.planned_tss or 0
    return load


def project(weeks: list[Week], load: dict[int, float], ctl: float, atl: float, scale: float = 1.0) -> list[tuple[float, float]]:
    """Daily (CTL, ATL) through the plan, filling each week's end-of-week values."""
    days = []
    for d in range(len(weeks) * 7):
        l = load.get(d, 0) * scale
        ctl += (l - ctl) / CTL_DAYS
        atl += (l - atl) / ATL_DAYS
        days.append((ctl, atl))
    for wk in weeks:
        wk.ctl, wk.atl = days[wk.number * 7 - 1]
    return days


def load_from_atl(atl_by_day: list[tuple[date, float]]) -> dict[date, float]:
    """Back out daily training load from consecutive ATL values (ATL_t = ATL_{t-1} + (L - ATL_{t-1})/7)."""
    return {
        d1: ATL_DAYS * (a1 - a0) + a0
        for (_, a0), (d1, a1) in zip(atl_by_day, atl_by_day[1:])
    }


def max_sustained_ramp(ctl_by_day: list[tuple[date, float]], weeks: int = 4) -> float | None:
    """Largest average weekly CTL rise held over `weeks` weeks."""
    span = weeks * 7
    if len(ctl_by_day) <= span:
        return None
    return max((ctl_by_day[i + span][1] - ctl_by_day[i][1]) / weeks for i in range(len(ctl_by_day) - span))


def flags(weeks: list[Week], start_ctl: float) -> list[str]:
    out = []
    for prev, wk in zip(weeks, weeks[1:]):
        if prev.endurance_hours and wk.endurance_hours > prev.endurance_hours * (1 + VOLUME_JUMP):
            out.append(f"week {wk.number}: endurance hours jump {prev.endurance_hours:.1f} → {wk.endurance_hours:.1f} "
                       f"(+{100 * (wk.endurance_hours / prev.endurance_hours - 1):.0f}%)")
        if prev.hours["Run"] and wk.hours["Run"] > prev.hours["Run"] * (1 + RUN_JUMP):
            out.append(f"week {wk.number}: run time jumps {prev.hours['Run']:.1f} → {wk.hours['Run']:.1f} h "
                       f"(+{100 * (wk.hours['Run'] / prev.hours['Run'] - 1):.0f}%)")
    # Runs of weeks with no week at least RECOVERY_DROP below the run's peak.
    streaks, streak, peak = [], [], 0.0
    for wk in weeks:
        if peak and wk.endurance_hours <= peak * (1 - RECOVERY_DROP):
            streaks.append(streak)
            streak, peak = [], 0.0
            continue
        streak.append(wk.number)
        peak = max(peak, wk.endurance_hours)
    streaks.append(streak)
    for run in streaks:
        if len(run) > MAX_WEEKS_WITHOUT_RECOVERY:
            out.append(f"weeks {run[0]}-{run[-1]}: {len(run)} weeks with no recovery week "
                       f"(none {100 * RECOVERY_DROP:.0f}% below the block's peak)")
    prev_ctl = start_ctl
    for wk in weeks:
        if wk.ctl - prev_ctl > STEEP_RAMP:
            out.append(f"week {wk.number}: CTL ramp +{wk.ctl - prev_ctl:.1f}/week")
        if wk.ctl - wk.atl < DEEP_TSB:
            out.append(f"week {wk.number}: TSB {wk.ctl - wk.atl:.0f} at week end")
        prev_ctl = wk.ctl
    return out
