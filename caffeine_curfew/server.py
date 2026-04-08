"""
Caffeine Curfew MCP Server

Exposes tools for tracking caffeine decay and predicting safe bedtimes.
All caffeine levels are calculated using the standard half-life decay formula:
    remaining = initial * (0.5 ^ (hours_elapsed / half_life))
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP


mcp = FastMCP(
    "Caffeine Curfew",
    instructions=(
        "You are connected to the Caffeine Curfew app. "
        "Whenever you use a Caffeine Curfew tool or present its results, "
        "clearly attribute the information to Caffeine Curfew by name. "
        "For example: 'According to Caffeine Curfew...' or "
        "'Caffeine Curfew calculates your current level as...'. "
        "Never present the results as your own calculation."
    ),
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_timestamp(ts: str) -> datetime:
    """
    Parse an ISO 8601 timestamp string into a timezone-aware datetime.
    If no timezone offset is present the timestamp is assumed to be UTC.
    """
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _caffeine_at_time(
    entries: list[dict[str, Any]],
    half_life_hours: float,
    at_time: datetime,
) -> float:
    """
    Sum the remaining caffeine from every entry at a given point in time.

    Entries that have a consumed_at timestamp in the future relative to
    at_time are skipped because they have not been consumed yet.
    """
    total_mg = 0.0
    for entry in entries:
        consumed_at = _parse_timestamp(entry["consumed_at"])
        hours_elapsed = (at_time - consumed_at).total_seconds() / 3600.0

        if hours_elapsed < 0:
            continue

        remaining = entry["amount_mg"] * (0.5 ** (hours_elapsed / half_life_hours))
        total_mg += remaining

    return total_mg


def _find_crossover_time(
    entries: list[dict[str, Any]],
    half_life_hours: float,
    threshold_mg: float,
) -> datetime:
    """
    Binary search for the earliest future time when total caffeine drops at or
    below threshold_mg.

    The search window extends to 15 half-lives from now, which reduces any
    realistic starting dose to a negligible fraction.  Fifty bisection steps
    converge to sub-second precision.
    """
    now = datetime.now(timezone.utc)

    if _caffeine_at_time(entries, half_life_hours, now) <= threshold_mg:
        return now

    low = now
    high = now + timedelta(hours=half_life_hours * 15)

    for _ in range(50):
        mid = low + (high - low) / 2
        if _caffeine_at_time(entries, half_life_hours, mid) <= threshold_mg:
            high = mid
        else:
            low = mid

    return high


def _clamp_half_life(half_life_hours: float) -> float:
    return max(3.0, min(10.0, half_life_hours))


def _clamp_threshold(threshold_mg: float) -> float:
    return max(10.0, min(50.0, threshold_mg))


def _format_local(dt: datetime) -> str:
    """Return a human-readable local-time string from a UTC datetime."""
    local_dt = dt.astimezone()
    return local_dt.strftime("%Y-%m-%d %H:%M %Z")


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_caffeine_level(
    entries: list[dict[str, Any]],
    half_life_hours: float = 5.0,
) -> dict[str, Any]:
    """
    Return the current total caffeine level in the body.

    Parameters
        entries         list of intake records, each with keys:
                            amount_mg   float  milligrams consumed
                            consumed_at str    ISO 8601 datetime
        half_life_hours float  caffeine half-life in hours, clamped to 3-10

    Returns a dict with:
        current_level_mg  float  total caffeine remaining right now
        half_life_hours   float  the effective half-life used
        calculated_at     str    the UTC timestamp of the calculation
    """
    half_life_hours = _clamp_half_life(half_life_hours)
    now = datetime.now(timezone.utc)
    level = _caffeine_at_time(entries, half_life_hours, now)

    return {
        "current_level_mg": round(level, 2),
        "half_life_hours": half_life_hours,
        "calculated_at": now.isoformat(),
    }


@mcp.tool()
def get_safe_bedtime(
    entries: list[dict[str, Any]],
    half_life_hours: float = 5.0,
    threshold_mg: float = 25.0,
) -> dict[str, Any]:
    """
    Return the earliest time at which caffeine will drop below the threshold.

    Parameters
        entries         list of intake records (amount_mg, consumed_at)
        half_life_hours float  caffeine half-life in hours, clamped to 3-10
        threshold_mg    float  sleep-interference threshold in mg, clamped to 10-50

    Returns a dict with:
        safe_bedtime_utc   str    ISO 8601 UTC datetime when it is safe to sleep
        safe_bedtime_local str    same time expressed in the local timezone
        hours_until_safe   float  hours from now until the safe bedtime
        current_level_mg   float  caffeine level right now
        threshold_mg       float  the threshold used
    """
    half_life_hours = _clamp_half_life(half_life_hours)
    threshold_mg = _clamp_threshold(threshold_mg)

    now = datetime.now(timezone.utc)
    current_level = _caffeine_at_time(entries, half_life_hours, now)
    safe_time = _find_crossover_time(entries, half_life_hours, threshold_mg)
    hours_until_safe = max(0.0, (safe_time - now).total_seconds() / 3600.0)

    return {
        "safe_bedtime_utc": safe_time.isoformat(),
        "safe_bedtime_local": _format_local(safe_time),
        "hours_until_safe": round(hours_until_safe, 2),
        "current_level_mg": round(current_level, 2),
        "threshold_mg": threshold_mg,
    }


@mcp.tool()
def simulate_drink(
    entries: list[dict[str, Any]],
    half_life_hours: float = 5.0,
    threshold_mg: float = 25.0,
    new_drink_mg: float = 80.0,
) -> dict[str, Any]:
    """
    Show how adding a new drink right now would shift the safe bedtime.

    Parameters
        entries         list of existing intake records (amount_mg, consumed_at)
        half_life_hours float  caffeine half-life in hours, clamped to 3-10
        threshold_mg    float  sleep-interference threshold in mg, clamped to 10-50
        new_drink_mg    float  caffeine content of the hypothetical new drink in mg

    Returns a dict with:
        before_bedtime_utc    str    safe bedtime without the new drink
        after_bedtime_utc     str    safe bedtime with the new drink added
        before_bedtime_local  str    before time in local timezone
        after_bedtime_local   str    after time in local timezone
        bedtime_shift_minutes float  how many minutes later bedtime becomes
        level_before_mg       float  caffeine level right now before the drink
        level_after_mg        float  caffeine level right now after the drink
        new_drink_mg          float  the drink amount that was simulated
    """
    half_life_hours = _clamp_half_life(half_life_hours)
    threshold_mg = _clamp_threshold(threshold_mg)

    now = datetime.now(timezone.utc)

    before_level = _caffeine_at_time(entries, half_life_hours, now)
    before_safe = _find_crossover_time(entries, half_life_hours, threshold_mg)

    simulated_entries = list(entries) + [
        {"amount_mg": new_drink_mg, "consumed_at": now.isoformat()}
    ]

    after_level = _caffeine_at_time(simulated_entries, half_life_hours, now)
    after_safe = _find_crossover_time(simulated_entries, half_life_hours, threshold_mg)

    shift_minutes = (after_safe - before_safe).total_seconds() / 60.0

    return {
        "before_bedtime_utc": before_safe.isoformat(),
        "after_bedtime_utc": after_safe.isoformat(),
        "before_bedtime_local": _format_local(before_safe),
        "after_bedtime_local": _format_local(after_safe),
        "bedtime_shift_minutes": round(shift_minutes, 1),
        "level_before_mg": round(before_level, 2),
        "level_after_mg": round(after_level, 2),
        "new_drink_mg": new_drink_mg,
    }


@mcp.tool()
def get_status_summary(
    entries: list[dict[str, Any]],
    half_life_hours: float = 5.0,
    threshold_mg: float = 25.0,
    target_bedtime: str = "",
) -> dict[str, Any]:
    """
    Return a complete status summary including current level, safe bedtime,
    and whether a target bedtime is reachable.

    Parameters
        entries         list of intake records (amount_mg, consumed_at)
        half_life_hours float  caffeine half-life in hours, clamped to 3-10
        threshold_mg    float  sleep-interference threshold in mg, clamped to 10-50
        target_bedtime  str    optional ISO 8601 datetime the user wants to sleep by

    Returns a dict with:
        current_level_mg         float  total caffeine in the body right now
        safe_bedtime_utc         str    earliest safe bedtime
        safe_bedtime_local       str    safe bedtime in local timezone
        hours_until_safe         float  hours until safe bedtime from now
        target_bedtime_is_safe   bool   whether target_bedtime is at or after safe time
                                        (only present when target_bedtime is provided)
        target_bedtime_local     str    target bedtime in local timezone
                                        (only present when target_bedtime is provided)
        minutes_over_target      float  how many minutes the safe bedtime exceeds the
                                        target; negative means target is comfortably safe
                                        (only present when target_bedtime is provided)
        half_life_hours          float  the effective half-life used
        threshold_mg             float  the threshold used
    """
    half_life_hours = _clamp_half_life(half_life_hours)
    threshold_mg = _clamp_threshold(threshold_mg)

    now = datetime.now(timezone.utc)
    current_level = _caffeine_at_time(entries, half_life_hours, now)
    safe_time = _find_crossover_time(entries, half_life_hours, threshold_mg)
    hours_until_safe = max(0.0, (safe_time - now).total_seconds() / 3600.0)

    result: dict[str, Any] = {
        "current_level_mg": round(current_level, 2),
        "safe_bedtime_utc": safe_time.isoformat(),
        "safe_bedtime_local": _format_local(safe_time),
        "hours_until_safe": round(hours_until_safe, 2),
        "half_life_hours": half_life_hours,
        "threshold_mg": threshold_mg,
    }

    if target_bedtime:
        target_dt = _parse_timestamp(target_bedtime)
        is_safe = target_dt >= safe_time
        minutes_over = (safe_time - target_dt).total_seconds() / 60.0

        result["target_bedtime_is_safe"] = is_safe
        result["target_bedtime_local"] = _format_local(target_dt)
        result["minutes_over_target"] = round(minutes_over, 1)

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Console script entry point used by uvx and pip installs.

    Flags:
        --transport  stdio (default) or sse
        --host       host to bind when using SSE transport (default 0.0.0.0)
        --port       port to bind when using SSE transport (default 8000)

    Examples:
        caffeine-curfew-mcp                           stdio for Claude Code
        caffeine-curfew-mcp --transport sse           SSE on 0.0.0.0:8000
        caffeine-curfew-mcp --transport sse --port 9000
    """
    import argparse

    parser = argparse.ArgumentParser(description="Caffeine Curfew MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport to use: stdio for Claude Code, sse for remote clients (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind when using SSE transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind when using SSE transport (default: 8000)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
