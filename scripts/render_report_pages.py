"""Render report/final/MarketLabVN30_FINAL.pdf to PNG pages (pdftoppm) and build contact sheets for page-by-page QA.

uv run --no-project --with pillow python scripts/render_report_pages.py [--dpi 70] [--per-sheet 6]
Output: var/report_render/page-XX.png and var/report_render/sheet-YY.png (gitignored).
"""
import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--dpi", type=int, default=70)
ap.add_argument("--per-sheet", type=int, default=6)
ap.add_argument("--pdf", default=str(ROOT / "report" / "final" / "MarketLabVN30_FINAL.pdf"))
a = ap.parse_args()
out = ROOT / "var" / "report_render"
out.mkdir(parents=True, exist_ok=True)
for old in out.glob("*.png"):
    old.unlink()
subprocess.run(["pdftoppm", "-png", "-r", str(a.dpi), a.pdf, str(out / "page")], check=True)
pages = sorted(out.glob("page-*.png"))
cols = 3
for s in range(0, len(pages), a.per_sheet):
    chunk = [Image.open(p) for p in pages[s:s + a.per_sheet]]
    w, h = chunk[0].size
    rows = (len(chunk) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 10) + 10, rows * (h + 30) + 10), "#888888")
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(chunk):
        x, y = 10 + (i % cols) * (w + 10), 10 + (i // cols) * (h + 30)
        sheet.paste(im, (x, y + 20))
        d.text((x, y + 2), f"page {s + i + 1}", fill="white")
    sheet.save(out / f"sheet-{s // a.per_sheet + 1:02d}.png")
print(f"{len(pages)} pages, {(len(pages) + a.per_sheet - 1) // a.per_sheet} sheets -> {out}")
