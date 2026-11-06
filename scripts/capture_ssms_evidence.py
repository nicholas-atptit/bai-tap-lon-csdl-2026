"""Capture REAL SQL Server Management Studio (SSMS 22) screenshots for the report (Windows desktop automation).

uv run --no-project --with pywinauto --with pillow python scripts/capture_ssms_evidence.py [--only 01,05]
For each report/final/evidence/ssms/sql/NN_*.sql: paste the script into the SSMS query window (connected with Windows
authentication), press F5, expand the matching Object Explorer folders, capture the SSMS window with PrintWindow, blur
every UI element that shows the Windows login, crop away the Copilot pane, save report/final/evidence/ssms/NN_*.png and
write manifest.json (file, database, Object Explorer path, capture time, SQL file sha256, status-bar result).
Scripts are read-only, except 12 which runs a CHECK violation inside a transaction on MarketLabVN30_Demo and rolls back.
The user's clipboard text is saved and restored.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

import win32clipboard
from PIL import Image, ImageFilter
from pywinauto import Desktop

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "report" / "final" / "evidence" / "ssms"
SSMS = r"C:\Program Files\Microsoft SQL Server Management Studio 22\Release\Common7\IDE\SSMS.exe"
LOGIN_MARKERS = ("\\",)          # Windows logins look like MACHINE\user; any UI text with a backslash login is blurred

# shot id -> Object Explorer path to expand under the server node (None = leave collapsed), crop mode
SHOTS = {
    "01": (["Databases", "MarketLabVN30_Demo", "Tables"], "full"),
    "02": (None, "query"),
    "03": (None, "query"),
    "04": (None, "query"),
    "05": (None, "query"),
    "06": (None, "query"),
    "07": (None, "query"),
    "08": (["Databases", "MarketLabVN30_Demo", "Views"], "full"),
    "09": (["Databases", "MarketLabVN30_Demo", "Programmability", "Stored Procedures"], "full"),
    "10": (["Databases", "MarketLabVN30_Demo", "Programmability", "Functions"], "full"),
    "11": (None, "query"),
    "12": (None, "query"),
}

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def capture(hwnd: int) -> tuple[Image.Image, tuple[int, int]]:
    """PrintWindow(PW_RENDERFULLCONTENT): the real window pixels even if other windows cover it."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = w, -h, 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1), (rect.left, rect.top)


def get_clip() -> str | None:
    try:
        win32clipboard.OpenClipboard()
        return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) \
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT) else None
    finally:
        win32clipboard.CloseClipboard()


def set_clip(text: str) -> None:
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def main_window(pid: int | None = None):
    for w in Desktop(backend="uia").windows():
        if "Microsoft SQL Server Management Studio" in w.window_text() and w.element_info.class_name == "Window" \
                and (pid is None or w.process_id() == pid):
            return w
    return None


def editor_of(main):
    for p in main.descendants(control_type="Pane"):
        n = p.window_text()
        if n.startswith("SQLQuery") and ".sql" in n:
            return p
    raise RuntimeError("SQLQuery editor pane not found")


def status_texts(main) -> list[str]:
    return [t.window_text() for t in main.descendants(control_type="Text")
            if any(k in t.window_text() for k in ("Query executed", "Query completed", "rows", "Executing query"))]


def server_node(main):
    for t in main.descendants(control_type="TreeItem"):
        if "SQL Server 17" in t.window_text():
            return t
    raise RuntimeError("Object Explorer server node not found (not connected?)")


def child(item, name: str):
    for _ in range(40):
        for c in item.children(control_type="TreeItem"):
            if c.window_text() == name or c.window_text().startswith(name + " ("):
                return c
        time.sleep(0.25)
    raise RuntimeError(f"Object Explorer node {name!r} not found")


def collapse_all(main) -> None:
    """Collapse the folders opened by earlier shots (deepest first) so each picture shows only its own subject."""
    root = server_node(main)
    try:
        dbs = child(root, "Databases")
        if not dbs.is_expanded():
            return
        demo = child(dbs, "MarketLabVN30_Demo")
        if demo.is_expanded():
            for name in ("Tables", "Views", "Programmability"):
                node = next((c for c in demo.children(control_type="TreeItem") if c.window_text() == name), None)
                if node is None or not node.is_expanded():
                    continue
                for sub in node.children(control_type="TreeItem"):
                    if sub.window_text() in ("Stored Procedures", "Functions") and sub.is_expanded():
                        for leaf in sub.children(control_type="TreeItem"):
                            if leaf.window_text().endswith("Functions") and leaf.is_expanded():
                                leaf.collapse()
                        sub.collapse()
                node.collapse()
        dbs.collapse()
    except Exception:  # noqa: BLE001
        pass


