"""Native application window hosting the control panel.

Uses the WebView2 runtime that ships with Windows 11, so the UI renders in a real
app window - no browser, no address bar, no localhost URL on screen. The HTML is
an implementation detail, the same way it is inside any Electron or Tauri app.

Closing the window hides it to the tray; only tray -> Quit actually exits.
"""
import threading

_window = None
_quitting = False
_available = None


def available():
    """True if a native window can be created on this machine."""
    global _available
    if _available is None:
        try:
            import webview  # noqa
            _available = True
        except Exception:
            _available = False
    return _available


def _on_closing():
    """Return False to veto the close, then hide instead - unless really quitting."""
    if _quitting:
        return True
    try:
        _window.hide()
    except Exception:
        pass
    return False


def create(url, title, start_hidden):
    """Build the window. Must run before start(), on the main thread."""
    global _window
    import webview
    _window = webview.create_window(
        title, url,
        width=1120, height=860, min_size=(420, 560),
        hidden=start_hidden, confirm_close=False,
    )
    _window.events.closing += _on_closing
    return _window


def start():
    """Blocks on the main thread until the window is destroyed."""
    import webview
    webview.start(debug=False)


def show():
    if not _window:
        return False
    try:
        _window.show()
        _window.restore()
        return True
    except Exception:
        return False


def set_title(text):
    if not _window:
        return
    try:
        _window.set_title(text)
    except Exception:
        pass


def destroy():
    """Tear the window down for real, releasing start()."""
    global _quitting
    _quitting = True
    if not _window:
        return
    try:
        _window.destroy()
    except Exception:
        pass
