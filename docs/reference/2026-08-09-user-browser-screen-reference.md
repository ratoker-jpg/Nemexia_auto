# User-supplied Nemexia browser screen reference — sanitized

Date: 2026-08-09

Source archive supplied by the user: `для автоматизации.zip`.

- SHA-256: `7dc6466c462d679548c8667907f431cd8ee04584de450a9239d535aade4f5130`
- ZIP entries: 654
- main saved-page captures: 11
- additional browser-saved helper HTML resources: 3

## Why the raw ZIP is not committed

The repository is public. The saved pages contain real account-specific game data: planet names and coordinates, resource totals, alliance/player data, fleet/report/message IDs and other live-state facts. The archive also bundles third-party game JavaScript/CSS/images.

For that reason this repository stores a **sanitized structural reference** instead of the raw archive. The goal is to retain the DOM/navigation/action evidence needed for V2 automation without publishing the user's live account snapshot.

No conclusion below should be broadened beyond what the supplied captures prove.

## Captured screen/state inventory

| Capture | Page title | Proven state / useful evidence | Future relevance |
| --- | --- | --- | --- |
| `16-35-04` | `Полеты` | `TabChooseShips` visible; ship quantity inputs; `#FleetsCount/#MaxFleets`; exact `processSpy(<fleet_id>)` rows are present in DOM | raid/spy dispatch preparation, fleet capacity |
| `16-35-14` | `Полеты` | second fleets capture with the same stable ship/fleet/spy contracts | selector stability / multi-state regression |
| `16-35-23` | `Опции` | messages shell; `#messagesFolders`; System entry uses `loadTabContent('TabAdministrative',2,0)` + `showTab('TabAdministrative')` | automatic System-message acquisition |
| `16-35-33` | `Опции` | System messages rendered; spy report item present with timestamp/resources/ships/defence | report parsing and page readiness |
| `16-35-43` | `Опции` | later System-message state with more rendered message items | dynamic message refresh / dedupe |
| `16-35-56` | `Галактика` | `#galaxyWrapper`, `#galaxySearch`, `#c1`, `#c2`, `#galaxyHolder`, `#galaxyPlanets`; global planet switch is also present | verified system navigation and scan ownership |
| `16-36-09` | `Союз` | alliance/team surface: `#allianceMenu`, `#teamInfo`, members and team-planet controls | future account/team context work; not required for first automation batch |
| `16-36-20` | `Просмотр` | account/empire overview with all owned planet cards collapsed | owned-planet discovery / identity |
| `16-36-32` | `Просмотр` | expanded planet state with resource/building/ship/defence/science sub-surfaces | future resource import / planet-state reads |
| `16-37-00` | `Полеты` | fleet-list state; `processSpy(<fleet_id>)` links and spy checkboxes present | exact spy-fleet processing |
| `16-37-12` | `Полеты` | post-process/cooldown state: `spy1Link-<id>` hidden and `spy1Time-<id>` timer shown | exact processSpy recovery/readiness semantics |

## High-value contracts proven by the captures

### Owned planet selector

The global header contains:

```text
#planetSwitch
#planetsListHolder
a href=".../change_planet.php?id=<planet_id>"
#planetListImg-<planet_id>
current planet label + coordinate
```

The selected planet is marked by the active list item. This is direct evidence that a V2 `PlanetIdentity` can be built from:

- stable internal planet ID;
- coordinate;
- display name;
- selected/active state.

It also confirms why the earlier navigation audit stopped: planet switching is a real `change_planet.php` server-side context mutation, not merely a cosmetic tab change.

### Fleet preparation / dispatch

The fleets capture contains stable controls:

```text
#ship_1_2 / #ship_1_2_max       megatransporter
#my_c1 #my_c2 #my_c3            source coordinates
#target_c1 #target_c2 #target_c3 target coordinates
#mission                         mission selector
#speed                           speed selector
#SendFleetButton                 remote send trigger
#FleetsCount / #MaxFleets        authoritative capacity
```

Observed mission codes include at least:

- `2` — `Шпионаж`
- `3` — `Атака`
- `8` — `Добыча газа`

The current V2 exactly-one mutation and verification contracts remain authoritative; this evidence is for automation/page ownership, not permission to bypass those contracts.

### Exact spy-fleet processing

A real fleet row has the shape:

```text
<tr class="espionageClass">
  source
  target
  ...
  <a id="spy1Link-<fleet_id>" onclick="processSpy(<fleet_id>)">Шпионаж</a>
  <input name="spySelect-<fleet_id>" value="<fleet_id>">
</tr>
```

A later capture proves a cooldown state:

```text
#spy1Link-<fleet_id> hidden
#spy1Time-<fleet_id> visible
```

with client timer logic eventually restoring the link.

This supports a future automatic recon workflow that discovers processable spy fleets without asking the user to type the exact fleet ID manually.

### System messages / spy reports

The Options screen exposes the System message route:

```text
#messagesFolders
loadTabContent('TabAdministrative', 2, 0)
showTab('TabAdministrative')
```

Rendered System messages include full spy reports with target, report time and resource/intel facts. The captures prove both an unloaded shell state and later loaded message states.

### Galaxy surface

Observed structural anchors:

```text
#galaxyWrapper
#galaxyMenu
#galaxyBreadcrumb
#galaxySearch
#c1
#c2
#screenHolder
#galaxyLoading
#galaxyHolder
#galaxyPlanets
```

The supplied capture proves the visible current-system page structure. It does **not** by itself prove that `refreshGalaxy` / `ajax_galaxy.php` or arbitrary system switching is account-context-neutral. Those mutations still need explicit before/after account + planet + destination verification.

### Empire / all-planets overview

The `Просмотр` captures show one card per owned planet with IDs of the form:

```text
#planetInfoTitle-<planet_id>
#PlanetHolder-<planet_id>
#PlanetContentHolder-<planet_id>
#BuildingsLi-<planet_id>
#ShipsLi-<planet_id>
#DefenceLi-<planet_id>
#ScienceLi-<planet_id>
```

One capture is collapsed; another contains expanded detail. This is useful for future resource/planet-state import without requiring a separate page per planet.

## Product implication

These captures support the post-release goal that the user should not have to service browser pages manually.

The intended future path is:

```text
discover browser/account/planet context
→ choose/verify source planet
→ prepare required game page
→ perform bounded verified action/read
→ verify account + selected planet + destination afterwards
→ continue workflow
```

All navigation/context mutations must remain centralized and fail-closed. CAPTCHA remains STOP-only and ambiguous remote mutations remain non-retryable.
