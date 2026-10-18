"""Intervals.icu personal API client and MCP tools.

Personal API auth is HTTP Basic with username literally ``API_KEY`` and the
developer key as the password. Intervals sits behind Cloudflare, which
challenges the default ``Python-urllib`` user agent — send a browser UA.

The key must never be committed. Load it from the environment or
``~/.intervalsicu/api_key`` (written by ``intervals-icu-auth``).
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from garmin_mcp.token_utils import resolve_token_path, secure_token_dir

BASE_URL = "https://intervals.icu/api/v1"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)
DEFAULT_KEY_DIR = "~/.intervalsicu"
# Athlete id ``0`` resolves to whoever owns the API key.
DEFAULT_ATHLETE_ID = "0"
# Gabriel's Intervals athlete id from the 2023 signup mail (not a secret).
KNOWN_ATHLETE_ID = "i172982"
BASIC_USERNAME = "API_KEY"

_KEY_ENV_VARS = (
    "INTERVALS_ICU_API_KEY",
    "INTERVALS_API_KEY",
    "ICU_API_KEY",
)
_KEY_FILE_ENV = "INTERVALS_ICU_API_KEY_FILE"
_ATHLETE_ENV_VARS = (
    "INTERVALS_ICU_ATHLETE_ID",
    "INTERVALS_ATHLETE_ID",
    "ICU_ATHLETE_ID",
)


class IntervalsAuthError(RuntimeError):
    """No usable Intervals.icu API key is configured."""


class IntervalsAPIError(RuntimeError):
    """The Intervals.icu API rejected a request."""


def get_key_dir() -> str:
    """Directory that holds the local API key file."""
    return resolve_token_path(os.getenv("INTERVALS_ICU_HOME") or DEFAULT_KEY_DIR)


def get_key_path() -> str:
    return str(Path(get_key_dir()) / "api_key")


def get_athlete_id_path() -> str:
    return str(Path(get_key_dir()) / "athlete_id")


def get_athlete_id() -> str:
    """Athlete id for path substitution. ``0`` follows the key's owner."""
    for name in _ATHLETE_ENV_VARS:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    stored = Path(get_athlete_id_path())
    if stored.is_file():
        value = stored.read_text().strip()
        if value:
            return value
    return DEFAULT_ATHLETE_ID


def load_api_key() -> Optional[str]:
    """Return the API key from env, a key file env, or ``~/.intervalsicu``."""
    file_env = os.getenv(_KEY_FILE_ENV)
    env_values = [os.getenv(name) for name in _KEY_ENV_VARS if os.getenv(name)]
    if file_env and env_values:
        raise ValueError(
            f"Must only provide one of {' / '.join(_KEY_ENV_VARS)} and "
            f"{_KEY_FILE_ENV}, got both"
        )
    if len(env_values) > 1:
        raise ValueError(
            f"Must only provide one of {' / '.join(_KEY_ENV_VARS)}, got several"
        )
    if env_values:
        return env_values[0].strip() or None
    if file_env:
        path = Path(resolve_token_path(file_env))
        return path.read_text().strip() or None
    stored = Path(get_key_path())
    if stored.is_file():
        return stored.read_text().strip() or None
    return None


def save_api_key(api_key: str, athlete_id: Optional[str] = None) -> str:
    """Write the key (and optional athlete id) under ``~/.intervalsicu``."""
    key = (api_key or "").strip()
    if not key:
        raise ValueError("API key is required")
    key_dir = Path(get_key_dir())
    key_dir.mkdir(parents=True, exist_ok=True)
    key_path = Path(get_key_path())
    key_path.write_text(key + "\n")
    if athlete_id and athlete_id.strip():
        Path(get_athlete_id_path()).write_text(athlete_id.strip() + "\n")
    secure_token_dir(str(key_dir))
    return str(key_path)


def key_configured() -> bool:
    try:
        return bool(load_api_key())
    except ValueError:
        return False


