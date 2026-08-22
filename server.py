#!/usr/bin/env python3
import base64
import hashlib
import http.server
import json
import os
import struct
import sys
import threading
import urllib.error
import urllib.request

PORT = 18081
API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_cache")
SETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sets_data.json")
_sets_lock = threading.Lock()

ACCENT_PROMPTS = {
    "en-GB": "Read the following aloud in a natural British English accent, clearly and at a normal pace",
    "en-US": "Read the following aloud in a natural American English accent, clearly and at a normal pace",
}

KOKORO_VOICES = {
    "en-GB": {"lang": "b", "voice": "bf_emma"},
    "en-US": {"lang": "a", "voice": "af_heart"},
}
# Kokoro's own voicepack happens to share several names with the Gemini
# voice list this app exposes in Settings — map to those so a voice choice
# still audibly matters when Gemini is unavailable and Kokoro is used
# instead, rather than every selection sounding identical.
KOKORO_VOICE_BY_NAME = {
    "Kore":   {"en-US": "af_kore",    "en-GB": "bf_isabella"},
    "Puck":   {"en-US": "am_puck",    "en-GB": "bm_george"},
    "Charon": {"en-US": "am_michael", "en-GB": "bm_lewis"},
    "Fenrir": {"en-US": "am_fenrir",  "en-GB": "bm_daniel"},
    "Aoede":  {"en-US": "af_aoede",   "en-GB": "bf_emma"},
    "Leda":   {"en-US": "af_nicole",  "en-GB": "bf_alice"},
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
    style = ACCENT_PROMPTS.get(accent, ACCENT_PROMPTS["en-US"])
    if " " not in text.strip():
        # A single word with no sentence context is where LLM-driven TTS is
        # most prone to misreading silent letters (e.g. the "k" in "know")
        # — nudge it toward the standard dictionary pronunciation.
        prompt = f"{style}, using its normal standard English pronunciation (respect silent letters): {text}"
    else:
        prompt = f"{style}: {text}"
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


def kokoro_tts(text, voice, accent):
    from kokoro import KPipeline

    default = KOKORO_VOICES.get(accent, KOKORO_VOICES["en-US"])
    lang = default["lang"]
    voice_name = KOKORO_VOICE_BY_NAME.get(voice, {}).get(accent, default["voice"])
    pipeline = _kokoro_pipelines.get(lang)
    if pipeline is None:
        pipeline = KPipeline(lang_code=lang)
        _kokoro_pipelines[lang] = pipeline

    chunks = []
    for r in pipeline(text, voice=voice_name, speed=0.92):
        chunks.append((r.audio.numpy() * 32767).astype("int16").tobytes())
    return pcm_to_wav(b"".join(chunks))


def load_sets_file():
    if not os.path.exists(SETS_FILE):
        return {}
    with open(SETS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sets_file(data):
    tmp_path = SETS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp_path, SETS_FILE)


def ollama_chat(body):
    headers = {"Content-Type": "application/json"}
    if OLLAMA_API_KEY:
        headers["Authorization"] = "Bearer " + OLLAMA_API_KEY
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.headers.get("Content-Type", "application/json"), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "application/json"), e.read()


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/sets":
            with _sets_lock:
                data = load_sets_file()
            self._respond_json(list(data.values()))
            return
        super().do_GET()

    def do_DELETE(self):
        if self.path.startswith("/sets/"):
            set_id = self.path[len("/sets/"):]
            with _sets_lock:
                data = load_sets_file()
                data.pop(set_id, None)
                save_sets_file(data)
            self.send_response(204)
            self.end_headers()
            return
        self.send_error(404)

    def do_POST(self):
        if self.path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self.send_error(400)
                return
            status, content_type, response_body = ollama_chat(body)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
            return

        if self.path == "/sets":
            length = int(self.headers.get("Content-Length", 0))
            try:
                item = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self.send_error(400)
                return
            if not item.get("id"):
                self.send_error(400)
                return
            with _sets_lock:
                data = load_sets_file()
                data[item["id"]] = item
                save_sets_file(data)
            self._respond_json(item)
            return

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
        accent = body.get("accent") or "en-US"
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
                wav = kokoro_tts(text, voice, accent)
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

    def _respond_json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()
