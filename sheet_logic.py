from __future__ import annotations

import re
from dataclasses import dataclass, field


TEAMS: dict[str, list[str]] = {
    "CSK": ["Chennai Super Kings"],
    "DC": ["Delhi Capitals", "Delhi Daredevils"],
    "GT": ["Gujarat Titans"],
    "KKR": ["Kolkata Knight Riders"],
    "LSG": ["Lucknow Super Giants", "Lucknow Supergiants"],
    "MI": ["Mumbai Indians"],
    "PBKS": ["Punjab Kings", "Kings XI Punjab"],
    "RCB": ["Royal Challengers Bengaluru", "Royal Challengers Bangalore"],
    "RR": ["Rajasthan Royals"],
    "SRH": ["Sunrisers Hyderabad"],
}
TEAM_FULL_NAME = {code: names[0] for code, names in TEAMS.items()}

SQUAD_MAX = 25
OVERSEAS_MAX = 8
HOME_COUNTRY = "india"


def norm(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


_TEAM_LOOKUP = {}
for _code, _names in TEAMS.items():
    _TEAM_LOOKUP[norm(_code)] = _code
    for _n in _names:
        _TEAM_LOOKUP[norm(_n)] = _code


def team_code(text) -> str | None:
    return _TEAM_LOOKUP.get(norm(text))


def parse_money(text) -> float | None:
    s = str(text or "").replace("₹", "").replace(",", "")
    s = re.sub(r"(?i)\s*(cr|crore|crores)\s*$", "", s).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt_money(x: float) -> str:
    return f"₹{x:,.2f} Cr"


def round_money(x: float) -> float:
    return round(x + 0.0, 2)


def pad(grid: list[list[str]], min_cols: int = 0) -> list[list[str]]:
    width = max([len(r) for r in grid] + [min_cols, 1])
    return [list(r) + [""] * (width - len(r)) for r in grid]


def cell(grid, r, c) -> str:
    if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
        return str(grid[r][c] if grid[r][c] is not None else "")
    return ""


def col_letter(c0: int) -> str:
    s, n = "", c0 + 1
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def a1(r0: int, c0: int) -> str:
    return f"{col_letter(c0)}{r0 + 1}"


def is_formula(raw) -> bool:
    return str(raw or "").startswith("=")


def row_blank(grid, r) -> bool:
    return r < len(grid) and all(not str(v).strip() for v in grid[r])


@dataclass
class AuctionLayout:
    header_row: int
    name_col: int
    price_col: int
    team_col: int
    set_col: int | None = None
    set_no_col: int | None = None
    base_col: int | None = None
    country_col: int | None = None


@dataclass
class Player:
    row: int
    name: str
    set_name: str
    set_no: str
    base: float | None
    country: str
    price: float | None
    team: str

    @property
    def sold(self) -> bool:
        return bool(self.team.strip())

    @property
    def overseas(self) -> bool:
        return bool(self.country.strip()) and norm(self.country) != HOME_COUNTRY


def find_auction_layout(grid) -> AuctionLayout:
    for r in range(min(len(grid), 15)):
        heads = {norm(v): c for c, v in enumerate(grid[r])}
        name_col = next((heads[k] for k in ("fullname", "playername", "name", "player") if k in heads), None)
        price_col = next((heads[k] for k in ("price", "soldprice", "soldfor", "amount", "pricecr", "priceincr") if k in heads), None)
        team_col = next((heads[k] for k in ("team", "teamname", "soldto", "franchise") if k in heads), None)
        if name_col is not None and price_col is not None and team_col is not None:
            base_col = next((c for k, c in heads.items() if k.startswith("baseprice")), None)
            return AuctionLayout(
                header_row=r,
                name_col=name_col,
                price_col=price_col,
                team_col=team_col,
                set_col=heads.get("set"),
                set_no_col=heads.get("setno") if "setno" in heads else heads.get("setnumber"),
                base_col=base_col,
                country_col=heads.get("country") if "country" in heads else heads.get("nationality"),
            )
    raise ValueError(
        "Couldn't find the header row in the auction tab. It needs columns "
        "named FULL NAME, PRICE and TEAM."
    )


def list_players(grid) -> tuple[AuctionLayout, list[Player]]:
    lay = find_auction_layout(grid)
    out = []
    for r in range(lay.header_row + 1, len(grid)):
        name = cell(grid, r, lay.name_col).strip()
        if not name:
            continue
        g = lambda c: cell(grid, r, c).strip() if c is not None else ""
        out.append(Player(
            row=r,
            name=name,
            set_name=g(lay.set_col),
            set_no=g(lay.set_no_col),
            base=parse_money(g(lay.base_col)),
            country=g(lay.country_col),
            price=parse_money(g(lay.price_col)),
            team=g(lay.team_col),
        ))
    return lay, out


def find_player(players: list[Player], name: str) -> Player | None:
    key = norm(name)
    return next((p for p in players if norm(p.name) == key), None)


@dataclass
class TeamBlock:
    code: str
    header_row: int
    name_col: int
    price_col: int
    purse_row: int | None
    first_row: int = 0
    last_row: int = 0

    @property
    def purse_cell(self):
        return None if self.purse_row is None else (self.purse_row, self.price_col)


@dataclass
class SummaryRow:
    code: str
    row: int
    cols: dict[str, int] = field(default_factory=dict)


_SUMMARY_KEYS = {
    "purseavailable": "purse_available",
    "purseremaining": "purse_available",
    "purseused": "purse_used",
    "overseasused": "overseas_used",
    "overseasleft": "overseas_left",
}

_RANGE_RE = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)\s*:\s*\$?([A-Z]{1,3})\$?(\d+)")


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _formula_range_rows(formula: str, col: int) -> tuple[int, int] | None:
    for m in _RANGE_RE.finditer(formula.upper()):
        c1, r1, c2, r2 = _col_index(m.group(1)), int(m.group(2)) - 1, _col_index(m.group(3)), int(m.group(4)) - 1
        if c1 <= col <= c2:
            return min(r1, r2), max(r1, r2)
    return None


