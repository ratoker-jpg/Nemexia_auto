from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'v2' / 'ui' / 'main_window.py').read_text(encoding='utf-8')
RECON = (ROOT / 'v2' / 'ui' / 'pages' / 'recon.py').read_text(encoding='utf-8')
STORE = (ROOT / 'v2' / 'application' / 'read_store.py').read_text(encoding='utf-8')


def test_recon_page_replaces_placeholder() -> None:
    assert 'if key == "recon"' in MAIN
    assert 'ReconPage(self.context' in MAIN
    assert 'context.recon()' in RECON


def test_recon_source_is_persisted_spy_reports_only() -> None:
    assert 'FROM spy_reports' in STORE
    assert 'ORDER BY COALESCE(report_at, imported_at) DESC' in STORE
    assert 'request_spy' not in STORE + RECON
    assert 'BrowserWorker' not in STORE + RECON
