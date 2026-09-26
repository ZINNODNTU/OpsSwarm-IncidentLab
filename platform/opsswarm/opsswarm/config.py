from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml


def _load_dotenv() -> None:
    """Load the project .env without overriding explicit process environment."""
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[1] / ".env"]
    env_path = next((p for p in candidates if p.is_file()), None)
    if not env_path:
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv()

_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return _PATTERN.sub(lambda m: os.getenv(m.group(1), m.group(0)), value)
    if isinstance(value, list): return [_expand(v) for v in value]
    if isinstance(value, dict): return {k: _expand(v) for k, v in value.items()}
    return value


def load_config(path: str | None = None) -> dict[str, Any]:
    default_path = Path(__file__).resolve().parents[1] / "config" / "production.yaml"

    # A caller-supplied path is authoritative and must fail fast when wrong.
    if path is not None:
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(f"OpsSwarm config not found: {config_path}")
    else:
        # OPSWARM_CONFIG is a deployment hint. A stale absolute path can remain
        # after moving/cloning the workspace on Windows, so fall back to this
        # repository's production config instead of making imports unusable.
        env_path = os.getenv("OPSWARM_CONFIG")
        candidate = Path(env_path) if env_path else default_path
        config_path = candidate if candidate.is_file() else default_path
        if not config_path.is_file():
            raise FileNotFoundError(f"OpsSwarm default config not found: {config_path}")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return _expand(data)
