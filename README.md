# IPL Auction Desk 🏏

A Streamlit app for running an IPL mock auction off a Google Sheet. Type the player, price and team, hit
**Confirm sale**, and the app:

1. writes the **price** and **team** beside the player on the auction tab (`Sheet`),
2. adds the **player + price** to the next empty row in that team's column on the `ROSTER` tab,
3. takes the price off the team's **purse**: the "Salary Purse Remaining" cell and the summary table
   (Purse Available / Purse Used, and Overseas Used / Left for non-Indian players).

Cells that are formulas are left alone, because the sheet recalculates them itself.

It also has a **roulette** to draw a random unsold player from a set, a preview of every cell that will change,
purse / squad (25) / overseas (8) checks, **Undo last sale**, **Reverse a sale**, and tabs for purses, squads and
the full auction list.

## How it connects

The app talks to a small **Google Apps Script** that lives inside your sheet. The script runs as the sheet's
owner, so:

- the sheet can be **view-only** for everyone else ("Anyone with the link → Viewer"),
- no Google Cloud project, service account or key file is needed,
- whoever runs the app does **not** need their own Google access to the sheet.

Every request carries a password (`token`) that must match the one in the script, so the script URL alone
can't be used to edit the sheet.

## 1. Set up the Apps Script (once, by the sheet owner)

1. Open the Google Sheet → **Extensions → Apps Script**.
2. Delete whatever is in `Code.gs` and paste in the contents of `apps_script/Code.gs` from this folder.
3. On the first line, change `CHANGE-ME-TO-A-LONG-RANDOM-PASSWORD` to a long password of your own. Save.
4. **Deploy → New deployment** → gear icon → **Web app**.
   - *Execute as:* **Me**
   - *Who has access:* **Anyone**
5. Click **Deploy**, then **Authorize access** and allow it with your Google account. (Google may show
   "Google hasn't verified this app": click **Advanced → Go to … (unsafe)**. It's your own script.)
6. Copy the **Web app URL** (it ends in `/exec`). Opening it in a browser should show
   `IPL Auction Desk script is running.`

If you change the script later, use **Deploy → Manage deployments → Edit → Version: New version** so the URL
stays the same.

## 2. Share the sheet view-only

**Share → General access → Anyone with the link → Viewer.** Send that link to the participants.

## 3. Deploy the app on Streamlit Community Cloud

1. Push these to a GitHub repo:
   ```
   app.py
   sheet_logic.py
   backends.py
   requirements.txt
   sample_data/auction.csv
   sample_data/roster.csv
   .gitignore
   ```
   (`apps_script/`, `tests/` and `README.md` are optional. Never push `.streamlit/secrets.toml`.)
2. At <https://share.streamlit.io> create the app from the repo with **Main file path** `app.py`.
3. **Settings → Secrets**, paste:
   ```toml
   [apps_script]
   url = "https://script.google.com/macros/s/…/exec"
   token = "the password from Code.gs"
   auction_tab = "Sheet"
   roster_tab = "ROSTER"
   ```
4. **Share → make the app private**, then invite the people who will run the auction by email. They sign in
   with Google or a one-time email link. (Community Cloud allows one private app per account.)

The sidebar should say *Google Sheet · <your sheet name>*. If it says **Demo mode**, the secrets weren't read.

## Handing over to someone else

Anyone you invite to the private app can run the auction. The script keeps writing as the sheet owner even
when the owner is offline, so nobody else needs edit access to the sheet.

If the person taking over should be the one the script runs as (for example, the owner is leaving the
project for good), they need edit access to the sheet. They then open **Extensions → Apps Script**, make a
**new deployment** themselves (same settings) and put the new URL in the Streamlit secrets.

## Try it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Without secrets the app runs in demo mode on a local copy of the sample sheet (`sample_data/`). To use the
real sheet locally, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in.

## What the sheet needs to look like

The app finds everything by header text, not fixed cell addresses:

- **Auction tab**: a header row with `FULL NAME`, `PRICE`, `TEAM` (optionally `SET NO.`, `SET`, `BASE PRICE`,
  `Country`). Team is written as the short code (`KKR`, `RCB`, …).
- **Roster tab**: each team has a header cell with its full name and `in CR` to its right, players below,
  and a `Salary Purse Remaining` row closing the block; plus an optional summary table with
  `Team Name | Purse Available | Purse Used | Overseas Used | Overseas Left`.
- If a team's column is full, a row is inserted inside that block so the other columns and any `SUM()`
  ranges still line up.

## Files

| File | What it does |
|---|---|
| `app.py` | Streamlit UI |
| `sheet_logic.py` | Finds the layout and plans every cell edit |
| `backends.py` | Talks to the Apps Script, plus the local demo backend |
| `apps_script/Code.gs` | The script you paste into the Google Sheet |
| `tests/` | `pytest -q tests` (needs Node.js for the Apps Script tests) |
