from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_debris_discovery_remains_attach_only_and_current_system_only() -> None:
    reader = text("v2/infrastructure/cdp_debris_reader.py")
    asteroid_reader = text("v2/infrastructure/cdp_asteroid_reader.py")
    page = text("v2/ui/pages/debris.py")
    assert "class ReadOnlyDebrisCdpBackend(ReadOnlyAsteroidCdpBackend)" in reader
    assert "_read_current_galaxy" in reader
    assert "fetch('ajax_info.php'" in asteroid_reader
    assert "type:'squareInfo'" in asteroid_reader
    assert "Прочитать открытую систему" in page
    assert "автоматический обход 3×40" in page
    for forbidden in (
        "refreshGalaxy(",
        "ajax_galaxy.php",
        ".goto(",
        "new_page(",
        "launch_yandex",
    ):
        assert forbidden not in reader
        assert forbidden not in page


def test_debris_uses_one_authoritative_asteroid_mutation_and_journal_boundary() -> None:
    dispatch = text("v2/application/debris_dispatch.py")
    context = text("v2/application/debris_context.py")
    journal = text("v2/application/asteroid_journal.py")
    backend = text("v2/infrastructure/cdp_asteroid_backend.py")
    asteroid_domain = text("v2/domain/asteroids.py")

    assert "AsteroidDispatchCommand" in dispatch
    assert "AsteroidRequestCoordinator" in dispatch
    assert "AsteroidRequestCoordinator(self._asteroid_actions, database)" in context
    assert "DebrisDispatchReuseGate(coordinator)" in context
    assert "idx_asteroid_actions_unresolved_identity" in text("v2/persistence/asteroid_journal.py")
    assert "pending" in journal and "ambiguous" in journal
    assert "#ship_1_11_max" in backend
    assert "#FleetsCount" in backend and "#MaxFleets" in backend
    assert "select_verified_asteroid_flight(" in backend
    assert "ASTEROID_MISSION_NAME" in backend
    assert 'ASTEROID_MISSION_NAME = "Добыча газа"' in asteroid_domain
    assert "#SendFleetButton" in backend

    combined = dispatch + context
    assert '"debris_actions"' not in combined
    assert "CREATE TABLE debris_actions" not in combined
    assert "class V2DebrisCdpBackend" not in combined


def test_debris_evidence_is_v2_owned_append_only_and_does_not_fake_full_scan() -> None:
    storage = text("v2/persistence/debris_candidates.py")
    repository = text("v2/application/debris_repository.py")
    domain = text("v2/domain/debris.py")
    database = text("v2/persistence/database.py")

    assert "CREATE TABLE IF NOT EXISTS debris_observations" in storage
    assert "UNIQUE(" in storage
    assert "INSERT OR IGNORE INTO debris_observations" in storage
    assert "DebrisReadState.NO_DEBRIS" in repository
    assert "return DebrisIngestResult(0, 0" in repository
    assert "PARTIAL_EVIDENCE" in domain
    assert "LIVE_UNAVAILABLE" in domain
    assert "CAPTCHA" in domain
    assert "V2_SCHEMA_VERSION = 8" in database
    for forbidden in (
        "DELETE FROM debris_observations",
        "completed 120",
        "120/120",
    ):
        assert forbidden.casefold() not in repository.casefold()


def test_debris_controlled_workflow_is_bounded_confirmed_stop_first_and_non_repeating() -> None:
    workflow = text("v2/application/debris_workflow.py")
    page = text("v2/ui/pages/debris.py")
    assert "DEBRIS_SELECTED_BATCH_LIMIT = ASTEROID_SELECTED_BATCH_LIMIT" in workflow
    assert "AWAITING_CONFIRMATION" in workflow
    assert "confirmation_id" in workflow
    assert "STOPPED_CAPTCHA" in workflow
    assert "STOPPED_AMBIGUOUS" in workflow
    assert "STOPPED_ERROR" in workflow
    assert "STOPPED_MANUAL" in workflow
    assert "self._stop_requested" in workflow
    assert "request_debris_stop" in page
    assert "cancel_debris_preparation" in page
    for forbidden in (
        "QTimer",
        ".retry(",
        "sleep(",
        "debris_scheduler",
        "debris_auto_repeat",
        "debris_next_cycle_at",
    ):
        assert forbidden not in workflow


def test_recovery_matrix_is_pinned_by_concrete_regressions() -> None:
    hardening = text("tests/test_v2_debris_recovery_hardening.py")
    repository = text("tests/test_v2_debris_repository.py")
    reader = text("tests/test_v2_attach_only_debris_reader.py")
    workflow = text("tests/test_v2_debris_workflow.py")
    reuse = text("tests/test_v2_debris_dispatch_reuse.py")

    for required in (
        "pending_debris_attempt_survives_restart",
        "ambiguous_and_unknown_after_possible_acceptance_survive_restart",
        "proven_pre_acceptance_failures_are_failed_safe_without_retry_loop",
        "marker_missing_is_proven_no_debris_but_partial_marker_is_not",
        "page_hide_input_change_and_window_close_disarm_future_debris_attempts",
    ):
        assert required in hardening
    for required in (
        "survives_restart",
        "exact_duplicates",
        "no_debris_never_erases_other_system_evidence",
        "reading_two_manually_opened_systems_accumulates_evidence",
    ):
        assert required in repository
    assert "partial_square_info_stays_partial" in reader
    assert "manual_stop_during_started_attempt_does_not_cancel_it_but_blocks_next" in workflow
    assert "debris_label_cannot_bypass_same_unresolved_asteroid_trajectory" in reuse


def test_legacy_storage_default_launcher_and_deferred_boundaries_remain_intact() -> None:
    read_store = text("v2/application/read_store.py")
    launcher = text("run_app.bat")
    qt = text("app_qt.py")
    debris_page = text("v2/ui/pages/debris.py")

    assert "mode=ro" in read_store
    assert "PRAGMA query_only=ON" in read_store
    assert "app_entry.py" in launcher
    assert "app_qt.py" not in launcher
    assert "DebrisEnabledApplicationContext" in qt

    combined = qt + debris_page + text("v2/application/debris_context.py")
    for forbidden in (
        "delete_messages",
        "processSpy(0)",
        "solve_captcha",
        "click_captcha",
        "debris_auto_enabled",
        "debris_next_cycle_at",
        "refreshGalaxy(",
        "ajax_galaxy.php",
    ):
        assert forbidden not in combined
