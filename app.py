from __future__ import annotations

import hmac
import random
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from backends import AppsScriptBackend, LocalBackend, record_sale, reverse_sale
from sheet_logic import (OVERSEAS_MAX, SQUAD_MAX, TEAM_FULL_NAME, TEAMS, find_player,
                         find_summary, find_team_blocks, fmt_money, list_players, norm,
                         plan_reverse, plan_sale, squad, team_status)

st.set_page_config(page_title="IPL Auction Desk", page_icon="🏏", layout="wide")

TEAM_COLORS = {
    "CSK": "#F9CD05", "DC": "#17479E", "GT": "#1B2133", "KKR": "#3A225D", "LSG": "#00A7E1",
    "MI": "#004BA0", "PBKS": "#D71920", "RCB": "#EC1C24", "RR": "#EA1A85", "SRH": "#F26522",
}

st.markdown("""
<style>
.block-container {padding-top: 1.6rem;}
.badge {display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;font-weight:600;font-size:.85rem}
.wheel {font-size:2.1rem;font-weight:800;text-align:center;padding:18px 8px;border-radius:14px;
        background:linear-gradient(135deg,#0b1f4b,#1d3f8f);color:#fff;letter-spacing:.5px}
.wheel small {display:block;font-size:.9rem;font-weight:500;opacity:.8;margin-top:4px}
</style>
""", unsafe_allow_html=True)


