#!/usr/bin/env python3
"""uguis UserPromptSubmit hook: replay the latest answer WITHOUT a Claude turn.

If the user's prompt is exactly a replay keyword ("re", "다시 읽어줘", ...), touch
the daemon's replay signal and BLOCK the prompt (exit 2) so it never reaches the
model — no chatter, and the daemon re-speaks the real previous answer. Any other
prompt passes through untouched (exit 0).
"""
import json
import os
import sys

REPLAY_WORDS = {
    "re", "replay",
    "다시", "다시 읽어줘", "다시읽어줘", "다시 읽어",
    "한번 더", "한번더", "방금 다시", "방금다시",
}


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return                       # unparseable -> pass through (exit 0)
    prompt = (payload.get("prompt") or "").strip()
    # exact whole-prompt match only, so normal messages ("re factor this") pass
    if prompt.lower() not in REPLAY_WORDS:
        return
    try:
        open(os.path.join(os.path.expanduser("~"), ".claude", ".tts-replay"), "w").close()
    except Exception:
        return                       # flag write failed -> let the prompt through
    sys.stderr.write("🔊 다시 재생")   # intentional notice (Claude Code shows this)
    sys.exit(2)                      # block only after the signal is set


if __name__ == "__main__":
    main()
