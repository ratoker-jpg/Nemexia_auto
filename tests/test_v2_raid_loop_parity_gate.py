from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_default_launcher_and_rollback_boundary_remain_legacy_safe() -> None:
    launcher = text("run_app.bat")
    assert "app_entry.py" in launcher
    assert "app_qt.py" not in launcher


def test_legacy_sqlite_boundary_remains_strictly_read_only() -> None:
    store = text("v2/application/read_store.py")
    assert "?mode=ro" in store
    assert 'PRAGMA query_only=ON' in store
    for forbidden in ("INSERT INTO targets", "UPDATE targets", "DELETE FROM targets"):
        assert forbidden not in store


def test_spy_mutation_is_exact_fleet_one_attempt_not_bulk() -> None:
    backend = text("v2/infrastructure/cdp_spy_backend.py")
    journal = text("v2/application/spy_journal.py")
    assert "window.processSpy(Number(fleetId))" in backend
    assert "Exactly one game mutation attempt" in backend
    assert "processSpy(0)" not in backend
    assert "begin_spy_action" in journal
    assert "status=\"ambiguous\"" in journal
    assert "automatic retry" in journal


def test_verified_recon_is_exact_and_empty_scan_cooldown_is_separate() -> None:
    refill = text("v2/application/recon_refill.py")
    recon = text("v2/domain/recon.py")
    settings = text("v2/application/v2_settings.py")
    assert "report.report_id == result.report_id" in refill
    assert "report.target == result.target" in refill
    assert "as_utc(report.reported_at) == as_utc(result.report_at)" in refill
    assert "LEGACY_EMPTY_SCAN_COOLDOWN_MINUTES = 25" in recon
    assert 'COOLDOWN_SETTING = "farm_no_target_cooldown_until"' in refill
    assert '"farm_no_target_cooldown_until"' in settings
    assert '"farm_return_buffer_minutes"' in settings


def test_queue_policies_keep_accepted_metal_mineral_autofarm_contracts() -> None:
    recon = text("v2/domain/recon.py")
    policy = text("v2/domain/queue_policy.py")
    assert "LEGACY_METAL_QUEUE_MINIMUM = 480_000" in recon
    assert "LEGACY_AUTOFARM_MINERALS_MINIMUM = 500_000" in recon
    assert 'if mode == "metal"' in policy
    assert "int(item.metal) < max(0, int(minimum_metal))" in policy
    assert 'elif mode == "minerals"' in policy
    assert "item.minerals is None" in policy
    assert 'elif mode == "autofarm"' in policy
    assert "int(item.minerals) < LEGACY_AUTOFARM_MINERALS_MINIMUM" in policy
    assert "-int(item.minerals or 0), -int(item.metal or 0), item.coord" in policy


def test_continuous_cycle_is_explicit_session_only_and_fail_closed() -> None:
    farm = text("v2/ui/pages/farm.py")
    controller = text("v2/application/farm_controller.py")
    assert "self._armed = False" in farm
    assert "FarmSpyFleetId" in farm
    assert "Spy fleet ID тоже не сохраняется" in farm
    assert "run_controlled_recon_refill" in farm
    assert "FarmState.NEED_RECON" in farm
    assert "FarmState.BLOCKED_UNRESOLVED" in farm
    assert "recent_spy_actions" in controller
    assert "unresolved_spy" in controller
    for forbidden in ("processSpy(0)", "deleteSelectedMessages", "deleteAllMessages"):
        assert forbidden not in farm


def test_captcha_and_browser_navigation_remain_outside_v2_automation_contract() -> None:
    spy = text("v2/infrastructure/cdp_spy_backend.py")
    read = text("v2/infrastructure/cdp_read_backend.py")
    combined = spy + read
    assert "SpyCaptchaBlocked" in spy
    for forbidden in (".goto(", "new_page(", "solve_captcha", "click_captcha"):
        assert forbidden not in combined


def test_v2_storage_contains_owned_action_and_recon_state() -> None:
    database = text("v2/persistence/database.py")
    asteroid_journal = text("v2/persistence/asteroid_journal.py")
    assert "V2_SCHEMA_VERSION = 7" in database
    for table in ("raid_actions", "raid_queue", "spy_actions", "recon_targets", "recon_reports"):
        assert table in database
    assert "asteroid_actions" in asteroid_journal
    assert "idx_asteroid_actions_unresolved_identity" in asteroid_journal
