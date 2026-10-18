"""Unit tests for the Intervals.icu client and local key store."""

import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from garmin_mcp.intervals import (
    BROWSER_UA,
    BASIC_USERNAME,
    IntervalsAPIError,
    IntervalsAuthError,
    IntervalsClient,
    _date_range,
    get_athlete_id,
    get_client,
    key_configured,
    load_api_key,
    save_api_key,
)


@pytest.fixture
def key_home(tmp_path, monkeypatch):
    home = tmp_path / "icu"
    monkeypatch.setenv("INTERVALS_ICU_HOME", str(home))
    for name in (
        "INTERVALS_ICU_API_KEY",
        "INTERVALS_API_KEY",
        "ICU_API_KEY",
        "INTERVALS_ICU_API_KEY_FILE",
        "INTERVALS_ICU_ATHLETE_ID",
        "INTERVALS_ATHLETE_ID",
        "ICU_ATHLETE_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    return home


def test_save_and_load_api_key(key_home):
    path = save_api_key("  secret-key  ", athlete_id="i172982")
    assert Path(path).read_text().strip() == "secret-key"
    assert oct(Path(path).stat().st_mode)[-3:] == "600"
    assert load_api_key() == "secret-key"
    assert get_athlete_id() == "i172982"
    assert key_configured() is True


def test_env_key_wins_over_file(key_home, monkeypatch):
    save_api_key("file-key")
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", "env-key")
    assert load_api_key() == "env-key"


def test_key_file_env(key_home, monkeypatch, tmp_path):
    other = tmp_path / "other.key"
    other.write_text("from-file\n")
    monkeypatch.setenv("INTERVALS_ICU_API_KEY_FILE", str(other))
    assert load_api_key() == "from-file"


def test_both_env_and_file_env_error(key_home, monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", "env-key")
    monkeypatch.setenv("INTERVALS_ICU_API_KEY_FILE", str(tmp_path / "x"))
    with pytest.raises(ValueError, match="Must only provide one"):
        load_api_key()


def test_empty_save_rejected(key_home):
    with pytest.raises(ValueError, match="API key is required"):
        save_api_key("   ")


def test_client_sets_basic_auth_and_browser_ua():
    session = requests.Session()
    client = IntervalsClient("abc123", athlete_id="0", session=session)
    assert client.session.auth == (BASIC_USERNAME, "abc123")
    assert client.session.headers["User-Agent"] == BROWSER_UA


def test_client_get_sends_date_params():
    session = Mock()
    response = Mock()
    response.status_code = 200
    response.ok = True
    response.content = b'[{"id":"i1"}]'
    response.json.return_value = [{"id": "i1"}]
    session.get.return_value = response

    client = IntervalsClient("k", athlete_id="i172982", session=session)
    payload = client.activities("2026-06-01", "2026-10-18")

    assert payload == [{"id": "i1"}]
    session.get.assert_called_once()
    args, kwargs = session.get.call_args
    assert args[0] == "https://intervals.icu/api/v1/athlete/i172982/activities"
    assert kwargs["params"] == {"oldest": "2026-06-01", "newest": "2026-10-18"}


def test_client_401_is_auth_error():
    session = Mock()
    response = Mock()
    response.status_code = 401
    response.ok = False
    session.get.return_value = response
    client = IntervalsClient("bad", session=session)
    with pytest.raises(IntervalsAuthError, match="401"):
        client.athlete()


def test_client_falls_back_from_profile_404():
    session = Mock()
    missing = Mock()
    missing.status_code = 404
    missing.ok = False
    missing.text = "missing"
    missing.content = b"missing"
    found = Mock()
    found.status_code = 200
    found.ok = True
    found.content = b'{"id":"i172982"}'
    found.json.return_value = {"id": "i172982"}
    session.get.side_effect = [missing, found]

    client = IntervalsClient("k", session=session)
    assert client.athlete() == {"id": "i172982"}
    assert session.get.call_count == 2


def test_get_client_requires_key(key_home):
    with pytest.raises(IntervalsAuthError, match="No Intervals.icu API key"):
        get_client()


def test_date_range_defaults_and_rejects_reversed():
    start, end = _date_range("2026-06-01", "2026-10-18")
    assert (start, end) == ("2026-06-01", "2026-10-18")
    with pytest.raises(ValueError, match="oldest must be on or before newest"):
        _date_range("2026-10-18", "2026-06-01")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _date_range("18/10/2026", None)
