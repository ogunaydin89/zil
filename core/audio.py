"""Priority-aware audio engine.

Carries over the rule established in v2: a lower-priority sound can never cut off
a higher-priority one, and stop_all() always wins. Playback streams from disk via
pygame.mixer.music, so a 17 MB siren starts instantly and costs no memory.
"""
import os
import threading

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from . import store

PRIORITY = {"bell": 1, "ceremony": 2, "emergency": 3}


class AudioEngine:
    def __init__(self, on_change=None):
        self._lock = threading.RLock()
        self._priority = 0
        self._label = ""
        self._key = ""
        self._ready = False
        self._error = ""
        self._on_change = on_change or (lambda: None)
        self._mixer = None

    def _ensure(self):
        if self._ready:
            return True
        try:
            import pygame
            pygame.mixer.init()
            self._mixer = pygame.mixer
            self._ready = True
            self._error = ""
        except Exception as exc:                      # no sound card, driver busy, ...
            self._error = "%s: %s" % (type(exc).__name__, exc)
            self._ready = False
        return self._ready

    # ---- state -------------------------------------------------------

    def _busy(self):
        if not self._ready:
            return False
        try:
            return bool(self._mixer.music.get_busy())
        except Exception:
            return False

    def _release(self):
        """Let go of the audio file.

        The mixer keeps an open handle on whatever is loaded, which stops
        Windows from replacing that file while Zil is running. Unloading once
        playback is over keeps the audio folder editable in place.
        """
        if not self._ready:
            return
        try:
            self._mixer.music.unload()
        except Exception:
            pass                                  # older pygame has no unload()

    def status(self):
        with self._lock:
            busy = self._busy()
            if not busy and self._priority:
                self._priority, self._label, self._key = 0, "", ""
                self._release()
            return {"playing": busy, "label": self._label,
                    "key": self._key, "priority": self._priority,
                    "audio_error": self._error}

    # ---- playback ----------------------------------------------------

    def play(self, key, settings, source="manual"):
        """Returns (ok, message). ok=False when blocked or unplayable."""
        with self._lock:
            category = store.category_for(key)
            prio = PRIORITY.get(category, 1)

            if self._busy() and prio < self._priority:
                msg = "blocked by higher-priority audio (%s)" % (self._label or "?")
                store.log_event("blocked", key, key, msg)
                return False, msg

            if not self._ensure():
                store.log_event("error", key, key, self._error)
                return False, "audio device unavailable: " + self._error

            path = store.sound_path(settings, key)
            if not path:
                msg = "no audio file configured"
                store.log_event("error", key, key, msg)
                return False, msg
            if not os.path.isfile(path):
                msg = "file not found: " + os.path.basename(path)
                store.log_event("error", key, key, msg)
                return False, msg

            vol = store.clamp_volume((settings.get("volumes") or {}).get(category), 100)
            try:
                self._mixer.music.load(path)
                # Explicit /100.0 with no `or` fallback: 0 must mean silent.
                self._mixer.music.set_volume(vol / 100.0)
                self._mixer.music.play()
            except Exception as exc:
                msg = "%s: %s" % (type(exc).__name__, exc)
                store.log_event("error", key, key, msg)
                return False, msg

            self._priority = prio
            self._label = key
            self._key = key
            store.log_event("played", key, key, "%s, volume %d%%" % (source, vol))
            self._on_change()
            return True, "playing"

    def stop_all(self):
        """The override. Always succeeds, whatever is playing."""
        with self._lock:
            if self._ready:
                try:
                    self._mixer.music.stop()
                except Exception:
                    pass
                self._release()
            was = self._label
            self._priority, self._label, self._key = 0, "", ""
            if was:
                store.log_event("stopped", was, was, "manual stop")
            self._on_change()
            return True
