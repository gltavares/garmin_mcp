"""CLI to store an Intervals.icu personal API key locally.

The key is written to ``~/.intervalsicu/api_key`` (mode 0600). It is never
committed. Username for the HTTP call is literally ``API_KEY``.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from garmin_mcp.intervals import (
    IntervalsAPIError,
    IntervalsAuthError,
    IntervalsClient,
    KNOWN_ATHLETE_ID,
    get_athlete_id,
    get_key_path,
    key_configured,
    load_api_key,
    save_api_key,
)


def get_api_key_from_user() -> str:
    env_key = None
    try:
        env_key = load_api_key()
    except ValueError:
        env_key = None
    # load_api_key() also reads the stored file; only treat env/file-env as provided.
    if os.getenv("INTERVALS_ICU_API_KEY") or os.getenv("INTERVALS_API_KEY") or os.getenv(
        "ICU_API_KEY"
    ) or os.getenv("INTERVALS_ICU_API_KEY_FILE"):
        if env_key:
            return env_key
    if not sys.stdin.isatty():
        raise ValueError(
            "No Intervals.icu API key. Set INTERVALS_ICU_API_KEY or run "
            "intervals-icu-auth in a terminal."
        )
    print("\nIntervals.icu API key")
    print("-" * 40)
    print("Settings → Developer Settings on https://intervals.icu/settings")
    key = getpass.getpass("API key: ").strip()
    if not key:
        raise ValueError("API key is required")
    return key


def verify_key(api_key: str, athlete_id: str) -> dict:
    client = IntervalsClient(api_key=api_key, athlete_id=athlete_id)
    profile = client.athlete()
    if not isinstance(profile, dict):
        raise IntervalsAPIError("Unexpected Intervals.icu athlete payload")
    return profile


def _profile_label(profile: dict) -> str:
    name = profile.get("name") or profile.get("icu_name") or "unknown"
    athlete_id = profile.get("id") or profile.get("athlete_id") or get_athlete_id()
    return f"{name} ({athlete_id})"


def authenticate(force: bool = False, athlete_id: str | None = None) -> int:
    stored_id = athlete_id or get_athlete_id()
    if key_configured() and not force:
        key = load_api_key()
        try:
            profile = verify_key(key, stored_id)
        except (IntervalsAuthError, IntervalsAPIError) as exc:
            print(f"Saved Intervals.icu key failed: {exc}", file=sys.stderr)
            if not force:
                print("Re-run with --force-reauth to replace it.", file=sys.stderr)
                return 1
        else:
            print(f"Intervals.icu already connected as {_profile_label(profile)}")
            print(f"Key file: {get_key_path()}")
            return 0

    key = get_api_key_from_user()
    profile = verify_key(key, stored_id)
    resolved_id = str(profile.get("id") or stored_id or KNOWN_ATHLETE_ID)
    save_api_key(key, resolved_id)
    print(f"Connected to Intervals.icu as {_profile_label(profile)}")
    print(f"Key saved to {get_key_path()} (not in git)")
    return 0


def verify_tokens() -> int:
    if not key_configured():
        print(
            "No Intervals.icu API key. Run intervals-icu-auth or set "
            "INTERVALS_ICU_API_KEY.",
            file=sys.stderr,
        )
        return 1
    try:
        profile = verify_key(load_api_key(), get_athlete_id())
    except (IntervalsAuthError, IntervalsAPIError, ValueError) as exc:
        print(f"Intervals.icu verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Intervals.icu OK: {_profile_label(profile)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Save an Intervals.icu personal API key to ~/.intervalsicu"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Check the saved or env key against GET /athlete/0/profile",
    )
    parser.add_argument(
        "--force-reauth",
        action="store_true",
        help="Replace a saved key",
    )
    parser.add_argument(
        "--athlete-id",
        default=None,
        help="Athlete id (default 0, which follows the key). Gabriel is i172982.",
    )
    args = parser.parse_args(argv)

    try:
        if args.verify:
            return verify_tokens()
        return authenticate(force=args.force_reauth, athlete_id=args.athlete_id)
    except (ValueError, IntervalsAuthError, IntervalsAPIError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
