#!/bin/bash
# uguis installer — Claude Code TTS voice output via a background daemon.
# Copies files into ~/.claude, installs edge-tts, removes the old Stop hook,
# and registers a launchd agent that tails the active transcript.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

echo "==> Installing uguis into $CLAUDE"

# 1. files
mkdir -p "$CLAUDE/hooks" "$CLAUDE/scripts" "$CLAUDE/skills/uguis"
cp "$SRC/hooks/tts-speak.py"        "$CLAUDE/hooks/"   # shared synth helpers
cp "$SRC/hooks/tts-daemon.py"       "$CLAUDE/hooks/"
cp "$SRC/scripts/tts-toggle.sh"     "$CLAUDE/scripts/"
cp "$SRC/skills/uguis/SKILL.md"     "$CLAUDE/skills/uguis/"
chmod +x "$CLAUDE/scripts/tts-toggle.sh"

# 2. edge-tts (neural voice). Skip if already present; fall back to macOS `say`.
if ! command -v edge-tts >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/edge-tts" ]; then
  if command -v pipx >/dev/null 2>&1; then
    echo "==> pipx install edge-tts"
    pipx install edge-tts || echo "!! edge-tts install failed — will use macOS 'say' fallback"
  else
    echo "!! pipx not found. Install it (brew install pipx) for neural voice,"
    echo "   or set TTS_ENGINE=say to use the offline macOS voice."
  fi
fi

# 3. remove any old Stop hook (the daemon replaces it; avoids double-voicing)
python3 - "$CLAUDE" <<'PY'
import json, os, sys
sp = os.path.join(sys.argv[1], "settings.json")
if os.path.exists(sp):
    try: cfg = json.load(open(sp))
    except Exception: cfg = {}
    stop = cfg.get("hooks", {}).get("Stop", [])
    kept = [g for g in stop if "tts-speak.py" not in json.dumps(g)]
    if len(kept) != len(stop):
        open(sp + ".bak-uguis", "w").write(json.dumps(cfg, indent=2, ensure_ascii=False))
        if kept: cfg["hooks"]["Stop"] = kept
        else: cfg.get("hooks", {}).pop("Stop", None)
        json.dump(cfg, open(sp, "w"), indent=2, ensure_ascii=False)
        print("==> Removed old Stop hook from", sp)
PY

# 4. launchd agent: fill the plist template with real paths, load it
PY_BIN="$(command -v python3)"
PLIST="$HOME/Library/LaunchAgents/com.uguis.tts.plist"
mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s#__PYTHON__#$PY_BIN#" \
    -e "s#__DAEMON__#$CLAUDE/hooks/tts-daemon.py#" \
    -e "s#__HOME__#$HOME#" \
    "$SRC/com.uguis.tts.plist" > "$PLIST"
# bootstrap into the GUI domain so afplay reaches the user's audio session
# (plain `launchctl load` can land in a domain with no audio).
GUI="gui/$(id -u)"
launchctl bootout "$GUI/com.uguis.tts" 2>/dev/null || true
launchctl bootstrap "$GUI" "$PLIST"
launchctl kickstart -k "$GUI/com.uguis.tts" 2>/dev/null || true
echo "==> Bootstrapped launchd agent com.uguis.tts into $GUI"

echo
echo "Done. The daemon is running now — no Claude Code restart needed."
echo "Toggle:  bash $CLAUDE/scripts/tts-toggle.sh {on|off|status|start|stop}   or say '/uguis'"