def find_team_blocks(values, formulas) -> dict[str, TeamBlock]:
    blocks: dict[str, TeamBlock] = {}
    for r, row in enumerate(values):
        for c, v in enumerate(row):
            code = team_code(v)
            if not code or code in blocks:
                continue
            right = norm(cell(values, r, c + 1))
            if right not in ("incr", "cr", "price", "amount", "pricecr", "priceincr", "incrore"):
                continue
            purse_row = None
            for rr in range(r + 1, len(values)):
                t = norm(cell(values, rr, c))
                if "purse" in t:
                    purse_row = rr
                    break
                if team_code(cell(values, rr, c)) and norm(cell(values, rr, c + 1)) in ("incr", "cr"):
                    break
            end = (purse_row if purse_row is not None else len(values)) - 1
            first, last = r + 1, end
            raw = cell(formulas, purse_row, c + 1) if purse_row is not None else ""
            rng = _formula_range_rows(raw, c + 1) if is_formula(raw) else None
            if rng:
                first, last = max(first, rng[0]), min(end, rng[1])
            else:
                while last > first and row_blank(values, last):
                    last -= 1
                if purse_row is None:
                    last = max(last, first)
            blocks[code] = TeamBlock(code, r, c, c + 1, purse_row, first, last)
    return blocks


def find_summary(values) -> dict[str, SummaryRow]:
    out: dict[str, SummaryRow] = {}
    for r, row in enumerate(values):
        heads = {norm(v): c for c, v in enumerate(row)}
        if "teamname" not in heads:
            continue
        name_col = heads["teamname"]
        cols = {key: heads[h] for h, key in _SUMMARY_KEYS.items() if h in heads}
        if not cols:
            continue
        for rr in range(r + 1, len(values)):
            code = team_code(cell(values, rr, name_col))
            if not code:
                break
            out[code] = SummaryRow(code, rr, dict(cols))
        break
    return out


def squad(values, block: TeamBlock) -> list[tuple[int, str, float | None]]:
    rows = []
    stop = block.purse_row if block.purse_row is not None else len(values)
    for r in range(block.header_row + 1, stop):
        name = cell(values, r, block.name_col).strip()
        if name:
            rows.append((r, name, parse_money(cell(values, r, block.price_col))))
    return rows


def squad_players(values, block) -> list[tuple[int, str, float | None]]:
    return [s for s in squad(values, block) if not norm(s[1]).startswith("penalty")]


def free_slot(values, block: TeamBlock) -> int | None:
    for r in range(block.first_row, block.last_row + 1):
        if not cell(values, r, block.name_col).strip():
            return r
    return None


