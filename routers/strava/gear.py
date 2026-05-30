import json
from typing import Optional

from pydantic import BaseModel

from app import mcp
from client_strava import BASE_URL, get_client, handle_response

_WARN_PCT = 0.9  # flag as WARNING when >= 90% of threshold


class GearThresholds(BaseModel):
    bike_km: Optional[float] = None
    shoe_km: Optional[float] = None


@mcp.tool()
def strava_get_gear(gear_id: str) -> str:
    """
    Get details for a piece of gear (bike or shoes) including components and distance.

    Args:
        gear_id: The gear ID string (e.g. 'b1234567' for bikes, 'g1234567' for shoes).
            Find gear IDs in the athlete profile from strava_get_athlete.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/gear/{gear_id}")
    return handle_response(r)


@mcp.tool()
def strava_list_athlete_gear() -> str:
    """
    List all bikes and shoes registered to the authenticated athlete,
    including total distance logged on each.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/athlete")
    handle_response(r)
    athlete = r.json()
    gear = {
        "bikes": athlete.get("bikes", []),
        "shoes": athlete.get("shoes", []),
    }
    return json.dumps(gear)


@mcp.tool()
def strava_get_gear_maintenance_status(thresholds: GearThresholds) -> str:
    """
    Check maintenance status for all bikes and shoes based on cumulative logged distance.

    Compares each item's distance against the provided thresholds. Items within 10%
    of their threshold are flagged WARNING; items at or above the threshold are
    flagged EXCEEDED.

    Args:
        thresholds: Distance thresholds in km. bike_km applies to all bikes;
            shoe_km applies to all shoes. Omit either to report distance only
            without a threshold comparison.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/athlete")
    handle_response(r)
    athlete = r.json()

    def _item_line(item: dict, threshold_km: Optional[float]) -> str:
        name = item.get("name") or item.get("id", "Unknown")
        distance_km = item.get("distance", 0) / 1000.0

        if threshold_km is None:
            return f"  {name}: {distance_km:.0f} km  (no threshold set)"

        pct = distance_km / threshold_km
        if pct >= 1.0:
            status = "EXCEEDED"
        elif pct >= _WARN_PCT:
            status = "WARNING "
        else:
            status = "OK      "

        remaining = max(0.0, threshold_km - distance_km)
        return (
            f"  [{status}] {name}: {distance_km:.0f} / {threshold_km:.0f} km"
            f"  ({pct * 100:.0f}% used, {remaining:.0f} km remaining)"
        )

    lines = []

    bikes = athlete.get("bikes", [])
    lines.append("Bikes:" if bikes else "Bikes: none registered")
    for bike in bikes:
        lines.append(_item_line(bike, thresholds.bike_km))

    shoes = athlete.get("shoes", [])
    lines.append("Shoes:" if shoes else "Shoes: none registered")
    for shoe in shoes:
        lines.append(_item_line(shoe, thresholds.shoe_km))

    return "\n".join(lines)
