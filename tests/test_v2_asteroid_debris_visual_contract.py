from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASTEROIDS = (ROOT / "v2" / "ui" / "pages" / "asteroids.py").read_text(encoding="utf-8")
DEBRIS = (ROOT / "v2" / "ui" / "pages" / "debris.py").read_text(encoding="utf-8")


def test_asteroid_and_debris_share_command_visual_language() -> None:
    for source, title in ((ASTEROIDS, "Asteroid command"), (DEBRIS, "Debris command")):
        assert title in source
        assert "ATTACH-ONLY · CURRENT SYSTEM" in source
        assert "SOURCE" in source
        assert "RECYCLERS / TARGET" in source
        assert "SAFETY · SEC" in source
        assert 'tone="warning"' in source
        assert 'tone="danger"' in source
        assert "ExtendedSelection" in source


def test_asteroid_workflow_keeps_existing_bounded_dispatch_contract() -> None:
    for token in (
        'getattr(self.context, "live_asteroids", None)',
        'getattr(self.context, "ingest_asteroid_observations", None)',
        'getattr(self.context, "prepare_asteroid_candidates", None)',
        'getattr(self.context, "dispatch_asteroid_candidates", None)',
        "should_stop=self._poll_manual_stop",
        "QApplication.processEvents()",
        "STOPPED_MANUAL",
        "автоматических повторов нет",
    ):
        assert token in ASTEROIDS


def test_debris_keeps_separate_confirmation_and_lifecycle_contract() -> None:
    for token in (
        'context.legacy_setting("debris_recyclers", "100")',
        'getattr(self.context, "live_debris", None)',
        'getattr(self.context, "ingest_debris_read", None)',
        'getattr(self.context, "prepare_debris_candidates", None)',
        'getattr(self.context, "cancel_debris_preparation", None)',
        'getattr(self.context, "confirm_debris_candidates", None)',
        'getattr(self.context, "request_debris_stop", None)',
        "confirmation_id",
        "STOPPED_MANUAL",
        "автоматический обход 3×40",
        "Прочитать открытую систему",
    ):
        assert token in DEBRIS


def test_candidate_pages_add_no_browser_navigation_primitives() -> None:
    combined = ASTEROIDS + DEBRIS
    for forbidden in (
        "from browser import",
        "import browser",
        "BrowserWorker",
        "playwright",
        ".goto(",
        "new_page(",
        "refreshGalaxy(",
        "change_planet.php",
        "launch_yandex(",
        "QTimer",
    ):
        assert forbidden not in combined
