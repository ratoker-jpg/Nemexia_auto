from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


_COORD_RE = re.compile(r"^\d+:\d+:\d+$")
_PLANET_ID_RE = re.compile(r"^\d+$")


class BrowserIdentityError(RuntimeError):
    """Raised when browser/account/planet identity evidence is inconsistent."""


@dataclass(frozen=True)
class PlanetDomFact:
    """Neutral read-only fact extracted from the game's own planet selector."""

    planet_id: str
    coord: str
    display_name: str
    selected_by_list: bool = False


@dataclass(frozen=True)
class BrowserSession:
    """Read-only observation of the currently reachable Nemexia browser surface."""

    endpoint: str
    page_url: str
    server_host: str
    page_count: int
    game_page_count: int
    evidence: str


@dataclass(frozen=True)
class AccountContext:
    """Account/server ownership evidence without inventing an unproven player ID."""

    server_host: str
    ownership_fingerprint: str
    planet_ids: tuple[str, ...]
    planet_coords: tuple[str, ...]
    evidence: str


@dataclass(frozen=True)
class PlanetIdentity:
    """First-class identity for one planet owned by the observed account."""

    planet_id: str
    coord: str
    display_name: str
    selected: bool
    selected_proof: str
    server_host: str
    account_fingerprint: str
    ownership_evidence: str


@dataclass(frozen=True)
class BrowserIdentitySnapshot:
    session: BrowserSession
    account: AccountContext
    planets: tuple[PlanetIdentity, ...]
    current_planet: PlanetIdentity | None

    def by_id(self, planet_id: str) -> PlanetIdentity | None:
        key = str(planet_id)
        return next((planet for planet in self.planets if planet.planet_id == key), None)

    def by_coord(self, coord: str) -> PlanetIdentity | None:
        key = str(coord).replace(" ", "")
        return next((planet for planet in self.planets if planet.coord == key), None)


def ownership_fingerprint(server_host: str, facts: tuple[PlanetDomFact, ...]) -> str:
    """Stable account evidence derived only from server + owned internal planet IDs."""

    rows = sorted(f"{fact.planet_id}:{fact.coord}" for fact in facts)
    payload = "\n".join([server_host.casefold(), *rows]).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_browser_identity(
    *,
    endpoint: str,
    page_url: str,
    page_count: int,
    game_page_count: int,
    planets: tuple[PlanetDomFact, ...],
    trigger_coord: str | None,
) -> BrowserIdentitySnapshot:
    """Build fail-closed identity from already-rendered, read-only DOM evidence."""

    host = (urlsplit(str(page_url)).hostname or "").casefold()
    if not host:
        raise BrowserIdentityError("Nemexia server host is not proven")
    if int(game_page_count) <= 0:
        raise BrowserIdentityError("No live Nemexia game page is proven")
    if not planets:
        raise BrowserIdentityError("Owned planet list is empty or unavailable")

    ids: set[str] = set()
    coords: set[str] = set()
    normalized: list[PlanetDomFact] = []
    for raw in planets:
        planet_id = str(raw.planet_id).strip()
        coord = str(raw.coord).replace(" ", "").strip()
        name = " ".join(str(raw.display_name).split()).strip() or coord
        if not _PLANET_ID_RE.fullmatch(planet_id):
            raise BrowserIdentityError(f"Invalid internal planet ID: {planet_id or 'missing'}")
        if not _COORD_RE.fullmatch(coord):
            raise BrowserIdentityError(f"Invalid owned planet coordinate: {coord or 'missing'}")
        if planet_id in ids:
            raise BrowserIdentityError(f"Duplicate internal planet ID: {planet_id}")
        if coord in coords:
            raise BrowserIdentityError(f"Duplicate owned planet coordinate: {coord}")
        ids.add(planet_id)
        coords.add(coord)
        normalized.append(PlanetDomFact(planet_id, coord, name, bool(raw.selected_by_list)))

    facts = tuple(normalized)
    active = tuple(fact for fact in facts if fact.selected_by_list)
    if len(active) > 1:
        raise BrowserIdentityError("Multiple owned planets are marked active")

    trigger = str(trigger_coord or "").replace(" ", "").strip()
    trigger_match = None
    if trigger:
        if not _COORD_RE.fullmatch(trigger):
            raise BrowserIdentityError("#planetSwitch selected coordinate is malformed")
        trigger_match = next((fact for fact in facts if fact.coord == trigger), None)
        if trigger_match is None:
            raise BrowserIdentityError("#planetSwitch points outside the owned planet list")

    if active and trigger_match is not None and active[0].planet_id != trigger_match.planet_id:
        raise BrowserIdentityError("Selected planet evidence disagrees between list and trigger")

    selected_fact = active[0] if active else trigger_match
    fingerprint = ownership_fingerprint(host, facts)
    account = AccountContext(
        server_host=host,
        ownership_fingerprint=fingerprint,
        planet_ids=tuple(sorted(fact.planet_id for fact in facts)),
        planet_coords=tuple(sorted(fact.coord for fact in facts)),
        evidence="#planetsListHolder + change_planet.php?id + server host",
    )
    session = BrowserSession(
        endpoint=str(endpoint).rstrip("/"),
        page_url=str(page_url),
        server_host=host,
        page_count=max(0, int(page_count)),
        game_page_count=max(0, int(game_page_count)),
        evidence="CDP connection + already-open Nemexia page",
    )

    identities: list[PlanetIdentity] = []
    for fact in facts:
        selected = selected_fact is not None and fact.planet_id == selected_fact.planet_id
        if not selected:
            proof = ""
        elif fact.selected_by_list and trigger_match is not None:
            proof = "#planetsListHolder li.active + #planetSwitch"
        elif fact.selected_by_list:
            proof = "#planetsListHolder li.active"
        else:
            proof = "#planetSwitch"
        identities.append(
            PlanetIdentity(
                planet_id=fact.planet_id,
                coord=fact.coord,
                display_name=fact.display_name,
                selected=selected,
                selected_proof=proof,
                server_host=host,
                account_fingerprint=fingerprint,
                ownership_evidence="#planetsListHolder anchor change_planet.php?id",
            )
        )

    result = tuple(identities)
    current = next((planet for planet in result if planet.selected), None)
    return BrowserIdentitySnapshot(session=session, account=account, planets=result, current_planet=current)
