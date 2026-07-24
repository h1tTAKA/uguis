#!/usr/bin/env python3
"""uguis TTS daemon: watch the active Claude Code transcript and speak new
assistant events in real time.

Why a daemon instead of the Stop hook: an AskUserQuestion suspends the turn,
so Stop never fires while the question is on screen and no hook can voice it.
Tailing the transcript file lets us speak each assistant event (progress text,
final answer, question) the moment it is written — independent of any hook.

Reuses the synthesis/clean helpers from tts-speak.py so there is one code path
for voice, code-filtering, and chunking.
"""
import glob
import importlib.util
import json
import os
import subprocess
import tempfile
import time

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
OFF_FLAG = os.path.join(CLAUDE, ".tts-off")
PROJECTS = os.path.join(CLAUDE, "projects")
POLL = float(os.environ.get("TTS_DAEMON_POLL", "0.3"))   # seconds between checks

# reuse helpers/constants from the sibling hook script (hyphenated name -> importlib)
_spec = importlib.util.spec_from_file_location(
    "tts_speak", os.path.join(CLAUDE, "hooks", "tts-speak.py"))
tts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tts)

_DEVNULL = subprocess.DEVNULL


def off():
    return os.path.exists(OFF_FLAG)


def active_transcript():
    """Most recently modified session transcript = the one in use now."""
    files = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
    return max(files, key=os.path.getmtime) if files else None


def iter_events(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue          # partial/!json line: retried next poll
    except Exception:
        return


def _state_path(tp):
    import hashlib
    h = hashlib.sha1((tp or "").encode()).hexdigest()[:12]
    return os.path.join(CLAUDE, ".tts-daemon-" + h)


def read_state(tp):
    try:
        return open(_state_path(tp)).read().strip()
    except Exception:
        return ""


def write_state(tp, ts):
    try:
        with open(_state_path(tp), "w") as f:
            f.write(ts)
    except Exception:
        pass


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


def play_segment(text, rate, should_stop):
    """Clean + chunk + synthesize + play one segment; abort between chunks if
    should_stop() becomes true (tts turned off / superseded)."""
    speech = tts.clean(text)
    if not speech:
        return
    if len(speech) > tts.MAX_CHARS:
        speech = speech[:tts.MAX_CHARS].rsplit(" ", 1)[0] + " ..."
    edge = tts.find_edge()
    for ch in tts.chunk_text(speech):
        if should_stop():
            return
        mp3 = tempfile.mktemp(suffix=".mp3", prefix="ttsd_")
        if edge and tts.synth_chunk(edge, ch, mp3, rate):
            if should_stop():
                _rm(mp3)
                return
            subprocess.run(["afplay", "-v", tts.VOLUME, mp3])
            _rm(mp3)
        else:
            subprocess.run(["say", "-v", tts.VOICE, "-r", tts.RATE, ch],
                           stdout=_DEVNULL, stderr=_DEVNULL)


def speak_new_events(tp):
    """Speak assistant text events newer than last-spoken. Baselines a freshly
    seen transcript (no history flood)."""
    last = read_state(tp)
    events = [e for e in iter_events(tp) if e.get("type") == "assistant"]
    if not events:
        return
    if not last:
        # first sight of this transcript: mark current tail as already spoken
        write_state(tp, max(e.get("timestamp", "") for e in events))
        return
    for ev in events:
        ts = ev.get("timestamp", "")
        if not ts or ts <= last:
            continue
        if off():
            return
        content = ev.get("message", {}).get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                txt = b.get("text", "").strip()
                if txt:
                    play_segment(txt, tts.EDGE_RATE, off)
        write_state(tp, ts)


def main():
    seen_mtime, seen_tp = 0.0, None
    while True:
        if off():
            subprocess.run(["pkill", "-x", "afplay"], stderr=_DEVNULL)
            time.sleep(POLL)
            continue
        tp = active_transcript()
        if not tp:
            time.sleep(POLL)
            continue
        try:
            m = os.path.getmtime(tp)
        except OSError:
            time.sleep(POLL)
            continue
        if tp == seen_tp and m == seen_mtime:
            time.sleep(POLL)
            continue
        seen_tp, seen_mtime = tp, m
        speak_new_events(tp)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
