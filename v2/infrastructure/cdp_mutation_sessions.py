from __future__ import annotations

from v2.infrastructure.cdp_asteroid_backend import V2AsteroidCdpBackend
from v2.infrastructure.cdp_navigation_backend import V2NavigationCdpBackend
from v2.infrastructure.cdp_raid_backend import V2RaidCdpBackend
from v2.infrastructure.cdp_spy_backend import V2SpyCdpBackend


class _NoAutoReconnectMixin:
    """Permit the initial CDP attach, then fail closed if that session is lost.

    Mutation-capable paths must never silently create a fresh browser attachment
    after an established session disappears. AUTO-13 may later perform explicit,
    journal-aware recovery; this mixin intentionally does not.
    """

    async def _ensure_browser(self):
        browser = getattr(self, "_browser", None)
        if browser is not None and browser.is_connected():
            self._mutation_session_established = True
            return browser
        if bool(getattr(self, "_mutation_session_established", False)):
            raise RuntimeError(
                "Mutation CDP session was lost; auto_reconnect=False, explicit recovery is required"
            )
        browser = await super()._ensure_browser()
        self._mutation_session_established = True
        return browser


class V2NavigationCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2NavigationCdpBackend):
    """Production NavigationCoordinator backend with auto_reconnect=False."""


class V2RaidCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2RaidCdpBackend):
    """Production raid action backend with auto_reconnect=False."""


class V2SpyCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2SpyCdpBackend):
    """Production spy action/read backend with auto_reconnect=False."""


class V2AsteroidCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2AsteroidCdpBackend):
    """Production asteroid action/read backend with auto_reconnect=False."""
