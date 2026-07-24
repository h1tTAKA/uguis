# uguis 🐦

Make **Claude Code speak its answers out loud** in a natural voice, on macOS.

`uguis` (うぐいす / 꾀꼬리, the Japanese bush warbler) is a Claude Code `Stop`
hook: when Claude finishes a turn, it reads the last message aloud using
Microsoft Edge neural TTS — skipping code blocks, stripping markdown, and
streaming audio chunk-by-chunk so it starts talking almost immediately.

Default voice is Korean (`ko-KR-SunHiNeural`), but it works in any language
Edge TTS supports (English, Japanese, …) via one env var.

## Features

- **Natural neural voice** (Edge TTS), not the robotic macOS `say`.
- **Code-aware**: dense code clauses are dropped; a stray method name in prose
  is read by name only (args stripped). Code blocks, backticks, URLs, emoji,
  and markdown are always removed.
- **Whole turn, in order**: intermediate progress narration (the lines shown
  between tool calls) and **AskUserQuestion prompts + option labels** are voiced
  too — not just the final message. Progress is spoken faster
  (`TTS_EDGE_RATE_FAST`) since it's just status; the final answer and questions
  stay at normal speed.
- **Streaming-ish**: the answer is split into ~200-char chunks; the first chunk
  plays while later chunks synthesize in the background.
- **Non-blocking**: the hook returns instantly (~0.08s) and a detached worker
  handles playback, so your prompt is never held up.
- **Toggle on/off** any time — no restart, no settings edit.
- **Offline fallback**: if Edge/network fails, falls back to macOS `say`.

## Requirements

- macOS (uses `afplay` + `say`)
- `python3` (ships with macOS)
- [`edge-tts`](https://github.com/rany2/edge-tts) — installed automatically via
  `pipx` (needs internet at runtime). Without it, uses the offline `say` voice.

## Install

```bash
git clone https://github.com/h1tTAKA/uguis.git
cd uguis
bash install.sh
```

Then restart Claude Code (or open a new session). That's it.

The installer copies files into `~/.claude/`, installs `edge-tts` if missing,
and adds the `Stop` hook to `~/.claude/settings.json` (backed up to
`settings.json.bak-uguis`, existing hooks preserved). Respects
`$CLAUDE_CONFIG_DIR` if you set it.

## Usage

Toggle with the skill (just talk to Claude):

> "uguis off" · "우구이스 꺼줘" · "voice on" · "tts 상태"

Or directly:

```bash
bash ~/.claude/scripts/tts-toggle.sh off      # mute
bash ~/.claude/scripts/tts-toggle.sh on       # unmute
bash ~/.claude/scripts/tts-toggle.sh status
```

Instant mute without the script: `touch ~/.claude/.tts-off` (delete to unmute).

## Configuration

Set env vars on the hook command in `~/.claude/settings.json`
(`"command": "TTS_EDGE_VOICE=en-US-AvaMultilingualNeural python3 '.../tts-speak.py'"`):

| Var | Default | Meaning |
|---|---|---|
| `TTS_ENGINE` | `edge` | `say` = offline macOS voice |
| `TTS_EDGE_VOICE` | `ko-KR-SunHiNeural` | any Edge voice (e.g. `en-US-AvaMultilingualNeural`) |
| `TTS_EDGE_RATE` | `+60%` | speaking rate (final answer + questions) |
| `TTS_EDGE_RATE_FAST` | `+100%` | speaking rate for intermediate progress narration |
| `TTS_VOLUME` | `0.6` | afplay gain (1.0 = normal) |
| `TTS_MAX` | `1000` | max chars (truncates beyond) |
| `TTS_CODE_MAX` | `3` | clauses with ≥ this many code tokens are dropped |
| `TTS_VOICE` / `TTS_RATE` | `Yuna` / `210` | macOS `say` fallback voice/rate |

List Edge voices: `edge-tts --list-voices`.

## How it works

`Stop` is the earliest hook Claude Code fires, so audio starts after the turn
completes (no true token-level streaming — Claude Code has no streaming hook).
At `Stop` the current turn may not be flushed to the transcript yet, so the
worker records the last-spoken timestamp per transcript and polls (~6s max)
until a genuinely newer assistant turn appears — preventing both double-play
and replaying the previous turn.

A turn spans several assistant events (progress text, tool calls, a final
answer, an AskUserQuestion) interleaved with tool-result events. The worker
walks back from the end collecting assistant events until the real user prompt
(tool-result events are crossed, not treated as the boundary), then speaks each
segment in order at its rate.

## Uninstall

```bash
bash uninstall.sh
```

## License

MIT
