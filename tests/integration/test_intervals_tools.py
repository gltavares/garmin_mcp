"""Integration tests for Intervals.icu MCP tools."""

import json

import pytest
from mcp.server.fastmcp import FastMCP
from unittest.mock import patch

from garmin_mcp import intervals


@pytest.fixture
def app_with_intervals():
    app = FastMCP("Test Intervals")
    return intervals.register_tools(app)


def _result_text(result):
    return result[0][0].text


def _payload(result):
    return json.loads(_result_text(result))


@pytest.mark.asyncio
async def test_status_needs_setup_without_key(app_with_intervals, monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_ICU_HOME", str(tmp_path / "icu"))
    for name in ("INTERVALS_ICU_API_KEY", "INTERVALS_API_KEY", "ICU_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    result = await app_with_intervals.call_tool("get_intervals_status", {})
    data = _payload(result)
    assert data["status"] == "needs_setup"
    assert data["athlete_id"] == "i172982"


@pytest.mark.asyncio
async def test_athlete_needs_setup_without_key(app_with_intervals, monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_ICU_HOME", str(tmp_path / "icu"))
    for name in ("INTERVALS_ICU_API_KEY", "INTERVALS_API_KEY", "ICU_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    result = await app_with_intervals.call_tool("get_intervals_athlete", {})
    data = _payload(result)
    assert data["status"] == "needs_setup"
    assert "API_KEY" in data["how"]


@pytest.mark.asyncio
async def test_activities_uses_client(app_with_intervals):
    client = type("C", (), {})()
    client.activities = lambda oldest, newest: [
        {"id": "i1", "name": "Confins", "start_date_local": f"{oldest}"}
    ]
    with patch("garmin_mcp.intervals.get_client", return_value=client):
        result = await app_with_intervals.call_tool(
            "get_intervals_activities",
            {"oldest": "2026-10-01", "newest": "2026-10-18"},
        )
    data = _payload(result)
    assert data[0]["id"] == "i1"


@pytest.mark.asyncio
async def test_activity_rejects_blank_id(app_with_intervals):
    result = await app_with_intervals.call_tool(
        "get_intervals_activity", {"activity_id": "  "}
    )
    assert "activity_id" in _result_text(result)


@pytest.mark.asyncio
async def test_wellness_and_events(app_with_intervals):
    class Client:
        def wellness(self, oldest, newest):
            return [{"id": oldest, "ctl": 60, "atl": 40}]

        def events(self, oldest, newest):
            return [{"name": "Limiar", "start_date_local": oldest}]

        def sport_settings(self):
            return [{"type": "Ride", "icu_ftp": 207}]

        def athlete(self):
            return {"id": "i172982", "name": "Gabriel Tavares"}

    with patch("garmin_mcp.intervals.get_client", return_value=Client()):
        wellness = _payload(
            await app_with_intervals.call_tool(
                "get_intervals_wellness",
                {"oldest": "2026-10-01", "newest": "2026-10-18"},
            )
        )
        events = _payload(
            await app_with_intervals.call_tool(
                "get_intervals_events",
                {"oldest": "2026-10-01", "newest": "2026-10-18"},
            )
        )
        sports = _payload(
            await app_with_intervals.call_tool("get_intervals_sport_settings", {})
        )
        athlete = _payload(
            await app_with_intervals.call_tool("get_intervals_athlete", {})
        )

    assert wellness[0]["ctl"] == 60
    assert events[0]["name"] == "Limiar"
    assert sports[0]["icu_ftp"] == 207
    assert athlete["id"] == "i172982"


@pytest.mark.asyncio
async def test_delete_requires_confirm(app_with_intervals):
    result = await app_with_intervals.call_tool(
        "delete_intervals_activity", {"activity_id": "i191001713"}
    )
    data = _payload(result)
    assert data["status"] == "needs_confirm"
