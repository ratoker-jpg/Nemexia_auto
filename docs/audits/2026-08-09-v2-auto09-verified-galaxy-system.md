# AUTO-09 — verified galaxy/system navigation

Date: 2026-08-09

Baseline: `a29ea5786eb4e651cbcc3d9e826e3e52ff3862e4` (AUTO-08 squash PR #138, exact post-main CI #341 green).

## Contract

AUTO-09 adds one central verified system step on top of the existing NavigationCoordinator ownership boundary.

```text
ready galaxy.php
→ journal immutable request
→ exactly one refreshGalaxy() call
→ observe ajax_galaxy.php POST / holder settle
→ verify same page token
→ verify same account fingerprint
→ verify same selected PlanetIdentity
→ verify requested galaxy + solar
→ VERIFIED / AMBIGUOUS / FAILED_SAFE
```

Solar system is constrained to `1..40`. Galaxy must be positive.

## Architecture

`VerifiedGalaxyNavigationCoordinator` subclasses the existing central `NavigationCoordinator`; it does not introduce a second navigation owner.

Production still shares one mutation-capable CDP backend instance between:

- NavigationCoordinator ownership;
- AUTO-07 exact-fleet reconnaissance;
- AUTO-09 galaxy/system navigation.

The AUTO-09 browser effect is implemented as a mixin on that same guarded `auto_reconnect=False` session.

Qt and application code contain no browser selectors or `refreshGalaxy` JavaScript. The application context exposes only the typed `navigate_galaxy_system(...)` service.

## Browser evidence

The step mirrors the effective legacy system-load evidence:

- `#c1` galaxy control;
- `#c2` solar control;
- `#galaxyHolder` rendered-system evidence;
- optional `#galaxyLoading` settle state;
- one `refreshGalaxy()` call;
- expected `POST ajax_galaxy.php` response.

Byte-identical holder HTML is allowed only when the AJAX response completed, exact requested controls are selected, the holder is populated and the loader is settled.

## Safety

Before the remote effect:

- selected PlanetIdentity must be proven;
- galaxy page readiness must be proven;
- account fingerprint must be known;
- required controls/function must exist;
- CAPTCHA evidence stops the step;
- invalid coordinate input is `failed_safe`.

After `refreshGalaxy()` begins, any unverified result is `ambiguous`; the coordinator does not retry automatically.

If the requested system is already rendered, the journal is completed `verified` without any remote effect.

## Scope

AUTO-09 does not implement traversal. It provides the verified primitive required by AUTO-10.

Not included:

- no 3×40 loop;
- no scheduler;
- no asteroid/debris persistence changes;
- no UI changes;
- no Rest Mode;
- no recovery rebind after a lost mutation session.

## Acceptance

AUTO-09 is complete when:

1. one requested system results in at most one `refreshGalaxy()` call;
2. success requires same page/account/planet plus exact requested galaxy/system;
3. pre-attempt errors are failed-safe;
4. post-attempt uncertainty is ambiguous and never retried automatically;
5. CAPTCHA remains STOP;
6. full CI is green;
7. substantive P1/P2 review findings are resolved;
8. squash merge is followed by exact green post-main push CI.

Then proceed to AUTO-10 controlled automatic 3×40 discovery.
