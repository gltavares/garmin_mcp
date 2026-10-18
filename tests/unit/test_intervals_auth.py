"""Unit tests for intervals-icu-auth."""

from unittest.mock import patch

from garmin_mcp.intervals_auth import authenticate, main, verify_tokens


def test_verify_without_key(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_ICU_HOME", str(tmp_path / "icu"))
    for name in ("INTERVALS_ICU_API_KEY", "INTERVALS_API_KEY", "ICU_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert verify_tokens() == 1


def test_authenticate_saves_verified_key(monkeypatch, tmp_path):
    home = tmp_path / "icu"
    monkeypatch.setenv("INTERVALS_ICU_HOME", str(home))
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", "new-key")
    for name in ("INTERVALS_API_KEY", "ICU_API_KEY", "INTERVALS_ICU_API_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)

    with patch(
        "garmin_mcp.intervals_auth.verify_key",
        return_value={"id": "i172982", "name": "Gabriel Tavares"},
    ) as verify:
        assert authenticate(force=True, athlete_id="0") == 0
        verify.assert_called_once()
    assert (home / "api_key").read_text().strip() == "new-key"
    assert (home / "athlete_id").read_text().strip() == "i172982"


def test_authenticate_reuses_valid_saved_key(monkeypatch, tmp_path):
    home = tmp_path / "icu"
    home.mkdir()
    (home / "api_key").write_text("saved-key\n")
    monkeypatch.setenv("INTERVALS_ICU_HOME", str(home))
    for name in (
        "INTERVALS_ICU_API_KEY",
        "INTERVALS_API_KEY",
        "ICU_API_KEY",
        "INTERVALS_ICU_API_KEY_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    with patch(
        "garmin_mcp.intervals_auth.verify_key",
        return_value={"id": "i172982", "name": "Gabriel"},
    ) as verify:
        assert authenticate(force=False) == 0
        verify.assert_called_once()


def test_main_verify_flag(monkeypatch):
    monkeypatch.setattr("garmin_mcp.intervals_auth.verify_tokens", lambda: 0)
    assert main(["--verify"]) == 0
