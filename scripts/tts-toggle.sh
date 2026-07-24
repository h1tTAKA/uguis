#!/bin/bash
# Toggle / query the uguis TTS voice output, and control the daemon.
#   on|off|toggle|status   — mute flag (~/.claude/.tts-off); the daemon respects it
#   start|stop|restart     — the launchd daemon (com.uguis.tts)
FLAG="$HOME/.claude/.tts-off"
PLIST="$HOME/Library/LaunchAgents/com.uguis.tts.plist"
action="${1:-toggle}"

daemon_alive() { pgrep -f "tts-daemon.py" >/dev/null 2>&1; }

case "$action" in
  on)     rm -f "$FLAG" ;;
  off)    : > "$FLAG" ; pkill -x afplay 2>/dev/null ;;
  toggle) if [ -f "$FLAG" ]; then rm -f "$FLAG"; else : > "$FLAG"; pkill -x afplay 2>/dev/null; fi ;;
  start)   launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; launchctl kickstart -k "gui/$(id -u)/com.uguis.tts" 2>/dev/null; echo "daemon: starting..."; exit 0 ;;
  stop)    launchctl bootout "gui/$(id -u)/com.uguis.tts" 2>/dev/null; pkill -f tts-daemon.py 2>/dev/null; pkill -x afplay 2>/dev/null; echo "daemon: stopped"; exit 0 ;;
  restart) launchctl kickstart -k "gui/$(id -u)/com.uguis.tts" 2>/dev/null; echo "daemon: restarted"; exit 0 ;;
  status)  : ;;
  *)       echo "usage: tts-toggle.sh {on|off|toggle|status|start|stop|restart}"; exit 1 ;;
esac

if [ -f "$FLAG" ]; then echo "TTS 음성 출력: OFF (꺼짐)"; else echo "TTS 음성 출력: ON (켜짐)"; fi
echo "daemon: $(daemon_alive && echo RUNNING || echo 'NOT running')"
