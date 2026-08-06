from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def application_directory(
    *,
    frozen: bool | None = None,
    executable: str | Path | None = None,
    module_file: str | Path | None = None,
) -> Path:
    """Return the folder containing the source project or the built executable."""
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else bool(frozen)
    if is_frozen:
        return Path(executable or sys.executable).resolve().parent
    return Path(module_file or __file__).resolve().parent


def default_snapshot_root() -> Path:
    """Keep manual snapshots next to the project or packaged application."""
    return application_directory() / "saved_pages"


async def _focused_game_page(worker: Any):
    """Return the focused Nemexia tab, with safe fallbacks to the worker page."""
    browser = getattr(worker, "_browser", None)
    if browser is None:
        raise RuntimeError("Браузер не подключён")

    pages = [
        page
        for context in browser.contexts
        for page in context.pages
        if not page.is_closed() and "game.ares.nemexia.com" in page.url
    ]
    if not pages:
        raise RuntimeError("Открытая вкладка Nemexia не найдена")

    for page in pages:
        try:
            if await page.evaluate("() => document.hasFocus()"):
                return page
        except Exception:
            continue

    current = getattr(worker, "_page", None)
    if current in pages:
        return current
    return pages[0]


def _cleanup_snapshots(root: Path, keep: int) -> None:
    snapshots = sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    for old in snapshots[max(1, int(keep)):]:
        shutil.rmtree(old, ignore_errors=True)


async def capture_current_page(worker: Any, root: Path, *, keep: int = 10) -> dict[str, str]:
    """Save the current Nemexia page as screenshot, DOM HTML, MHTML and metadata."""
    page = await _focused_game_page(worker)
    root.mkdir(parents=True, exist_ok=True)

    now = datetime.now().astimezone()
    folder = root / now.strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]
    folder.mkdir(parents=True, exist_ok=False)

    screenshot_path = folder / "screenshot.png"
    html_path = folder / "page.html"
    mhtml_path = folder / "page.mhtml"
    metadata_path = folder / "metadata.json"

    warnings: list[str] = []
    title = ""
    try:
        title = await page.title()
    except Exception as exc:
        warnings.append(f"Не прочитан заголовок: {exc}")

    try:
        await page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception as exc:
        warnings.append(f"Не сохранён скриншот: {exc}")

    try:
        html_path.write_text(await page.content(), encoding="utf-8")
    except Exception as exc:
        warnings.append(f"Не сохранён HTML: {exc}")

    session = None
    try:
        session = await page.context.new_cdp_session(page)
        snapshot = await session.send("Page.captureSnapshot", {"format": "mhtml"})
        data = str(snapshot.get("data") or "")
        if not data:
            raise RuntimeError("Chromium вернул пустой MHTML")
        mhtml_path.write_text(data, encoding="utf-8")
    except Exception as exc:
        warnings.append(f"Не сохранён MHTML: {exc}")
    finally:
        if session is not None:
            try:
                await session.detach()
            except Exception:
                pass

    metadata = {
        "captured_at": now.isoformat(),
        "url": page.url,
        "title": title,
        "warnings": warnings,
        "files": {
            "screenshot": screenshot_path.name if screenshot_path.exists() else None,
            "html": html_path.name if html_path.exists() else None,
            "mhtml": mhtml_path.name if mhtml_path.exists() else None,
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    if not any(path.exists() for path in (screenshot_path, html_path, mhtml_path)):
        shutil.rmtree(folder, ignore_errors=True)
        raise RuntimeError("Не удалось сохранить ни один файл страницы")

    _cleanup_snapshots(root, keep)
    return {
        "folder": str(folder),
        "url": page.url,
        "title": title,
        "warnings": "\n".join(warnings),
    }
