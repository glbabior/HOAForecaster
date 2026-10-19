"""Recalculate an .xlsx in LibreOffice headless and fail on any formula error.

    python tools/recalc.py WORKBOOK.xlsx

LibreOffice opens the workbook hidden, recalculates every formula, and saves
it in place with the computed values cached, so openpyxl can read them back
(`data_only=True`). Then every cell is scanned for Excel error values.

For the app's own reference and demo workbooks only – macros and external
links are disabled, but do not point it at untrusted files.
"""

from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl

ERRORS = {"#VALUE!", "#REF!", "#NAME?", "#DIV/0!", "#N/A", "#NUM!", "#NULL!", "Err:502", "Err:504"}

# Runs inside LibreOffice's own Python, which ships the `uno` bridge.
UNO_SCRIPT = r"""
import sys, time, subprocess, uno
from com.sun.star.beans import PropertyValue

soffice, path, pipe, profile = sys.argv[1:5]
# A private named pipe, not a TCP port, so no other process can find the UNO bridge.
proc = subprocess.Popen([soffice, "--headless", "--invisible", "--nologo", "--norestore",
    "-env:UserInstallation=" + profile, "--accept=pipe,name=%s;urp;" % pipe])
try:
    ctx = None
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local)
    for _ in range(120):
        try:
            ctx = resolver.resolve("uno:pipe,name=%s;urp;StarOffice.ComponentContext" % pipe)
            break
        except Exception:
            time.sleep(0.5)
    if ctx is None:
        sys.exit("LibreOffice did not start")
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    def prop(name, value):
        p = PropertyValue(); p.Name = name; p.Value = value; return p
    url = uno.systemPathToFileUrl(path)
    load = (prop("Hidden", True), prop("MacroExecutionMode", 0), prop("UpdateDocMode", 0))
    doc = desktop.loadComponentFromURL(url, "_blank", 0, load)
    if doc is None:
        sys.exit("LibreOffice could not open " + path)
    try:
        doc.calculateAll()
        doc.storeToURL(url, (prop("FilterName", "Calc MS Excel 2007 XML"), prop("Overwrite", True)))
    finally:
        doc.close(True)
        try:
            desktop.terminate()
        except Exception:
            pass
finally:
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
"""


def find_soffice() -> Path:
    candidates = [
        os.environ.get("SOFFICE", ""),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        shutil.which("soffice") or "",
        shutil.which("libreoffice") or "",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    sys.exit("LibreOffice not found – install it or set SOFFICE to the soffice path")


def find_uno_python(soffice: Path) -> str:
    bundled = soffice.parent / ("python.exe" if os.name == "nt" else "python")
    if bundled.exists():  # Windows and macOS ship their own Python with uno
        return str(bundled)
    return "python3"  # Linux distributions install uno into the system Python


def recalc(workbook: Path) -> None:
    soffice = find_soffice()
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "recalc_uno.py"
        script.write_text(UNO_SCRIPT, encoding="utf-8")
        profile = (Path(tmp) / "profile").as_uri()
        pipe = f"hoa_recalc_{secrets.token_hex(8)}"
        args = [find_uno_python(soffice), str(script), str(soffice), str(workbook.resolve())]
        helper = subprocess.Popen([*args, pipe, profile], start_new_session=True)
        try:
            code = helper.wait(timeout=300)
        except subprocess.TimeoutExpired:
            _kill_tree(helper.pid)
            raise
        if code:
            raise subprocess.CalledProcessError(code, args)


def _kill_tree(pid: int) -> None:
    """Stop the helper and the LibreOffice it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], check=False)
    else:
        os.killpg(pid, signal.SIGKILL)


def formula_errors(workbook: Path) -> list[str]:
    wb = openpyxl.load_workbook(workbook, data_only=True)
    return [
        f"{ws.title}!{cell.coordinate} {cell.value}"
        for ws in wb
        for row in ws.iter_rows()
        for cell in row
        if isinstance(cell.value, str) and cell.value in ERRORS
    ]


def main() -> None:
    workbook = Path(sys.argv[1])
    recalc(workbook)
    errors = formula_errors(workbook)
    if errors:
        sys.exit(f"{len(errors)} formula errors\n" + "\n".join(errors[:50]))
    print(f"recalculated {workbook} – zero formula errors")


if __name__ == "__main__":
    main()
