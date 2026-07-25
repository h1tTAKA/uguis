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
import datetime
import glob
import importlib.util
import json
import os
import subprocess
import time

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
OFF_FLAG = os.path.join(CLAUDE, ".tts-off")
REPLAY_FLAG = os.path.join(CLAUDE, ".tts-replay")   # touch -> re-read latest
PROJECTS = os.path.join(CLAUDE, "projects")
POLL = float(os.environ.get("TTS_DAEMON_POLL", "0.1"))   # seconds between checks
# how long a still-streaming final text must be stable before we voice it at
# normal rate (can't tell "final" from "progress" until work stops following)
PENDING_TIMEOUT = float(os.environ.get("TTS_DAEMON_TIMEOUT", "0.2"))

_pending_since = {}   # transcript path -> (ts, wallclock first seen)
TAIL_LINES = int(os.environ.get("TTS_DAEMON_TAIL", "400"))   # parse only last N
# if one poll's backlog spans more than this many seconds of conversation, we're
# too far behind to play it all — jump to the newest segment (fast-forward).
FASTFWD_GAP = float(os.environ.get("TTS_DAEMON_FASTFWD", "10"))

# reuse helpers/constants from the sibling hook script (hyphenated name -> importlib)
_spec = importlib.util.spec_from_file_location(
    "tts_speak", os.path.join(CLAUDE, "hooks", "tts-speak.py"))
tts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tts)

_DEVNULL = subprocess.DEVNULL


def off():
    return os.path.exists(OFF_FLAG)


def active_transcript():
    """Most recently modified session transcript = the one in use now.
    Skip files that vanish between glob and stat (a session file can be removed
    mid-scan), so the daemon never crashes on the race."""
    best, best_m = None, -1.0
    for f in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        try:
            m = os.path.getmtime(f)
        except OSError:
            continue
        if m > best_m:
            best, best_m = f, m
    return best


def iter_events(path):
    # Only parse the tail: transcripts grow to thousands of lines over a
    # session, and a single turn spans at most a few dozen events. Parsing the
    # whole file every poll made first-audio latency grow with session length.
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return
    for line in lines[-TAIL_LINES:]:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue              # partial/!json line: retried next poll


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


def _has_more_work_after(all_events, i):
    """Does the turn continue after event i? (later assistant event, or a
    tool_result user event). A real user prompt = boundary = no more work."""
    for e in all_events[i + 1:]:
        t = e.get("type")
        if t == "assistant":
            return True
        if t == "user":
            return not tts._is_user_prompt(e)
    return False


def _event_segments(ev, all_events, i):
    """(speech, rate, kind) list for one assistant event. kind is 'progress'
    (mid-turn, fast), 'final' (turn's last text, normal), or 'question'
    (normal, voiced immediately). kind — not rate — drives catch-up, since the
    two rates may be configured equal."""
    content = ev.get("message", {}).get("content", [])
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    blocks = [b for b in content if isinstance(b, dict)]
    tail_continues = _has_more_work_after(all_events, i)
    segs = []
    for j, b in enumerate(blocks):
        more_in_event = any(bb.get("type") in ("text", "tool_use")
                            for bb in blocks[j + 1:])
        if b.get("type") == "text":
            txt = b.get("text", "").strip()
            if not txt:
                continue
            is_final = not more_in_event and not tail_continues
            segs.append((txt, tts.cfg_rate() if is_final else tts.cfg_rate_fast(),
                         "final" if is_final else "progress"))
        elif b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
            q = tts.question_to_text(b.get("input", {}))
            if q:
                segs.append((q, tts.cfg_rate(), "question"))
    return segs


def _stable_long_enough(tp, ts):
    """True once the newest event's ts has stayed newest for PENDING_TIMEOUT —
    i.e. streaming stopped, so it's a final answer, not mid-turn progress."""
    now = time.time()
    prev = _pending_since.get(tp)
    if not prev or prev[0] != ts:
        _pending_since[tp] = (ts, now)
        return False
    return (now - prev[1]) >= PENDING_TIMEOUT


