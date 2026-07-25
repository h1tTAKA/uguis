#!/bin/bash
# Toggle / query the uguis TTS voice output, and control the daemon.
#   on|off|toggle|status   — mute flag (~/.claude/.tts-off); the daemon respects it
#   shush                  — stop the CURRENT playback only, keep TTS on
#   start|stop|restart     — the launchd daemon (com.uguis.tts)
FLAG="$HOME/.claude/.tts-off"
PLIST="$HOME/Library/LaunchAgents/com.uguis.tts.plist"
CONFIG="$HOME/.claude/.tts-config"
action="${1:-toggle}"

daemon_alive() { pgrep -f "tts-daemon.py" >/dev/null 2>&1; }
setcfg() {  # replace-or-append KEY=VALUE in the live config file
  touch "$CONFIG"; grep -v "^$1=" "$CONFIG" 2>/dev/null > "$CONFIG.tmp"
  echo "$1=$2" >> "$CONFIG.tmp"; mv "$CONFIG.tmp" "$CONFIG"
}

case "$action" in
  on)     rm -f "$FLAG" ;;
  off)    : > "$FLAG" ; pkill -x afplay 2>/dev/null ;;
  toggle) if [ -f "$FLAG" ]; then rm -f "$FLAG"; else : > "$FLAG"; pkill -x afplay 2>/dev/null; fi ;;
  shush)  # stop current playback without muting future: briefly set the mute
          # flag (the only signal speak_edge checks) so the running batch aborts,
          # then auto-restore after 1s. Don't restore if it was already off.
          had_off=0; [ -f "$FLAG" ] && had_off=1
          : > "$FLAG"; pkill -x afplay 2>/dev/null; pkill -f edge-tts 2>/dev/null
          [ "$had_off" = 0 ] && ( sleep 1; rm -f "$FLAG" ) >/dev/null 2>&1 &
          echo "현재 재생 멈춤 (음성 기능은 유지)"; exit 0 ;;
  start)   launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; launchctl kickstart -k "gui/$(id -u)/com.uguis.tts" 2>/dev/null; echo "daemon: starting..."; exit 0 ;;
  stop)    launchctl bootout "gui/$(id -u)/com.uguis.tts" 2>/dev/null; pkill -f tts-daemon.py 2>/dev/null; pkill -x afplay 2>/dev/null; echo "daemon: stopped"; exit 0 ;;
  restart) launchctl kickstart -k "gui/$(id -u)/com.uguis.tts" 2>/dev/null; echo "daemon: restarted"; exit 0 ;;
  rate)    n="${2//[!0-9]/}"; [ -z "$n" ] && { echo "usage: rate <숫자>  예: rate 60"; exit 1; }
           setcfg rate "+${n}%"; setcfg rate_fast "+${n}%"; echo "말속도: +${n}% (다음 발화부터)"; exit 0 ;;
  pause)   n="${2//[!0-9]/}"; n="${n:-0}"; setcfg pause "$n"
           echo "쉼 레벨: $n (0=정지없음 1=약간 2=많이)"; exit 0 ;;
  status)  : ;;
  *)       echo "usage: tts-toggle.sh {on|off|toggle|status|shush|rate <n>|pause <0-2>|start|stop|restart}"; exit 1 ;;
esac

if [ -f "$FLAG" ]; then echo "TTS 음성 출력: OFF (꺼짐)"; else echo "TTS 음성 출력: ON (켜짐)"; fi
echo "daemon: $(daemon_alive && echo RUNNING || echo 'NOT running')"
