"""
Intervals.icu MCP Server
Remote MCP server exposing Intervals.icu REST API as MCP tools via SSE transport.
Designed for deployment on Railway.
"""

import os
from datetime import date, timedelta
from typing import Optional

import httpx
import uvicorn
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

load_dotenv()

# --- Configuration -----------------------------------------------------------

API_KEY = os.environ.get("INTERVALS_API_KEY", "")
ATHLETE_ID = os.environ.get("INTERVALS_ATHLETE_ID", "")
BASE_URL = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"

# Optional shared secret — set MCP_AUTH_TOKEN in production to restrict access.
# If unset, auth is disabled (suitable for local dev only).
# Connect with: https://your-app.railway.app/sse?token=<MCP_AUTH_TOKEN>
AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")

if not API_KEY or not ATHLETE_ID:
    raise RuntimeError(
        "INTERVALS_API_KEY and INTERVALS_ATHLETE_ID environment variables must be set."
    )

# HTTP Basic auth: username is always the literal string "API_KEY"
AUTH = ("API_KEY", API_KEY)

# --- MCP Server --------------------------------------------------------------

mcp = FastMCP("intervals-icu")


def get_client() -> httpx.AsyncClient:
    """Create an authenticated async HTTP client for the Intervals.icu API."""
    return httpx.AsyncClient(
        base_url=BASE_URL,
        auth=AUTH,
        headers={"Accept": "application/json"},
        timeout=30.0,
    )


