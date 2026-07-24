#!/usr/bin/env python3
"""Claude Code Stop hook: speak the final assistant message via macOS `say`.

Fix for off-by-one: at Stop time the current turn's message may not be flushed
to the transcript yet, so we track the last-spoken timestamp in a state file
and poll (in a detached worker) until a genuinely newer assistant text turn
appears, then speak it. The hook itself returns immediately so it never blocks
the prompt.

Toggle off without editing settings:  touch ~/.claude/.tts-off
Config via env vars:
  TTS_VOICE (default: Yuna)   TTS_RATE (wpm, default: 210)   TTS_MAX (chars, default: 1000)
"""
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import sys
import time

HOME = os.path.expanduser("~")
OFF_FLAG = os.path.join(HOME, ".claude", ".tts-off")
# engine: "edge" (Microsoft neural, natural, needs net) or "say" (macOS offline)
ENGINE = os.environ.get("TTS_ENGINE", "edge")
EDGE_VOICE = os.environ.get("TTS_EDGE_VOICE", "ko-KR-SunHiNeural")
EDGE_RATE = os.environ.get("TTS_EDGE_RATE", "+60%")
VOLUME = os.environ.get("TTS_VOLUME", "0.6")   # afplay gain: 1.0 = normal
VOICE = os.environ.get("TTS_VOICE", "Yuna")   # say fallback voice
RATE = os.environ.get("TTS_RATE", "210")       # say fallback rate (wpm)
MAX_CHARS = int(os.environ.get("TTS_MAX", "1000"))
# clauses with >= this many code tokens are dropped from speech entirely
CODE_MAX = int(os.environ.get("TTS_CODE_MAX", "3"))
POLL_TRIES = 40      # 40 * 0.15s = ~6s max wait for flush
POLL_SLEEP = 0.15


def off():
    return os.path.exists(OFF_FLAG)


def _is_user_prompt(ev):
    """A real user turn-start, not a mid-turn tool_result user event."""
    content = ev.get("message", {}).get("content", [])
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        # tool_result blocks = mid-turn (Claude called a tool); anything else
        # (text/image typed by the user) = an actual prompt = turn boundary.
        return not any(isinstance(b, dict) and b.get("type") == "tool_result"
                       for b in content)
    return True


