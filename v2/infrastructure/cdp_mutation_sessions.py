from __future__ import annotations

from v2.infrastructure.cdp_asteroid_backend import V2AsteroidCdpBackend
from v2.infrastructure.cdp_automatic_recon import V2AutomaticReconCdpBackend
from v2.infrastructure.cdp_discovery_reader import OwnedDiscoveryReadMixin
from v2.infrastructure.cdp_galaxy_navigation import VerifiedGalaxyNavigationMixin
from v2.infrastructure.cdp_navigation_backend import V2NavigationCdpBackend
from v2.infrastructure.cdp_raid_backend import V2RaidCdpBackend
from v2.infrastructure.cdp_rest_mode_reader import OwnedRestModeReadMixin
from v2.infrastructure.cdp_spy_backend import V2SpyCdpBackend


class _NoAutoReconnectMixin:
    """Permit initial CDP attach and reuse its exact browser object, never reattach silently.

    Some read paths deliberately clear ``self._browser`` after a transient DOM
    evaluation failure even though the original CDP Browser object is still alive.
    Keep that exact established object separately so clearing the working handle is
    not misclassified as session loss. A genuinely disconnected established object
    still fails closed; AUTO-13 owns explicit recovery.
    """

    async def _ensure_browser(self):
        browser = getattr(self, "_browser", None)
        if browser is not None and browser.is_connected():
            self._mutation_session_established = True
            self._mutation_browser_identity = browser
            return browser

        retained = getattr(self, "_mutation_browser_identity", None)
        if retained is not None and retained.is_connected():
            self._browser = retained
            self._mutation_session_established = True
            return retained

        if bool(getattr(self, "_mutation_session_established", False)):
            raise RuntimeError(
                "Mutation CDP session was lost; auto_reconnect=False, explicit recovery is required"
            )

        browser = await super()._ensure_browser()
        self._mutation_session_established = True
        self._mutation_browser_identity = browser
        return browser


class V2NavigationCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2NavigationCdpBackend):
    """Production NavigationCoordinator backend with auto_reconnect=False."""


class V2AutomaticReconCdpBackendNoAutoReconnect(
    _NoAutoReconnectMixin,
    OwnedDiscoveryReadMixin,
    OwnedRestModeReadMixin,
    VerifiedGalaxyNavigationMixin,
    V2AutomaticReconCdpBackend,
):
    """Shared AUTO-07/AUTO-09/AUTO-10/AUTO-12 page owner with auto_reconnect=False."""


class V2RaidCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2RaidCdpBackend):
    """Production raid action backend with auto_reconnect=False."""


class V2SpyCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2SpyCdpBackend):
    """Production spy action/read backend with auto_reconnect=False."""


class V2AsteroidCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2AsteroidCdpBackend):
    """Production asteroid action/read backend with auto_reconnect=False."""
