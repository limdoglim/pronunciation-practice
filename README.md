# 영국식 발음 연습 (Pronunciation Practice)

브라우저 TTS로 단어 발음/예문을 듣고 연습하는 정적 웹앱. 빌드 과정 없음 — `index.html` 하나로 동작.

## 실행

정적 파일이라 아무 웹서버로 서빙하면 됨. `file://`로 직접 열어도 대부분 기능은 동작하지만,
Ollama API 호출(예문 자동 생성)은 브라우저 보안 정책상 `http(s)://`로 서빙해야 안정적으로 동작함.

```bash
python3 -m http.server 8080
# http://<호스트>:8080/index.html 접속
```

다른 정적 서버(caddy, nginx, `npx serve` 등)도 무방함.

## 기능

- 단어 카드 탭 1회 = 단어 발음(TTS), 탭 2회 = 예문 읽기
- 세트 생성: 직접 입력 / Ollama API로 예문·이모지 자동 생성 / JSON 붙여넣기
- 세트는 브라우저 localStorage에 저장 — 기기·브라우저별로 별도 저장됨(동기화 없음)
- 설정에서 TTS 음성(억양·성별 추정 표시, 노벨티 음성 제외) 및 말하기 속도 선택
- "듣고 맞추기" 게임: 세트 전체 단어를 한 번씩, 단어/예문 난이도로 듣고 맞추기

## 설정 — Ollama API 키

설정(⚙️)에서 입력한 Ollama API 키는 **이 브라우저의 localStorage에만 저장**되고 코드에는 없음.
`https://ollama.com/api/chat`을 브라우저에서 직접 호출하는 구조라 CORS가 막힐 수 있음 — 그 경우
"JSON 붙여넣기" 탭으로 대체 가능.

## 배포 참고

- 정적 파일이라 GitHub Pages로도 바로 호스팅 가능(저장소 Settings → Pages).
- 개인 서버(Mac mini 등)에서 상시 서비스하려면 위 `http.server` 명령을 launchd/systemd 등으로
  등록해 자동 시작되게 하면 됨.
