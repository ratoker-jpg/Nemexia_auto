from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from v2.application.automation_authority import AUTOFARM_OWNER
from v2.ui.pages.farm import FarmPage


class AuthorityFarmPage(FarmPage):
    """Existing FarmPage with typed mutual exclusion for automatic mutation loops.

    This wrapper adds no browser knowledge and no new visible controls. It only
    acquires the application-owned AutoFarm authority before the existing page can
    prepare/arm a continuous cycle or execute a manual wave, then releases it on
    every disarm/cancel/return path.
    """

    def _ensure_farm_authority_available(self) -> bool:
        ensure = getattr(self.context, "ensure_automation_cycle_available", None)
        if not callable(ensure):
            QMessageBox.warning(
                self,
                "Автофарм V2",
                "Shared automation authority недоступен; автоматическая отправка заблокирована.",
            )
            return False
        try:
            ensure(AUTOFARM_OWNER)
        except Exception as exc:
            QMessageBox.warning(self, "Автофарм V2", str(exc))
            return False
        return True

    def _acquire_farm_authority(self) -> bool:
        acquire = getattr(self.context, "acquire_automation_cycle", None)
        if not callable(acquire):
            QMessageBox.warning(
                self,
                "Автофарм V2",
                "Shared automation authority недоступен; автоматическая отправка заблокирована.",
            )
            return False
        try:
            acquire(AUTOFARM_OWNER)
        except Exception as exc:
            QMessageBox.warning(self, "Автофарм V2", str(exc))
            return False
        return True

    def _release_farm_authority(self) -> None:
        release = getattr(self.context, "release_automation_cycle", None)
        if callable(release):
            try:
                release(AUTOFARM_OWNER)
            except Exception:
                # Release cannot authorize a new remote effect. Keep UI disarmed;
                # context/application shutdown remains the final cleanup boundary.
                pass

    def start_cycle(self) -> None:
        if self._armed or self._busy:
            return
        if not self._ensure_farm_authority_available():
            return
        if not self._acquire_farm_authority():
            return
        try:
            super().start_cycle()
        finally:
            # Confirmation/readiness/preparation can return before `_armed=True`.
            # Do not leak the owner token on any such pre-arm path.
            if not self._armed:
                self._release_farm_authority()

    def run_wave(self) -> None:
        if self._armed:
            super().run_wave()
            return
        if not self._ensure_farm_authority_available():
            return
        if not self._acquire_farm_authority():
            return
        try:
            super().run_wave()
        finally:
            self._release_farm_authority()

    def _disarm(self, reason: str) -> None:
        try:
            super()._disarm(reason)
        finally:
            self._release_farm_authority()