@dataclass
class TeamStatus:
    code: str
    purse_left: float | None
    purse_used: float | None
    squad_size: int
    overseas: int | None


def team_status(roster_values, auction_players, blocks, summary) -> dict[str, TeamStatus]:
    overseas_names = {norm(p.name) for p in auction_players if p.overseas}
    out = {}
    for code in TEAMS:
        b, s = blocks.get(code), summary.get(code)
        purse = used = ov = None
        if s and "purse_available" in s.cols:
            purse = parse_money(cell(roster_values, s.row, s.cols["purse_available"]))
        if purse is None and b and b.purse_cell:
            purse = parse_money(cell(roster_values, *b.purse_cell))
        if s and "purse_used" in s.cols:
            used = parse_money(cell(roster_values, s.row, s.cols["purse_used"]))
        if s and "overseas_used" in s.cols:
            ov = parse_money(cell(roster_values, s.row, s.cols["overseas_used"]))
            ov = int(ov) if ov is not None else None
        size = len(squad_players(roster_values, b)) if b else 0
        if ov is None and b:
            ov = sum(1 for _, n, _ in squad_players(roster_values, b) if norm(n) in overseas_names)
        out[code] = TeamStatus(code, purse, used, size, ov)
    return out


@dataclass
class Change:
    tab: str
    row: int
    col: int
    value: object
    note: str = ""

    @property
    def a1(self) -> str:
        return a1(self.row, self.col)


@dataclass
class Plan:
    changes: list[Change] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    needs_row_at: int | None = None
    format_from: tuple[int, int, int] | None = None


def _adjust(plan, tab, values, formulas, r, c, delta, label):
    if is_formula(cell(formulas, r, c)):
        return
    old = parse_money(cell(values, r, c))
    if old is None and cell(values, r, c).strip():
        plan.warnings.append(f"Couldn't read {label} ({a1(r, c)} = '{cell(values, r, c)}'); left unchanged.")
        return
    plan.changes.append(Change(tab, r, c, round_money((old or 0) + delta), label))


def plan_sale(auction_values, roster_values, roster_formulas, player_name, price, code,
              overseas_override: bool | None = None,
              slot_row: int | None = None) -> Plan:
    plan = Plan()
    player_name = player_name.strip()
    if not player_name:
        plan.errors.append("Enter a player name.")
    if price is None or price <= 0:
        plan.errors.append("Enter a price above zero.")
    if code not in TEAMS:
        plan.errors.append("Pick a team.")
    if plan.errors:
        return plan

    lay, players = list_players(auction_values)
    blocks = find_team_blocks(roster_values, roster_formulas)
    summary = find_summary(roster_values)
    if code not in blocks:
        plan.errors.append(f"Couldn't find the {TEAM_FULL_NAME[code]} squad column in the roster tab "
                           f"(a cell with the team name and 'in CR' next to it).")
        return plan
    block = blocks[code]

    p = find_player(players, player_name)
    overseas = p.overseas if p else bool(overseas_override)
    if p is None:
        plan.warnings.append(f"'{player_name}' isn't in the auction list, so only the roster tab will be updated.")
    else:
        player_name = p.name
        if p.sold:
            plan.errors.append(f"{p.name} is already sold to {p.team} for {p.price:g} Cr. "
                               f"Reverse that sale first if it needs changing.")
        if p.base is not None and price < p.base:
            plan.warnings.append(f"Price is below {p.name}'s base price ({fmt_money(p.base)}).")

    for other_code, b in blocks.items():
        if any(norm(n) == norm(player_name) for _, n, _ in squad(roster_values, b)):
            plan.errors.append(f"{player_name} is already listed in the {other_code} squad on the roster tab.")
            break

    status = team_status(roster_values, players, blocks, summary)[code]
    if status.purse_left is not None and price > status.purse_left + 1e-9:
        plan.errors.append(f"{code} only has {fmt_money(status.purse_left)} left.")
    if status.squad_size + 1 > SQUAD_MAX:
        plan.warnings.append(f"{code} will have {status.squad_size + 1} players (limit {SQUAD_MAX}).")
    if overseas:
        s_row = summary.get(code)
        left = None
        if s_row and "overseas_left" in s_row.cols:
            left = parse_money(cell(roster_values, s_row.row, s_row.cols["overseas_left"]))
        if (status.overseas is not None and status.overseas >= OVERSEAS_MAX) or (left is not None and left < 1):
            used = f"{status.overseas}/{OVERSEAS_MAX}" if status.overseas is not None else "all"
            plan.errors.append(f"{code} has no overseas slots left ({used} used), so it can't buy "
                               f"{p.name if p else player_name}.")
    if plan.errors:
        return plan

    if p is not None:
        plan.changes.append(Change("auction", p.row, lay.price_col, price, "auction price"))
        plan.changes.append(Change("auction", p.row, lay.team_col, code, "auction team"))

    slot = free_slot(roster_values, block)
    if slot is None and slot_row is not None and block.header_row < slot_row < (block.purse_row or len(roster_values)) \
            and not cell(roster_values, slot_row, block.name_col).strip():
        slot = slot_row
    if slot is None:
        plan.needs_row_at = block.last_row
        return plan
    plan.changes.append(Change("roster", slot, block.name_col, player_name, f"{code} squad name"))
    plan.changes.append(Change("roster", slot, block.price_col, price, f"{code} squad price"))
    if slot > block.header_row + 1:
        plan.format_from = (slot - 1, slot, block.name_col)

    if block.purse_cell:
        _adjust(plan, "roster", roster_values, roster_formulas, *block.purse_cell, -price, f"{code} purse remaining")
    s = summary.get(code)
    if s:
        if "purse_available" in s.cols:
            _adjust(plan, "roster", roster_values, roster_formulas, s.row, s.cols["purse_available"], -price, f"{code} purse available")
        if "purse_used" in s.cols:
            _adjust(plan, "roster", roster_values, roster_formulas, s.row, s.cols["purse_used"], price, f"{code} purse used")
        if overseas and "overseas_used" in s.cols:
            _adjust(plan, "roster", roster_values, roster_formulas, s.row, s.cols["overseas_used"], 1, f"{code} overseas used")
        if overseas and "overseas_left" in s.cols:
            _adjust(plan, "roster", roster_values, roster_formulas, s.row, s.cols["overseas_left"], -1, f"{code} overseas left")
    return plan


