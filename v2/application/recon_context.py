from __future__ import annotations

from datetime import datetime

from v2.application.recon_repository import ReconIngestResult, V2ReconRecord, V2ReconRepository, V2TargetRecord
from v2.application.spy_context import SpyEnabledApplicationContext
from v2.domain.recon import LEGACY_SPY_REPORT_LOOKBACK_HOURS


class ReconOwnedApplicationContext(SpyEnabledApplicationContext):
    """Expose V2-owned recon/targets while legacy remains read-only reference input."""

    def __init__(self, *args, v2_recon: V2ReconRepository, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._v2_recon = v2_recon

    def recon(self, *, limit: int = 2000) -> list[V2ReconRecord]:
        return self._v2_recon.list_recon(limit=limit)

    def targets(self, *, limit: int = 5000) -> list[V2TargetRecord]:
        return self._v2_recon.list_targets(limit=limit)

    def ingest_live_recon(
        self,
        *,
        now: datetime | None = None,
        lookback_hours: int = LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    ) -> ReconIngestResult:
        snapshot = self.live_recon(now=now, lookback_hours=lookback_hours)
        return self._v2_recon.ingest_snapshot(snapshot, now=now, lookback_hours=lookback_hours)
