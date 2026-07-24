---
name: uguis
description: (우구이스/うぐいす, 트리거 /uguis) 클로드 코드 응답을 macOS 음성으로 읽어주는 TTS 훅을 켜고 끄는 스킬. 새(꾀꼬리)처럼 답변을 소리내 읽어준다. 사용자가 "우구이스 꺼/켜", "uguis off/on", "tts 꺼", "tts 켜", "음성 꺼줘", "음성 출력 켜", "말하는거 그만", "읽어주기 꺼/켜", "voice off/on", "TTS 상태" 등 음성 출력 on/off/상태를 요청할 때 발동. Stop 훅(~/.claude/hooks/tts-speak.py)이 실제 음성을 재생하고, 이 스킬은 ~/.claude/.tts-off 플래그로 그 훅을 제어한다.
---

# TTS 음성 출력 제어 (uguis / うぐいす)

클로드 코드가 답변을 마칠 때(`Stop` 훅) 마지막 답변을 macOS `say`로 읽어주는 기능을 켜고 끈다.

## 동작 방식
- 실제 재생: `~/.claude/hooks/tts-speak.py` (Stop 훅에 등록됨)
- on/off 제어: `~/.claude/.tts-off` 플래그 파일 (있으면 OFF)
- 이 스킬은 아래 스크립트를 실행해서 그 플래그만 조작한다.

## 사용자 의도 → 실행 인자
사용자 요청을 아래로 매핑해 `bash ~/.claude/scripts/tts-toggle.sh <인자>` 를 실행한다:

| 사용자 말 | 인자 |
|---|---|
| "우구이스 꺼", "uguis off", "tts 꺼", "음성 꺼줘", "말하지마", "voice off" | `off` |
| "우구이스 켜", "uguis on", "tts 켜", "음성 켜줘", "읽어줘", "voice on" | `on` |
| "우구이스 토글", "반대로" | `toggle` |
| "우구이스 상태", "지금 켜져있어?" | `status` |
| 그냥 "/uguis" | `toggle` |

## 실행
```bash
bash ~/.claude/scripts/tts-toggle.sh off      # 끄기
bash ~/.claude/scripts/tts-toggle.sh on       # 켜기
bash ~/.claude/scripts/tts-toggle.sh status   # 현재 상태
```
스크립트가 출력하는 최종 상태(ON/OFF)를 사용자에게 그대로 알려준다.

## 참고
- 이 토글은 **즉시** 적용된다 (다음 답변부터 반영). 클로드 코드 재시작 불필요.
- 엔진: 기본 `edge`(Microsoft 뉴럴 TTS, 자연스러움, 인터넷 필요). 답변을 문장 청크로 나눠 **첫 청크부터 재생 시작 + 뒷청크는 재생 중 미리 합성**(스트리밍 유사). 오프라인/실패 시 macOS `say`로 자동 폴백.
- 커스터마이즈는 `settings.json`의 tts 훅 커맨드에 환경변수로:
  - `TTS_ENGINE`(기본 `edge`; `say`로 두면 오프라인 macOS 음성)
  - `TTS_EDGE_VOICE`(기본 `ko-KR-SunHiNeural`) · `TTS_EDGE_RATE`(기본 `+60%`) · `TTS_VOLUME`(afplay 게인, 기본 `0.6`, 1.0=기본)
  - `TTS_VOICE`/`TTS_RATE` = say 폴백용(기본 Yuna/210) · `TTS_MAX`(기본 1000자) · `TTS_CODE_MAX`(기본 3)
- 진짜 토큰 단위 실시간 스트리밍은 불가(Claude Code 훅에 스트리밍 트리거 없음; `Stop`이 가장 이른 신호). 청크 파이프라인이 최선의 근사.
- 코드 필터: 답변을 절 단위로 나눠 **코드 토큰이 `TTS_CODE_MAX`개 이상 뭉친 절은 통째로 음성에서 생략**하고, 프로즈에 메소드명 1~2개만 섞인 절은 인자 `(...)`만 벗겨 이름만 읽는다. 숫자를 낮추면 더 공격적으로 코드를 생략, 높이면 더 많이 읽는다. 코드블록·백틱·URL·이모지·마크다운은 항상 제거.
