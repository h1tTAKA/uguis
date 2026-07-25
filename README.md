# uguis 🐦

Make **Claude Code speak its answers out loud** in a natural voice, on macOS.

`uguis` (うぐいす / 꾀꼬리, the Japanese bush warbler) is a small background
daemon that tails Claude Code's active transcript and reads new assistant
output aloud in real time using Microsoft Edge neural TTS — skipping code
blocks, stripping markdown, and voicing each event the moment it's written.

Default voice is Korean (`ko-KR-SunHiNeural`), but it works in any language
Edge TTS supports (English, Japanese, …) via one env var.

## Features

- **Natural neural voice** (Edge TTS), not the robotic macOS `say`.
- **Real-time, event by event**: a background daemon tails the transcript and
  speaks each assistant event as it's written — progress narration, the final
  answer, and **AskUserQuestion prompts + option labels** (voiced the instant
  the question appears, which no Stop hook can do).
- **Code-aware**: dense code clauses are dropped; a stray method name in prose
  is read by name only. Code blocks, backticks, URLs, emoji, markdown removed.
- **Stays in sync**: when it falls behind (lots of fast tool calls), stale
  progress is skipped so playback jumps to the latest — never a long backlog.
- **Fast first audio**: the first chunk is kept tiny (`TTS_FIRST_CHUNK`) and
  later chunks synthesize while the current one plays (no gaps).
- **Toggle on/off** any time — no restart. Daemon `start/stop` via one script.
- **Offline fallback**: if Edge/network fails, falls back to macOS `say`.

## Requirements

- macOS (uses `afplay` + `say`, `launchd`)
- `python3` (ships with macOS)
- [`edge-tts`](https://github.com/rany2/edge-tts) — installed automatically via
  `pipx` (needs internet at runtime). Without it, uses the offline `say` voice.

## Install

```bash
git clone https://github.com/h1tTAKA/uguis.git
cd uguis
bash install.sh
```

The daemon starts immediately — no Claude Code restart needed. The installer
copies files into `~/.claude/`, installs `edge-tts` if missing, removes any old
Stop hook, and registers a `launchd` agent (`com.uguis.tts`) that runs at login
and restarts if it dies. Respects `$CLAUDE_CONFIG_DIR`.

## Usage

Toggle with the skill (just talk to Claude):

> "uguis off" · "우구이스 꺼줘" · "voice on" · "tts 상태"

Or directly:

```bash
bash ~/.claude/scripts/tts-toggle.sh off       # mute (daemon keeps running)
bash ~/.claude/scripts/tts-toggle.sh on        # unmute
bash ~/.claude/scripts/tts-toggle.sh shush     # stop the CURRENT playback only
bash ~/.claude/scripts/tts-toggle.sh rate 55   # speaking rate +55% (live, no restart)
bash ~/.claude/scripts/tts-toggle.sh pause 1   # pause at ,.:; — 0 none / 1 some / 2 more
bash ~/.claude/scripts/tts-toggle.sh status    # mute state + daemon alive?
bash ~/.claude/scripts/tts-toggle.sh stop      # stop the daemon
bash ~/.claude/scripts/tts-toggle.sh start     # start it
```

Instant mute without the script: `touch ~/.claude/.tts-off` (delete to unmute).

`rate`/`pause` write to `~/.claude/.tts-config` (`KEY=VALUE`), which the daemon
re-reads live — no restart. Say "속도 50" / "쉼 1" and the uguis skill runs them.

## Configuration

Env vars (set them on the `launchd` plist, or export before `start`):

| Var | Default | Meaning |
|---|---|---|
| `TTS_ENGINE` | `edge` | `say` = offline macOS voice |
| `TTS_EDGE_VOICE` | `en-US-AvaMultilingualNeural` | any Edge voice (Korean: `ko-KR-SunHiNeural`) |
| `TTS_EDGE_RATE` | `+70%` | speaking rate (final answer + questions) |
| `TTS_EDGE_RATE_FAST` | `+70%` | speaking rate for intermediate progress |
| `TTS_FIRST_CHUNK` | `15` | first-chunk size in chars (smaller = faster first audio) |
| `TTS_JOIN` | `" "` | clause joiner; `", "` restores pauses between clauses |
| `TTS_DAEMON_POLL` | `0.1` | transcript poll interval (s) |
| `TTS_DAEMON_TIMEOUT` | `0.3` | wait (s) before a still-streaming line is treated as final |
| `TTS_DAEMON_FASTFWD` | `10` | if a batch spans more than this many seconds, jump to the newest segment |
| `TTS_VOLUME` | `0.6` | afplay gain (1.0 = normal) |
| `TTS_MAX` | `1000` | max chars per batch (truncates beyond) |
| `TTS_CODE_MAX` | `3` | clauses with ≥ this many code tokens are dropped |
| `TTS_VOICE` / `TTS_RATE` | `Yuna` / `210` | macOS `say` fallback voice/rate |

List Edge voices: `edge-tts --list-voices`.

## How it works

Claude Code has no hook that fires while an `AskUserQuestion` is on screen (the
turn is suspended waiting for the answer), and the `Stop` hook only fires at
turn end — so a hook can't voice questions and tends to dump a whole exchange
at once. Instead, `tts-daemon.py` tails the most-recently-modified transcript
under `~/.claude/projects` and, each poll, speaks assistant events newer than
the last one spoken:

- **Rate by lookahead**: text followed by more work = progress (fast); text
  ending the turn = final; `AskUserQuestion` = voiced immediately.
- **Catch-up**: within a batch, stale progress that has a later segment is
  dropped; and if a batch spans more than `TTS_DAEMON_FASTFWD` seconds, only the
  newest segment is spoken (global fast-forward) — playback never trails a
  minutes-long backlog. Playback is not auto-cut on a new prompt; say "멈춰"
  (`shush`) to stop the current playback yourself.
- **Baseline on start**: a freshly seen transcript is marked as already spoken,
  so the daemon never replays history.

Synthesis/clean/chunk helpers are reused from `tts-speak.py` (kept as a library;
the Stop hook is no longer registered).

## Uninstall

```bash
bash uninstall.sh   # stops + removes the daemon, files, and any Stop hook
```

## License

MIT
