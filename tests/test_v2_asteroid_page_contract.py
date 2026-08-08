from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "v2/ui/pages/asteroids.py").read_text(encoding="utf-8")
WINDOW = (ROOT / "v2/ui/main_window.py").read_text(encoding="utf-8")
CONTEXT = (ROOT / "v2/application/asteroid_context.py").read_text(encoding="utf-8")
WORKFLOW = (ROOT / "v2/application/asteroid_workflow.py").read_text(encoding="utf-8")


def test_asteroid_navigation_uses_real_v2_page_not_placeholder() -> None:
    assert "from v2.ui.pages.asteroids import AsteroidsPage" in WINDOW
    assert 'if key == "asteroids":' in WINDOW
    assert "return AsteroidsPage(self.context, self)" in WINDOW


def test_page_uses_typed_context_boundaries_not_browser_backend_or_ui_text_logic() -> None:
    for required in (
        "live_asteroids",
        "ingest_asteroid_observations",
        "asteroid_candidates",
        "prepare_asteroid_candidates",
        "dispatch_asteroid_candidates",
        "AsteroidReadState.CAPTCHA",
        "AsteroidWorkflowState.READY",
        "AsteroidWorkflowState.COMPLETED",
        "ExtendedSelection",
    ):
        assert required in PAGE
    for forbidden in (
        "V2AsteroidCdpBackend",
        "ReadOnlyAsteroidCdpBackend",
        "SendFleet(",
        "page.evaluate",
        ".goto(",
        "refreshGalaxy",
        "QTimer",
        "deleteSelectedMessages",
        "processSpy",
    ):
        assert forbidden not in PAGE


def test_context_owns_candidate_repository_and_routes_series_through_journaled_dispatch() -> None:
    assert "V2AsteroidRepository" in CONTEXT
    assert "def asteroid_candidates(" in CONTEXT
    assert "def ingest_asteroid_observations(" in CONTEXT
    assert "def asteroid_action_record(" in CONTEXT
    assert "prepare_selected_asteroids(" in CONTEXT
    assert "dispatch_selected_asteroids(" in CONTEXT
    assert "AsteroidRequestCoordinator" in CONTEXT


def test_bounded_workflow_has_no_retry_scheduler_or_browser_dependency() -> None:
    assert "ASTEROID_SELECTED_BATCH_LIMIT = 200" in WORKFLOW
    assert "STOPPED_CAPTCHA" in WORKFLOW
    assert "STOPPED_AMBIGUOUS" in WORKFLOW
    assert "STOPPED_ERROR" in WORKFLOW
    assert "asteroid_action_record" in WORKFLOW
    for forbidden in (
        "while True",
        "for attempt in",
        "retry_count",
        "max_retries",
        "QTimer",
        "playwright",
        "CDP",
        "SendFleet",
        "sleep(",
    ):
        assert forbidden not in WORKFLOW
