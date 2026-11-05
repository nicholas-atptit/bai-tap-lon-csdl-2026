"""Draw the final architecture diagram used in the report (design diagram, not a screenshot).

uv run --with matplotlib python scripts/draw_architecture.py  -> report/final/assets/architecture_final.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "report" / "final" / "assets" / "architecture_final.png"
plt.rcParams["font.family"] = "Times New Roman"
fig, ax = plt.subplots(figsize=(11, 7.4), dpi=200)
ax.set_xlim(0, 104)
ax.set_ylim(-2, 70)
ax.axis("off")

def box(x, y, w, h, title, lines, fc, ec="#1d3b63"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec=ec, lw=1.2))
    ax.text(x + w / 2, y + h - 2.4, title, ha="center", va="top", fontsize=10.5, weight="bold", color="#0b0b0b")
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, y + h - 6.0 - i * 2.75, ln, ha="center", va="top", fontsize=8.2, color="#2c2c2c")

def arrow(x1, y1, x2, y2, label="", both=False, dy=1.2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="<|-|>" if both else "-|>", mutation_scale=12, lw=1.2, color="#2a78d6"))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + dy, label, ha="center", va="bottom", fontsize=7.8, color="#23568f",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none"))

box(1, 46, 24, 19, "Trình duyệt", ["Edge / Chrome", "HTML + CSS", "enhance.js: vẽ biểu đồ", "từ dữ liệu nhúng (không gọi mạng)"], "#eef4fc")
box(36, 41, 30, 25, "Ứng dụng web Python", ["marketlab_app/web_app.py", "FastAPI (ASGI) + Jinja2 templates", "5 trang: /, /market, /forecast,", "/compare, /ops (+ form POST /ops/eod)", "CSRF, token, Host/Origin, CSP", "queries.py: truy vấn tham số hóa"], "#fffbea")
box(75, 35, 28, 31, "SQL Server (MSSQLSERVER)", ["MarketLabVN30_Demo (SYNTHETIC)", "MarketLabVN30_Live (REAL_PRIVATE)", "  13 bảng + schema ops (1 proc)", "MarketLabVN30_Research (chỉ đọc)", "MarketLabVN30_Ops (nhật ký v2)", "view / function / procedure /", "trigger giữ nguyên"], "#e2f3e9", ec="#0b6b37")
box(36, 2, 30, 27, "EOD Worker", ["marketlab_app/eod/service.py", "lịch phiên Asia/Ho_Chi_Minh", "validate OHLCV đủ 30 mã", "ops.usp_EodApplySession", "(all-or-nothing, applock)", "kích hoạt: PowerShell / Task", "Scheduler / form web"], "#fde6d8", ec="#9a3f15")
box(1, 5, 24, 19, "Nguồn KBS", ["vnstock (interpreter riêng)", "kbs_bridge.py chạy subprocess", "-I, timeout, retry, rate limit", "dữ liệu EOD, không realtime"], "#ece6fb", ec="#4b2f9a")

arrow(25.5, 55, 35.5, 55, "HTTP (HTML)", both=True, dy=1.5)
arrow(66.5, 55, 74.5, 55, "pyodbc", both=True, dy=1.5)
arrow(66.5, 16, 89, 34.5, "transaction + nhật ký", dy=1.0)
arrow(25.5, 14, 35.5, 14, "JSON nến", both=True, dy=1.5)
arrow(51, 40.5, 51, 29.5, "form Dry run / Sync", dy=-0.6)
ax.text(52, -1.5, "Sơ đồ thiết kế của nhóm — kiến trúc cuối: không có API Gateway, REST JSON cho giao diện hay Swagger; trình duyệt không kết nối SQL Server.",
        ha="center", fontsize=8.5, style="italic", color="#4a4f57")
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(OUT)
