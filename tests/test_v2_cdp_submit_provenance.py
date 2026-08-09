from __future__ import annotations

import pytest

from v2.application.navigation import NavigationMutationError
from v2.infrastructure.cdp_read_backend import ReadOnlyCdpBackend


async def _raise_navigation_error(*, remote_attempted: bool) -> None:
    raise NavigationMutationError("typed navigation failure", remote_attempted=remote_attempted)


@pytest.mark.parametrize("remote_attempted", [False, True])
def test_cdp_submit_preserves_navigation_mutation_provenance(remote_attempted: bool) -> None:
    backend = ReadOnlyCdpBackend("http://127.0.0.1:9222", timeout_seconds=1.0)
    try:
        with pytest.raises(NavigationMutationError) as caught:
            backend._submit(_raise_navigation_error(remote_attempted=remote_attempted))
        assert caught.value.remote_attempted is remote_attempted
    finally:
        backend.close()
