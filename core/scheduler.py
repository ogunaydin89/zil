"""Wall-clock scheduler.

Runs on a background thread and compares against the real clock every second, so
it does not depend on a browser tab staying awake. Two properties matter:

  * Catch-up  - a bell fires if its moment passed within `catchup_seconds`, so a
                skipped tick (sleep, load spike) does not silently lose a bell.
  * Idempotent - each bell is keyed by date+time+type and rings at most once a day.
"""
import threading
from datetime import date, datetime, timedelta

from . import store

DAYS = store.DAYS


def _parse_hhmm(text):
    try:
        h, m = str(text).strip().split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h, m


def _day_name(d):
    return DAYS[d.weekday()]


def covers(h, d):
    """Does this holiday record cover date `d`?

    A record is either a single day ("date") or an inclusive range
    ("date" .. "end_date"), so a two-week break is one row, not fourteen.
    """
    start = h.get("date")
    if not start:
        return False
    end = h.get("end_date") or start
    if end < start:
        start, end = end, start
    return start <= d.isoformat() <= end


def holiday_for(schedule, d):
    """The holiday covering `d`, if any.

    When several records overlap (say a break range laid over an arefe
    half-day), the more restrictive one wins: a full closure beats a half-day.
    """
    match = None
    for h in schedule.get("holidays", []):
        if not covers(h, d):
            continue
        if not h.get("from_time"):
            return h                            # full day off - cannot be beaten
        match = match or h
    return match


def holiday_cutoff(h):
    """For a half-day (arefe), the (h, m) after which bells stop.

    None means the record is a full day off. This is what separates
    "no bells at all" from "morning bells ring, afternoon does not".
    """
    if not h:
        return None
    ft = h.get("from_time")
    return _parse_hhmm(ft) if ft else None


def effective_day(schedule, d):
    """Which weekday's timetable applies on this date (None = no bells)."""
    h = holiday_for(schedule, d)
    if h and not holiday_cutoff(h):
        return None                             # full day off
    # A half-day keeps its normal timetable; events_for() trims the afternoon.
    iso = d.isoformat()
    for o in schedule.get("overrides", []):
        if o.get("date") == iso:
            use = o.get("use_day")
            return use if use in DAYS else None
    return _day_name(d)


def events_for(schedule, d):
    """All bell + ceremony events for a date, sorted, as dicts with a datetime."""
    out = []
    day = effective_day(schedule, d)
    if day:
        for ev in schedule["weekly"].get(day, []):
            if not ev.get("enabled", True):
                continue
            hm = _parse_hhmm(ev.get("time"))
            if not hm:
                continue
            out.append({
                "when": datetime(d.year, d.month, d.day, hm[0], hm[1]),
                "time": ev["time"].strip(),
                "key": ev.get("type"),
                "lesson": ev.get("lesson"),
                "source": "bell",
            })

    # Dated ceremonies fire even on holidays - that is usually the whole point
    # (national days are holidays and still need the anthem).
    iso = d.isoformat()
    for c in schedule.get("ceremonies", []):
        if c.get("date") != iso or not c.get("enabled", True):
            continue
        hm = _parse_hhmm(c.get("time"))
        if not hm:
            continue
        out.append({
            "when": datetime(d.year, d.month, d.day, hm[0], hm[1]),
            "time": c["time"].strip(),
            "key": c.get("sound"),
            "lesson": None,
            "name": c.get("name", ""),
            "source": "ceremony",
        })

    # On a half-day, drop the lesson bells from the cutoff onwards. Dated
    # ceremonies are deliberately kept: they are scheduled for that exact day.
    cut = holiday_cutoff(holiday_for(schedule, d))
    if cut:
        cut_at = datetime(d.year, d.month, d.day, cut[0], cut[1])
        out = [e for e in out if e["source"] != "bell" or e["when"] < cut_at]

    out.sort(key=lambda e: e["when"])
    return out


class Scheduler(threading.Thread):
    def __init__(self, engine, get_settings, get_schedule, on_tick=None):
        super().__init__(daemon=True, name="zil-scheduler")
        self._engine = engine
        self._get_settings = get_settings
        self._get_schedule = get_schedule
        self._on_tick = on_tick or (lambda: None)
        self._stop = threading.Event()
        self._fired_day = date.today().isoformat()
        # Seeded from disk: a restart must not re-ring a bell that already rang.
        self._fired = store.load_fired(self._fired_day)
        self.last_tick = None

    def stop(self):
        self._stop.set()

    def _mark(self, ident):
        """Record a bell as rung, in memory and on disk."""
        self._fired.add(ident)
        store.save_fired(self._fired_day, self._fired)

    # ---- introspection used by the UI --------------------------------

    def next_event(self, now=None):
        now = now or datetime.now()
        schedule = self._get_schedule()
        for offset in range(0, 8):                 # look up to a week ahead
            d = now.date() + timedelta(days=offset)
            for ev in events_for(schedule, d):
                if ev["when"] > now:
                    return ev
        return None

    def todays_events(self, now=None):
        now = now or datetime.now()
        return events_for(self._get_schedule(), now.date())

    # ---- the loop ----------------------------------------------------

    def run(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                pass                                # never let the thread die
            self._stop.wait(1.0)

    def tick(self, now=None):
        now = now or datetime.now()
        self.last_tick = now
        settings = self._get_settings()

        today_iso = now.date().isoformat()
        if today_iso != self._fired_day:            # new day: everything is due again
            self._fired_day = today_iso
            self._fired = store.load_fired(today_iso)

        if not settings.get("enabled", True):
            self._on_tick()
            return None

        grace = timedelta(seconds=int(settings.get("catchup_seconds", 90)))
        schedule = self._get_schedule()

        for ev in events_for(schedule, now.date()):
            ident = (ev["time"], ev["key"])
            if ident in self._fired:
                continue

            delta = now - ev["when"]
            if delta.total_seconds() < 0:
                break                               # future; so is everything after

            if delta <= grace:
                ok, _msg = self._engine.play(ev["key"], settings, source=ev["source"])
                # If an emergency is playing, leave the key unmarked so the bell
                # retries next tick until the grace window closes.
                if ok:
                    self._mark(ident)
                self._on_tick()
                return ev if ok else None

            self._mark(ident)                       # too late to be meaningful

        self._on_tick()
        return None
