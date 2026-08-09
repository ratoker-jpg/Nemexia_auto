# AUTO-08 — espionage route parity gate

Date: 2026-08-09

Baseline: `a59228bc4fa35616febc1cbad278b2aa11beda93` (UI follow-up to AUTO-07, exact post-main CI #339 green).

## Decision

**AUTO-08 is a contract/no-op gate. Do not implement creation of a new espionage route.**

The effective legacy runtime proves processing already-existing espionage fleets. It does not prove that the automation creates a new mission-2 spy route when no processable existing spy fleet is available.

The browser reference contains mission value `2`, but a visible game-form option is only capability evidence. It is not evidence that the effective legacy automation selected spy ships, selected mission 2, submitted `SendFleet`, and verified a newly-created espionage flight.

Therefore adding such a V2 mutation under the name of parity would invent behavior not established by the AUTO-01 evidence contract.

## Evidence rechecked

AUTO-08 rechecked the evidence chain against the effective runtime rather than against isolated game HTML.

### Effective legacy composition

AUTO-01 established that parity must be measured against the composite runtime installed by `app_entry.py` and its patch modules, with `browser.py` remaining the underlying browser implementation.

The effective runtime proves:

```text
existing spy fleet
→ exact/bulk processSpy(...) action
→ System messages
→ parse fresh report
```

AUTO-07 intentionally migrated this to the safer exact-fleet contract:

```text
spy1Link-<fleet_id>
spy1Time-<fleet_id>
→ exactly one processSpy(<fleet_id>)
→ new exact-target fresh report
```

### Saved browser/reference evidence

The supplied Fleets reference proves the game UI contains:

```text
<select id="mission">
  <option value="2">Шпионаж</option>
  <option value="3">Атака</option>
  <option value="8">Добыча газа</option>
</select>
```

It also proves existing espionage rows expose:

```text
#spy1Link-<fleet_id>
processSpy(<fleet_id>)
#spy1Time-<fleet_id>
```

This is enough for AUTO-07 existing-fleet acquisition. It does **not** prove a legacy route-creation workflow.

### Legacy mutation evidence

The retained legacy code contains proven SendFleet flows for other missions, including normal raid/attack and asteroid gas collection. Reinspection did not establish an effective legacy call path that performs the equivalent of:

```text
choose spy ships
→ target coordinates
→ mission = 2
→ SendFleet
→ verify new espionage flight
```

The existing bulk `processSpy(0)` control is report acquisition for existing spy fleets, not route creation.

### Existing V2-45 correction

`2026-08-08-v2-spy-acquisition-correction.md` already corrected the earlier interpretation: the proven action identity is an existing espionage fleet ID. It explicitly rejects fabrication of probe counts, ship keys, or arbitrary spy-dispatch APIs from insufficient evidence.

AUTO-08 preserves that correction.

## Required V2 behavior after AUTO-08

When AUTO-07 finds no proven-ready existing spy fleet:

- it stops safely;
- it does not manufacture a mission-2 SendFleet request;
- it does not guess ship/probe type or count;
- it does not bulk-call `processSpy(0)`;
- it does not treat absence of a processable fleet as permission for a different remote mutation.

This is the correct parity result with the currently proven effective legacy behavior.

## What would reopen this gate

A future route-creation implementation requires new evidence proving that the effective legacy automation actually created spy routes, for example a retained runtime call path or equivalent evidence sufficient to establish all of:

- exact ship identity and count policy;
- source planet requirements;
- target coordinate contract;
- mission 2 selection;
- exact remote mutation boundary;
- before/after flight evidence;
- failure/ambiguity semantics.

If such evidence appears, route creation must be implemented as a **separate typed, persistent, exactly-one action journal**. It must not be folded into AUTO-07's `processSpy` journal.

## Safety invariants

AUTO-08 changes no runtime and therefore does not weaken any existing guard:

- CAPTCHA = STOP;
- no CAPTCHA solve/click/bypass;
- exactly one remote mutation attempt per immutable request;
- no automatic retry after ambiguous effect;
- account/planet/page verification remains required;
- automatic/manual spy journals remain interlocked;
- legacy SQLite remains read-only;
- `run_legacy.bat` rollback remains intact.

## AUTO-08 acceptance

AUTO-08 is complete when:

1. the no-invention decision is persisted in project documentation;
2. the effective legacy evidence is explicitly distinguished from game-form capability evidence;
3. no mission-2 SendFleet production code is added;
4. full CI is green;
5. review has no unresolved substantive P1/P2 findings;
6. squash merge is followed by exact green post-main push CI.

After that, proceed directly to **AUTO-09 — verified galaxy/system step**.
