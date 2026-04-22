import os, json, datetime, sys
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from google.cloud import storage
import io

def log(msg):
    print(f"[{datetime.datetime.utcnow().isoformat()}] {msg}", flush=True)

def main():
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    log(f"Starting backup run {ts}")

    # Load credentials
    drive_creds_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    gcs_creds_info = json.loads(os.environ["GCS_KEY_JSON"])
    file_id = os.environ["SOURCE_FILE_ID"]
    bucket_name = os.environ["GCS_BUCKET_NAME"]

    # Drive auth + download (supports both native Excel files and Google Sheets)
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

    # Upload to GCS
    gcs_creds = service_account.Credentials.from_service_account_info(gcs_creds_info)
    client = storage.Client(credentials=gcs_creds, project=gcs_creds_info.get("project_id"))
    bucket = client.bucket(bucket_name)

    timestamped = f"backups/AFF-Evals-{ts}.xlsx"
    latest = "backups/AFF-Evals-LATEST.xlsx"
    bucket.blob(timestamped).upload_from_string(content, content_type=xlsx_mime)
    log(f"Uploaded {timestamped}")
    bucket.blob(latest).upload_from_string(content, content_type=xlsx_mime)
    log(f"Uploaded {latest}")

    log("Backup completed successfully")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
