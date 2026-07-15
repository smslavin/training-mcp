# training-mcp

MCP server for training data — Strava activities, intervals.icu wellness and analytics, HRV4Training metrics, and cross-source correlations. Consolidates three separate servers (strava-mcp, intervals-mcp, analytics-mcp) into one process.

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

### 5. Configure Claude Desktop

Add to `claude_desktop_config.json`:

```json
"training": {
  "command": "/path/to/miniconda3/envs/training-mcp/bin/python",
  "args": ["/path/to/training-mcp/server.py"]
}
```

## Project structure

```
training-mcp/
├── app.py                 — FastMCP instance
├── server.py              — entry point
├── client_strava.py       — Strava HTTP client + token refresh
├── client_intervals.py    — intervals.icu HTTP client
├── client_dropbox.py      — HRV CSV reader (local dir or Dropbox)
├── auth_strava.py         — one-time Strava OAuth flow
├── auth_dropbox.py        — one-time Dropbox OAuth flow
├── requirements.txt
├── environment.yml
├── .env.example
└── routers/
    ├── strava/            — activities, athlete, gear, routes, segments
    ├── intervals/         — activities, athlete, events, hrv, wellness
    └── analytics/         — cross-source correlations
```
