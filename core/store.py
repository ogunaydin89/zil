"""Settings, schedule and ring-log persistence.

Everything lives in data/ next to the app, so the whole folder is portable and
nothing depends on browser localStorage.
"""
import json
import os
import threading
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
AUDIO = os.path.join(ROOT, "audio")

SETTINGS_PATH = os.path.join(DATA, "settings.json")
SCHEDULE_PATH = os.path.join(DATA, "schedule.json")
LOG_PATH = os.path.join(DATA, "ring-log.jsonl")
FIRED_PATH = os.path.join(DATA, "fired-today.json")

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday"]

# sound key -> (subfolder, priority category)
SOUND_KINDS = {
    "student": ("bells", "bell"),
    "teacher": ("bells", "bell"),
    "exit": ("bells", "bell"),
    "anthem_only": ("anthems", "ceremony"),
    "anthem_1min": ("anthems", "ceremony"),
    "anthem_2min": ("anthems", "ceremony"),
    "em_yellow": ("sirens", "emergency"),
    "em_red": ("sirens", "emergency"),
    "em_black": ("sirens", "emergency"),
    "em_white": ("sirens", "emergency"),
    "em_quake": ("sirens", "emergency"),
    "em_fire": ("sirens", "emergency"),
}

DEFAULT_SETTINGS = {
    "school_name": "",
    "language": "tr",
    "enabled": True,
    "catchup_seconds": 90,
    "ui_port": 8765,
    "volumes": {"bell": 90, "ceremony": 100, "emergency": 100},
    "melodies": {},
}

DEFAULT_SCHEDULE = {"weekly": {d: [] for d in DAYS},
                    "holidays": [], "overrides": [], "ceremonies": []}

_lock = threading.RLock()


def _read(path, fallback):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return json.loads(json.dumps(fallback))


def _write_atomic(path, obj):
    """Write via a temp file + replace so a crash can never truncate the real one."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def clamp_volume(v, default=100):
    try:
        return max(0, min(100, int(v)))
    except (TypeError, ValueError):
        return default


def load_settings():
    with _lock:
        s = _read(SETTINGS_PATH, DEFAULT_SETTINGS)
        for k, v in DEFAULT_SETTINGS.items():
            s.setdefault(k, json.loads(json.dumps(v)))
        vols = s.get("volumes") or {}
        s["volumes"] = {k: clamp_volume(vols.get(k), DEFAULT_SETTINGS["volumes"][k])
                        for k in DEFAULT_SETTINGS["volumes"]}
        try:
            s["catchup_seconds"] = max(0, min(3600, int(s["catchup_seconds"])))
        except (TypeError, ValueError):
            s["catchup_seconds"] = 90
        return s


def save_settings(s):
    with _lock:
        _write_atomic(SETTINGS_PATH, s)
        return s


def load_schedule():
    with _lock:
        sch = _read(SCHEDULE_PATH, DEFAULT_SCHEDULE)
        weekly = sch.get("weekly") or {}
        for d in DAYS:
            weekly.setdefault(d, [])
        sch["weekly"] = weekly
        for key in ("holidays", "overrides", "ceremonies"):
            sch.setdefault(key, [])
        return sch


def save_schedule(sch):
    with _lock:
        _write_atomic(SCHEDULE_PATH, sch)
        return sch


def sound_path(settings, key):
    """Absolute path to the audio file configured for a sound key, or None."""
    kind = SOUND_KINDS.get(key)
    if not kind:
        return None
    filename = (settings.get("melodies") or {}).get(key) or ""
    filename = filename.strip()
    if not filename:
        return None
    # Guard against a stray path separator in a hand-edited settings file.
    filename = os.path.basename(filename)
    return os.path.join(AUDIO, kind[0], filename)


def category_for(key):
    kind = SOUND_KINDS.get(key)
    return kind[1] if kind else "bell"


def list_audio_files():
    """What is actually on disk, so the UI can offer a dropdown instead of free text."""
    out = {}
    for folder in ("bells", "anthems", "sirens"):
        d = os.path.join(AUDIO, folder)
        try:
            out[folder] = sorted(f for f in os.listdir(d)
                                 if f.lower().endswith((".wav", ".mp3", ".ogg")))
        except OSError:
            out[folder] = []
    return out


def load_fired(day_iso):
    """Bells already rung on `day_iso`, as a set of (time, key).

    Kept on disk so a restart inside the catch-up window does not ring a bell
    that has already rung - an in-memory set alone would double-ring after a
    crash, an update or a reboot.
    """
    with _lock:
        data = _read(FIRED_PATH, {})
    if data.get("date") != day_iso:
        return set()
    out = set()
    for item in data.get("keys", []):
        if isinstance(item, list) and len(item) == 2:
            out.add((item[0], item[1]))
    return out


def save_fired(day_iso, pairs):
    with _lock:
        try:
            _write_atomic(FIRED_PATH, {"date": day_iso,
                                       "keys": sorted([list(p) for p in pairs])})
        except OSError:
            pass


def log_event(kind, key, label, detail=""):
    """Append-only record of what actually rang, for later auditing."""
    rec = {"ts": datetime.now().isoformat(timespec="seconds"),
           "kind": kind, "key": key, "label": label, "detail": detail}
    with _lock:
        try:
            os.makedirs(DATA, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return rec


def read_log(limit=200):
    with _lock:
        try:
            with open(LOG_PATH, encoding="utf-8") as fh:
                lines = fh.readlines()[-limit:]
        except OSError:
            return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    out.reverse()
    return out
