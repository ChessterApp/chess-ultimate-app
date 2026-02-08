#!/usr/bin/env python3
"""Transcribe audio file using faster-whisper."""
import sys, json

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No audio file path provided"}))
        sys.exit(1)
    audio_path = sys.argv[1]
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path)
        text = " ".join(segment.text for segment in segments).strip()
        print(json.dumps({"text": text, "language": info.language, "language_probability": round(info.language_probability, 3), "duration": round(info.duration, 2)}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
