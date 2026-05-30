from app import mcp
from client_strava import BASE_URL, get_client, handle_response


@mcp.tool()
def strava_list_routes(per_page: int = 30, page: int = 1) -> str:
    """
    List routes created by the authenticated athlete on Strava.

    Args:
        per_page: Number of results per page (max 200).
        page: Page number for pagination.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/athlete")
        handle_response(r)
        athlete_id = r.json()["id"]
        r2 = c.get(
            f"{BASE_URL}/athletes/{athlete_id}/routes",
            params={"per_page": min(per_page, 200), "page": page},
        )
    return handle_response(r2)


@mcp.tool()
def strava_get_route(route_id: int) -> str:
    """
    Get details for a Strava route (name, description, distance, elevation, map).

    Args:
        route_id: The Strava route ID (integer).
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/routes/{route_id}")
    return handle_response(r)


@mcp.tool()
def strava_get_route_streams(route_id: int) -> str:
    """
    Get time-series streams for a Strava route (latlng, distance, altitude).

    Args:
        route_id: The Strava route ID (integer).
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/routes/{route_id}/streams")
    return handle_response(r)
