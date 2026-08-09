from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from v2.application.navigation import NavigationCoordinator, NavigationObservation


class ReadinessState(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    BLOCKED = "blocked"
    STOPPED = "stopped"


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    label: str
    state: ReadinessState
    detail: str = ""

    @property
    def ready(self) -> bool:
        return self.state is ReadinessState.READY


@dataclass(frozen=True)
class BrowserReadinessSnapshot:
    browser: ReadinessItem
    account: ReadinessItem
    planet: ReadinessItem
    fleets: ReadinessItem
    messages: ReadinessItem
    galaxy: ReadinessItem
    detail: str = ""

    @property
    def captcha_stopped(self) -> bool:
        return any(
            item.state is ReadinessState.STOPPED
            for item in self.items()
        )

    def items(self) -> tuple[ReadinessItem, ...]:
        return (
            self.browser,
            self.account,
            self.planet,
            self.fleets,
            self.messages,
            self.galaxy,
        )


class BrowserReadinessError(RuntimeError):
    pass


class BrowserReadinessManager:
    """Human-readable readiness and safe page/planet preparation orchestration.

    This application service never imports browser selectors. All browser context
    changes are delegated to the journaled NavigationCoordinator.
    """

    def __init__(self, navigation: NavigationCoordinator) -> None:
        self._navigation = navigation

    @staticmethod
    def _request_id(prefix: str) -> str:
        return f"readiness:{prefix}:{uuid4().hex}"

    @staticmethod
    def _item(key: str, label: str, ready: bool, detail: str = "") -> ReadinessItem:
        return ReadinessItem(
            key=key,
            label=label,
            state=ReadinessState.READY if ready else ReadinessState.NOT_READY,
            detail=detail,
        )

    @staticmethod
    def _failure_snapshot(detail: str) -> BrowserReadinessSnapshot:
        stopped = "captcha" in detail.casefold()
        state = ReadinessState.STOPPED if stopped else ReadinessState.BLOCKED
        browser = ReadinessItem("browser", "Browser", state, detail)
        unavailable = lambda key, label: ReadinessItem(key, label, state, detail)
        return BrowserReadinessSnapshot(
            browser=browser,
            account=unavailable("account", "Account"),
            planet=unavailable("planet", "Planet"),
            fleets=unavailable("fleets", "Fleets"),
            messages=unavailable("messages", "Messages"),
            galaxy=unavailable("galaxy", "Galaxy"),
            detail=detail,
        )

    @classmethod
    def from_observation(cls, observation: NavigationObservation) -> BrowserReadinessSnapshot:
        identity = observation.identity
        current = identity.current_planet
        account_ready = bool(identity.account.ownership_fingerprint and identity.planets)
        planet_ready = bool(current is not None and current.selected)
        return BrowserReadinessSnapshot(
            browser=cls._item(
                "browser", "Browser", True,
                f"connected · {identity.session.endpoint}",
            ),
            account=cls._item(
                "account", "Account", account_ready,
                f"identified · {identity.session.server_host}" if account_ready else "account ownership is not proven",
            ),
            planet=cls._item(
                "planet", "Planet", planet_ready,
                f"selected · {current.display_name} [{current.coord}]" if current is not None else "no selected owned planet",
            ),
            fleets=cls._item(
                "fleets", "Fleets", observation.page.fleets_ready,
                "ready" if observation.page.fleets_ready else "not prepared",
            ),
            messages=cls._item(
                "messages", "Messages", observation.page.messages_ready,
                "ready" if observation.page.messages_ready else "not prepared",
            ),
            galaxy=cls._item(
                "galaxy", "Galaxy", observation.page.galaxy_ready,
                (
                    f"ready · {observation.page.galaxy}:{observation.page.solar}"
                    if observation.page.galaxy_ready else "not prepared"
                ),
            ),
        )

    def snapshot(self) -> BrowserReadinessSnapshot:
        try:
            return self.from_observation(self._navigation.observe())
        except Exception as exc:
            return self._failure_snapshot(str(exc) or exc.__class__.__name__)

    def _observe_or_raise(self) -> NavigationObservation:
        try:
            return self._navigation.observe()
        except Exception as exc:
            detail = str(exc) or exc.__class__.__name__
            if "captcha" in detail.casefold():
                raise BrowserReadinessError(f"CAPTCHA = STOP: {detail}") from exc
            raise BrowserReadinessError(f"Browser readiness unavailable: {detail}") from exc

    def ensure_planet_coord(self, coord: str) -> BrowserReadinessSnapshot:
        target_coord = str(coord).replace(" ", "").strip()
        before = self._observe_or_raise()
        target = before.identity.by_coord(target_coord)
        if target is None:
            raise BrowserReadinessError(
                f"Requested planet {target_coord or 'missing'} is not in the proven owned-planet set"
            )
        current = before.identity.current_planet
        if current is None or current.planet_id != target.planet_id:
            record = self._navigation.switch_planet(
                request_id=self._request_id("planet"),
                planet_id=target.planet_id,
            )
            if record.status != "verified":
                raise BrowserReadinessError(
                    f"Planet preparation stopped safely: {record.status} · {record.detail}"
                )
        return self.from_observation(self._observe_or_raise())

    def ensure_fleets(self, *, planet_coord: str | None = None) -> BrowserReadinessSnapshot:
        if planet_coord:
            self.ensure_planet_coord(planet_coord)
        before = self._observe_or_raise()
        if not before.page.fleets_ready:
            record = self._navigation.prepare_fleets(request_id=self._request_id("fleets"))
            if record.status != "verified":
                raise BrowserReadinessError(
                    f"Fleets preparation stopped safely: {record.status} · {record.detail}"
                )
        snapshot = self.from_observation(self._observe_or_raise())
        if not snapshot.fleets.ready:
            raise BrowserReadinessError("Fleets page did not reach verified readiness")
        return snapshot

    def ensure_messages(self, *, planet_coord: str | None = None) -> BrowserReadinessSnapshot:
        if planet_coord:
            self.ensure_planet_coord(planet_coord)
        before = self._observe_or_raise()
        if not before.page.messages_ready:
            result = self._navigation.prepare_system_messages(
                request_id=self._request_id("messages")
            )
            if not result.verified:
                terminal = result.system_tab or result.page
                raise BrowserReadinessError(
                    f"Messages preparation stopped safely: {terminal.status} · {terminal.detail}"
                )
        snapshot = self.from_observation(self._observe_or_raise())
        if not snapshot.messages.ready:
            raise BrowserReadinessError("System messages did not reach verified readiness")
        return snapshot

    def ensure_galaxy(self, *, planet_coord: str | None = None) -> BrowserReadinessSnapshot:
        if planet_coord:
            self.ensure_planet_coord(planet_coord)
        before = self._observe_or_raise()
        if not before.page.galaxy_ready:
            record = self._navigation.prepare_galaxy(request_id=self._request_id("galaxy"))
            if record.status != "verified":
                raise BrowserReadinessError(
                    f"Galaxy preparation stopped safely: {record.status} · {record.detail}"
                )
        snapshot = self.from_observation(self._observe_or_raise())
        if not snapshot.galaxy.ready:
            raise BrowserReadinessError("Galaxy page did not reach verified readiness")
        return snapshot
