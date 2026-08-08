# V2-59 — debris/recycling contract audit

Date: 2026-08-08

Baseline: `f51add2023054d341f49138c92225f08a117722e` (`main`, docs handoff PR #93).

Scope: research + pure domain contract + sanitized fixtures only. This stage does **not** navigate the browser, call `squareInfo` live, mutate either SQLite database, prepare ships, call SendFleet, add a Qt action, or add any scheduler.

## Effective legacy runtime

The default runtime remains `run_app.bat -> app_entry.py`. The effective debris behavior is therefore:

1. the current `BrowserWorker` asteroid implementation in `browser.py`;
2. the dedicated `debris_asteroids_feature.py` feature wrapper;
3. installed presentation-only `visual_layout.install_debris_layout(...)` overrides.

`install_debris_layout(...)` replaces only the debris page construction/navigation helpers. It does not alter discovery, persistence, movement calculation, capacity checks or dispatch semantics.

Git history confirms the feature was introduced by `6830f24be86854ddc557b69fa0ff7e604b0219a6` (`Add debris asteroid scanning and selected send workflow`) explicitly by reusing the existing stabilized asteroid interception/send path.

## Exact debris evidence

The effective detector uses the `squareInfo` response returned by the existing asteroid detail read:

```text
POST ajax_info.php
type=squareInfo&c1=<g>&c2=<s>&c3=<p>
```

The accepted canonical sentence is:

```text
Этот астероид содержит обломки
```

The effective legacy predicate strips tags, decodes HTML entities, converts NBSP to spaces, case-folds and collapses whitespace, then looks for the stable fragment:

```text
содержит обломки
```

This distinction is intentional: the audit records the exact observed/canonical sentence, while parsing preserves the already-accepted normalization rule rather than depending on presentation markup or capitalization.

The legacy unit test `test_debris_asteroids_feature.py` pins the same `squareInfo`-style payload together with:

- `Информация об астероиде`;
- `Последнее перемещение 2026-08-06 20:45:08`;
- `Следующее перемещение 2026-08-06 21:46:08`;
- `Скорость 61 Минут / поле`;
- `Этот астероид содержит обломки`.

V2-59 preserves this as a sanitized fixture with no account/session/player identifiers.

## Movement and provenance

Debris is not a different moving object. Legacy first reads the normal asteroid `squareInfo`, checks the debris marker and then passes the same tooltip through `parse_asteroid_tooltip(...)`.

Therefore a proven debris observation requires the same trajectory provenance already accepted by V2-51:

- origin galaxy/system/position;
- last movement server time;
- next movement server time;
- positive movement period;
- exact observation/server-read time;
- provenance source `galaxy.squareInfo`;
- debris marker fact.

V2-59 deliberately composes `DebrisObservationFact` around the existing immutable `AsteroidObservationFact`. It does not introduce a second movement model.

A marker without readable movement timestamps is **partial/unreadable evidence**, not a valid debris candidate. Conversely, a completely readable current system with no debris markers is the typed state `no_debris`.

## Legacy 120-system scan semantics

Legacy `debris_scan_sequence()` covers exactly:

```text
galaxy 1: systems 40 -> 1
galaxy 2: systems 40 -> 1
galaxy 3: systems 40 -> 1
```

for 120 systems total.

The effective legacy scanner:

- obtains/navigates a galaxy page through `_ensure_galaxy_page(...)`;
- calls `_load_galaxy_system(...)` for later systems;
- checks CAPTCHA before reading a system;
- reads asteroid links already rendered in that system;
- calls `_fetch_asteroid_info(...)` / `squareInfo` for each asteroid;
- keeps only marker-positive observations;
- stops on CAPTCHA;
- historically skips other per-asteroid parsing/read exceptions and continues.

Persistence semantics are important:

- after a **completed** 120-system scan, `_replace_debris_observations(...)` deletes the previous legacy result set and replaces it with the completed scan result;
- after **manual cancellation**, the partial observations remain only in the current UI/session and do **not** replace the last persisted completed scan.

V2 must not copy the navigation itself. Automatic 3×40 traversal, `_load_galaxy_system`, `refreshGalaxy`, `goto` and system switching remain deferred. A V2 read of one manually opened system can never claim `completed 120-system scan` and a zero-debris current system must never erase proven evidence from other systems.

The legacy behavior of swallowing individual read/parse failures also cannot be interpreted as `no_debris` in V2. V2 must expose partial/unreadable evidence fail-closed.

## Recycler/capacity/movement behavior

Legacy selected-debris dispatch performs a wave-level precheck using:

- configured recycler count per selected target (default UI value 100);
- selected target count;
- free fleet slots;
- available recyclers;
- configured asteroid movement safety margin.

Each selected observation is then sent by calling the **existing**:

```python
self.worker.send_asteroid(
    observation,
    recycler_count,
    home,
    safety_seconds,
)
```

No debris-specific flight calculator or SendFleet implementation exists. After the call, legacy only annotates the returned result with `player = "Астероид с обломками"` and `debris = True` for presentation/history.

The underlying asteroid path performs the accepted moving-target calculation, recycler mission preparation and strict verification. The canonical mission is mission code `8`, `Добыча газа`.

V2 already improves the legacy safety boundary by rechecking live trajectory, recycler availability and live fleet capacity immediately before the one remote attempt. Those authoritative per-attempt checks remain required for debris even if a bounded workflow also previews multiple candidates.

## SendFleet reuse decision — PROVEN REUSE

**Decision: debris must reuse the existing V2 asteroid mutation boundary. A second SendFleet backend or second action journal would be an architectural defect.**

Evidence:

1. Effective legacy debris execution delegates directly to `BrowserWorker.send_asteroid(...)`; the debris feature itself never owns a SendFleet click.
2. Debris uses the same recycler ship selector/count and the same gas-mining mission (`8` / `Добыча газа`).
3. The moving target is the same asteroid trajectory represented by the same movement timestamps/period.
4. Current V2 `AsteroidDispatchCommand` already accepts exactly the required source, immutable asteroid observation, recycler count and safety margin.
5. Current V2 `V2AsteroidCdpBackend` already performs the required fresh live trajectory check, live recycler/capacity check, exactly one `#SendFleetButton` attempt and exact new-fleet verification by new fleet ID + source + target + mission `Добыча газа`.
6. Current `asteroid_actions` unresolved identity is based on the actual remote trajectory facts (source + observation trajectory + target), not a UI category label. A `debris` label therefore cannot legitimately create a second retry namespace.

V2-62 must map a proven debris candidate to the existing `AsteroidDispatchCommand` / `AsteroidRequestCoordinator` path and add tests that the same trajectory remains blocked by the same unresolved `asteroid_actions` identity regardless of whether it originated from the generic Asteroids or Debris surface.

## Typed current-system read outcomes

V2-59 pins these distinct states for the next read stage:

- `live_unavailable` — no usable already-open/current galaxy evidence;
- `captcha` — bot/human verification detected; stop;
- `partial_evidence` — one or more visible asteroid `squareInfo` responses or required movement facts are unreadable/unproven;
- `no_debris` — the currently opened system was fully readable and contains zero proven debris markers (including a fully readable system with zero asteroid links);
- `ready` — at least one debris-bearing asteroid has complete movement provenance.

Precedence is conservative: CAPTCHA beats other outcomes; unavailable remains distinct; any unreadable visible asteroid prevents `no_debris`.

These are domain states. UI strings must not drive later business logic.

## V2-59 implementation scope

This PR adds only:

- `v2/domain/debris.py` with pure marker normalization, movement-parser reuse and typed read classification;
- `tests/fixtures/v2_debris_contract.html` sanitized examples;
- pure contract tests;
- this audit.

It adds no CDP adapter, storage schema/table, application dispatch mapping, Qt page, automatic navigation, retry or scheduler.

## Constraints for V2-60+

V2-60 may reuse the current attach-only asteroid reader mechanics, including the proven read-only `squareInfo` POST, but only from an already-open/current `galaxy.php`. It must not navigate or call `refreshGalaxy`.

V2-61 must accumulate immutable V2-owned debris evidence across manually opened systems. A current-system `no_debris` result is not authority to delete evidence from other systems.

V2-62 must reuse the single authoritative asteroid SendFleet/journal boundary proven above. Any attempt to add `debris_actions` or a separate debris CDP SendFleet implementation requires new evidence of a real side-effect difference; V2-59 found none.