def password_gate():
    try:
        password = str(st.secrets.get("app_password", ""))
    except Exception:
        password = ""
    if not password or st.session_state.get("unlocked"):
        return
    st.title("IPL Auction Desk")
    with st.form("unlock"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Unlock", type="primary")
    if submitted:
        if hmac.compare_digest(entered.encode(), password.encode()):
            st.session_state.unlocked = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()


password_gate()


def badge(code: str) -> str:
    fg = "#111" if code == "CSK" else "#fff"
    return f'<span class="badge" style="background:{TEAM_COLORS.get(code, "#555")};color:{fg}">{code}</span>'


@st.cache_resource(show_spinner=False)
def apps_script_backend(url: str, token: str, auction_tab: str, roster_tab: str):
    return AppsScriptBackend(url, token, auction_tab or None, roster_tab or None)


def get_backend():
    try:
        cfg = dict(st.secrets["apps_script"]) if "apps_script" in st.secrets else None
    except Exception:
        cfg = None
    if cfg:
        return apps_script_backend(cfg["url"], cfg["token"], cfg.get("auction_tab", ""), cfg.get("roster_tab", ""))
    if "demo_backend" not in st.session_state:
        st.session_state.demo_backend = LocalBackend(Path(__file__).parent / "sample_data")
    return st.session_state.demo_backend


try:
    backend = get_backend()
except Exception as e:
    st.error(f"Couldn't connect to the Google Sheet: {e}")
    st.stop()


def load(force=False):
    if force or "data" not in st.session_state:
        with st.spinner("Reading the sheet…"):
            st.session_state.data = backend.read()
    return st.session_state.data


try:
    data = load()
except Exception as e:
    st.error(f"Couldn't read the sheet: {e}")
    st.info("Check the Apps Script URL and token in your Streamlit secrets, and that the script is deployed "
            "as a web app with 'Execute as: Me' and 'Who has access: Anyone'.")
    st.stop()

a_vals, _ = data["auction"]
r_vals, r_forms = data["roster"]
try:
    _, players = list_players(a_vals)
except ValueError as e:
    st.error(str(e))
    st.stop()
blocks = find_team_blocks(r_vals, r_forms)
summary = find_summary(r_vals)
status = team_status(r_vals, players, blocks, summary)
missing = [c for c in TEAMS if c not in blocks]

st.session_state.setdefault("history", [])
st.session_state.setdefault("flash", None)


with st.sidebar:
    st.markdown("### 🏏 IPL Auction Desk")
    st.caption(backend.label)
    if st.session_state.get("unlocked") and st.button("🔒 Lock", use_container_width=True):
        st.session_state.unlocked = False
        st.rerun()
    if backend.url:
        st.link_button("Open the sheet", backend.url, use_container_width=True)
    if st.button("🔄 Refresh from sheet", use_container_width=True):
        load(force=True)
        st.rerun()
    if backend.is_demo:
        st.warning("**Demo mode.** Sales go into a local copy of your sample sheet. "
                   "Add your Apps Script URL and token to the Streamlit secrets to write to the real sheet "
                   "(see README).")
        if st.button("Reset demo data", use_container_width=True):
            del st.session_state["demo_backend"]
            st.session_state.pop("data", None)
            st.session_state.history = []
            st.rerun()
    if missing:
        st.error("No squad column found for: " + ", ".join(missing))

    st.markdown("#### Purses")
    for code in sorted(TEAMS, key=lambda c: -(status[c].purse_left or 0)):
        s = status[code]
        purse = fmt_money(s.purse_left) if s.purse_left is not None else "—"
        ov = f"{s.overseas}/{OVERSEAS_MAX}" if s.overseas is not None else "—"
        st.markdown(f"{badge(code)} &nbsp;**{purse}** &nbsp;·&nbsp; {s.squad_size}/{SQUAD_MAX} · ✈️ {ov}",
                    unsafe_allow_html=True)


st.title("IPL Auction Desk")
sold_n = sum(p.sold for p in players)
c1, c2, c3 = st.columns(3)
c1.metric("Players in auction", len(players))
c2.metric("Sold", sold_n)
c3.metric("Still to go", len(players) - sold_n)

if st.session_state.flash:
    kind, msg = st.session_state.flash
    getattr(st, kind)(msg)
    st.session_state.flash = None


by_name = {p.name: p for p in players}


def set_label(p):
    return f"Set {p.set_no} · {p.set_name}" if p.set_no else (p.set_name or "No set")


sets: dict[str, list] = {}
for p in players:
    sets.setdefault(set_label(p), []).append(p)


def on_player_change():
    p = by_name.get(st.session_state.get("player"))
    if p and p.base:
        st.session_state.price = float(p.base)


left, right = st.columns([1, 1.35], gap="large")

with left:
    st.subheader("🎡 Roulette")
    set_names = list(sets)
    first_open = next((s for s in set_names if any(not p.sold for p in sets[s])), set_names[0] if set_names else None)
    chosen_set = st.selectbox(
        "Set", set_names, index=set_names.index(first_open) if first_open else 0,
        format_func=lambda s: f"{s}  ({sum(not p.sold for p in sets[s])} left)",
    )
    pool = [p for p in sets.get(chosen_set, []) if not p.sold]
    wheel = st.empty()
    spin = st.button("Spin the wheel", type="primary", use_container_width=True, disabled=not pool)
    if spin and pool:
        winner = random.choice(pool)
        names = [p.name for p in pool]
        frames = 22 if len(pool) > 1 else 1
        for i in range(frames):
            n = random.choice(names)
            wheel.markdown(f'<div class="wheel">{n}<small>spinning…</small></div>', unsafe_allow_html=True)
            time.sleep(0.04 + i * 0.012)
        st.session_state.player = winner.name
        if winner.base:
            st.session_state.price = float(winner.base)
    current = by_name.get(st.session_state.get("player"))
    if current:
        info = f"{current.country} · {current.set_name} · base {fmt_money(current.base) if current.base else '—'}"
        wheel.markdown(f'<div class="wheel">{current.name}<small>{info}</small></div>', unsafe_allow_html=True)
    elif not pool:
        wheel.info("Every player in this set has been sold.")
    else:
        wheel.markdown(f'<div class="wheel">?<small>{len(pool)} players left in this set</small></div>',
                       unsafe_allow_html=True)


with right:
    st.subheader("🔨 Record a sale")

    def player_label(name):
        p = by_name.get(name)
        if not p:
            return f"{name}  (not in auction list)"
        tag = f"  ✅ SOLD → {p.team} {p.price:g}" if p.sold and p.price is not None else ("  ✅ SOLD" if p.sold else "")
        return f"{p.name}  ·  {p.set_name}{tag}"

    unsold_first = [p.name for p in players if not p.sold] + [p.name for p in players if p.sold]
    st.selectbox("Player name", unsold_first, key="player", index=None, placeholder="Type to search…",
                 format_func=player_label, accept_new_options=True, on_change=on_player_change)
    pc1, pc2 = st.columns(2)
    pc1.number_input("Price (₹ Cr)", min_value=0.0, step=0.05, format="%.2f", key="price")

    def team_label(code):
        s = status[code]
        purse = fmt_money(s.purse_left) if s.purse_left is not None else "?"
        return f"{code} · {purse} left"

    pc2.selectbox("Team", list(TEAMS), key="team", index=None, placeholder="Pick the buyer", format_func=team_label)

    player_name = st.session_state.get("player") or ""
    price = st.session_state.get("price") or 0.0
    team = st.session_state.get("team")
    known = find_player(players, player_name) if player_name else None

    overseas = None
    if player_name and not known:
        overseas = st.checkbox("Overseas player", value=False,
                               help="This player isn't in the auction list, so the app can't read their country.")

    preview = None
    if player_name and team and price > 0:
        preview = plan_sale(a_vals, r_vals, r_forms, player_name, price, team, overseas_override=overseas)
        for e in preview.errors:
            st.error(e)
        for w in preview.warnings:
            st.warning(w)
        if not preview.errors:
            s = status[team]
            after = (s.purse_left - price) if s.purse_left is not None else None
            st.markdown(
                f"{badge(team)} &nbsp; buys **{known.name if known else player_name}** for **{fmt_money(price)}**"
                + (f" &nbsp;→&nbsp; purse left **{fmt_money(after)}**" if after is not None else "")
                + f" &nbsp;·&nbsp; squad {s.squad_size + 1}/{SQUAD_MAX}",
                unsafe_allow_html=True,
            )
            with st.expander("Cells that will change"):
                if preview.needs_row_at is not None:
                    st.write(f"• The {team} column is full — a new row will be added to {backend.tab_title('roster')}.")
                for ch in preview.changes:
                    st.write(f"• {backend.tab_title(ch.tab)}!{ch.a1} → {ch.value!r}  ({ch.note})")
                if not any("purse" in ch.note for ch in preview.changes) and preview.needs_row_at is None:
                    st.caption("Purse cells are formulas, so the sheet recalculates them itself.")

    if st.button("✅ Confirm sale", type="primary", use_container_width=True,
                 disabled=not (preview and not preview.errors)):
        with st.spinner("Writing to the sheet…"):
            try:
                plan = record_sale(backend, player_name, price, team, overseas_override=overseas)
            except Exception as e:
                plan = None
                st.session_state.flash = ("error", f"Sheet update failed: {e}")
        if plan is not None:
            if plan.errors:
                st.session_state.flash = ("error", " ".join(plan.errors))
            else:
                name = known.name if known else player_name
                st.session_state.history.append((name, team, price))
                extra = (" " + " ".join(plan.warnings)) if plan.warnings else ""
                st.session_state.flash = ("success", f"🎉 {name} sold to {TEAM_FULL_NAME[team]} for {fmt_money(price)}.{extra}")
                for k in ("player", "team", "price"):
                    st.session_state.pop(k, None)
        load(force=True)
        st.rerun()

    if st.session_state.history:
        name, t, pr = st.session_state.history[-1]
        if st.button(f"↩️ Undo last sale ({name} → {t}, {pr:g} Cr)", use_container_width=True):
            plan = reverse_sale(backend, name)
            st.session_state.flash = (("error", " ".join(plan.errors)) if plan.errors
                                      else ("info", f"Reversed: {name} is back in the pool and {t}'s purse was refunded."))
            if not plan.errors:
                st.session_state.history.pop()
            load(force=True)
            st.rerun()

st.divider()


t1, t2, t3, t4 = st.tabs(["🏟️ Teams", "👥 Squads", "📋 Auction list", "↩️ Reverse a sale"])

with t1:
    rows = []
    for code in TEAMS:
        s = status[code]
        rows.append({"Team": f"{code} — {TEAM_FULL_NAME[code]}", "Purse left (Cr)": s.purse_left,
                     "Purse used (Cr)": s.purse_used, "Squad": s.squad_size, "Overseas": s.overseas,
                     "Slots left": SQUAD_MAX - s.squad_size})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"Purse left (Cr)": st.column_config.NumberColumn(format="₹%.2f"),
                                "Purse used (Cr)": st.column_config.NumberColumn(format="₹%.2f")})

