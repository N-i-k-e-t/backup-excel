import { google } from "googleapis";
import { Storage } from "@google-cloud/storage";

export const config = { runtime: "nodejs18.x" };

function log(level, msg, data = {}) {
  const entry = { ts: new Date().toISOString(), level, msg, ...data };
  console.log(JSON.stringify(entry));
  return entry;
}

export default async function handler(req, res) {
  const startTime = Date.now();
  const logs = [];
  function addLog(level, msg, data = {}) {
    const entry = log(level, msg, data);
    logs.push(entry);
    return entry;
  }

  const authHeader = req.headers["authorization"];
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    addLog("ERROR", "Unauthorized request");
    return res.status(401).json({ ok: false, error: "Unauthorized", logs });
  }

  addLog("INFO", "Backup job started");

  try {
    const required = ["GOOGLE_SERVICE_ACCOUNT_JSON", "SOURCE_FILE_ID", "GCS_BUCKET_NAME", "GCS_KEY_JSON", "CRON_SECRET"];
    for (const key of required) {
      if (!process.env[key]) throw new Error(`Missing env var: ${key}`);
    }
    addLog("INFO", "Env vars validated");

    let driveCredentials, gcsCredentials;
    try {
      driveCredentials = JSON.parse(process.env.GOOGLE_SERVICE_ACCOUNT_JSON);
      gcsCredentials = JSON.parse(process.env.GCS_KEY_JSON);
    } catch {
      throw new Error("Invalid JSON in service account env vars.");
    }
    addLog("INFO", "Credentials parsed", { account: driveCredentials.client_email });

    const auth = new google.auth.GoogleAuth({
      credentials: driveCredentials,
      scopes: ["https://www.googleapis.com/auth/drive.readonly"],
    });
    const drive = google.drive({ version: "v3", auth });
    addLog("INFO", "Google Drive auth ready");

    const meta = await drive.files.get({
      fileId: process.env.SOURCE_FILE_ID,
      fields: "name,modifiedTime,size",
    });
    const fileName = meta.data.name;
    const modifiedTime = meta.data.modifiedTime;
    addLog("INFO", "Source file found", { name: fileName, modified: modifiedTime });

    addLog("INFO", "Downloading from Google Drive...");
    const response = await drive.files.get(
      { fileId: process.env.SOURCE_FILE_ID, alt: "media" },
      { responseType: "arraybuffer" }
    );
    const fileBuffer = Buffer.from(response.data);
    addLog("INFO", "Downloaded", { bytes: fileBuffer.length });

    const storage = new Storage({ credentials: gcsCredentials });
    const bucket = storage.bucket(process.env.GCS_BUCKET_NAME);

    const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const backupFileName = `backups/AFF-Evals-${timestamp}.xlsx`;
    const latestFileName = `backups/AFF-Evals-LATEST.xlsx`;
    const meta2 = {
      contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      metadata: { source_modified: modifiedTime, source_name: fileName },
    };

    addLog("INFO", "Uploading to GCS...", { dest: backupFileName });
    await bucket.file(backupFileName).save(fileBuffer, { metadata: meta2 });
    await bucket.file(latestFileName).save(fileBuffer, {
      metadata: { ...meta2, metadata: { ...meta2.metadata, backed_up_at: new Date().toISOString() } }
    });
    addLog("INFO", "Upload complete");

    const logEntry = {
      run_at: new Date().toISOString(), status: "SUCCESS",
      file_name: fileName, source_modified: modifiedTime,
      bytes_backed_up: fileBuffer.length, gcs_path: backupFileName,
      duration_ms: Date.now() - startTime,
    };
    try {
      const logFile = bucket.file("logs/backup-log.json");
      let existing = [];
      try { const [c] = await logFile.download(); existing = JSON.parse(c.toString()); } catch {}
      existing.unshift(logEntry);
      if (existing.length > 500) existing = existing.slice(0, 500);
      await logFile.save(JSON.stringify(existing, null, 2), { contentType: "application/json" });
      addLog("INFO", "Run log updated in GCS");
    } catch (e) { addLog("WARN", "Could not update log: " + e.message); }

    addLog("INFO", "BACKUP COMPLETE", { duration_ms: Date.now() - startTime });
    return res.status(200).json({
      ok: true, file: backupFileName, latest: latestFileName,
      source: fileName, source_modified: modifiedTime,
      bytes: fileBuffer.length, duration_ms: Date.now() - startTime, logs,
    });
  } catch (err) {
    addLog("ERROR", "BACKUP FAILED: " + err.message, { duration_ms: Date.now() - startTime });
    try {
      const gcsCredentials = JSON.parse(process.env.GCS_KEY_JSON || "{}");
      const bucket = new Storage({ credentials: gcsCredentials }).bucket(process.env.GCS_BUCKET_NAME);
      const logFile = bucket.file("logs/backup-log.json");
      let existing = [];
      try { const [c] = await logFile.download(); existing = JSON.parse(c.toString()); } catch {}
      existing.unshift({ run_at: new Date().toISOString(), status: "FAILED", error: err.message, duration_ms: Date.now() - startTime });
      if (existing.length > 500) existing = existing.slice(0, 500);
      await logFile.save(JSON.stringify(existing, null, 2), { contentType: "application/json" });
    } catch {}
    return res.status(500).json({ ok: false, error: err.message, logs });
  }
}