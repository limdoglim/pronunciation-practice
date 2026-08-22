# CLAUDE.md

이 저장소에서 작업할 때 참고할 아키텍처 노트.

## 구조

- `index.html` — 앱 전체 (HTML/CSS/JS 한 파일, 빌드 없음)
- `server.py` — 백엔드. 정적 파일 서빙 + `POST /tts`(TTS) + `POST /api/chat`(Ollama 중계) +
  `GET/POST /sets`, `DELETE /sets/<id>`(연습 세트 저장소)를 처리함. 클라이언트가 Ollama API 키를
  직접 보내지 않도록 AI 호출도 같은 백엔드로 통일함.
- `sets_data.json` — 연습 세트 저장소(`{id: set}` 딕셔너리). gitignore됨. 클라이언트는 localStorage를
  즉시반응용 캐시로 쓰면서 이 파일과 동기화(`updatedAt` 비교로 diff 후 push/delete) — 여러 계정이
  같은 배포에 로그인해도 세트를 공유해서 봄.
- `tts_cache/` — `(text, voice, accent)` 해시 기준 WAV 캐시. gitignore됨.
- `.venv/` — Kokoro(로컬 TTS 폴백)용 가상환경. gitignore됨. Python 3.11~3.12 권장
  (torch/spacy 계열이 최신 Python wheel을 늦게 지원함).

## TTS 흐름

1. `POST /tts` → 캐시 확인 (`tts_cache/<sha256(voice|accent|text)>.wav`) → 있으면 즉시 반환
2. 없으면 `GEMINI_API_KEY` 있을 때 Gemini 2.5 Flash TTS 시도
3. 실패(키 없음/429/네트워크 오류 등)하면 로컬 Kokoro-82M으로 폴백 (`kokoro_tts()`) — Kokoro 자체
   보이스팩에 Gemini 보이스명과 겹치는 이름이 있어(`KOKORO_VOICE_BY_NAME`) 폴백 중에도 보이스 선택이
   실제로 다르게 들리도록 매핑함 (안 겹치는 이름은 accent별 기본 보이스로 대체)
4. 결과를 캐시에 저장 후 응답 (`X-TTS-Engine` 헤더로 어느 엔진 썼는지 확인 가능)

## 지켜야 할 것

- **API 키는 절대 `index.html`(클라이언트)에 넣지 말 것.** public하게 서빙되는 정적 파일이라 그대로 노출됨.
  키가 필요한 호출은 항상 `server.py`를 거치게(같은 오리진 상대경로 `/tts`, `/api/...`) 할 것.
- `sentence` = 짧은 예문, `sentenceLong` = 긴 예문 필드명 유지 (기존 저장된 세트/JSON과 호환성 때문).
- 단어 카드 인터랙션은 버튼 3개(단어/짧은예문/긴예문) 개별 클릭 방식 — 탭 토글 방식으로 되돌리지 말 것 (연타 방지 요구사항 때문에 바뀜).
- AI 음성 재생 중에는 전역 버튼 비활성화(`body.tts-busy`) — 연타로 인한 API 폭주 방지 로직이니 제거 금지.
- 브라우저 내장 음성(`speechSynthesis`)은 완전히 제거됨 — 되살리지 말 것. 음성은 전부 `server.py`의
  `/tts`(Gemini → Kokoro 폴백)를 거침. 기본 억양은 미국식(`en-US`).
