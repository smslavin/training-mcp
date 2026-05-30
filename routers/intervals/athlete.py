from typing import Optional

from app import mcp
from client_intervals import BASE_URL, athlete_id, get_client, handle_response


@mcp.tool()
def intervals_get_athlete(athlete_id_override: Optional[str] = None) -> str:
    """
    Get profile and settings for the athlete from intervals.icu.

    Args:
        athlete_id_override: Athlete ID (e.g. 'i12345'). Defaults to INTERVALS_ATHLETE_ID env var.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}")
    return handle_response(r)
