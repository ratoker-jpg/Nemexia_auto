from __future__ import annotations

import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import CombatReport, SpyReport


COORD_RE = re.compile(r"(\d+)\s*[:\-]\s*(\d+)\s*[:\-]\s*(\d+)")


def _text(node: Tag | None) -> str:
    if node is None:
        return ""
    value = " ".join(node.get_text(" ", strip=True).split())
    # Some saved pages are decoded as mojibake by Windows tooling.
    if "Р" in value:
        try:
            repaired = value.encode("latin1").decode("utf-8")
            if any("а" <= char.lower() <= "я" for char in repaired):
                return repaired
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return value


def _number(value: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", value or "")
    return int(digits) if digits else None


def _coord(node: Tag) -> str | None:
    for link in node.select("a[href]"):
        match = re.search(r"[?&]c1=(\d+).*?[&]c2=(\d+).*?[&]c3=(\d+)", link.get("href", ""))
        if match:
            return ":".join(match.groups())
    match = COORD_RE.search(_text(node))
    return ":".join(match.groups()) if match else None


def _date(node: Tag) -> datetime | None:
    value = _text(node.select_one(".messageDate"))
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _message_id(node: Tag) -> str | None:
    body = node.select_one(".messageBody[id]")
    if body and body.get("id", "").startswith("body-"):
        return body["id"][5:]
    selected = node.select_one("input[name^='messageSelect']")
    if selected:
        return str(selected.get("value") or "") or None
    return None


def _resources(node: Tag) -> tuple[int | None, int | None, int | None]:
    values: dict[str, int] = {}
    for item in node.select(".messageResources li, tr"):
        classes = " ".join(item.get("class", []))
        label = f"{classes} {_text(item)}".lower()
        amount = _number(_text(item))
        if amount is None:
            continue
        if "metal" in label or "металл" in label:
            values["metal"] = amount
        elif "crystal" in label or "mineral" in label or "минерал" in label:
            values["minerals"] = amount
        elif "gas" in label or "газ" in label:
            values["gas"] = amount
    return values.get("metal"), values.get("minerals"), values.get("gas")


def _spy_values(node: Tag) -> dict[str, int]:
    values: dict[str, int] = {}
    labels = {
        "энерг": "energy", "energy": "energy", "металл": "metal", "metal": "metal",
        "минерал": "minerals", "crystal": "minerals", "газ": "gas", "gas": "gas",
        "населен": "population", "population": "population", "кораб": "ships", "ship": "ships",
        "оборон": "defense", "defen": "defense",
    }
    for row in node.select("tr"):
        cells = row.select("td")
        if len(cells) < 2:
            continue
        label, amount = _text(cells[0]).lower(), _number(_text(cells[1]))
        if amount is None:
            continue
        for token, key in labels.items():
            if token in label:
                values[key] = amount
                break
    # Some reports use resource list markup instead of a table.
    metal, minerals, gas = _resources(node)
    for key, value in (("metal", metal), ("minerals", minerals), ("gas", gas)):
        if value is not None:
            values[key] = value
    return values


def _items(html: str) -> list[Tag]:
    soup = BeautifulSoup(html, "html.parser")
    return list(soup.select(".messageItem"))


def parse_spy_reports_html(html: str) -> list[SpyReport]:
    reports: list[SpyReport] = []
    for item in _items(html):
        body = item.select_one(".messageBody")
        text = _text(body or item).lower()
        if not any(token in text for token in ("шпион", "espionage", "spy")):
            continue
        coord = _coord(body or item)
        if not coord:
            continue
        values = _spy_values(body or item)
        reports.append(SpyReport(
            coord=coord, player="—", energy=values.get("energy", 0), report_at=_date(item),
            message_id=_message_id(item), metal=values.get("metal"), minerals=values.get("minerals"),
            gas=values.get("gas"), population=values.get("population"), ships=values.get("ships"),
            defense=values.get("defense"), completeness="partial" if not values else "reported",
            raw_payload=_text(body or item),
        ))
    return reports


def parse_battle_reports_html(html: str) -> list[CombatReport]:
    reports: list[CombatReport] = []
    for item in _items(html):
        body = item.select_one(".messageBody")
        if body is None:
            continue
        if not (body.select_one(".battleReportLink, .messageResult") or "бой" in _text(body).lower()):
            continue
        coord = _coord(body)
        if not coord:
            continue
        metal, minerals, gas = _resources(body)
        reports.append(CombatReport(
            coord=coord, report_at=_date(item), message_id=_message_id(item),
            result=_text(body.select_one(".messageResult")) or None,
            metal=metal, minerals=minerals, gas=gas, raw_payload=_text(body),
        ))
    return reports


def parse_report_html(html: str) -> list[SpyReport]:
    """Compatibility entry point for the prior spy-only importer."""
    return parse_spy_reports_html(html)


def parse_report_file(path: Path) -> list[SpyReport]:
    return parse_report_html(path.read_text(encoding="utf-8", errors="ignore"))


def parse_report_paths(paths: Iterable[Path]) -> list[SpyReport]:
    """Compatibility import: returns only the newest spy snapshot per target."""
    collected: dict[str, SpyReport] = {}
    for path in paths:
        if path.suffix.lower() in {".html", ".htm"}:
            source = path.read_text(encoding="utf-8", errors="ignore")
            for report in parse_spy_reports_html(source):
                current = collected.get(report.coord)
                if current is None or (report.report_at and (current.report_at is None or report.report_at >= current.report_at)):
                    collected[report.coord] = report
        elif path.suffix.lower() == ".zip":
            with tempfile.TemporaryDirectory(prefix="nemexia_reports_") as temp:
                root = Path(temp)
                with zipfile.ZipFile(path) as archive:
                    archive.extractall(root)
                for report in parse_report_paths(root.rglob("*.htm*")):
                    current = collected.get(report.coord)
                    if current is None or (report.report_at and (current.report_at is None or report.report_at >= current.report_at)):
                        collected[report.coord] = report
    return sorted(collected.values(), key=lambda item: tuple(int(x) for x in item.coord.split(":")))