def plan_reverse(auction_values, roster_values, roster_formulas, player_name) -> Plan:
    plan = Plan()
    lay, players = list_players(auction_values)
    blocks = find_team_blocks(roster_values, roster_formulas)
    summary = find_summary(roster_values)
    p = find_player(players, player_name)

    found = None
    for code, b in blocks.items():
        for r, n, pr in squad(roster_values, b):
            if norm(n) == norm(player_name):
                found = (code, b, r, pr)
                break
        if found:
            break

    if p is None and found is None:
        plan.errors.append(f"Couldn't find {player_name} in either tab.")
        return plan

    if p is not None and (p.team or p.price is not None):
        plan.changes.append(Change("auction", p.row, lay.price_col, "", "auction price"))
        plan.changes.append(Change("auction", p.row, lay.team_col, "", "auction team"))

    if found is None:
        plan.warnings.append(f"{player_name} wasn't in any squad column, so no purse was refunded.")
        return plan

    code, b, r, price = found
    price = price if price is not None else (p.price if p else None)
    plan.changes.append(Change("roster", r, b.name_col, "", f"{code} squad name"))
    plan.changes.append(Change("roster", r, b.price_col, "", f"{code} squad price"))
    if price is None:
        plan.warnings.append("Couldn't read the sale price, so the purse wasn't refunded.")
        return plan
    overseas = p.overseas if p else False
    if b.purse_cell:
        _adjust(plan, "roster", roster_values, roster_formulas, *b.purse_cell, price, f"{code} purse remaining")
    s = summary.get(code)
    if s:
        if "purse_available" in s.cols:
            _adjust(plan, "roster", roster_values, roster_formulas, s.row, s.cols["purse_available"], price, f"{code} purse available")
        if "purse_used" in s.cols:
            _adjust(plan, "roster", roster_values, roster_formulas, s.row, s.cols["purse_used"], -price, f"{code} purse used")
        if overseas and "overseas_used" in s.cols:
            _adjust(plan, "roster", roster_values, roster_formulas, s.row, s.cols["overseas_used"], -1, f"{code} overseas used")
        if overseas and "overseas_left" in s.cols:
            _adjust(plan, "roster", roster_values, roster_formulas, s.row, s.cols["overseas_left"], 1, f"{code} overseas left")
    return plan
