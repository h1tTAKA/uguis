#!/usr/bin/env python3
"""uguis UserPromptSubmit hook: voice commands WITHOUT a Claude turn.

If the user's prompt is exactly a command keyword, run the side effect and BLOCK
the prompt (exit 2) so it never reaches the model — no chatter:
  - replay ("re", "다시 읽어줘", ...) -> signal the daemon to re-speak the latest answer
  - stop   ("stop", "멈춰", "그만", ...) -> stop the current playback (shush)
Any other prompt passes through untouched (exit 0).
"""
import json
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
REPLAY_FLAG = os.path.join(HOME, ".claude", ".tts-replay")
TOGGLE = os.path.join(HOME, ".claude", "scripts", "tts-toggle.sh")

REPLAY_WORDS = {
    "re", "replay",
    "다시", "다시 읽어줘", "다시읽어줘", "다시 읽어",
    "한번 더", "한번더", "방금 다시", "방금다시",
}
STOP_WORDS = {
    "stop", "shush", "멈춰", "그만", "닥쳐", "조용", "그만해",
}


def _block(notice):
    sys.stderr.write(notice)          # Claude Code shows this next to the block
    sys.exit(2)                       # exit 2 = block: prompt not sent to model


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return                        # unparseable -> pass through (exit 0)
    # exact whole-prompt match only, so normal messages ("re factor this") pass
    prompt = (payload.get("prompt") or "").strip().lower()

    if prompt in REPLAY_WORDS:
        try:
            open(REPLAY_FLAG, "w").close()
        except Exception:
            return                    # signal failed -> let the prompt through
        _block("🔊 다시 재생")
    elif prompt in STOP_WORDS:
        try:
            subprocess.run(["bash", TOGGLE, "shush"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            return
        _block("🔇 멈춤")


if __name__ == "__main__":
    main()