def _parse_ts(ts):
    """ISO-8601 (…Z) -> naive UTC datetime. strptime works on py3.9 (no Z in
    fromisoformat there)."""
    try:
        return datetime.datetime.strptime(
            ts.replace("Z", "").split(".")[0], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def _seconds_between(a, b):
    da, db = _parse_ts(a), _parse_ts(b)
    return (db - da).total_seconds() if da and db else 0.0


def _speak_segments(segs, tp):
    """clean + MAX_CHARS cap + play (edge prefetch pipeline, say fallback).
    Shared by normal playback and replay."""
    cleaned, total = [], 0
    for txt, rate in segs:
        s = tts.clean(txt)
        if not s:
            continue
        if total + len(s) > tts.MAX_CHARS:
            s = s[:max(0, tts.MAX_CHARS - total - 4)]
            s = (s.rsplit(" ", 1)[0] if " " in s else s) + " ..."
        cleaned.append((s, rate))
        total += len(s)
        if total >= tts.MAX_CHARS:
            break
    if not cleaned or off():
        return
    # ts="~" (> any ISO-8601 ts lexically) so speak_edge.superseded() ignores the
    # legacy .tts-last state and only aborts on off(); passing "" made a stale
    # .tts-last mark every chunk superseded -> no edge playback -> say fallback.
    if not tts.speak_edge(cleaned, tp, "~"):             # edge pipeline
        for s, rate in cleaned:                          # offline say fallback
            if off():
                break
            subprocess.run(["say", "-v", tts.VOICE, "-r", tts.RATE, s],
                           stdout=_DEVNULL, stderr=_DEVNULL)


def replay_latest(tp):
    """Re-speak the most recent turn's final answer / question (skip progress).
    Independent of state, so it never disturbs normal dedup."""
    all_events = list(iter_events(tp))
    a_idx = [i for i, e in enumerate(all_events) if e.get("type") == "assistant"]
    for i in reversed(a_idx):
        finals = [(t, r) for (t, r, k) in _event_segments(all_events[i], all_events, i)
                  if k in ("final", "question")]
        if finals:
            _speak_segments(finals, tp)
            return


def speak_new_events(tp):
    """Speak assistant events newer than last-spoken, in order, classifying
    rate by lookahead. Baselines a freshly seen transcript (no history flood)."""
    last = read_state(tp)
    all_events = list(iter_events(tp))
    a_idx = [i for i, e in enumerate(all_events) if e.get("type") == "assistant"]
    if not a_idx:
        return
    if not last:
        write_state(tp, max(all_events[i].get("timestamp", "") for i in a_idx))
        return
    n = len(all_events)
    # collect this poll's new events (in order) as flat (text, rate) segments
    flat, first_ts, last_ts = [], None, None
    for i in a_idx:
        ev = all_events[i]
        ts = ev.get("timestamp", "")
        if not ts or ts <= last:
            continue
        blocks = ev.get("message", {}).get("content", [])
        has_q = isinstance(blocks, list) and any(
            isinstance(b, dict) and b.get("name") == "AskUserQuestion" for b in blocks)
        # newest line with no follower: still streaming -> stop here and wait
        # unless it's a question (nothing follows a question until answered).
        if i == n - 1 and not has_q and not _stable_long_enough(tp, ts):
            break
        flat.extend(_event_segments(ev, all_events, i))
        if first_ts is None:
            first_ts = ts
        last_ts = ts
    if not flat:
        return
    # global fast-forward: if this batch spans more than FASTFWD_GAP seconds of
    # conversation, playback can't keep up — skip the backlog and play only the
    # newest segment so we're speaking "now", not minutes ago. state jumps to
    # last_ts regardless, so the skipped events are never replayed.
    if len(flat) > 1 and _seconds_between(first_ts, last_ts) > FASTFWD_GAP:
        flat = flat[-1:]
    # catch-up: if we're behind, drop stale progress that has a later segment;
    # always keep final answers / questions. Keeps playback near real time
    # instead of trailing a backlog. (keyed on kind, not rate)
    plan = [(t, r) for k, (t, r, kind) in enumerate(flat)
            if not (kind == "progress" and k < len(flat) - 1)]
    _speak_segments(plan, tp)
    if last_ts:
        write_state(tp, last_ts)


def main():
    # No mtime gate: it conflicted with the PENDING_TIMEOUT wait — a final answer
    # that is the last write leaves mtime frozen, so the gate never re-invoked
    # speak_new_events and the pending line was never spoken. Tail parse is ~2ms,
    # so polling every tick is cheap.
    while True:
        # consume the one-shot replay flag first, even when muted, so a request
        # made while off is dropped (not fired later on unmute).
        replay_requested = os.path.exists(REPLAY_FLAG)
        if replay_requested:
            try:
                os.remove(REPLAY_FLAG)
            except OSError:
                pass
        if off():
            subprocess.run(["pkill", "-x", "afplay"], stderr=_DEVNULL)
            time.sleep(POLL)
            continue
        tp = active_transcript()
        if tp:
            if replay_requested:
                replay_latest(tp)
            speak_new_events(tp)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
