from __future__ import annotations

from v2.infrastructure.cdp_asteroid_backend import V2AsteroidCdpBackend
from v2.infrastructure.cdp_automatic_recon import V2AutomaticReconCdpBackend
from v2.infrastructure.cdp_navigation_backend import V2NavigationCdpBackend
from v2.infrastructure.cdp_raid_backend import V2RaidCdpBackend
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
            # Restore only the exact Browser object originally attached. This is
            # handle recovery, not a new connect_over_cdp call or silent rebind.
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
    V2AutomaticReconCdpBackend,
):
    """Single-page AUTO-07 navigation/recon backend with auto_reconnect=False."""


class V2RaidCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2RaidCdpBackend):
    """Production raid action backend with auto_reconnect=False."""


class V2SpyCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2SpyCdpBackend):
    """Production spy action/read backend with auto_reconnect=False."""


class V2AsteroidCdpBackendNoAutoReconnect(_NoAutoReconnectMixin, V2AsteroidCdpBackend):
    """Production asteroid action/read backend with auto_reconnect=False."""
