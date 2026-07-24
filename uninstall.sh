#!/bin/bash
# uguis uninstaller — stops the daemon, removes files and any Stop hook entry.
set -euo pipefail
CLAUDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

# stop + remove the launchd daemon
PLIST="$HOME/Library/LaunchAgents/com.uguis.tts.plist"
launchctl unload "$PLIST" 2>/dev/null || true
pkill -f tts-daemon.py 2>/dev/null || true
rm -f "$PLIST"

rm -f "$CLAUDE/hooks/tts-speak.py" \
      "$CLAUDE/hooks/tts-daemon.py" \
      "$CLAUDE/scripts/tts-toggle.sh" \
      "$CLAUDE/.tts-off" "$CLAUDE/.tts-daemon.log"
rm -rf "$CLAUDE/skills/uguis"
rm -f "$CLAUDE"/.tts-last-* "$CLAUDE"/.tts-daemon-* 2>/dev/null || true

python3 - "$CLAUDE" <<'PY'
import json, os, sys
sp = os.path.join(sys.argv[1], "settings.json")
if not os.path.exists(sp): sys.exit(0)
cfg = json.load(open(sp))
stop = cfg.get("hooks", {}).get("Stop", [])
kept = [g for g in stop if "tts-speak.py" not in json.dumps(g)]
if kept: cfg["hooks"]["Stop"] = kept
else: cfg.get("hooks", {}).pop("Stop", None)
json.dump(cfg, open(sp, "w"), indent=2, ensure_ascii=False)
print("Removed Stop hook from", sp)
PY

echo "uguis uninstalled. (edge-tts left installed — 'pipx uninstall edge-tts' to remove.)"
