---
name: uguis
description: (우구이스/うぐいす, 트리거 /uguis) 클로드 코드 응답을 macOS 음성으로 읽어주는 TTS 데몬을 켜고 끄는 스킬. 새(꾀꼬리)처럼 답변을 소리내 읽어준다. 사용자가 "우구이스 꺼/켜", "uguis off/on", "tts 꺼", "tts 켜", "음성 꺼줘", "음성 출력 켜", "말하는거 그만", "읽어주기 꺼/켜", "voice off/on", "TTS 상태" 등 음성 출력 on/off/상태를 요청할 때 발동. 백그라운드 데몬(~/.claude/hooks/tts-daemon.py)이 실제 음성을 재생하고, 이 스킬은 ~/.claude/.tts-off 플래그로 그 데몬을 제어한다.
---

# TTS 음성 출력 제어 (uguis / うぐいす)

클로드 코드의 응답을 실시간으로 macOS 음성으로 읽어주는 백그라운드 데몬을 켜고 끈다.

## 동작 방식
- 실제 재생: `~/.claude/hooks/tts-daemon.py` (launchd 상주 데몬 `com.uguis.tts`). active transcript를 tail 하며 새 assistant 이벤트를 실시간 재생.
- on/off 제어: `~/.claude/.tts-off` 플래그 파일 (있으면 OFF — 데몬은 계속 살아있되 음소거).
- 이 스킬은 아래 스크립트로 그 플래그(및 데몬 start/stop)를 조작한다.

## 사용자 의도 → 실행 인자
사용자 요청을 아래로 매핑해 `bash ~/.claude/scripts/tts-toggle.sh <인자>` 를 실행한다:

| 사용자 말 | 인자 |
|---|---|
| "우구이스 꺼", "uguis off", "tts 꺼", "음성 꺼줘", "말하지마", "voice off" | `off` |
| "우구이스 켜", "uguis on", "tts 켜", "음성 켜줘", "읽어줘", "voice on" | `on` |
| "우구이스 토글", "반대로" | `toggle` |
| "멈춰", "그만", "지금 그만", "재생 멈춰", "stop", "shush", "그거 그만 읽어" | `shush` |
| "우구이스 상태", "지금 켜져있어?" | `status` |
| 그냥 "/uguis" | `toggle` |

- `shush` = **지금 나오는 재생만** 멈춤(음성 기능은 켜진 채, 다음 답변은 정상). `off`(음소거 지속)와 다름.

## 실행
```bash
bash ~/.claude/scripts/tts-toggle.sh off      # 끄기(음소거, 데몬은 유지)
bash ~/.claude/scripts/tts-toggle.sh on       # 켜기
bash ~/.claude/scripts/tts-toggle.sh status   # 상태(음소거 여부 + 데몬 생존)
bash ~/.claude/scripts/tts-toggle.sh stop     # 데몬 정지
bash ~/.claude/scripts/tts-toggle.sh start    # 데몬 기동
```
스크립트가 출력하는 최종 상태(ON/OFF + daemon RUNNING 여부)를 사용자에게 그대로 알려준다.

## 참고
- 이 토글은 **즉시** 적용된다 (다음 발언부터 반영). 클로드 코드 재시작 불필요.
- 엔진: 기본 `edge`(Microsoft 뉴럴 TTS, 자연스러움, 인터넷 필요). 데몬이 새 이벤트를 실시간으로 잡아 **첫 청크(작게)부터 재생 + 뒷청크 미리 합성**. 오프라인/실패 시 macOS `say`로 자동 폴백.
- 환경변수(launchd plist 또는 start 전 export):
  - `TTS_ENGINE`(기본 `edge`; `say`로 두면 오프라인 macOS 음성)
  - `TTS_EDGE_VOICE`(기본 `en-US-AvaMultilingualNeural` 다국어; 한국어만은 `ko-KR-SunHiNeural`) · `TTS_EDGE_RATE`(기본 `+70%`, 최종답변·질문) · `TTS_EDGE_RATE_FAST`(기본 `+70%`, 중간 진행상태) · `TTS_VOLUME`(기본 `0.6`)
  - `TTS_FIRST_CHUNK`(첫 청크 글자수, 기본 15 — 작을수록 첫 소리 빠름) · `TTS_JOIN`(절 조인, 기본 공백 `" "`; `", "`면 절 사이 정지 복원)
  - `TTS_DAEMON_POLL`(폴링 간격, 기본 0.1초) · `TTS_DAEMON_TIMEOUT`(최종 확정 대기, 기본 0.3초) · `TTS_DAEMON_FASTFWD`(밀림 점프 임계, 기본 10초)
  - `TTS_VOICE`/`TTS_RATE` = say 폴백용(기본 Yuna/210) · `TTS_MAX`(기본 1000자) · `TTS_CODE_MAX`(기본 3)
- 읽는 범위: 클로드 발언 전체(중간 진행상태 + 최종답변 + `AskUserQuestion` 질문·선택지 라벨)를 **실시간**으로 순서대로 읽는다. 진행상태가 밀리면 옛것은 건너뛰고 최신으로 따라잡는다(catch-up). 질문은 뜨는 즉시 읽는다.
- 코드 필터: 답변을 절 단위로 나눠 **코드 토큰이 `TTS_CODE_MAX`개 이상 뭉친 절은 통째로 음성에서 생략**하고, 프로즈에 메소드명 1~2개만 섞인 절은 인자 `(...)`만 벗겨 이름만 읽는다. 숫자를 낮추면 더 공격적으로 코드를 생략, 높이면 더 많이 읽는다. 코드블록·백틱·URL·이모지·마크다운은 항상 제거.
