from types import SimpleNamespace

import pytest

from v2.application.automation_context import DebrisEnabledApplicationContextWithReadiness


class UnresolvedNavigation:
    def unresolved(self):
        return (SimpleNamespace(request_id="nav-pending", status="ambiguous"),)


class NeverReadRepository:
    def __init__(self) -> None:
        self.read_calls = 0

    def read(self, _scan_id: str):
        self.read_calls += 1
        raise AssertionError("repository read must not precede unresolved navigation gate")


class NeverStartedService:
    def __init__(self) -> None:
        self.start_calls = 0
        self.resume_calls = 0
        self.repository = NeverReadRepository()

    def start(self, **_kwargs):
        self.start_calls += 1
        raise AssertionError("discovery start must remain blocked")

    def resume(self, _scan_id: str):
        self.resume_calls += 1
        raise AssertionError("discovery resume must remain blocked")


def context_with_unresolved_navigation():
    context = object.__new__(DebrisEnabledApplicationContextWithReadiness)
    service = NeverStartedService()
    readiness_calls: list[str | None] = []
    context._navigation_coordinator = UnresolvedNavigation()
    context._discovery_scan = service
    context.ensure_galaxy_ready = lambda *, planet_coord=None: readiness_calls.append(planet_coord)
    return context, service, readiness_calls


def test_start_blocks_before_any_readiness_or_discovery_mutation() -> None:
    context, service, readiness_calls = context_with_unresolved_navigation()

    with pytest.raises(RuntimeError, match="unresolved navigation"):
        context.start_discovery_scan(scan_id="scan-new", planet_coord="3:39:11")

    assert readiness_calls == []
    assert service.start_calls == 0
    assert service.repository.read_calls == 0


def test_resume_blocks_before_any_readiness_or_discovery_mutation() -> None:
    context, service, readiness_calls = context_with_unresolved_navigation()

    with pytest.raises(RuntimeError, match="unresolved navigation"):
        context.resume_discovery_scan("scan-old")

    assert readiness_calls == []
    assert service.resume_calls == 0
    assert service.repository.read_calls == 0
