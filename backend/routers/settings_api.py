"""
Settings endpoint — read/write API keys to backend/.env.

GET  /api/v1/settings  — returns which keys are set (masked, never exposes values)
POST /api/v1/settings  — writes keys to backend/.env (empty string = clear key)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["settings"])

ENV_PATH = Path(__file__).parent.parent / ".env"

KNOWN_KEYS = ["SARVAM_API_KEY", "OPENROUTER_API_KEY", "GOOGLE_API_KEY"]


def _read_env() -> dict[str, str]:
    """Parse .env file into a dict."""
    result: dict[str, str] = {}
    if not ENV_PATH.exists():
        return result
    for line in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env(data: dict[str, str]) -> None:
    """Write .env file, preserving comments and unknown lines."""
    existing_lines = ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines() if ENV_PATH.exists() else []
    written_keys: set[str] = set()
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            new_lines.append(line)
            continue
        if "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in data:
                if data[k]:  # only write if value non-empty
                    new_lines.append(f"{k}={data[k]}")
                # if empty, drop the line (clearing the key)
                written_keys.add(k)
                continue
        new_lines.append(line)

    # Append any new keys not already in file
    for k, v in data.items():
        if k not in written_keys and v:
            new_lines.append(f"{k}={v}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


class SettingsResponse(BaseModel):
    sarvam_key_set: bool
    openrouter_key_set: bool
    google_key_set: bool


class SettingsWrite(BaseModel):
    sarvam_api_key: str | None = None
    openrouter_api_key: str | None = None
    google_api_key: str | None = None


@router.get("/settings", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """Return which API keys are configured (never exposes key values)."""
    env = _read_env()
    return SettingsResponse(
        sarvam_key_set=bool(env.get("SARVAM_API_KEY", "").strip()),
        openrouter_key_set=bool(env.get("OPENROUTER_API_KEY", "").strip()),
        google_key_set=bool(env.get("GOOGLE_API_KEY", "").strip()),
    )


@router.post("/settings", response_model=SettingsResponse)
async def save_settings(body: SettingsWrite) -> SettingsResponse:
    """Save API keys to backend/.env. Also updates os.environ for immediate use."""
    updates: dict[str, str] = {}
    if body.sarvam_api_key is not None:
        updates["SARVAM_API_KEY"] = body.sarvam_api_key.strip()
    if body.openrouter_api_key is not None:
        updates["OPENROUTER_API_KEY"] = body.openrouter_api_key.strip()
    if body.google_api_key is not None:
        updates["GOOGLE_API_KEY"] = body.google_api_key.strip()

    _write_env(updates)

    # Update live environment so translate.py picks up new keys without restart
    for k, v in updates.items():
        if v:
            os.environ[k] = v
        elif k in os.environ:
            del os.environ[k]

    return await get_settings()
