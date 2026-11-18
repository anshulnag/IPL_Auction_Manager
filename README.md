# IPL Auction Desk 🏏

A Streamlit app for running an IPL mock auction off a Google Sheet. Type the player, price and team, hit
**Confirm sale**, and the app:

1. writes the **price** and **team** beside the player on the auction tab (`Sheet`),
2. adds the **player + price** to the next empty row in that team's column on the `ROSTER` tab,
3. takes the price off the team's **purse**: the "Salary Purse Remaining" cell and the summary table
   (Purse Available / Purse Used, and Overseas Used / Left for non-Indian players).

Cells that are formulas are left alone, because the sheet recalculates them itself. The app only does the
arithmetic on cells that hold typed-in numbers.

It also has:
- **Roulette**: pick a set and spin to draw a random unsold player, which fills in the form.
- A **preview** of every cell that will change, plus checks for purse, squad size (25) and overseas (8) limits.
- **Undo last sale** and **Reverse a sale**, which take a player off the team and give the money back.
- Tabs with team purses, each squad and a searchable auction list.

## 1. Try it locally (demo mode, no Google needed)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Without credentials the app runs on a local copy of the sample sheet (`sample_data/`), so you can test the flow.

## 2. Connect your Google Sheet (about 5 minutes)

1. Go to <https://console.cloud.google.com/>, create a project (or pick one), and enable the **Google Sheets API**.
2. **IAM & Admin → Service Accounts → Create service account**. Give it any name; it doesn't need any roles.
3. Open the service account, go to **Keys → Add key → JSON**, and download the file.
4. Open your auction Google Sheet → **Share** → paste the service account's `client_email`
   (looks like `…@….iam.gserviceaccount.com`) → **Editor**.
5. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, put in your sheet URL, and paste
   the values from the JSON key under `[gcp_service_account]`.
6. `streamlit run app.py`. The sidebar should now say *Google Sheet · <your sheet name>*.

**Deploying on Streamlit Community Cloud:** push this folder to GitHub (`secrets.toml` is git-ignored), create the
app at <https://share.streamlit.io>, and paste the contents of your `secrets.toml` into **Settings → Secrets**.

## What the sheet needs to look like

The app finds everything by header text, not by fixed cell addresses, so you can move things around:

- **Auction tab**: a header row with `FULL NAME`, `PRICE`, `TEAM` (and optionally `SET NO.`, `SET`,
  `BASE PRICE`, `Country`). The team is written as the short code (`KKR`, `RCB`, …).
- **Roster tab**:
  - each team has a header cell with its full name and `in CR` in the cell to its right, players listed
    below, and a `Salary Purse Remaining` row at the bottom of the block;
  - optional summary table with `Team Name | Purse Available | Purse Used | Overseas Used | Overseas Left`.
- If a team's column is full, the app inserts a row inside that block, so other teams' columns and any
  `SUM()` ranges still line up.

Team names it recognises: CSK, DC, GT, KKR, LSG, MI, PBKS, RCB, RR, SRH, by code or full name (both
"Bengaluru" and "Bangalore", and both "Super Giants" and "Supergiants").

## Files

| File | What it does |
|---|---|
| `app.py` | Streamlit UI |
| `sheet_logic.py` | Finds the layout and plans every cell edit (pure Python, no Google calls) |
| `backends.py` | Google Sheets read/write (gspread), plus the local demo backend |
| `tests/` | `pytest -q tests` runs the sale, undo, full-column and formula cases against the sample data |
