"""Add or remove Zil from Windows startup, and make a Desktop shortcut.

Uses only the per-user Startup folder - no admin rights, no registry writes, and
nothing for Smart App Control to object to, because the thing being launched is
the signed pythonw.exe that is already on this machine.

  python autostart.py status
  python autostart.py enable
  python autostart.py disable
  python autostart.py desktop      (Desktop shortcut only)
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(ROOT, "zil.pyw")
# Deliberately NOT "Zil.lnk": that name is already taken on the Desktop by the
# shortcut to the old v2 HTML app, and overwriting it would destroy the fallback.
LINK_NAME = "Zil v3.lnk"


def _pythonw():
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.isfile(cand) else exe


def _startup_dir():
    return os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                        "Start Menu", "Programs", "Startup")


def _desktop_dir():
    return os.path.join(os.path.expanduser("~"), "Desktop")


def _make_shortcut(folder, args=""):
    """Create the .lnk via PowerShell's WScript.Shell - no extra dependency."""
    import subprocess
    path = os.path.join(folder, LINK_NAME)
    ps = (
        "$s=New-Object -ComObject WScript.Shell;"
        "$l=$s.CreateShortcut('{lnk}');"
        "$l.TargetPath='{exe}';"
        "$l.Arguments='\"{target}\" {args}';"
        "$l.WorkingDirectory='{root}';"
        "$l.Description='Zil - Okul Zil Sistemi';"
        "$l.Save()"
    ).format(lnk=path.replace("'", "''"), exe=_pythonw().replace("'", "''"),
             target=TARGET.replace("'", "''"), args=args,
             root=ROOT.replace("'", "''"))
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   check=True, capture_output=True)
    return path


def status():
    s = os.path.join(_startup_dir(), LINK_NAME)
    d = os.path.join(_desktop_dir(), LINK_NAME)
    print("launcher      :", _pythonw())
    print("app           :", TARGET)
    print("autostart     :", "ON  -> " + s if os.path.isfile(s) else "OFF")
    print("desktop icon  :", "yes -> " + d if os.path.isfile(d) else "no")


def enable():
    print("autostart enabled:", _make_shortcut(_startup_dir()))


def disable():
    p = os.path.join(_startup_dir(), LINK_NAME)
    if os.path.isfile(p):
        os.remove(p)
        print("autostart disabled (removed", p + ")")
    else:
        print("autostart was not enabled")


def desktop():
    print("desktop shortcut:", _make_shortcut(_desktop_dir(), "--panel"))


if __name__ == "__main__":
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    fn = {"status": status, "enable": enable, "disable": disable, "desktop": desktop}.get(cmd)
    if not fn:
        print(__doc__)
        sys.exit(2)
    fn()
