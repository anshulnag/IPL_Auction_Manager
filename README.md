# IPL Auction Desk 🏏

A Streamlit app for running an IPL mock auction off a Google Sheet. Pick the player, enter the price and team,
press **Confirm sale**, and the app:

1. writes the **price** and **team** beside the player on the auction tab,
2. adds the **player + price** to the next empty row in that team's column on the roster tab,
3. takes the price off the team's **purse**: the "Salary Purse Remaining" cell and the summary table
   (Purse Available / Purse Used, and Overseas Used / Left for overseas players).

Cells that are formulas are left alone, because the sheet recalculates them itself.

It also has:
- a **roulette** that draws a random unsold player from a set,
- a **password screen** for the app,
- **Undo last sale** and a **Reverse a sale** tab,
- tabs for team purses, squads and the full auction list.

## Rules the app enforces

A sale is **blocked** (Confirm stays greyed out) when:
- the team doesn't have enough purse left,
- the player is already sold (reverse the sale first to change it),
- the player is already in a squad on the roster tab,
- the player is overseas and the team has no overseas slots left (8 used, or Overseas Left is 0).

A **warning** is shown (the sale is still allowed) when the price is below the base price or the squad goes
over 25.

## Who counts as overseas

The app reads the `Country` column on the auction tab: any country other than India counts as overseas.
A team's overseas count comes from `Overseas Used` in the roster summary table (or, if that column isn't
there, from counting overseas players in the squad). For a player who isn't in the auction list, an
"Overseas player" tick box appears.

## How it connects

The app talks to a small **Google Apps Script** inside the sheet. The script runs as the sheet's owner, so:
- the sheet can be **view-only** for everyone else,
- no Google Cloud project, service account or key file is needed,
- whoever runs the app does **not** need their own Google access to the sheet.

Every request carries a password (`token`) that must match the one in the script, so the script URL alone
can't read or edit the sheet.

## Setup (using a spare Google account)

### 1. Apps Script (signed in to the spare account)

1. Open the auction sheet in the spare account. If it belongs to another account, use **File → Make a copy**
   and work on the copy.
2. **Extensions → Apps Script**. Delete everything in `Code.gs` and paste in `apps_script/Code.gs`.
3. Change the first line to your own long password:
   `const TOKEN = "your-script-password";` and save.
4. **Deploy → New deployment** → gear icon → **Web app**.
   - *Execute as:* **Me**
   - *Who has access:* **Anyone**
5. **Deploy → Authorize access**, pick the spare account. If Google says "Google hasn't verified this app",
   click **Advanced → Go to … (unsafe) → Allow**.
6. Copy the **Web app URL** (ends in `/exec`). Opening it in a browser should show
   `IPL Auction Desk script is running.`

Lost the URL? **Deploy → Manage deployments** shows it. Don't make a new deployment, because that creates a
different URL.

If you edit `Code.gs` later: **Deploy → Manage deployments → Edit → Version: New version → Deploy**. The URL
stays the same.

### 2. Share the sheet view-only

**Share → General access → Anyone with the link → Viewer.** Send that link to the participants.

### 3. GitHub

Create a **private** repository and upload:
```
app.py
sheet_logic.py
backends.py
requirements.txt
```
`sample_data/` (only used for demo mode), `apps_script/`, `tests/` and this README are optional.
Never upload a `.streamlit/secrets.toml` file.

### 4. Streamlit Community Cloud

1. At <https://share.streamlit.io>, sign in with GitHub → **Create app → Deploy a public app from GitHub**
   (it stays private because the repo is private).
2. Repository: your repo · Branch: `main` · Main file path: `app.py`.
3. **Advanced settings**: Python 3.12, and paste into **Secrets**:
   ```toml
   app_password = "password for whoever runs the auction"

   [apps_script]
   url = "https://script.google.com/macros/s/XXXXXXXX/exec"
   token = "the same password as TOKEN in Code.gs"
   auction_tab = ""
   roster_tab = ""
   ```
   Leave `auction_tab` and `roster_tab` empty to find the tabs automatically (first tab = players; a tab
   named ROSTER / Squads / Squad / Teams, otherwise the second tab = squads). Or type the exact tab names.
4. **Deploy**. Then **Share → make sure the app is private**, and invite whoever will run the auction by
   email.

**Check it works:** the app asks for the app password, and the sidebar shows **Google Sheet · (sheet name)**,
not "Demo mode". Record a test sale, check the sheet, then press **Undo last sale**.

## Troubleshooting

| Message | Fix |
|---|---|
| `Wrong token` | `token` in Secrets and `TOKEN` in `Code.gs` don't match exactly. |
| `No tab called '…'` | The tab name in Secrets doesn't match the sheet. Fix it, or set it to `""`. |
| `didn't send back data` | The URL must end in `/exec`, and the deployment must have access set to Anyone. |
| Red error page with `requests.exceptions.HTTPError` | Google's server returned an error. Check the sheet first, because the last sale was probably saved. Then reload the page. If it keeps happening, open **Manage app → logs** and look for the status code (below). |
| `401` / `403` in the error or logs | The deployment's "Who has access" must be **Anyone**. |
| `404` | Wrong URL or archived deployment. Copy it again from **Manage deployments**. |
| `429` / `500` / `503` | A temporary Google problem. Wait a few seconds and reload the page. |
| Sidebar says **Demo mode** | The `[apps_script]` secrets weren't found. |

## Changing names later

- **Spreadsheet name:** nothing to change.
- **Tab names:** update `auction_tab` / `roster_tab` in Secrets, or leave them as `""`.
- **Inside the tabs**, keep these labels: `FULL NAME`, `PRICE`, `TEAM` and `Country` on the player list;
  each team's full name with `in CR` next to it, and a `Salary Purse Remaining` row under each team, on the
  roster tab. Rows and columns can move; the app finds them by these labels.

## Handing over to someone else

Invite them to the private Streamlit app and give them the app password. The script keeps writing as the
spare account even when nobody is signed in to it, so they don't need edit access to the sheet.

## Try it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Without secrets the app runs in demo mode on `sample_data/`. To use the real sheet locally, copy
`.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in.

## Files

| File | What it does |
|---|---|
| `app.py` | Streamlit app |
| `sheet_logic.py` | Finds the sheet layout and works out every cell to change |
| `backends.py` | Talks to the Apps Script, plus the local demo |
| `apps_script/Code.gs` | The script you paste into the Google Sheet |
| `tests/` | `pytest -q tests` (needs Node.js for the Apps Script tests) |