def expand_path(main, path: list[str]):
    node = server_node(main)
    for name in path:
        node = child(node, name)
        node.expand()
        time.sleep(0.8)
    for sub in node.children(control_type="TreeItem"):      # functions: open both scalar and table-valued folders
        if sub.window_text() in ("Scalar-valued Functions", "Table-valued Functions"):
            sub.expand()
            time.sleep(0.6)
    node.select()
    return node


def sensitive_rects(main) -> list:
    out = []
    for el in main.descendants():
        n = el.window_text() or ""
        if "\\" in n and any(c.isalpha() for c in n.split("\\")[-1][:1]) and el.element_info.control_type in (
                "TabItem", "TitleBar", "Text", "TreeItem", "Button", "MenuItem", "ListItem", "DataItem"):
            r = el.rectangle()
            if r.width() > 0 and r.height() > 0:
                out.append(r)
    return out


def pane_rect(main, name: str):
    for p in main.descendants(control_type="Pane"):
        if p.window_text() == name:
            return p.rectangle()
    return None


def shoot(main, sid: str, sql_file: Path, oe_path, crop_mode: str) -> dict:
    text = sql_file.read_text(encoding="utf-8")
    collapse_all(main)
    if oe_path:
        expand_path(main, oe_path)
    ed = editor_of(main)
    main.set_focus()
    time.sleep(0.4)
    ed.click_input(coords=(300, 120))
    set_clip(text)
    main.type_keys("^a")
    time.sleep(0.2)
    main.type_keys("^v")
    time.sleep(0.6)
    main.type_keys("^{HOME}")
    time.sleep(0.3)
    main.type_keys("{F5}")
    status = []
    for _ in range(120):
        time.sleep(0.5)
        status = status_texts(main)
        if any("Query executed" in s or "Query completed" in s for s in status):
            break
    time.sleep(1.2)
    img, (wx, wy) = capture(main.handle)
    for r in sensitive_rects(main):
        box = (max(0, r.left - wx - 2), max(0, r.top - wy - 2), min(img.width, r.right - wx + 2), min(img.height, r.bottom - wy + 2))
        if box[2] > box[0] and box[3] > box[1]:
            img.paste(img.crop(box).filter(ImageFilter.GaussianBlur(6)), box[:2])
    # avatar / account picture in the title row: blur the top-right corner icons
    cop = pane_rect(main, "GitHub Copilot Chat")
    right = (cop.left - wx - 4) if cop else img.width
    ed_rect = ed.rectangle()
    oe = pane_rect(main, "Object Explorer")
    left = (oe.left - wx - 2) if (crop_mode == "full" and oe) else (ed_rect.left - wx - 4)
    top = 92 if crop_mode == "full" else 92
    bottom = img.height - 46
    out = img.crop((max(0, left), top, right, bottom))
    name = sql_file.with_suffix(".png").name
    out.save(EVID / name)
    return {"file": f"report/final/evidence/ssms/{name}", "sql": f"report/final/evidence/ssms/sql/{sql_file.name}",
            "sql_sha256": hashlib.sha256(sql_file.read_bytes()).hexdigest()[:16], "object_explorer": " > ".join(oe_path or []) or None,
            "status_bar": [s for s in status if "luong" not in s.lower()], "size": list(out.size),
            "captured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "redaction": "Windows login text blurred; Copilot pane and account picture cropped"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    subprocess.run(["taskkill", "/IM", "SSMS.exe", "/F"], capture_output=True)
    time.sleep(2)
    p = subprocess.Popen([SSMS, "-S", ".", "-d", "MarketLabVN30_Demo", "-C", "-nosplash"])
    win = None
    t0 = time.time()
    while time.time() - t0 < 180:
        time.sleep(2)
        win = main_window(p.pid)
        if win:
            try:
                server_node(win)
                editor_of(win)
                break
            except RuntimeError:
                continue
    if not win:
        raise SystemExit("SSMS did not start")
    time.sleep(3)
    saved_clip = get_clip()
    manifest_path = EVID / "manifest.json"
    manifest = {m["file"]: m for m in json.loads(manifest_path.read_text(encoding="utf-8"))} if manifest_path.exists() else {}
    try:
        for sql_file in sorted((EVID / "sql").glob("*.sql")):
            sid = sql_file.name[:2]
            if only and sid not in only:
                continue
            oe_path, mode = SHOTS[sid]
            m = shoot(win, sid, sql_file, oe_path, mode)
            manifest[m["file"]] = m
            print(sid, m["size"], m["status_bar"])
    finally:
        if saved_clip is not None:
            set_clip(saved_clip)
        manifest_path.write_text(json.dumps(sorted(manifest.values(), key=lambda x: x["file"]), ensure_ascii=False, indent=1), encoding="utf-8")
        subprocess.run(["taskkill", "/PID", str(p.pid), "/F"], capture_output=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
