# AFF Excel Auto-Backup

Zero-auth automatic backup of a public Google Sheet / Drive Excel file to this repo, every 30 minutes during active hours.

## Active window
- **Dates:** 2026-04-23 to 2026-04-26 (4 days)
- **Hours:** 08:00 to 22:00 IST
- **Frequency:** every 30 min (~29 runs/day, ~116 total)

## How it works
1. GitHub Actions cron fires every 30 min (UTC-mapped to IST window)
2. `backup.py` downloads the public Excel from `SOURCE_URL`
3. File is saved to `backups/` and committed back to this repo
4. Outside the active window, the Python guard auto-skips

## Setup (one-time)
1. Open your Excel file in Google Drive/Sheets
2. **Share** → General access → **Anyone with the link** → **Viewer** → Copy link
3. Add repo secret: **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `SOURCE_URL`
   - Value: the link you copied

## Trigger manually (bypass window)
**Actions** tab → *Excel Backup (no-auth, IST 8AM-10PM)* → **Run workflow** → set `force` = `true` → **Run workflow**

## Where backups are stored
`backups/` folder in this repo:
- `AFF-Evals-LATEST.xlsx` — always freshest
- `AFF-Evals-YYYY-MM-DD_HH-MM_IST.xlsx` — full timestamped history

Each backup is a git commit with IST timestamp. Browse history anytime via the repo UI.

## Files
- `backup.py` — backup logic with IST window guard
- `.github/workflows/backup.yml` — GitHub Actions cron + commit step

## Config (in `.github/workflows/backup.yml`)
```yaml
ACTIVE_WINDOW_START: "2026-04-23"
ACTIVE_WINDOW_END:   "2026-04-26"
ACTIVE_HOUR_START_IST: "8"
ACTIVE_HOUR_END_IST:   "22"
```
Change these to extend the window later.
