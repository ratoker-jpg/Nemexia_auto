from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from v2.domain.recon import SpyReportFact, server_wall_clock_to_utc


_SPY_MARKERS = ("шпион", "spy", "espionage")
_RESOURCE_LABELS = {
    "energy": ("энерг", "energy"),
    "metal": ("металл", "metal"),
    "minerals": ("минерал", "mineral"),
    "gas": ("газ", "gas"),
}


def _number(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9-]", "", value)
    if not digits or digits == "-":
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _message_id(item) -> str | None:
    body = item.select_one(".messageBody[id]")
    if body is not None:
        value = str(body.get("id") or "").strip()
        if value.startswith("body-") and len(value) > 5:
            return value[5:]
    selected = item.select_one("input[name^='messageSelect'][value]")
    if selected is not None:
        value = str(selected.get("value") or "").strip()
        if value:
            return value
    return None


def _target(item) -> str:
    for anchor in item.select("a[href]"):
        query = parse_qs(urlparse(str(anchor.get("href") or "")).query)
        if all(query.get(key) for key in ("c1", "c2", "c3")):
            try:
                parts = [int(query[key][0]) for key in ("c1", "c2", "c3")]
            except (TypeError, ValueError):
                continue
            if all(part > 0 for part in parts):
                return ":".join(str(part) for part in parts)
    match = re.search(r"\b(\d+)\s*:\s*(\d+)\s*:\s*(\d+)\b", item.get_text(" ", strip=True))
    if match and all(int(part) > 0 for part in match.groups()):
        return ":".join(match.groups())
    return ""


def _reported_at(item) -> datetime | None:
    node = item.select_one(".messageDate")
    text = node.get_text(" ", strip=True) if node is not None else ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
        try:
            return server_wall_clock_to_utc(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return None


def _resources(item) -> dict[str, int | None]:
    result: dict[str, int | None] = {key: None for key in _RESOURCE_LABELS}
    for row in item.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("th,td")]
        if len(cells) < 2:
            continue
        label = cells[0].lower()
        for key, markers in _RESOURCE_LABELS.items():
            if any(marker in label for marker in markers):
                result[key] = _number(cells[-1])
                break
    return result


def parse_rendered_spy_reports(html: str) -> tuple[SpyReportFact, ...]:
    """Parse only already-rendered administrative message DOM into V2 facts."""

    soup = BeautifulSoup(html or "", "html.parser")
    reports: list[SpyReportFact] = []
    for item in soup.select(".messageItem"):
        text = item.get_text(" ", strip=True)
        if not any(marker in text.lower() for marker in _SPY_MARKERS):
            continue
        target = _target(item)
        if not target:
            continue
        resources = _resources(item)
        reports.append(
            SpyReportFact(
                report_id=_message_id(item),
                target=target,
                reported_at=_reported_at(item),
                energy=resources["energy"],
                metal=resources["metal"],
                minerals=resources["minerals"],
                gas=resources["gas"],
                source="browser:TabAdministrative",
            )
        )
    return tuple(reports)
