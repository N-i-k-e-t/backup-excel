"""Zero-auth Excel backup.

Source: public Google Drive / Google Sheets link (Anyone with link - Viewer).
Destination: this GitHub repo under backups/ folder (committed by Actions bot).

Required env:
  SOURCE_URL : public Drive/Sheets link
"""
import os, sys, re, datetime, urllib.request, pathlib

IST = datetime.timedelta(hours=5, minutes=30)

def log(m):
    t = (datetime.datetime.utcnow() + IST).strftime("%Y-%m-%d %H:%M:%S IST")
    print(f"[{t}] {m}", flush=True)

def in_window():
    if os.environ.get("FORCE_RUN") == "1":
        return True, "FORCE_RUN bypass"
    now = datetime.datetime.utcnow() + IST
    s = datetime.datetime.strptime(os.environ.get("ACTIVE_WINDOW_START","2026-04-23"),"%Y-%m-%d").date()
    e = datetime.datetime.strptime(os.environ.get("ACTIVE_WINDOW_END","2026-04-26"),"%Y-%m-%d").date()
    hs = int(os.environ.get("ACTIVE_HOUR_START_IST","8"))
    he = int(os.environ.get("ACTIVE_HOUR_END_IST","22"))
    if now.date() < s or now.date() > e:
        return False, f"date {now.date()} outside {s}..{e}"
    if not (hs <= now.hour < he) and not (now.hour == he and now.minute == 0):
        return False, f"hour {now.hour}:{now.minute:02d} outside {hs}:00..{he}:00 IST"
    return True, f"in window ({now.strftime('%H:%M IST')})"

def build_download_url(src):
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", src)
    if m:
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx", "sheets"
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", src) or re.search(r"[?&]id=([a-zA-Z0-9_-]+)", src)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}", "drive"
    return src, "direct"

def download(url):
    log(f"Downloading: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 backup-bot"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    log(f"Got {len(data)} bytes")
    if len(data) < 1000 or data[:4] != b"PK\x03\x04":
        raise RuntimeError("Not a valid .xlsx. Ensure link is 'Anyone with link - Viewer'.")
    return data

def main():
    ok, why = in_window()
    log(f"Window: {why}")
    if not ok:
        log("Skipping (outside window).")
        return
    src = os.environ["SOURCE_URL"].strip()
    url, kind = build_download_url(src)
    log(f"Source kind: {kind}")
    data = download(url)
    ts_ist = (datetime.datetime.utcnow() + IST).strftime("%Y-%m-%d_%H-%M_IST")
    out_dir = pathlib.Path("backups")
    out_dir.mkdir(exist_ok=True)
    ts_file = out_dir / f"AFF-Evals-{ts_ist}.xlsx"
    latest = out_dir / "AFF-Evals-LATEST.xlsx"
    ts_file.write_bytes(data)
    latest.write_bytes(data)
    log(f"Saved {ts_file} ({len(data)} bytes)")
    log(f"Saved {latest}")
    log("OK")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
