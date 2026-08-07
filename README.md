# 영국식 발음 연습 (Pronunciation Practice)

단어/예문 TTS로 발음을 듣고 연습하는 웹앱. 빌드 과정 없음 — `index.html` 하나로 동작하지만,
AI 예문 생성과 AI 음성(TTS)을 쓰려면 백엔드(`server.py`)가 필요함.

## 실행

```bash
python3 server.py
# http://127.0.0.1:18081 접속
```

`server.py`는 정적 파일 서빙 + `/tts` 엔드포인트(TTS)를 처리함.
순수 정적 파일만 서빙하고 싶으면(`AI 음성`/`AI로 생성` 기능 없이 브라우저 내장 음성만 쓸 경우)
`python3 -m http.server`로도 충분함.

### 필요한 환경변수

| 변수 | 설명 |
|---|---|
| `GEMINI_API_KEY` | (선택) [Google AI Studio](https://aistudio.google.com)에서 발급. AI 음성(Gemini TTS)에 사용. 없거나 호출 실패 시 자동으로 로컬 Kokoro로 폴백됨 |

### AI 음성 — Gemini + 로컬 Kokoro 폴백

- 기본은 Gemini 2.5 Flash TTS (`GEMINI_API_KEY` 필요)
- 실패(할당량 초과 등) 시 로컬 [Kokoro-82M](https://github.com/hexgrad/kokoro)로 자동 폴백 — Apple Silicon에서 빠름
- 로컬 폴백을 쓰려면 별도 가상환경 세팅 필요:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install kokoro soundfile
  brew install espeak-ng   # macOS, 영어 g2p 폴백용
  ```
  (torch/spacy 계열 패키지가 최신 Python 버전 wheel을 아직 지원 안 할 수 있음 — 3.11~3.12 권장)
- 같은 `(문장, 보이스, 억양)` 조합은 `tts_cache/`에 WAV로 캐싱되어 재호출 안 함

### AI 예문 생성

`/api/chat`으로 [Ollama](https://ollama.com) 호환 API를 호출함 (기본 모델: `gemma4:31b-cloud`,
설정에서 변경 가능). 로컬 Ollama 인스턴스로 프록시하려면 별도 리버스 프록시 설정이 필요함
(`server.py`는 `/tts`만 처리하고 `/api/*`는 처리하지 않음 — nginx/caddy/Cloudflare Tunnel 등으로
`/api/*` → 로컬 Ollama(`127.0.0.1:11434`)로 라우팅해야 함). 안 쓰면 "JSON 붙여넣기" 탭으로 수동 입력 가능.

## 기능

- 단어 카드: **🔊 단어 / 📝 짧은 예문 / 📖 긴 예문** 버튼 각각 독립 재생 (AI 음성 재생 중엔 연타 방지를 위해 버튼 일시 비활성화)
- 세트 생성: 직접 입력 / AI로 예문(짧은 것 + 긴 것)·이모지 자동 생성 / JSON 붙여넣기
- 세트는 브라우저 localStorage에 저장 — 기기·브라우저별로 별도 저장됨(동기화 없음)
- 설정에서 발음 재생 방식(브라우저 음성 / AI 음성), TTS 음성(억양·성별 추정 표시, 노벨티 음성 제외), 말하기 속도 선택
- "듣고 맞추기" 게임: 세트 전체 단어를 한 번씩, 단어/예문 난이도로 듣고 맞추기

## JSON 형식

```json
[{"word": "beautiful", "sentence": "It looks beautiful.", "sentenceLong": "The sunset over the hills looked absolutely beautiful this evening.", "emoji": "🌅"}]
```

## 배포 참고

- `index.html`만 쓸 거면 GitHub Pages로도 호스팅 가능(저장소 Settings → Pages) — 단, AI 기능은 빠짐
- AI 기능까지 쓰려면 `server.py`를 상시 프로세스로 띄워야 함(launchd/systemd 등)
- API 키는 항상 서버 환경변수로만 주입할 것 — 클라이언트(`index.html`)에 절대 하드코딩하지 말 것 (public 서빙되는 파일이라 그대로 노출됨)
