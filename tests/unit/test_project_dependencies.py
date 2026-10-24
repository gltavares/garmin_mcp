"""Project metadata regression tests."""

from pathlib import Path


def test_project_caps_mcp_to_v1_series() -> None:
    """The project should explicitly stay on the MCP v1 series for compatibility."""
    repo_root = Path(__file__).resolve().parents[2]
    pyproject_text = (repo_root / "pyproject.toml").read_text()

    assert '"mcp>=1.30.0,<2"' in pyproject_text


def test_project_requires_patched_garminconnect_and_python() -> None:
    """Token-store permissions are fixed in garminconnect 0.3.5, which needs Python 3.12."""
    repo_root = Path(__file__).resolve().parents[2]
    pyproject_text = (repo_root / "pyproject.toml").read_text()

    assert 'requires-python = ">=3.12"' in pyproject_text
    assert '"garminconnect>=0.3.5"' in pyproject_text
