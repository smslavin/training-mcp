import json

import httpx
import pytest

import plan_format as pf
from plan_format import Block, Plan, Step, Workout
from routers.intervals import plans as push

KEY = "off-season"


def make_plan(*workouts):
    return Plan(format_version=1, name="Off season", workouts=list(workouts))


RIDE = Workout(day=1, sport="Ride", title="B ENDURANCE", target_unit="lthr", planned_minutes=75, source_id="101",
               blocks=[Block(steps=[Step(name="ENDURANCE", seconds=4500, target=(50, 85))])])
ADDED_RUN = Workout(day=2, sport="Run", title="R ENDURANCE 30min (added)", target_unit="lthr", planned_minutes=30,
                    blocks=[Block(steps=[Step(name="Endurance", seconds=1800, target=(73, 89))])])
DAY_OFF = Workout(day=4, sport="Note", title="Day off", source_id="103")
REST_PLACEHOLDER = Workout(day=4, sport="Ride", title="REST: Post training rest", planned_minutes=0, source_id="104")


class FakeIntervals:
    def __init__(self, existing=()):
        self.events = {e["id"]: e for e in existing}
        self.next_id = 1000
        self.calls = []

    def handler(self, request):
        self.calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=list(self.events.values()))
        if request.method == "POST":
            for e in json.loads(request.content):
                self.next_id += 1
                self.events[self.next_id] = {**e, "id": self.next_id}
            return httpx.Response(200, json=[])
        event_id = int(request.url.path.rsplit("/", 1)[1])
        if request.method == "PUT":
            self.events[event_id].update(json.loads(request.content))
        else:
            del self.events[event_id]
        return httpx.Response(200, json={})


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("TP_PLANS_DIR", str(tmp_path))

    def install(plan, existing=()):
        pf.save_plan(plan, tmp_path / f"{KEY}.json")
        fake = FakeIntervals(existing)
        monkeypatch.setattr(push, "get_client", lambda: httpx.Client(transport=httpx.MockTransport(fake.handler)))
        monkeypatch.setattr(push, "athlete_id", lambda override=None: "i1")
        return fake

    return install


def run(**kw):
    return json.loads(push.plan_push_to_intervals(f"{KEY}.json", "2026-10-05", **kw))


def test_events_have_dates_types_and_stable_ids():
    events = push.build_events(KEY, make_plan(RIDE, ADDED_RUN, DAY_OFF, REST_PLACEHOLDER), pf.date(2026, 10, 5))
    assert [(e.date, e.type, e.category, e.external_id) for e in events] == [
        ("2026-10-06", "Ride", "WORKOUT", "plan:off-season:101"),
        ("2026-10-07", "Run", "WORKOUT", "plan:off-season:d2-run-1"),
        ("2026-10-09", "Other", "NOTE", "plan:off-season:103"),
        ("2026-10-09", "Other", "NOTE", "plan:off-season:104"),
    ]
    assert events[0].moving_time == 4500 and events[2].moving_time is None


def test_dry_run_writes_nothing(setup):
    fake = setup(make_plan(RIDE, ADDED_RUN))
    summary = run()
    assert (summary["dry_run"], summary["created"]) == (True, 2)
    assert [m for m, _ in fake.calls] == ["GET"]


def test_push_creates_then_updates_in_place(setup):
    fake = setup(make_plan(RIDE, ADDED_RUN))
    assert run(dry_run=False)["created"] == 2
    again = run(dry_run=False)
    assert (again["created"], again["updated"], again["deleted"]) == (0, 2, 0)
    assert len(fake.events) == 2


def test_removed_workouts_are_pruned_but_other_events_are_not(setup):
    mine_stale = {"id": 1, "external_id": "plan:off-season:999", "name": "dropped swim"}
    other_plan = {"id": 2, "external_id": "plan:other-plan:5", "name": "other plan"}
    manual = {"id": 3, "external_id": None, "name": "my own ride"}
    fake = setup(make_plan(RIDE), existing=[mine_stale, other_plan, manual])
    summary = run(dry_run=False)
    assert (summary["created"], summary["deleted"]) == (1, 1)
    assert set(fake.events) - {1001} == {2, 3}
    assert run(dry_run=True, prune=False)["deleted"] == 0


def test_options_reach_the_workout_text(setup):
    setup(make_plan(RIDE))
    sample = run(bike_hr_as_power=True)["sample"]
    assert "LTHR" not in sample["description"] and "40-66%" in sample["description"]
