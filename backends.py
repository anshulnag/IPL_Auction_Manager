from __future__ import annotations

import copy
import csv
from pathlib import Path

from sheet_logic import Change, pad

TABS = ("auction", "roster")


class GoogleBackend:

    def __init__(self, service_account_info: dict, sheet_url: str,
                 auction_tab: str | None = None, roster_tab: str | None = None):
        import gspread
        from google.oauth2.service_account import Credentials

        creds = Credentials.from_service_account_info(
            dict(service_account_info),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self.gc = gspread.authorize(creds)
        self.sh = self.gc.open_by_url(sheet_url) if sheet_url.startswith("http") else self.gc.open_by_key(sheet_url)
        sheets = self.sh.worksheets()

        auction = self.sh.worksheet(auction_tab) if auction_tab else sheets[0]
        if roster_tab:
            roster = self.sh.worksheet(roster_tab)
        else:
            others = [ws for ws in sheets if ws.id != auction.id]
            if not others:
                raise ValueError("The spreadsheet needs a second tab for team squads (e.g. ROSTER).")
            roster = next((ws for ws in others if ws.title.strip().lower() in ("roster", "squads", "squad", "teams")),
                          others[0])
        self.ws = {"auction": auction, "roster": roster}
        self.label = f"Google Sheet · {self.sh.title}"
        self.url = self.sh.url
        self.is_demo = False

    def tab_title(self, tab):
        return self.ws[tab].title

    def read(self):
        from gspread.utils import ValueRenderOption

        out = {}
        for tab, ws in self.ws.items():
            vals = ws.get_all_values()
            forms = ws.get_all_values(value_render_option=ValueRenderOption.formula)
            width = max([len(r) for r in vals + forms] + [1])
            vals, forms = pad(vals, width), pad(forms, width)
            forms += [[""] * width] * (len(vals) - len(forms))
            out[tab] = (vals, forms)
        return out

    def write(self, changes: list[Change]):
        for tab in TABS:
            batch = [{"range": c.a1, "values": [[c.value]]} for c in changes if c.tab == tab]
            if batch:
                self.ws[tab].batch_update(batch, value_input_option="USER_ENTERED")

    def insert_row(self, tab, row0):
        sid = self.ws[tab].id
        self.sh.batch_update({"requests": [
            {"insertDimension": {"range": {"sheetId": sid, "dimension": "ROWS",
                                           "startIndex": row0, "endIndex": row0 + 1},
                                 "inheritFromBefore": row0 > 0}},
            {"copyPaste": {"source": {"sheetId": sid, "startRowIndex": row0 + 1, "endRowIndex": row0 + 2},
                           "destination": {"sheetId": sid, "startRowIndex": row0, "endRowIndex": row0 + 1},
                           "pasteType": "PASTE_NORMAL"}},
            {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": row0 + 1, "endRowIndex": row0 + 2},
                            "cell": {}, "fields": "userEnteredValue"}},
        ]})

    def copy_format(self, tab, src_row, dst_row, col, ncols=2):
        sid = self.ws[tab].id
        rng = lambda r: {"sheetId": sid, "startRowIndex": r, "endRowIndex": r + 1,
                         "startColumnIndex": col, "endColumnIndex": col + ncols}
        self.sh.batch_update({"requests": [
            {"copyPaste": {"source": rng(src_row), "destination": rng(dst_row), "pasteType": "PASTE_FORMAT"}}
        ]})


class LocalBackend:

    def __init__(self, folder: str | Path):
        folder = Path(folder)
        self.grids = {}
        for tab in TABS:
            with open(folder / f"{tab}.csv", encoding="utf-8", newline="") as f:
                self.grids[tab] = pad([row for row in csv.reader(f)])
        self.label = "Demo copy (nothing is written to Google)"
        self.url = None
        self.is_demo = True

    def tab_title(self, tab):
        return {"auction": "Sheet", "roster": "ROSTER"}[tab]

    def read(self):
        return {t: (copy.deepcopy(g), copy.deepcopy(g)) for t, g in self.grids.items()}

    def _ensure(self, tab, r, c):
        g = self.grids[tab]
        while len(g) <= r:
            g.append([""] * len(g[0]))
        if c >= len(g[0]):
            for row in g:
                row.extend([""] * (c + 1 - len(row)))

    def write(self, changes):
        for ch in changes:
            self._ensure(ch.tab, ch.row, ch.col)
            v = ch.value
            if isinstance(v, float):
                v = f"{v:.2f}".rstrip("0").rstrip(".")
            self.grids[ch.tab][ch.row][ch.col] = str(v)

    def insert_row(self, tab, row0):
        g = self.grids[tab]
        g.insert(row0, list(g[row0]))
        g[row0 + 1] = [""] * len(g[row0])

    def copy_format(self, *a, **k):
        pass


def record_sale(backend, player, price, team, *, dry_run=False, **opts):
    from sheet_logic import plan_sale

    data = backend.read()
    a_vals, _ = data["auction"]
    r_vals, r_forms = data["roster"]
    plan = plan_sale(a_vals, r_vals, r_forms, player, price, team, **opts)
    if plan.errors or dry_run:
        return plan
    if plan.needs_row_at is not None:
        new_row = plan.needs_row_at + 1
        backend.insert_row("roster", plan.needs_row_at)
        data = backend.read()
        r_vals, r_forms = data["roster"]
        plan = plan_sale(data["auction"][0], r_vals, r_forms, player, price, team, slot_row=new_row, **opts)
        if plan.errors or plan.needs_row_at is not None:
            plan.errors = plan.errors or ["Couldn't make room in the squad column."]
            return plan
        plan.warnings.append(f"The {team} column was full, so a new row was added to the roster tab.")
    backend.write(plan.changes)
    if plan.format_from:
        try:
            backend.copy_format("roster", *plan.format_from)
        except Exception:
            pass
    return plan


def reverse_sale(backend, player, *, dry_run=False):
    from sheet_logic import plan_reverse

    data = backend.read()
    plan = plan_reverse(data["auction"][0], data["roster"][0], data["roster"][1], player)
    if not plan.errors and not dry_run:
        backend.write(plan.changes)
    return plan