def collect_turn(path):
    """Return (segments, turn_max_ts) for the newest assistant turn.

    One turn spans multiple assistant events (progress text, tool calls,
    a final answer, an AskUserQuestion) interleaved with tool_result user
    events. We walk back from the end collecting assistant events until a
    genuine user prompt marks the turn start, then emit their speakable
    content in chronological order.

    segments = list of (speech_text, rate) in the order they should be spoken.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return [], ""
    turn = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        t = ev.get("type")
        if t == "assistant":
            turn.append(ev)
        elif t == "user":
            if _is_user_prompt(ev):
                break          # reached the start of this turn
            continue           # tool_result: still inside the turn
        # other event types: ignore
    turn.reverse()             # chronological
    segments, max_ts = [], ""
    for ev in turn:
        ts = ev.get("timestamp", "")
        if ts > max_ts:
            max_ts = ts
        content = ev.get("message", {}).get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                txt = b.get("text", "").strip()
                if txt:
                    segments.append((txt, EDGE_RATE))
    return segments, max_ts


# regexes used to score / strip bare (non-backtick) code in prose
_CALL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\([^()]*\)")
_CAMEL = re.compile(r"\b[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*\b")
_FILEEXT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z]{1,5}\b")
_SCREAM = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")
_OPGLUE = re.compile(r"[A-Za-z0-9_)\]]\s*[+=/*<>]\s*[A-Za-z0-9_(\[]")
_BRACE = re.compile(r"\{[^{}]*\}")
_BRACK = re.compile(r"\[[^\][]*\]")
_ASCII_PARENS = re.compile(r"\([\x20-\x7e]*\)")  # parens w/ no Hangul = code


def code_score(s):
    """Count code-ish tokens in a clause."""
    n = 0
    for rx in (_CALL, _CAMEL, _FILEEXT, _SCREAM, _BRACE, _BRACK, _OPGLUE):
        n += len(rx.findall(s))
    return n


def strip_prose_code(s):
    """For a KEPT clause: reduce calls to their name, drop code punctuation,
    but preserve method/identifier names and Korean prose."""
    s = _BRACE.sub(" ", s)
    s = _BRACK.sub(" ", s)
    # foo(args) -> foo  (twice, for chained/nested calls)
    s = _CALL.sub(lambda m: m.group(0).split("(", 1)[0], s)
    s = _CALL.sub(lambda m: m.group(0).split("(", 1)[0], s)
    s = _ASCII_PARENS.sub(" ", s)      # leftover ascii-only () = code bits
    s = re.sub(r"[{}\[\]<>|=*/\\^~\"']", " ", s)
    return s


def clean(t):
    # markdown / links / urls / emoji first
    t = re.sub(r"```.*?```", " ", t, flags=re.DOTALL)
    t = re.sub(r"~~~.*?~~~", " ", t, flags=re.DOTALL)
    t = re.sub(r"`[^`]*`", " ", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*>\s?", "", t, flags=re.M)
    t = re.sub(r"^\s*\|.*\|\s*$", " ", t, flags=re.M)
    t = re.sub(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]", "", t)

    # clause-level code-density filter: drop dense code chunks, keep prose.
    # split on structural separators + a period that ENDS a Korean sentence
    # (after Hangul), so file.ext (colors.ts) and decimals (0.05) stay intact.
    clauses = re.split(r"[\n·]+|\s+—\s+|(?<=[가-힣])\s*\.\s+", t)
    kept = []
    for c in clauses:
        c = re.sub(r"^\s*\d+\.\s*", "", c).strip()   # drop list numbers
        if not c:
            continue
        if code_score(c) >= CODE_MAX:
            continue  # code chunk -> omit
        kept.append(strip_prose_code(c).strip())
    t = ", ".join(k for k in kept if k)

    t = re.sub(r"[*_#>`~|]", "", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s*[,.]\s*(?:[,.]\s*)+", ", ", t)   # collapse punct runs
    return t.strip()


def state_path(transcript):
    import hashlib
    h = hashlib.sha1((transcript or "").encode()).hexdigest()[:12]
    return os.path.join(HOME, ".claude", ".tts-last-" + h)


def read_state(transcript):
    try:
        return open(state_path(transcript)).read().strip()
    except Exception:
        return ""


def write_state(transcript, ts):
    try:
        with open(state_path(transcript), "w") as f:
            f.write(ts)
    except Exception:
        pass


def worker(path):
    """Poll until a turn newer than last-spoken appears, then speak it."""
    last_spoken = read_state(path)
    segments, ts = [], ""
    for _ in range(POLL_TRIES):
        if off():
            return
        segments, ts = collect_turn(path)
        # ISO-8601 timestamps sort chronologically as strings
        if segments and ts and ts > last_spoken:
            break
        time.sleep(POLL_SLEEP)
    else:
        return  # nothing newer showed up
    if off():
        return
    write_state(path, ts)
    # clean each segment, keep its rate, cap total length
    spoken, total = [], 0
    for text, rate in segments:
        s = clean(text)
        if not s:
            continue
        if total + len(s) > MAX_CHARS:
            s = s[:max(0, MAX_CHARS - total)].rsplit(" ", 1)[0] + " ..."
        spoken.append((s, rate))
        total += len(s)
        if total >= MAX_CHARS:
            break
    if not spoken:
        # whole turn was code -> brief notice instead of silence
        spoken = [("코드 위주 답변이라 음성은 생략합니다.", EDGE_RATE)]
    # stop any in-flight playback so turns don't overlap
    subprocess.run(["pkill", "-x", "afplay"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-x", "say"], stderr=subprocess.DEVNULL)
    if ENGINE == "edge" and speak_edge(spoken, path, ts):
        return
    speak_say(" ".join(s for s, _ in spoken))   # offline / failure fallback


def find_edge():
    for p in (os.path.expanduser("~/.local/bin/edge-tts"),
              "/opt/homebrew/bin/edge-tts", "/usr/local/bin/edge-tts"):
        if os.path.exists(p):
            return p
    return shutil.which("edge-tts")


_END = object()   # queue sentinel


def chunk_text(s):
    """Split into chunks (~<=200 chars) at comma/sentence boundaries for
    pipelined synthesis. Fewer/larger chunks = fewer audible seams."""
    parts = re.split(r"(?<=[.!?。…,])\s+", s.strip())
    chunks, buf = [], ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if not buf:
            buf = p
        elif len(buf) + len(p) < 200:
            buf += " " + p
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks or [s]


def superseded(path, ts):
    """True if a newer turn took over (newer state ts) or tts was turned off."""
    return off() or (read_state(path) or "") > ts


def synth_chunk(edge, text, mp3, rate=EDGE_RATE):
    try:
        r = subprocess.run(
            [edge, "--voice", EDGE_VOICE, "--rate", rate,
             "--text", text, "--write-media", mp3],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25,
        )
        return r.returncode == 0 and os.path.exists(mp3) and os.path.getsize(mp3) > 0
    except Exception:
        return False


def speak_edge(segments, path, ts):
    """Chunked neural TTS: a producer thread synthesizes sentences while we
    play them in order, so audio starts right after the first chunk. Stops
    early if a newer turn supersedes this one. Returns True if anything played.

    segments = list of (speech_text, rate); each is chunked and synthesized
    at its own rate, so progress narration can be spoken faster than the
    final answer."""
    edge = find_edge()
    if not edge:
        return False
    chunks = [(ch, rate) for text, rate in segments for ch in chunk_text(text)]
    q = queue.Queue()

    def producer():
        for i, (ch, rate) in enumerate(chunks):
            if superseded(path, ts):
                break
            mp3 = tempfile.mktemp(suffix=".mp3", prefix="tts%d_" % i)
            q.put(mp3 if synth_chunk(edge, ch, mp3, rate) else None)
        q.put(_END)

    threading.Thread(target=producer, daemon=True).start()
    played = False
    while True:
        item = q.get()
        if item is _END:
            break
        if item is None:
            continue
        if superseded(path, ts):
            _rm(item)
            continue   # drain + discard until _END
        subprocess.run(["afplay", "-v", VOLUME, item])
        played = True
        _rm(item)
    return played


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


def speak_say(speech):
    subprocess.Popen(
        ["say", "-v", VOICE, "-r", RATE, speech],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def main():
    # worker mode (re-exec'd, detached)
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        worker(sys.argv[2])
        return

    # hook mode: parse payload, spawn detached worker, return immediately
    if off():
        return
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        return
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--worker", path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


if __name__ == "__main__":
    main()