with t2:
    code = st.selectbox("Team", list(TEAMS), format_func=lambda c: f"{c} — {TEAM_FULL_NAME[c]}", key="squad_team")
    if code in blocks:
        bought_here = {norm(p.name) for p in players if p.sold}
        df = pd.DataFrame([{"Player": n, "Price (Cr)": pr, "Bought at this auction": "🆕" if norm(n) in bought_here else ""}
                           for _, n, pr in squad(r_vals, blocks[code])])
        s = status[code]
        m1, m2, m3 = st.columns(3)
        m1.metric("Purse left", fmt_money(s.purse_left) if s.purse_left is not None else "—")
        m2.metric("Squad", f"{s.squad_size}/{SQUAD_MAX}")
        m3.metric("Overseas", f"{s.overseas}/{OVERSEAS_MAX}" if s.overseas is not None else "—")
        st.dataframe(df, hide_index=True, use_container_width=True,
                     column_config={"Price (Cr)": st.column_config.NumberColumn(format="₹%.2f")})
    else:
        st.info("This team's column wasn't found in the roster tab.")

with t3:
    f1, f2 = st.columns([1, 2])
    show = f1.radio("Show", ["All", "Unsold", "Sold"], horizontal=True)
    q = f2.text_input("Search", placeholder="Name, country, set or team")
    df = pd.DataFrame([{"Set": set_label(p), "Player": p.name, "Country": p.country, "Base (Cr)": p.base,
                        "Price (Cr)": p.price, "Team": p.team} for p in players])
    if show == "Unsold":
        df = df[df["Team"].str.strip() == ""]
    elif show == "Sold":
        df = df[df["Team"].str.strip() != ""]
    if q:
        mask = df.apply(lambda r: q.lower() in " ".join(map(str, r.values)).lower(), axis=1)
        df = df[mask]
    st.dataframe(df, hide_index=True, use_container_width=True, height=420)

with t4:
    st.caption("Clears the price and team in the auction list, removes the player from the squad column "
               "and puts the money back in the purse.")
    sold_names = [p.name for p in players if p.sold]
    target = st.selectbox("Sold player", sold_names, index=None, placeholder="Pick a player", key="reverse_pick",
                          accept_new_options=True)
    if target:
        rp = plan_reverse(a_vals, r_vals, r_forms, target)
        for e in rp.errors:
            st.error(e)
        for w in rp.warnings:
            st.warning(w)
        if st.button("Reverse this sale", disabled=bool(rp.errors)):
            plan = reverse_sale(backend, target)
            st.session_state.flash = (("error", " ".join(plan.errors)) if plan.errors
                                      else ("info", f"Reversed the sale of {target}."))
            st.session_state.history = [h for h in st.session_state.history if norm(h[0]) != norm(target)]
            st.session_state.pop("reverse_pick", None)
            load(force=True)
            st.rerun()
