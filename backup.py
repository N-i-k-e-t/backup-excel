import os, json, datetime, sys
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from google.cloud import storage
import io

IST_OFFSET = datetime.timedelta(hours=5, minutes=30)

def log(msg):
    now_ist = (datetime.datetime.utcnow() + IST_OFFSET).strftime("%Y-%m-%d %H:%M:%S IST")
    print(f"[{now_ist}] {msg}", flush=True)

def within_active_window():
    """Only run between ACTIVE_WINDOW_START and ACTIVE_WINDOW_END (inclusive),
    and only during ACTIVE_HOUR_START_IST <= IST hour < ACTIVE_HOUR_END_IST.
    Manual runs (workflow_dispatch) bypass this via FORCE_RUN=1."""
    if os.environ.get("FORCE_RUN") == "1":
        return True, "FORCE_RUN=1 bypass"

    now_ist = datetime.datetime.utcnow() + IST_OFFSET
    today = now_ist.date()

    start = datetime.datetime.strptime(os.environ.get("ACTIVE_WINDOW_START", "2026-04-23"), "%Y-%m-%d").date()
    end = datetime.datetime.strptime(os.environ.get("ACTIVE_WINDOW_END", "2026-04-26"), "%Y-%m-%d").date()
    hr_start = int(os.environ.get("ACTIVE_HOUR_START_IST", "8"))
    hr_end = int(os.environ.get("ACTIVE_HOUR_END_IST", "22"))

    if today < start or today > end:
        return False, f"Date {today} outside window {start}..{end}"
    if not (hr_start <= now_ist.hour < hr_end) and not (now_ist.hour == hr_end and now_ist.minute == 0):
        return False, f"IST hour {now_ist.hour}:{now_ist.minute:02d} outside {hr_start}:00..{hr_end}:00"
    return True, f"IST {now_ist.isoformat()} inside window"

def main():
    ok, reason = within_active_window()
    log(f"Window check: {reason}")
    if not ok:
        log("Skipping backup (outside active window). Exiting cleanly.")
        return

    ts_utc = datetime.datetime.utcnow()
    ts = ts_utc.strftime("%Y-%m-%dT%H-%M-%S")
    ts_ist = (ts_utc + IST_OFFSET).strftime("%Y-%m-%d_%H-%M_IST")
    log(f"Starting backup run (UTC: {ts} / IST: {ts_ist})")

    drive_creds_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    gcs_creds_info = json.loads(os.environ["GCS_KEY_JSON"])
    file_id = os.environ["SOURCE_FILE_ID"]
    bucket_name = os.environ["GCS_BUCKET_NAME"]

    drive_creds = service_account.Credentials.from_service_account_info(
        drive_creds_info, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    drive = build("drive", "v3", credentials=drive_creds)

    meta = drive.files().get(fileId=file_id, fields="id,name,mimeType").execute()
    log(f"Source file: {meta['name']} ({meta['mimeType']})")

    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if meta["mimeType"] == "application/vnd.google-apps.spreadsheet":
        request = drive.files().export_media(fileId=file_id, mimeType=xlsx_mime)
    else:
        request = drive.files().get_media(fileId=file_id)

    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            log(f"Download progress: {int(status.progress()*100)}%")
    content = buf.getvalue()
    log(f"Downloaded {len(content)} bytes")

    gcs_creds = service_account.Credentials.from_service_account_info(gcs_creds_info)
    client = storage.Client(credentials=gcs_creds, project=gcs_creds_info.get("project_id"))
    bucket = client.bucket(bucket_name)

    timestamped = f"backups/AFF-Evals-{ts_ist}.xlsx"
    latest = "backups/AFF-Evals-LATEST.xlsx"
    bucket.blob(timestamped).upload_from_string(content, content_type=xlsx_mime)
    log(f"Uploaded gs://{bucket_name}/{timestamped}")
    bucket.blob(latest).upload_from_string(content, content_type=xlsx_mime)
    log(f"Uploaded gs://{bucket_name}/{latest}")

    log("Backup completed successfully")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
