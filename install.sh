#!/bin/bash
# uguis installer — Claude Code TTS voice-output hook.
# Copies files into ~/.claude, installs edge-tts, and registers the Stop hook
# in settings.json (backing it up first, without clobbering existing hooks).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

echo "==> Installing uguis into $CLAUDE"

# 1. files
mkdir -p "$CLAUDE/hooks" "$CLAUDE/scripts" "$CLAUDE/skills/uguis"
cp "$SRC/hooks/tts-speak.py"        "$CLAUDE/hooks/"
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

# 3. register Stop hook in settings.json (merge, don't overwrite)
python3 - "$CLAUDE" <<'PY'
import json, os, sys
claude = sys.argv[1]
sp = os.path.join(claude, "settings.json")
cmd = "python3 '%s'" % os.path.join(claude, "hooks", "tts-speak.py")
entry = {"type": "command", "command": cmd, "timeout": 5}

cfg = {}
if os.path.exists(sp):
    with open(sp) as f:
        try: cfg = json.load(f)
        except Exception: cfg = {}
    open(sp + ".bak-uguis", "w").write(json.dumps(cfg, indent=2, ensure_ascii=False))

hooks = cfg.setdefault("hooks", {})
stop = hooks.setdefault("Stop", [])
# already installed?
if any(cmd in json.dumps(g) for g in stop):
    print("==> Stop hook already registered, skipping")
else:
    stop.append({"hooks": [entry]})
    with open(sp, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print("==> Registered Stop hook in", sp)
PY

echo
echo "Done. Restart Claude Code (or start a new session) so it picks up the hook + skill."
echo "Toggle:  bash $CLAUDE/scripts/tts-toggle.sh {on|off|status}   or say '/uguis'"
