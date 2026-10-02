import json

import httpx
import pytest

from routers.trainingpeaks import plans

START = "2027-10-04"


def workout(workout_id, day, title="R ENDURANCE"):
    return {
        "workoutId": workout_id,
        "workoutDay": f"2027-10-{4 + day:02d}T00:00:00",
        "workoutTypeValueId": 3,
        "title": title,
        "structure": {
            "primaryIntensityMetric": "percentOfThresholdHr",
            "structure": [{
                "type": "step",
                "length": {"value": 1, "unit": "repetition"},
                "steps": [{"name": "Easy", "length": {"value": 1800, "unit": "second"},
                           "targets": [{"minValue": 70, "maxValue": 80}], "intensityClass": "active"}],
            }],
        },
    }


class FakeTP:
    """Just enough of TrainingPeaks' private API for tp_fetch_plan."""

    def __init__(self, existing=(), plan=(), fail_read=False):
        self.existing, self.plan, self.fail_read = list(existing), list(plan), fail_read
        self.applied = False
        self.calls = []

    def handler(self, request):
        path = request.url.path
        self.calls.append((request.method, path))
        if path == "/plans/v1/plans":
            return httpx.Response(200, json=[
                {"planId": 2, "title": "RECREATIONAL OFF SEASON 8-Weeks", "workoutCount": 89},
                {"planId": 1, "title": "COMPETITIVE OFF SEASON 4-Weeks", "workoutCount": 44},
                {"planId": 3, "title": "KONA 18 Weeks", "workoutCount": 274},
            ])
        if path == "/plans/v1/plans/459451":
            return httpx.Response(200, json={"planId": 459451, "title": "RECREATIONAL OFF SEASON 8-Weeks"})
        if path == "/plans/v1/commands/applyplan":
            assert json.loads(request.content)[0]["targetDate"] == START
            self.applied = True
            return httpx.Response(200, json=[{"appliedPlanId": "77", "startDate": f"{START}T00:00:00", "endDate": "2027-11-28T00:00:00"}])
        if path == "/plans/v1/commands/removeplan":
            assert json.loads(request.content) == {"appliedPlanId": "77"}
            self.applied = False
            return httpx.Response(200, json={})
        if path.startswith("/fitness/v6/athletes/42/workouts/"):
            if self.applied and self.fail_read:
                return httpx.Response(500, json={"message": "boom"})
            return httpx.Response(200, json=self.existing + (self.plan if self.applied else []))
        return httpx.Response(404)


@pytest.fixture
def fake_tp(monkeypatch, tmp_path):
    fake = FakeTP()
    monkeypatch.setattr(plans, "get_client", lambda: httpx.Client(
        base_url="https://tpapi.trainingpeaks.com", transport=httpx.MockTransport(fake.handler)))
    monkeypatch.setattr(plans, "tp_user_id", lambda: "42")
    monkeypatch.setenv("TP_PLANS_DIR", str(tmp_path))
    return fake


def test_list_plans_filters_on_every_word_and_sorts(fake_tp):
    result = json.loads(plans.tp_list_plans("off season"))
    assert [p["title"] for p in result] == ["COMPETITIVE OFF SEASON 4-Weeks", "RECREATIONAL OFF SEASON 8-Weeks"]
    assert result[0] == {"plan_id": "1", "title": "COMPETITIVE OFF SEASON 4-Weeks", "workouts": 44}
    assert len(json.loads(plans.tp_list_plans())) == 3


def test_fetch_saves_plan_and_removes_it_from_calendar(fake_tp, tmp_path):
    fake_tp.plan = [workout(1, 0), workout(2, 9)]
    summary = json.loads(plans.tp_fetch_plan("459451", start_date=START))
    assert summary["path"] == str(tmp_path / "recreational-off-season-8-weeks.json")
    assert (summary["workouts"], summary["weeks"], summary["structured"]) == (2, 2, 2)
    assert summary["left_on_calendar"] is None
    assert ("POST", "/plans/v1/commands/removeplan") in fake_tp.calls
    assert not fake_tp.applied
    saved = json.loads((tmp_path / "recreational-off-season-8-weeks.json").read_text())
    assert [w["day"] for w in saved["workouts"]] == [0, 9]
    assert saved["source"]["plan_id"] == "459451"


def test_fetch_leaves_out_workouts_already_on_calendar(fake_tp):
    fake_tp.existing = [workout(99, 2, title="My own run")]
    fake_tp.plan = [workout(1, 0)]
    summary = json.loads(plans.tp_fetch_plan("459451", start_date=START))
    assert summary["workouts"] == 1
    assert summary["skipped_existing_calendar_workouts"] == 1


def test_plan_is_removed_even_when_reading_fails(fake_tp):
    fake_tp.fail_read = True
    with pytest.raises(RuntimeError, match="HTTP 500"):
        plans.tp_fetch_plan("459451", start_date=START)
    assert not fake_tp.applied


def test_keep_on_calendar_skips_removal_and_needs_a_date(fake_tp):
    with pytest.raises(ValueError, match="explicit start_date"):
        plans.tp_fetch_plan("459451", keep_on_calendar=True)
    fake_tp.plan = [workout(1, 0)]
    summary = json.loads(plans.tp_fetch_plan("459451", start_date=START, keep_on_calendar=True))
    assert fake_tp.applied
    assert summary["left_on_calendar"] == "2027-10-04 to 2027-11-28"


def test_existing_file_is_not_overwritten_by_default(fake_tp, tmp_path):
    (tmp_path / "mine.json").write_text("edited")
    with pytest.raises(ValueError, match="already exists"):
        plans.tp_fetch_plan("459451", start_date=START, filename="mine.json")
    assert not any(call[1] == "/plans/v1/commands/applyplan" for call in fake_tp.calls)
    fake_tp.plan = [workout(1, 0)]
    plans.tp_fetch_plan("459451", start_date=START, filename="mine.json", overwrite=True)
    assert (tmp_path / "mine.json").read_text() != "edited"


def test_default_start_is_a_monday_about_a_year_out():
    start = plans._next_monday_a_year_out()
    assert start.weekday() == 0
    assert 365 <= (start - plans.date.today()).days < 372
