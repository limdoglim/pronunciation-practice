#!/usr/bin/env python3
import base64
import hashlib
import http.server
import json
import os
import struct
import sys
import urllib.error
import urllib.request

PORT = 18081
API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_cache")

ACCENT_PROMPTS = {
    "en-GB": "Read the following aloud in a natural British English accent, clearly and at a normal pace",
    "en-US": "Read the following aloud in a natural American English accent, clearly and at a normal pace",
}

KOKORO_VOICES = {
    "en-GB": {"lang": "b", "voice": "bf_emma"},
    "en-US": {"lang": "a", "voice": "af_heart"},
}
_kokoro_pipelines = {}


def pcm_to_wav(pcm_bytes, sample_rate=24000, channels=1, sample_width=2):
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm_bytes), b"WAVE",
        b"fmt ", 16, 1, channels, sample_rate, byte_rate, block_align, sample_width * 8,
        b"data", len(pcm_bytes),
    )
    return header + pcm_bytes


def gemini_tts(text, voice, accent):
    prompt = f"{ACCENT_PROMPTS.get(accent, ACCENT_PROMPTS['en-GB'])}: {text}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    req = urllib.request.Request(
        f"{GEMINI_URL}?key={API_KEY}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    return pcm_to_wav(base64.b64decode(b64))


def kokoro_tts(text, accent):
    from kokoro import KPipeline

    cfg = KOKORO_VOICES.get(accent, KOKORO_VOICES["en-GB"])
    pipeline = _kokoro_pipelines.get(cfg["lang"])
    if pipeline is None:
        pipeline = KPipeline(lang_code=cfg["lang"])
        _kokoro_pipelines[cfg["lang"]] = pipeline

    chunks = []
    for r in pipeline(text, voice=cfg["voice"], speed=0.92):
        chunks.append((r.audio.numpy() * 32767).astype("int16").tobytes())
    return pcm_to_wav(b"".join(chunks))


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/tts":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_error(400)
            return

        text = (body.get("text") or "").strip()
        voice = body.get("voice") or "Kore"
        accent = body.get("accent") or "en-GB"
        if not text:
            self.send_error(400)
            return

        cache_key = hashlib.sha256(f"{voice}|{accent}|{text}".encode()).hexdigest()
        cache_path = os.path.join(CACHE_DIR, cache_key + ".wav")
        if os.path.exists(cache_path):
            self._respond_wav(open(cache_path, "rb").read(), "hit")
            return

        wav = None
        engine = None
        gemini_error = None
        if API_KEY:
            try:
                wav = gemini_tts(text, voice, accent)
                engine = "gemini"
            except Exception as e:
                gemini_error = e
                print(f"[tts] Gemini failed, falling back to Kokoro: {e}", file=sys.stderr)

        if wav is None:
            try:
                wav = kokoro_tts(text, accent)
                engine = "kokoro"
            except Exception as e:
                print(f"[tts] Kokoro failed too: {e}", file=sys.stderr)
                self.send_response(502)
                self.end_headers()
                msg = f"gemini_error={gemini_error}; kokoro_error={e}"
                self.wfile.write(msg.encode())
                return

        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp_path = cache_path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(wav)
        os.replace(tmp_path, cache_path)
        self._respond_wav(wav, "miss", engine)

    def _respond_wav(self, wav, cache_status, engine=None):
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav)))
        self.send_header("X-TTS-Cache", cache_status)
        if engine:
            self.send_header("X-TTS-Engine", engine)
        self.end_headers()
        self.wfile.write(wav)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()
