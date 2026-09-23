"""One-shot import of the old v2 config.js into the new JSON data model.

The old file is JavaScript, not JSON, so it is parsed with a tolerant regex pass
rather than json.loads. Run via:  python -m core.migrate <path-to-old-config.js>
"""
import json
import os
import re
import sys

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday"]

# old key -> new bell type
BELL_KEYS = [("ogrenci", "student"), ("ogretmen", "teacher"), ("cikis", "exit")]


def _js_object(src, varname):
    """Extract `const <varname> = { ... };` and parse it as JSON."""
    m = re.search(r"const\s+" + varname + r"\s*=\s*(\{)", src)
    if not m:
        raise ValueError("could not find " + varname)
    start = m.start(1)
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                body = src[start:i + 1]
                break
    else:
        raise ValueError("unbalanced braces in " + varname)

    body = re.sub(r"//[^\n]*", "", body)          # strip line comments
    body = re.sub(r",(\s*[}\]])", r"\1", body)     # strip trailing commas
    return json.loads(body)


def convert(old_path):
    src = open(old_path, encoding="utf-8-sig").read()
    settings_js = _js_object(src, "AppSettings")
    schedule_js = _js_object(src, "AppSchedule")

    mel = settings_js.get("default_melodies", {})
    settings = {
        "school_name": settings_js.get("school_name", ""),
        "language": "tr",
        "enabled": bool(settings_js.get("system_enabled", True)),
        "catchup_seconds": int(settings_js.get("catchup_seconds", 90)),
        "ui_port": 8765,
        "volumes": {
            "bell": int(settings_js.get("volume_bell", 90)),
            "ceremony": int(settings_js.get("volume_ceremony", 100)),
            "emergency": int(settings_js.get("volume_emergency", 100)),
        },
        "melodies": {
            "student": mel.get("ogrenci", ""),
            "teacher": mel.get("ogretmen", ""),
            "exit": mel.get("cikis", ""),
            "anthem_only": mel.get("anthem_only", "istiklalmarsi.wav"),
            "anthem_1min": mel.get("anthem_1min", "1dksaygiveistiklalmarsi.wav"),
            "anthem_2min": mel.get("anthem_2min", "2dksaygiveistiklalmarsi.wav"),
            "em_yellow": mel.get("em_yellow", "1_Sari_Ikaz_Hava_Tehdidi.wav"),
            "em_red": mel.get("em_red", "2_Kirmizi_Ikaz_Dogrudan_Tehlike.wav"),
            "em_black": mel.get("em_black", "3_Siyah_Ikaz_KBRN_Kimyasal_Tehlike.wav"),
            "em_white": mel.get("em_white", "4_Beyaz_Ikaz_Tehlike_Gecti.wav"),
            "em_quake": mel.get("em_quake", "5_Deprem_Cok_Kapan_Tutun.wav"),
            "em_fire": mel.get("em_fire", "6_Yangin_Tahliye_Sireni.wav"),
        },
    }

    # Flatten the old lesson rows into one event list per day.
    weekly = {}
    for day in DAYS:
        events = []
        for lesson in schedule_js.get(day, []):
            num = lesson.get("lesson_num")
            for old_key, new_type in BELL_KEYS:
                time_s = (lesson.get(old_key + "_time") or "").strip()
                if not lesson.get(old_key + "_enabled") or not time_s:
                    continue
                events.append({"lesson": num, "type": new_type,
                               "time": time_s, "enabled": True})
        events.sort(key=lambda e: e["time"])
        weekly[day] = events

    schedule = {
        "weekly": weekly,
        "holidays": [],     # {"date": "YYYY-MM-DD", "name": str}
        "overrides": [],    # {"date": "YYYY-MM-DD", "use_day": "Saturday"}
        "ceremonies": [],   # {"date": "...", "time": "HH:MM", "sound": key, "name": str}
    }
    return settings, schedule


def main():
    old = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    settings, schedule = convert(old)
    os.makedirs(out_dir, exist_ok=True)
    for name, obj in (("settings.json", settings), ("schedule.json", schedule)):
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
        print("wrote", path)
    total = sum(len(v) for v in schedule["weekly"].values())
    for day in DAYS:
        print("  %-10s %2d bells" % (day, len(schedule["weekly"][day])))
    print("  total:", total)


if __name__ == "__main__":
    main()
