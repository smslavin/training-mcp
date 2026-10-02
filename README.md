# training-mcp

MCP server for training data — Strava activities, intervals.icu wellness and analytics, HRV4Training metrics, cross-source correlations, and TrainingPeaks training plans you can analyze, edit and push to intervals.icu. Consolidates three separate servers (strava-mcp, intervals-mcp, analytics-mcp) into one process.

## Tools

**Strava** (`strava_*`)
- `strava_list_activities`, `strava_get_activity`, `strava_get_activity_laps`, `strava_get_activity_streams`, `strava_get_activity_zones`, `strava_get_activity_comments`, `strava_get_activity_kudos`, `strava_update_activity`
- `strava_get_athlete`, `strava_get_athlete_stats`, `strava_get_athlete_zones`
- `strava_get_gear`, `strava_list_athlete_gear`, `strava_get_gear_maintenance_status`
- `strava_list_routes`, `strava_get_route`, `strava_get_route_streams`
- `strava_get_segment`, `strava_get_segment_effort`, `strava_list_segment_efforts`, `strava_list_starred_segments`, `strava_get_activity_segment_efforts`

**intervals.icu** (`intervals_*`)
- `intervals_list_activities`, `intervals_search_activities`, `intervals_search_activities_full`, `intervals_interval_search_activities`, `intervals_get_activities_by_ids`
- `intervals_get_activity`, `intervals_update_activity`, `intervals_delete_activity`
- `intervals_get_activity_streams`, `intervals_get_activity_intervals`, `intervals_get_activity_interval_stats`
- `intervals_get_activity_best_efforts`, `intervals_get_activity_power_curve`, `intervals_get_activity_hr_curve`, `intervals_get_activity_pace_curve`
- `intervals_get_activity_power_histogram`, `intervals_get_activity_hr_histogram`, `intervals_get_activity_pace_histogram`, `intervals_get_activity_power_vs_hr`, `intervals_get_activity_time_at_hr`
- `intervals_get_activity_map`, `intervals_get_activity_weather`, `intervals_get_activity_segments`
- `intervals_get_activity_messages`, `intervals_post_activity_message`
- `intervals_get_athlete`
- `intervals_list_wellness`, `intervals_get_wellness`, `intervals_update_wellness`, `intervals_bulk_update_wellness`, `intervals_wellness_trend_alert`
- `intervals_create_workout`, `intervals_create_workouts_bulk`, `intervals_list_events`

