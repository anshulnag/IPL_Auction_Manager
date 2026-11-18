from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

from sheet_logic import Change, pad

TABS = ("auction", "roster")


class AppsScriptBackend:

    def __init__(self, url: str, token: str, auction_tab: str | None = None,
                 roster_tab: str | None = None, timeout: int = 60):
        import requests

        self.session = requests.Session()
        self.script_url = url.strip()
        self.token = token
        self.auction_tab = auction_tab or ""
        self.roster_tab = roster_tab or ""
        self.timeout = timeout
        self.titles = {"auction": "auction tab", "roster": "roster tab"}
        self.label = "Google Sheet (via Apps Script)"
        self.url = None
        self.is_demo = False

    def _call(self, action, **payload):
        body = {"token": self.token, "action": action, "auction_tab": self.auction_tab,
                "roster_tab": self.roster_tab, **payload}
        r = self.session.post(self.script_url, data=json.dumps(body),
                              headers={"Content-Type": "text/plain;charset=utf-8"}, timeout=self.timeout)
        r.raise_for_status()
        try:
            out = r.json()
        except ValueError:
            raise RuntimeError(
                "The Apps Script didn't send back data. Check you used the web app URL ending in /exec "
                "and that the deployment has 'Who has access: Anyone'."
            ) from None
        if not out.get("ok"):
            raise RuntimeError(out.get("error") or "Apps Script returned an error.")
        return out

    def tab_title(self, tab):
        return self.titles[tab]

    def read(self):
        out = self._call("read")
        self.label = f"Google Sheet · {out.get('title', '')}"
        self.url = out.get("url")
        data = {}
        for tab in TABS:
            t = out["tabs"][tab]
            self.titles[tab] = t["title"]
            vals = [[str(v) for v in row] for row in t["values"]]
            forms = [[str(v) for v in row] for row in t["formulas"]]
            width = max([len(r) for r in vals + forms] + [1])
            vals, forms = pad(vals, width), pad(forms, width)
            forms += [[""] * width for _ in range(len(vals) - len(forms))]
            data[tab] = (vals, forms)
        return data

    def write(self, changes: list[Change]):
        if changes:
            self._call("write", changes=[{"tab": c.tab, "row": c.row, "col": c.col, "value": c.value}
                                         for c in changes])

    def insert_row(self, tab, row0):
        self._call("insert_row", tab=tab, row=row0)

    def copy_format(self, tab, src_row, dst_row, col, ncols=2):
        self._call("copy_format", tab=tab, src_row=src_row, dst_row=dst_row, col=col, ncols=ncols)


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
