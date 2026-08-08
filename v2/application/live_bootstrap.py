from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from v2.application.context import legacy_db_path
from v2.application.read_store import ReadOnlyStore, ReadStoreUnavailable


DEFAULT_CDP_PORT = 9222


@dataclass(frozen=True)
class CdpEndpointConfig:
    endpoint: str
    source: str


def resolve_legacy_source_path(*, environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    override = str(env.get("NEMEXIA_V2_READ_DB", "")).strip()
    if override:
        return Path(override).expanduser()
    return legacy_db_path(environ=dict(env))


def _valid_port(value: str | int | None) -> int | None:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def resolve_cdp_endpoint(
    source_path: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> CdpEndpointConfig:
    """Resolve V2's attach-only CDP endpoint without mutating legacy storage."""
    env = os.environ if environ is None else environ
    endpoint_override = str(env.get("NEMEXIA_V2_CDP_ENDPOINT", "")).strip()
    if endpoint_override:
        return CdpEndpointConfig(endpoint_override.rstrip("/"), "environment override")

    port_override = _valid_port(env.get("NEMEXIA_V2_CDP_PORT"))
    if port_override is not None:
        return CdpEndpointConfig(
            f"http://127.0.0.1:{port_override}",
            "environment port override",
        )

    port = DEFAULT_CDP_PORT
    source = "default port"
    try:
        with ReadOnlyStore(Path(source_path)) as store:
            saved = _valid_port(store.get_setting("port"))
            if saved is not None:
                port = saved
                source = "legacy SQLite setting: port"
    except ReadStoreUnavailable:
        pass

    return CdpEndpointConfig(f"http://127.0.0.1:{port}", source)