**TrainingPeaks plans** (`tp_*`)
- `tp_list_plans` — plans in the TrainingPeaks account (e.g. a coaching program's library), filtered by title words
- `tp_fetch_plan` — save a plan's workouts as a plan file; repairs obvious coach data-entry errors and reports them

**Plan files** (`plan_*`)
- `plan_check` — flag implausible values in a plan file (e.g. after editing it)
- `plan_analyze` — compare plans against current and past fitness: weekly volume, intensity, CTL/ATL/TSB projection, and flags for risky weeks
- `plan_push_to_intervals` — put a plan on the intervals.icu calendar; re-pushing an edited plan updates it in place

**HRV4Training**
- `get_hrv_data` — daily HRV metrics, sleep, and subjective wellness markers from a local CSV or Dropbox

**Analytics**
- `correlate_hrv_with_performance` — HRV vs normalized power and HR efficiency (Pearson r)
- `training_load_vs_sleep` — CTL/ATL/form vs sleep score (Pearson r)
- `fitness_vs_segment_prs` — CTL/ATL/form vs Strava segment effort times (Pearson r)

## Setup

### 1. Create the conda environment

```bash
conda env create -f environment.yml
conda activate training-mcp
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Where to find it |
|---|---|
| `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` | [Strava API settings](https://www.strava.com/settings/api) |
| `INTERVALS_ATHLETE_ID` | intervals.icu URL: `/athlete/iXXXXXX/...` |
| `INTERVALS_API_KEY` | intervals.icu Settings → API |
| `DROPBOX_APP_KEY` / `DROPBOX_APP_SECRET` | [Dropbox App Console](https://www.dropbox.com/developers/apps) |
| `TP_AUTH_COOKIE` | TrainingPeaks login cookie — see [Connect TrainingPeaks](#5-connect-trainingpeaks-optional) |
| `TP_PLANS_DIR` | Optional. Where plan files live; defaults to `plans/` in this repo |

### 3. Authorize Strava

```bash
conda activate training-mcp
python auth_strava.py
```

A browser window opens. Authorize, and tokens are written to `.env` automatically. Tokens refresh automatically on expiry — you only need to run this once.

### 4. Authorize Dropbox (if using HRV via Dropbox)

```bash
python auth_dropbox.py
```

Same flow — browser opens, tokens saved to `.env`.

**Alternative:** Set `HRV4TRAINING_CSV_DIR` in `.env` to a local directory containing HRV4Training CSV exports, and skip Dropbox entirely.

### 5. Connect TrainingPeaks (optional)

TrainingPeaks has no public athlete API. The `tp_*` tools use the private API behind the TrainingPeaks web app (the same approach as [tp2intervals](https://github.com/freekode/tp2intervals)), authenticated with your browser's login cookie. It can change without notice.

1. Log in at [app.trainingpeaks.com](https://app.trainingpeaks.com) and open your browser's dev tools.
2. In **Network**, tick **Preserve log**, reload the page, and select the request to `tpapi.trainingpeaks.com/users/v3/token`.
3. Under **Request Headers**, copy the whole **Cookie** value, or open the request's **Cookies** tab and copy just `Production_tpAuth`.
   - Firefox shortens long header values with `...` in the Headers view. Use right-click → **Copy Value**, not a text selection.
4. Paste it into `.env`, in quotes:

   ```
   TP_AUTH_COOKIE="Production_tpAuth=..."
   ```

The whole Cookie header works too; tracking cookies in it are ignored. The server trades the cookie for a one-hour token and renews it as needed. When TrainingPeaks logs you out, tools fail with a "copy a fresh Production_tpAuth cookie" error: repeat the steps above.

### 6. Configure Claude Desktop

Add to `claude_desktop_config.json`:

```json
"training": {
  "command": "/path/to/miniconda3/envs/training-mcp/bin/python",
  "args": ["/path/to/training-mcp/server.py"]
}
```

## Training plan workflow

1. **Find** a plan: `tp_list_plans("off season 12")`.
2. **Fetch** it: `tp_fetch_plan(plan_id)`. The plan is applied to your TrainingPeaks calendar about a year out, read, and removed again; your real calendar is never touched. The file lands in `plans/`.
3. **Compare**: `plan_analyze(["a.json", "b.json"], start_date)` shows each plan week by week against your intervals.icu fitness and recent Strava volume.
4. **Edit** the plan file to fit. Each step is one line of JSON, so a diff against the coach's original shows exactly what changed. Run `plan_check` afterwards.
5. **Push**: `plan_push_to_intervals(file, start_date)` is a dry run; pass `dry_run=False` to write. Edit and push again any time; events update in place, and workouts removed from the file are deleted.

Push options rewrite targets without changing the plan file:

- `bike_hr_as_power` turns %LTHR rides into approximate %FTP targets. Zwift only accepts power-based workouts, so use it if intervals.icu sends your workouts to Zwift.
- `run_pace_as_power` turns %threshold-pace runs into %FTP targets, for running with a power meter.

Workout targets are percentages of threshold, so set FTP, LTHR and threshold pace in intervals.icu before pushing.

> [!IMPORTANT]
> Coach plans are usually licensed content. `plans/` is git-ignored so they never reach this repo. To keep edit history, run `git init` inside `plans/` (no remote), or point `TP_PLANS_DIR` at a private repo.

## Project structure

```
training-mcp/
├── app.py                 — FastMCP instance
├── server.py              — entry point
├── client_strava.py       — Strava HTTP client + token refresh
├── client_intervals.py    — intervals.icu HTTP client
├── client_dropbox.py      — HRV CSV reader (local dir or Dropbox)
├── client_trainingpeaks.py — TrainingPeaks private-API client (cookie → token)
├── plan_format.py         — plan file models, TrainingPeaks mapping, JSON writer
├── plan_checks.py         — implausible-value checks and repairs
├── plan_analysis.py       — weekly stats, fitness projection, flags
├── intervals_workout.py   — plan workout → intervals.icu workout text
├── auth_strava.py         — one-time Strava OAuth flow
├── auth_dropbox.py        — one-time Dropbox OAuth flow
├── requirements.txt
├── requirements-dev.txt   — adds pytest
├── environment.yml
├── .env.example
└── routers/
    ├── strava/            — activities, athlete, gear, routes, segments
    ├── intervals/         — activities, athlete, events, hrv, plans, wellness
    ├── trainingpeaks/     — plan list and fetch
    ├── plan_files.py      — plan_check, plan_analyze
    └── analytics/         — cross-source correlations
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests use synthetic plans and fake APIs; no credentials needed.
