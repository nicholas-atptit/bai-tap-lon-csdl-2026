"""Automated UI audit of RUNNING MarketLab web application instances with Microsoft Edge (Playwright, headless).

uv run python scripts/ui_audit.py --phase ssr --demo http://127.0.0.1:8000 --real http://127.0.0.1:8001
For every mode x viewport x page: console errors, failed app requests (>= 400), browser-side data fetches (must be none:
pages are rendered on the server), horizontal page overflow, clipped/unlabelled controls, NaN/undefined/None text,
empty containers without a message; plus /api/docs and /api/openapi.json must be gone (404). Full-page screenshots:
DEMO -> tests/product_evidence/ui_audit/<phase>/ ; REAL -> tests/product_evidence/private/ui_audit/<phase>/ (gitignored).
Read-only: never submits the EOD form. Requests to third-party domains injected by the local antivirus are ignored.
(Phases "before"/"after" in the repository were produced by the previous version of this script against the former
REST-backed single page; see docs/PRODUCT_UI_AUDIT.md.)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = {"1440x900": (1440, 900), "1280x800": (1280, 800), "768x1024": (768, 1024), "390x844": (390, 844)}
PAGES = {"overview": "/", "market": "/market", "forecast": "/forecast", "compare": "/compare", "ops": "/ops", "backfill": "/backfill"}

PROBE = """() => {
  const vw = document.documentElement.clientWidth;
  const issues = [];
  if (document.documentElement.scrollWidth > vw + 1) issues.push(`page horizontal overflow: ${document.documentElement.scrollWidth} > ${vw}`);
  for (const inp of document.querySelectorAll('main input, main select, main button, header select')) {
    if (inp.offsetParent === null || inp.type === 'hidden' || inp.closest('.table-wrap')) continue;
    const r = inp.getBoundingClientRect();
    if (r.right > vw + 1) issues.push(`control clipped: ${inp.id || inp.name}`);
    if (inp.tagName !== 'BUTTON' && inp.type !== 'checkbox') {
      const labelled = inp.closest('label') || inp.getAttribute('aria-label') || (inp.id && document.querySelector(`label[for="${inp.id}"]`));
      if (!labelled) issues.push(`unlabelled control: ${inp.id || inp.name}`);
    }
  }
  const text = document.querySelector('main').innerText;
  if (/\\bNaN\\b|undefined|\\bNone\\b/.test(text)) issues.push('NaN/undefined/None rendered');
  const empty = [...document.querySelectorAll('.table-wrap, .chart')].filter(e => e.offsetParent !== null && e.innerText.trim() === '' && !e.querySelector('svg'));
  if (empty.length) issues.push(`${empty.length} empty container(s) without state message`);
  if (!document.querySelector('[aria-current="page"]')) issues.push('no current-page marker in navigation');
  return issues;
}"""


def run(base: str, mode: str, out: Path, report: dict) -> None:
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        for vname, (w, h) in VIEWPORTS.items():
            ctx = b.new_context(viewport={"width": w, "height": h})
            page = ctx.new_page()
            console, failed, fetches = [], [], []
            local = lambda u: u.startswith(base)  # noqa: E731
            page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
            page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 400 and local(r.url) else None)
            page.on("request", lambda r: fetches.append(r.url) if r.resource_type in ("xhr", "fetch") and local(r.url) else None)
            for name, path in PAGES.items():
                page.goto(base + path + ("?t=ACB" if name == "market" and mode == "REAL" else ""))
                page.wait_for_timeout(500)
                issues = page.evaluate(PROBE)
                shot = out / f"{mode}_{vname}_{name}.png"
                page.screenshot(path=str(shot), full_page=True)
                report["items"].append({"mode": mode, "viewport": vname, "page": path, "issues": issues, "screenshot": str(shot.relative_to(ROOT))})
            page.goto(base + "/")
            page.keyboard.press("Tab")
            first = page.evaluate("() => { const e = document.activeElement; return {cls: e.className, outline: getComputedStyle(e).outlineStyle}; }")
            report["keyboard"].append({"mode": mode, "viewport": vname, "first_tab_stop": first})
            report["console"].extend({"mode": mode, "viewport": vname, "error": c} for c in console)
            report["network"].extend({"mode": mode, "viewport": vname, "failed": f} for f in failed)
            report["fetches"].extend({"mode": mode, "viewport": vname, "url": f} for f in fetches)
            ctx.close()
        pg = b.new_page()
        for path in ("/api/docs", "/api/openapi.json", "/docs", "/openapi.json"):
            report["removed_surface"].append({"mode": mode, "path": path, "status": pg.goto(base + path).status})
        b.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--demo", default="http://127.0.0.1:8000")
    ap.add_argument("--real", default="http://127.0.0.1:8001")
    args = ap.parse_args()
    report = {"phase": args.phase, "captured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
              "items": [], "console": [], "network": [], "fetches": [], "keyboard": [], "removed_surface": []}
    pub = ROOT / "tests" / "product_evidence" / "ui_audit" / args.phase
    run(args.demo, "DEMO", pub, report)
    if args.real:
        run(args.real, "REAL", ROOT / "tests" / "product_evidence" / "private" / "ui_audit" / args.phase, report)
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [i for i in report["items"] if i["issues"]]
    print(f"items={len(report['items'])} with_issues={len(bad)} console_errors={len(report['console'])} "
          f"failed_requests={len(report['network'])} browser_data_fetches={len(report['fetches'])}")
    for i in bad:
        print(i["mode"], i["viewport"], i["page"], "|", "; ".join(i["issues"]))
    for c in report["console"][:10]:
        print("CONSOLE", c)
    print("REMOVED", [(r["mode"], r["path"], r["status"]) for r in report["removed_surface"]])
    print("KEYBOARD", sorted({k["first_tab_stop"]["cls"] for k in report["keyboard"]}))
    return 0 if not bad and not report["console"] and not report["network"] and not report["fetches"] else 1


if __name__ == "__main__":
    sys.exit(main())
