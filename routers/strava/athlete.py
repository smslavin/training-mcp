from app import mcp
from client_strava import BASE_URL, get_client, handle_response


@mcp.tool()
def strava_get_athlete() -> str:
    """Get the authenticated athlete's Strava profile."""
    with get_client() as c:
        r = c.get(f"{BASE_URL}/athlete")
    return handle_response(r)


@mcp.tool()
def strava_get_athlete_stats() -> str:
    """Get lifetime stats for the authenticated athlete (totals for rides, runs, swims)."""
    with get_client() as c:
        r = c.get(f"{BASE_URL}/athlete")
        handle_response(r)
        athlete_id = r.json()["id"]
        r2 = c.get(f"{BASE_URL}/athletes/{athlete_id}/stats")
    return handle_response(r2)


@mcp.tool()
def strava_get_athlete_zones() -> str:
    """Get the authenticated athlete's heart rate and power zones from Strava."""
    with get_client() as c:
        r = c.get(f"{BASE_URL}/athlete/zones")
    return handle_response(r)
