from __future__ import annotations

from datetime import datetime
from typing import Sequence

from v2.application.queue_refill import QueueRefillService
from v2.application.recon_refill import ControlledReconRefill, ReconRefillResult
from v2.application.recon_repository import ReconIngestResult, V2ReconRecord, V2ReconRepository, V2TargetRecord
from v2.application.spy_context import SpyEnabledApplicationContext
from v2.domain.queue_policy import QueueMode, QueueRefillPreview
from v2.domain.recon import (
    LEGACY_METAL_QUEUE_MINIMUM,
    LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    ReportReadState,
    SpyReportFact,
)
from v2.persistence.queue_refill import QueueApplySummary


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
        if snapshot.state is not ReportReadState.FRESH:
            raise RuntimeError(f"{snapshot.state.value}: {snapshot.detail}")
        return self._v2_recon.ingest_snapshot(snapshot, now=now, lookback_hours=lookback_hours)

    def ingest_verified_recon_report(
        self,
        report: SpyReportFact,
        *,
        now: datetime | None = None,
        lookback_hours: int = LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    ) -> ReconIngestResult:
        """Ingest exactly one report already verified by the journaled spy boundary."""
        return self._v2_recon.ingest_reports(
            (report,),
            now=now,
            lookback_hours=lookback_hours,
        )

    def preview_queue_refill(
        self,
        *,
        mode: QueueMode,
        queue_size: int = 45,
        minimum_metal: int = LEGACY_METAL_QUEUE_MINIMUM,
        now: datetime | None = None,
        active_targets: Sequence[str] | None = None,
    ) -> QueueRefillPreview:
        if self._v2_queue is None:
            raise RuntimeError("V2 queue repository is unavailable")
        if active_targets is None:
            if self._live_snapshot_ready:
                active_targets = tuple(item.raw.target for item in self.cached_classified_active_flights())
            else:
                active_targets = ()
        return QueueRefillService(self._v2_queue).preview(
            self.targets(limit=5000),
            mode=mode,
            now=now,
            queue_size=queue_size,
            minimum_metal=minimum_metal,
            active_targets=active_targets,
        )

    def apply_queue_refill(self, preview: QueueRefillPreview) -> QueueApplySummary:
        if self._v2_queue is None:
            raise RuntimeError("V2 queue repository is unavailable")
        return QueueRefillService(self._v2_queue).apply(preview)

    def run_controlled_recon_refill(
        self,
        fleet_id: str,
        *,
        request_id: str,
        now: datetime | None = None,
        queue_size: int = 45,
    ) -> ReconRefillResult:
        """Run one explicit exact-fleet recon → verified ingest → AutoFarm refill cycle."""
        return ControlledReconRefill().run(
            self,
            fleet_id=str(fleet_id),
            request_id=str(request_id),
            now=now,
            queue_size=queue_size,
        )