def raise_for_status(response: httpx.Response) -> None:
    """Raise a clean RuntimeError on HTTP errors, truncating raw response bodies."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"Intervals.icu API error {e.response.status_code}: "
            f"{e.response.text[:200]}"
        ) from None


# --- Tools -------------------------------------------------------------------


@mcp.tool()
async def get_recent_activities(days: int = 28) -> list:
    """
    Fetch activities from the last N days.

    Args:
        days: Number of days to look back (default: 28).

    Returns:
        List of activity summaries from Intervals.icu.
    """
    newest = date.today().isoformat()
    oldest = (date.today() - timedelta(days=days)).isoformat()

    async with get_client() as client:
        response = await client.get(
            "/activities",
            params={"oldest": oldest, "newest": newest},
        )
        raise_for_status(response)
        return response.json()


@mcp.tool()
async def get_activity_detail(activity_id: str) -> dict:
    """
    Fetch full detail for a single activity, including data streams
    (heart rate, pace, power, cadence).

    Args:
        activity_id: The Intervals.icu activity ID.

    Returns:
        Full activity detail including streams.
    """
    async with get_client() as client:
        response = await client.get(
            f"/activities/{activity_id}",
            params={"streams": "true"},
        )
        raise_for_status(response)
        return response.json()


@mcp.tool()
async def get_fitness_metrics(oldest: str, newest: str) -> list:
    """
    Fetch fitness/wellness metrics (CTL, ATL, TSB) for a date range.

    Args:
        oldest: Start date in YYYY-MM-DD format (inclusive).
        newest: End date in YYYY-MM-DD format (inclusive).

    Returns:
        Wellness data including CTL (fitness), ATL (fatigue), and TSB (form).
    """
    async with get_client() as client:
        response = await client.get(
            "/wellness",
            params={"oldest": oldest, "newest": newest},
        )
        raise_for_status(response)
        return response.json()


@mcp.tool()
async def get_activity_intervals(activity_id: str) -> list:
    """
    Fetch interval/lap data for a specific activity.

    Args:
        activity_id: The Intervals.icu activity ID.

    Returns:
        List of intervals/laps with metrics for each segment.
    """
    async with get_client() as client:
        response = await client.get(f"/activities/{activity_id}/intervals")
        raise_for_status(response)
        return response.json()


@mcp.tool()
async def update_activity(
    activity_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    perceived_exertion: Optional[int] = None,
    sport_type: Optional[str] = None,
) -> dict:
    """
    Update metadata on a completed activity. Only supplied fields are changed.
    Use this to write coaching notes, correct the sport type, or log RPE
    after analysing a session.

    Args:
        activity_id: The Intervals.icu activity ID.
        name: New name for the activity.
        description: Coaching notes or post-session observations.
        perceived_exertion: Perceived effort rating (1–10 scale).
        sport_type: Correct the sport type if misdetected — e.g. "Ride", "Run", "Swim".

    Returns:
        The updated activity as returned by Intervals.icu.
    """
    body: dict = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if perceived_exertion is not None:
        body["perceived_exertion"] = perceived_exertion
    if sport_type is not None:
        body["type"] = sport_type

    async with get_client() as client:
        response = await client.put(f"/activities/{activity_id}", json=body)
        raise_for_status(response)
        return response.json()


@mcp.tool()
async def update_activity_intervals(
    activity_id: str,
    intervals: list,
) -> list:
    """
    Update detected intervals/laps on a completed activity.
    Use this to correct auto-detected interval boundaries, rename segments,
    or adjust which intervals are marked as "work" efforts.

    Each interval in the list must include its `id` (from get_activity_intervals)
    plus any fields to change, for example:
        {"id": 1, "label": "Warm-up"}
        {"id": 2, "start_index": 120, "end_index": 840}

    Args:
        activity_id: The Intervals.icu activity ID.
        intervals: List of interval update objects. Each must have an "id" field.

    Returns:
        The updated intervals as returned by Intervals.icu.
    """
    async with get_client() as client:
        response = await client.put(
            f"/activities/{activity_id}/intervals",
            json=intervals,
        )
        raise_for_status(response)
        return response.json()


# --- Athlete Profile ---------------------------------------------------------


@mcp.tool()
async def get_athlete_profile() -> dict:
    """
    Fetch the athlete's profile including FTP, heart rate zones, pace zones,
    weight, and sport-specific settings.

    Returns:
        Athlete profile with FTP, zones, and other settings needed to
        interpret training data in context.
    """
    # This endpoint lives one level up from the per-athlete base URL
    async with httpx.AsyncClient(
        base_url="https://intervals.icu/api/v1",
        auth=AUTH,
        headers={"Accept": "application/json"},
        timeout=30.0,
    ) as client:
        response = await client.get(f"/athlete/{ATHLETE_ID}")
        raise_for_status(response)
        return response.json()


# --- Calendar / Training Plan ------------------------------------------------


@mcp.tool()
async def get_calendar_events(oldest: str, newest: str) -> list:
    """
    Fetch planned workouts and events on the training calendar for a date range.
    Power, heart rate, and pace targets are resolved to absolute values.

    Args:
        oldest: Start date in YYYY-MM-DD format (inclusive).
        newest: End date in YYYY-MM-DD format (inclusive).

    Returns:
        List of calendar events with planned workout details and targets.
    """
    async with get_client() as client:
        response = await client.get(
            "/events",
            params={"oldest": oldest, "newest": newest, "resolve": "true"},
        )
        raise_for_status(response)
        return response.json()


@mcp.tool()
async def create_calendar_event(
    name: str,
    start_date: str,
    sport_type: str,
    description: Optional[str] = None,
    duration_secs: Optional[int] = None,
    load_target: Optional[float] = None,
) -> dict:
    """
    Create a planned workout event on the training calendar.

    Args:
        name: Name of the workout (e.g. "Zone 2 Ride", "Tempo Run").
        start_date: Date for the workout in YYYY-MM-DD format.
        sport_type: Sport type — e.g. "Ride", "Run", "Swim", "WeightTraining".
        description: Optional notes or workout description.
        duration_secs: Planned duration in seconds (e.g. 3600 for 1 hour).
        load_target: Target training stress score (TSS).

    Returns:
        The created event as returned by Intervals.icu.
    """
    body: dict = {"name": name, "start_date_local": start_date, "type": sport_type}
    if description is not None:
        body["description"] = description
    if duration_secs is not None:
        body["duration"] = duration_secs
    if load_target is not None:
        body["load_target"] = load_target

    async with get_client() as client:
        response = await client.post("/events", json=body)
        raise_for_status(response)
        return response.json()


@mcp.tool()
async def update_calendar_event(
    event_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    start_date: Optional[str] = None,
    duration_secs: Optional[int] = None,
    load_target: Optional[float] = None,
) -> dict:
    """
    Update an existing planned workout event on the training calendar.
    Only the fields provided will be changed.

    Args:
        event_id: The Intervals.icu event ID to update.
        name: New name for the workout.
        description: New notes or description.
        start_date: New date in YYYY-MM-DD format.
        duration_secs: New planned duration in seconds.
        load_target: New target TSS.

    Returns:
        The updated event as returned by Intervals.icu.
    """
    body: dict = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if start_date is not None:
        body["start_date_local"] = start_date
    if duration_secs is not None:
        body["duration"] = duration_secs
    if load_target is not None:
        body["load_target"] = load_target

    async with get_client() as client:
        response = await client.put(f"/events/{event_id}", json=body)
        raise_for_status(response)
        return response.json()


@mcp.tool()
async def delete_calendar_event(event_id: str) -> str:
    """
    Delete a planned workout event from the training calendar.

    Args:
        event_id: The Intervals.icu event ID to delete.

    Returns:
        Confirmation message.
    """
    async with get_client() as client:
        response = await client.delete(f"/events/{event_id}")
        raise_for_status(response)
        return f"Event {event_id} deleted successfully."


# --- Wellness Logging --------------------------------------------------------


@mcp.tool()
async def get_wellness_entry(entry_date: str) -> dict:
    """
    Fetch the wellness snapshot for a single specific day.

    Args:
        entry_date: The date in YYYY-MM-DD format.

    Returns:
        Wellness data for that day: CTL, ATL, TSB, HRV, resting HR,
        sleep, fatigue, motivation, and weight.
    """
    async with get_client() as client:
        response = await client.get(f"/wellness/{entry_date}")
        raise_for_status(response)
        return response.json()


@mcp.tool()
async def update_wellness_entry(
    entry_date: str,
    hrv: Optional[float] = None,
    resting_hr: Optional[int] = None,
    sleep_secs: Optional[int] = None,
    sleep_quality: Optional[int] = None,
    fatigue: Optional[int] = None,
    motivation: Optional[int] = None,
    weight_kg: Optional[float] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Log or update wellness data for a specific day. Only supplied fields are sent.

    Args:
        entry_date: The date in YYYY-MM-DD format.
        hrv: Heart rate variability reading.
        resting_hr: Resting heart rate (bpm).
        sleep_secs: Sleep duration in seconds (e.g. 27000 = 7.5 hours).
        sleep_quality: Sleep quality rating (1–5 scale).
        fatigue: Fatigue level (1–10 scale, 1 = very fresh).
        motivation: Motivation level (1–10 scale, 1 = very low).
        weight_kg: Body weight in kilograms.
        notes: Free-text notes for the day.

    Returns:
        The updated wellness entry as returned by Intervals.icu.
    """
    body: dict = {}
    if hrv is not None:
        body["hrv"] = hrv
    if resting_hr is not None:
        body["restingHR"] = resting_hr
    if sleep_secs is not None:
        body["sleepSecs"] = sleep_secs
    if sleep_quality is not None:
        body["sleepQuality"] = sleep_quality
    if fatigue is not None:
        body["fatigue"] = fatigue
    if motivation is not None:
        body["motivation"] = motivation
    if weight_kg is not None:
        body["weight"] = weight_kg
    if notes is not None:
        body["notes"] = notes

    async with get_client() as client:
        response = await client.put(f"/wellness/{entry_date}", json=body)
        raise_for_status(response)
        return response.json()


# --- SSE Transport & ASGI App ------------------------------------------------

sse_transport = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    # Token auth check — only enforced when MCP_AUTH_TOKEN is configured
    if AUTH_TOKEN and request.query_params.get("token") != AUTH_TOKEN:
        return Response("Unauthorized", status_code=401)

    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp._mcp_server.run(
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),
        )


app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse_transport.handle_post_message),
    ]
)

# --- Entry Point -------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
