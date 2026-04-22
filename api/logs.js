import { Storage } from "@google-cloud/storage";
export const config = { runtime: "nodejs18.x" };

export default async function handler(req, res) {
  const authHeader = req.headers["authorization"];
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  try {
    const creds = JSON.parse(process.env.GCS_KEY_JSON);
    const bucket = new Storage({ credentials: creds }).bucket(process.env.GCS_BUCKET_NAME);
    const [contents] = await bucket.file("logs/backup-log.json").download();
    const logs = JSON.parse(contents.toString());
    return res.status(200).json({ ok: true, logs });
  } catch (err) {
    return res.status(200).json({ ok: true, logs: [], message: "No logs yet: " + err.message });
  }
}