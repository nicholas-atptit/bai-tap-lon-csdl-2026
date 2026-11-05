"""Automated UI audit of RUNNING MarketLab servers with Microsoft Edge (Playwright, headless).

uv run python scripts/ui_audit.py --phase before --demo http://127.0.0.1:8000 --real http://127.0.0.1:8001
For every mode x viewport x tab: console errors, failed requests (status >= 400 other than expected),
horizontal page overflow, clipped/unlabelled controls, missing focus style, NaN/undefined text; full-page screenshots.
DEMO screenshots -> tests/product_evidence/ui_audit/<phase>/ ; REAL screenshots -> tests/product_evidence/private/ui_audit/<phase>/
(real market records stay out of git). Writes <phase>/audit.json. Read-only: never clicks write buttons.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = {"1440x900": (1440, 900), "1366x768": (1366, 768), "768x1024": (768, 1024), "390x844": (390, 844)}
TABS = ["overview", "market", "forecast", "compare", "ops"]

PROBE = """() => {
  const vw = document.documentElement.clientWidth;
  const issues = [];
  if (document.documentElement.scrollWidth > vw + 1) issues.push(`page horizontal overflow: ${document.documentElement.scrollWidth} > ${vw}`);
  const panel = document.querySelector('.tab-panel:not([hidden])') || document.body;
  for (const inp of panel.querySelectorAll('input, select, button')) {
    if (inp.offsetParent === null || inp.closest('.table-wrap')) continue;  // inside a horizontally scrollable table by design
    const r = inp.getBoundingClientRect();
    if (r.right > vw + 1) issues.push(`control clipped: ${inp.id || inp.textContent.trim().slice(0, 20)}`);
    if (inp.tagName !== 'BUTTON' && inp.type !== 'checkbox') {
      const labelled = inp.closest('label') || inp.getAttribute('aria-label') || (inp.id && document.querySelector(`label[for="${inp.id}"]`));
      if (!labelled) issues.push(`unlabelled control: ${inp.id || inp.name}`);
    }
  }
  const text = panel.innerText;
  if (/\\bNaN\\b|undefined/.test(text)) issues.push('NaN/undefined rendered');
  const empty = [...panel.querySelectorAll('.table-wrap, .chart')].filter(e => e.offsetParent !== null && e.innerText.trim() === '' && !e.querySelector('svg'));
  if (empty.length) issues.push(`${empty.length} empty container(s) without state message`);
  return issues;
}"""


def run(base: str, mode: str, out: Path, report: dict) -> None:
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        for vname, (w, h) in VIEWPORTS.items():
            ctx = b.new_context(bypass_csp=True, viewport={"width": w, "height": h})
            page = ctx.new_page()
            console, failed = [], []
            page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
            page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 400 else None)
            page.goto(base + "/")
            page.wait_for_timeout(1500)
            for tab in TABS:
                sel = f'[data-tab="{tab}"]'
                if page.locator(sel).count() == 0:
                    report["items"].append({"mode": mode, "viewport": vname, "tab": tab, "issues": ["tab not found"]})
                    continue
                page.locator(sel).first.click()
                page.wait_for_timeout(1800)
                issues = page.evaluate(PROBE)
                shot = out / f"{mode}_{vname}_{tab}.png"
                page.screenshot(path=str(shot), full_page=True)
                report["items"].append({"mode": mode, "viewport": vname, "tab": tab, "issues": issues, "screenshot": str(shot.relative_to(ROOT))})
            # keyboard: focus ring visible on first tab button
            page.keyboard.press("Tab")
            page.keyboard.press("Tab")
            focus = page.evaluate("() => { const e = document.activeElement; const s = getComputedStyle(e); return {tag: e.tagName, id: e.id, outline: s.outlineStyle + ' ' + s.outlineWidth, shadow: s.boxShadow}; }")
            report["focus"].append({"mode": mode, "viewport": vname, **focus})
            report["console"].extend({"mode": mode, "viewport": vname, "error": c} for c in console)
            report["network"].extend({"mode": mode, "viewport": vname, "failed": f} for f in failed)
            ctx.close()
        # swagger
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(base + "/api/docs")
        try:
            page.wait_for_selector(".opblock", timeout=10000)
            note = "rendered"
        except Exception:  # noqa: BLE001
            note = "NOT RENDERED: " + page.inner_text("#swagger-ui")[:160].replace("\n", " ")
        page.screenshot(path=str(out / f"{mode}_swagger.png"), full_page=False)
        report["swagger"].append({"mode": mode, "operations": page.locator(".opblock").count(), "status": note})
        ctx.close()
        b.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--demo", default="http://127.0.0.1:8000")
    ap.add_argument("--real", default="http://127.0.0.1:8001")
    args = ap.parse_args()
    report = {"phase": args.phase, "captured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
              "items": [], "console": [], "network": [], "focus": [], "swagger": []}
    pub = ROOT / "tests" / "product_evidence" / "ui_audit" / args.phase
    priv = ROOT / "tests" / "product_evidence" / "private" / "ui_audit" / args.phase
    run(args.demo, "DEMO", pub, report)
    if args.real:
        run(args.real, "REAL", priv, report)
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [i for i in report["items"] if i["issues"]]
    print(f"items={len(report['items'])} with_issues={len(bad)} console_errors={len(report['console'])} failed_requests={len(report['network'])}")
    for i in bad:
        print(i["mode"], i["viewport"], i["tab"], "|", "; ".join(i["issues"]))
    for c in report["console"][:20]:
        print("CONSOLE", c)
    for n in report["network"][:20]:
        print("NET", n)
    for f in report["focus"]:
        print("FOCUS", f)
    print("SWAGGER", report["swagger"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
