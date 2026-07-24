#!/bin/bash
# Toggle / query the Claude Code TTS voice-output hook.
# Off-state is signalled by the presence of ~/.claude/.tts-off
# Usage: tts-toggle.sh [on|off|toggle|status]
FLAG="$HOME/.claude/.tts-off"
action="${1:-toggle}"

case "$action" in
  on)     rm -f "$FLAG" ;;
  off)    : > "$FLAG" ;;
  status) : ;;
  toggle|*)
    if [ -f "$FLAG" ]; then rm -f "$FLAG"; else : > "$FLAG"; fi ;;
esac

if [ -f "$FLAG" ]; then
  echo "TTS 음성 출력: OFF (꺼짐)"
else
  echo "TTS 음성 출력: ON (켜짐)"
fi
