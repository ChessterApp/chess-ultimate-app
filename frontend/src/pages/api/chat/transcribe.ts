import type { NextApiRequest, NextApiResponse } from "next";
import { getAuth } from "@clerk/nextjs/server";
import { execSync } from "child_process";
import { randomUUID } from "crypto";
import fs from "fs";
import path from "path";

export const config = {
  api: {
    bodyParser: {
      sizeLimit: "25mb",
    },
  },
};

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== "POST") {
    return res.status(405).json({ success: false, error: "Method not allowed" });
  }

  // Clerk auth
  const { userId } = getAuth(req);
  if (!userId) {
    return res.status(401).json({ success: false, error: "Unauthorized" });
  }

  const { audio } = req.body;
  if (!audio || typeof audio !== "string") {
    return res.status(400).json({ success: false, error: "Missing or invalid audio data" });
  }

  const uuid = randomUUID();
  const webmPath = `/tmp/chesster-voice-${uuid}.webm`;
  const wavPath = `/tmp/chesster-voice-${uuid}.wav`;

  try {
    // Decode base64 and write to file
    const audioBuffer = Buffer.from(audio, "base64");
    fs.writeFileSync(webmPath, audioBuffer);

    // Convert to WAV with ffmpeg
    execSync(
      `ffmpeg -i ${webmPath} -ar 16000 -ac 1 -f wav ${wavPath} -y`,
      { timeout: 30000 }
    );

    // Find the worker script
    let workerPath = path.join(process.cwd(), "src/pages/api/chat/transcribe-worker.py");
    if (!fs.existsSync(workerPath)) {
      workerPath = path.join(process.cwd(), "transcribe-worker.py");
    }
    if (!fs.existsSync(workerPath)) {
      return res.status(500).json({ success: false, error: "Transcription worker not found" });
    }

    // Run transcription
    const output = execSync(`python3 ${workerPath} ${wavPath}`, {
      timeout: 120000,
    }).toString();

    const result = JSON.parse(output);

    if (result.error) {
      return res.status(500).json({ success: false, error: result.error });
    }

    return res.status(200).json({
      success: true,
      text: result.text,
      language: result.language,
      duration: result.duration,
    });
  } catch (error: any) {
    console.error("Transcription error:", error);
    return res.status(500).json({
      success: false,
      error: error.message || "Transcription failed",
    });
  } finally {
    // Clean up temp files
    try {
      fs.unlinkSync(webmPath);
    } catch (_) {}
    try {
      fs.unlinkSync(wavPath);
    } catch (_) {}
  }
}