class IntervalsClient:
    """Thin Intervals.icu REST client for personal API-key use."""

    def __init__(
        self,
        api_key: str,
        athlete_id: str = DEFAULT_ATHLETE_ID,
        session: Optional[requests.Session] = None,
        base_url: str = BASE_URL,
    ):
        if not api_key or not api_key.strip():
            raise IntervalsAuthError("Intervals.icu API key is required")
        self.api_key = api_key.strip()
        self.athlete_id = (athlete_id or DEFAULT_ATHLETE_ID).strip()
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.auth = (BASIC_USERNAME, self.api_key)
        self.session.headers.update(
            {
                "User-Agent": BROWSER_UA,
                "Accept": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _athlete_path(self, suffix: str = "") -> str:
        return f"/athlete/{self.athlete_id}{suffix}"

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        try:
            response = self.session.get(
                self._url(path), params=params, timeout=30
            )
        except requests.RequestException as exc:
            raise IntervalsAPIError(f"Intervals.icu request failed: {exc}") from exc
        if response.status_code == 401:
            raise IntervalsAuthError(
                "Intervals.icu rejected the API key (401). "
                "Regenerate it under Settings → Developer Settings."
            )
        if response.status_code == 403:
            raise IntervalsAPIError(
                "Intervals.icu returned 403. Check athlete id and that the "
                "User-Agent is a browser string (Cloudflare)."
            )
        if response.status_code == 429:
            retry = response.headers.get("Retry-After")
            raise IntervalsAPIError(
                f"Intervals.icu rate limit (429). Retry-After: {retry or 'unknown'}"
            )
        if not response.ok:
            snippet = (response.text or "")[:240]
            raise IntervalsAPIError(
                f"Intervals.icu HTTP {response.status_code}: {snippet}"
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise IntervalsAPIError("Intervals.icu returned non-JSON") from exc

    def athlete(self) -> Any:
        """Profile for the key's athlete. Prefer ``/profile``, fall back to ``/athlete/{id}``."""
        try:
            return self._get(self._athlete_path("/profile"))
        except IntervalsAPIError as exc:
            if "HTTP 404" not in str(exc):
                raise
            return self._get(self._athlete_path())

    def sport_settings(self) -> Any:
        return self._get(self._athlete_path("/sport-settings"))

    def activities(self, oldest: str, newest: str) -> Any:
        return self._get(
            self._athlete_path("/activities"),
            params={"oldest": oldest, "newest": newest},
        )

    def activity(self, activity_id: str, include_intervals: bool = False) -> Any:
        params = {"intervals": "true"} if include_intervals else None
        return self._get(f"/activity/{activity_id}", params=params)

    def wellness(self, oldest: str, newest: str) -> Any:
        return self._get(
            self._athlete_path("/wellness"),
            params={"oldest": oldest, "newest": newest},
        )

    def events(self, oldest: str, newest: str) -> Any:
        return self._get(
            self._athlete_path("/events"),
            params={"oldest": oldest, "newest": newest},
        )


def get_client() -> IntervalsClient:
    key = load_api_key()
    if not key:
        raise IntervalsAuthError(
            "No Intervals.icu API key. Generate one at "
            "https://intervals.icu/settings (Developer Settings), then run "
            "intervals-icu-auth or set INTERVALS_ICU_API_KEY."
        )
    return IntervalsClient(api_key=key, athlete_id=get_athlete_id())


def _needs_setup() -> str:
    return json.dumps(
        {
            "status": "needs_setup",
            "service": "intervals.icu",
            "athlete_id_hint": KNOWN_ATHLETE_ID,
            "docs": "https://forum.intervals.icu/t/api-access-to-intervals-icu/609",
            "how": (
                "Create a key at https://intervals.icu/settings → Developer Settings. "
                "Auth is HTTP Basic username API_KEY, password = that key. "
                "Save it with intervals-icu-auth or INTERVALS_ICU_API_KEY. "
                "Do not commit the key."
            ),
        },
        indent=2,
    )


def _dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str)


def _parse_iso_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD") from exc


def _date_range(oldest: Optional[str], newest: Optional[str], default_days: int = 90):
    end = _parse_iso_date(newest, "newest") if newest else date.today()
    start = (
        _parse_iso_date(oldest, "oldest")
        if oldest
        else end - timedelta(days=default_days)
    )
    if start > end:
        raise ValueError("oldest must be on or before newest")
    return start.isoformat(), end.isoformat()


def register_tools(app):
    """Register Intervals.icu read tools. Independent of the Garmin client."""

    @app.tool()
    async def get_intervals_status() -> str:
        """Show whether the Intervals.icu personal API key is configured locally."""
        try:
            configured = key_configured()
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, indent=2)
        payload = {
            "status": "configured" if configured else "needs_setup",
            "athlete_id": get_athlete_id() if configured else KNOWN_ATHLETE_ID,
            "key_path": get_key_path(),
            "docs": "https://forum.intervals.icu/t/api-access-to-intervals-icu/609",
        }
        if not configured:
            payload["how"] = (
                "Create a key at https://intervals.icu/settings → Developer Settings, "
                "then run intervals-icu-auth. Username is literally API_KEY."
            )
        return json.dumps(payload, indent=2)

    @app.tool()
    async def get_intervals_athlete() -> str:
        """Get the Intervals.icu athlete profile for the saved API key."""
        try:
            return _dump(get_client().athlete())
        except IntervalsAuthError:
            return _needs_setup()
        except Exception as exc:
            return f"Error retrieving Intervals.icu athlete: {exc}"

    @app.tool()
    async def get_intervals_sport_settings() -> str:
        """Get Intervals.icu sport settings (FTP, LTHR, zones) for the saved key."""
        try:
            return _dump(get_client().sport_settings())
        except IntervalsAuthError:
            return _needs_setup()
        except Exception as exc:
            return f"Error retrieving Intervals.icu sport settings: {exc}"

    @app.tool()
    async def get_intervals_activities(
        oldest: Optional[str] = None,
        newest: Optional[str] = None,
    ) -> str:
        """List Intervals.icu activities between oldest and newest (YYYY-MM-DD).

        Defaults to the last 90 days. Strava-sourced fields are not available
        through this API.
        """
        try:
            start, end = _date_range(oldest, newest)
            return _dump(get_client().activities(start, end))
        except IntervalsAuthError:
            return _needs_setup()
        except Exception as exc:
            return f"Error retrieving Intervals.icu activities: {exc}"

    @app.tool()
    async def get_intervals_activity(
        activity_id: str,
        include_intervals: bool = False,
    ) -> str:
        """Get one Intervals.icu activity. Set include_intervals for detected intervals."""
        try:
            if not activity_id or not str(activity_id).strip():
                raise ValueError("activity_id is required")
            return _dump(
                get_client().activity(str(activity_id).strip(), include_intervals)
            )
        except IntervalsAuthError:
            return _needs_setup()
        except Exception as exc:
            return f"Error retrieving Intervals.icu activity: {exc}"

    @app.tool()
    async def get_intervals_wellness(
        oldest: Optional[str] = None,
        newest: Optional[str] = None,
    ) -> str:
        """Get daily Intervals.icu wellness plus CTL/ATL fitness fields.

        Dates are YYYY-MM-DD. Defaults to the last 90 days.
        """
        try:
            start, end = _date_range(oldest, newest)
            return _dump(get_client().wellness(start, end))
        except IntervalsAuthError:
            return _needs_setup()
        except Exception as exc:
            return f"Error retrieving Intervals.icu wellness: {exc}"

    @app.tool()
    async def get_intervals_events(
        oldest: Optional[str] = None,
        newest: Optional[str] = None,
    ) -> str:
        """List Intervals.icu calendar events (planned workouts) in a date range."""
        try:
            start, end = _date_range(oldest, newest, default_days=30)
            return _dump(get_client().events(start, end))
        except IntervalsAuthError:
            return _needs_setup()
        except Exception as exc:
            return f"Error retrieving Intervals.icu events: {exc}"

    return app
