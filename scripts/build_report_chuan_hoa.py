"""FINAL report built on the user's standardized 42-page report (report/final/base/MarketLabVN30_FINAL_CHUAN_HOA_THEO_MAU.docx).

uv run --no-project --with python-docx --with pillow python scripts/build_report_chuan_hoa.py
-> report/final/MarketLabVN30_FINAL_CHUAN_HOA_SSMS.docx (then scripts/Finalize-Report.ps1 -Docx ... updates the TOC fields
   and exports the PDF). The base file and the FINAL v2 report are only read.

Edits are targeted: real SSMS screenshots inserted in chapters 2-4 next to the matching SQL, Web FINAL figures (6 pages)
replace the old screenshots in chapter 5, verified figures (28,097 rows, 30 tickers, 956 sessions, VPL limit, backfill,
EOD, 140/140 tests) replace outdated ones, wrong cross references (mục 3.6) fixed, figure/table numbers renumbered and the
static table of contents / lists replaced by Word fields. Every change is recorded in report/final/CHANGELOG_CHUAN_HOA.md.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "report" / "final" / "base" / "MarketLabVN30_FINAL_CHUAN_HOA_THEO_MAU.docx"
OUT = ROOT / "report" / "final" / "MarketLabVN30_FINAL_CHUAN_HOA_SSMS.docx"
SSMS = ROOT / "report" / "final" / "evidence" / "ssms"
WEB = ROOT / "report" / "final" / "assets" / "web_final"
CROP = ROOT / "var" / "report_build"
LOG: dict[str, list[str]] = {"Bổ sung": [], "Cập nhật": [], "Loại bỏ": [], "Giữ lại": []}

doc = Document(BASE)
body = doc.element.body


def paras():
    return list(doc.paragraphs)


def find(prefix: str, style: str | None = None):
    for p in paras():
        if p.text.strip().startswith(prefix) and (style is None or p.style.name == style):
            return p
    raise KeyError(prefix)


def find_contains(fragment: str):
    for p in paras():
        if fragment in p.text and not p.style.name.startswith("toc"):
            return p
    raise KeyError(fragment)


def set_text(p, text: str) -> None:
    runs = [r for r in p.runs if r._r.find(qn("w:t")) is not None]
    if not runs:
        p.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def replace_in(p, old: str, new: str) -> None:
    assert old in p.text, (old, p.text[:120])
    set_text(p, p.text.replace(old, new))


# ---- templates cloned from the base so new content keeps its exact formatting ----------------------------------------
T_NORMAL = find("MarketLab VN30 là hệ thống quản lý dữ liệu")._p
T_CODE = find("SELECT DB_NAME() AS DatabaseName;")._p
T_IMG = next(p for p in paras() if p._p.findall(".//" + qn("w:drawing")))._p
T_CAPFIG = find("Hình 1.", "Caption Figure")._p
T_CAPTAB = find("Bảng 24.", "Caption Table")._p
T_H3 = find("5.5.6.", "Heading 3")._p
T_LABEL = find("TRUY VẤN Q01")._p


def clone_para(template, text: str):
    el = copy.deepcopy(template)
    for child in list(el):
        if child.tag != qn("w:pPr"):
            el.remove(child)
    r = OxmlElement("w:r")
    src_r = template.find(qn("w:r"))
    if src_r is not None and src_r.find(qn("w:rPr")) is not None:
        r.append(copy.deepcopy(src_r.find(qn("w:rPr"))))
    t = OxmlElement("w:t")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    r.append(t)
    el.append(r)
    return el


def after(anchor_el, new_el):
    anchor_el.addnext(new_el)
    return new_el


def add_para(anchor_el, text: str, template=None):
    return after(anchor_el, clone_para(template if template is not None else T_NORMAL, text))


def add_code(anchor_el, lines: list[str]):
    el = anchor_el
    for line in lines:
        el = after(el, clone_para(T_CODE, line))
    return el


def fit(path: Path, max_h: int | None) -> Path:
    if not max_h:
        return path
    with Image.open(path) as im:
        if im.size[1] <= max_h:
            return path
        CROP.mkdir(parents=True, exist_ok=True)
        out = CROP / f"top_{path.name}"
        im.crop((0, 0, im.size[0], max_h)).save(out)
        return out


def trim_blank_bands(path: Path, min_run: int = 28, keep: int = 10) -> Path:
    """Report copy of a query screenshot without the empty editor/result bands (the evidence PNG is not modified)."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    def blank(y):
        vals = [px[x, y] for x in range(70, w - 60, 6)]
        return all(abs(v[0] - vals[0][0]) < 6 and abs(v[1] - vals[0][1]) < 6 and abs(v[2] - vals[0][2]) < 6 for v in vals)
    rows, y = [], 0
    while y < h:
        if blank(y):
            start = y
            while y < h and blank(y):
                y += 1
            if y - start >= min_run:
                rows.append((start + keep, y - keep))
        y += 1
    if not rows:
        return path
    keep_parts, last = [], 0
    for a, b in rows:
        keep_parts.append((last, a))
        last = b
    keep_parts.append((last, h))
    out = Image.new("RGB", (w, sum(b - a for a, b in keep_parts)), "white")
    yy = 0
    for a, b in keep_parts:
        out.paste(im.crop((0, a, w, b)), (0, yy))
        yy += b - a
    CROP.mkdir(parents=True, exist_ok=True)
    dst = CROP / f"trim_{path.name}"
    out.save(dst)
    return dst


def add_figure(anchor_el, img: Path, caption: str, width_cm: float, max_h: int | None = None):
    """Picture paragraph (formatting of the base picture paragraphs) + caption in style Caption Figure."""
    img = fit(img, max_h)
    tmp = doc.add_paragraph()
    tmp.add_run().add_picture(str(img), width=Cm(width_cm))
    pic = copy.deepcopy(T_IMG)
    for child in list(pic):
        if child.tag != qn("w:pPr"):
            pic.remove(child)
    for r in tmp._p.findall(qn("w:r")):
        pic.append(r)
    tmp._p.getparent().remove(tmp._p)
    keep = OxmlElement("w:keepNext")
    ppr = pic.find(qn("w:pPr"))
    if ppr is not None and ppr.find(qn("w:keepNext")) is None:
        style = ppr.find(qn("w:pStyle"))
        ppr.insert(1 if style is not None else 0, keep)      # schema order: pStyle, keepNext, ...
    after(anchor_el, pic)
    return after(pic, clone_para(T_CAPFIG, caption))


def replace_figure(caption_prefix: str, img: Path, caption: str, width_cm: float, max_h: int | None = None):
    """Swap the picture right before an existing caption and rewrite the caption."""
    cap = find(caption_prefix, "Caption Figure")
    pic = cap._p.getprevious()
    assert pic is not None and pic.findall(".//" + qn("w:drawing")), caption_prefix
    anchor = pic.getprevious()
    pic.getparent().remove(pic)
    cap._p.getparent().remove(cap._p)
    return add_figure(anchor, img, caption, width_cm, max_h)


def remove_figure(caption_prefix: str):
    cap = find(caption_prefix, "Caption Figure")
    pic = cap._p.getprevious()
    assert pic.findall(".//" + qn("w:drawing"))
    pic.getparent().remove(pic)
    cap._p.getparent().remove(cap._p)


def table_after(anchor_el, template_tbl, rows: list[list[str]], caption: str):
    """Caption (Caption Table) + a copy of a base table with the same column count, filled with rows."""
    cap = after(anchor_el, clone_para(T_CAPTAB, caption))
    tbl = copy.deepcopy(template_tbl._tbl)
    trs = tbl.findall(qn("w:tr"))
    head, body_tpl = trs[0], trs[1]
    for tr in trs[1:]:
        tbl.remove(tr)
    from docx.table import Table
    t = Table(tbl, template_tbl._parent)
    for _ in rows[1:]:                      # the template header row stays; one body row per data row
        tbl.append(copy.deepcopy(body_tpl))
    t = Table(tbl, template_tbl._parent)
    for r, values in zip(t.rows, rows):
        for c, v in zip(r.cells, values):
            set_text(c.paragraphs[0], v)
    after(cap, tbl)
    return tbl


def table_by_header(first_cell: str, contains: str | None = None):
    for t in doc.tables:
        if t.rows[0].cells[0].text.strip() == first_cell and (contains is None or any(contains in c.text for r in t.rows for c in r.cells)):
            return t
    raise KeyError(first_cell)


def set_row(t, first: str, values: list[str]) -> None:
    for r in t.rows:
        if r.cells[0].text.strip() == first:
            for c, v in zip(r.cells[1:], values):
                if v is not None:
                    set_text(c.paragraphs[0], v)
            return
    raise KeyError(first)


def add_row(t, values: list[str], like_row: int = -1) -> None:
    tr = copy.deepcopy(t.rows[like_row]._tr)
    t.rows[-1]._tr.addnext(tr)
    from docx.table import _Row
    row = _Row(tr, t)
    for c, v in zip(row.cells, values):
        set_text(c.paragraphs[0], v)


def toc_field(p_el, instr: str, placeholder: str):
    for child in list(p_el):
        if child.tag != qn("w:pPr"):
            p_el.remove(child)

    def run_with(tag, **attrs):
        r = OxmlElement("w:r")
        e = OxmlElement(tag)
        for k, v in attrs.items():
            e.set(qn(k), v)
        r.append(e)
        return r, e
    r1, _ = run_with("w:fldChar", **{"w:fldCharType": "begin", "w:dirty": "true"})
    r2, it = run_with("w:instrText")
    it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    it.text = f" {instr} "
    r3, _ = run_with("w:fldChar", **{"w:fldCharType": "separate"})
    r4, tx = run_with("w:t")
    tx.text = placeholder
    r5, _ = run_with("w:fldChar", **{"w:fldCharType": "end"})
    for r in (r1, r2, r3, r4, r5):
        p_el.append(r)


def static_list_to_field(heading: str, next_heading: str, instr: str, placeholder: str) -> None:
    h = find(heading)
    end = find(next_heading)._p
    items = []
    el = h._p.getnext()
    while el is not None and el is not end:
        items.append(el)
        el = el.getnext()
    first = items[0]
    toc_field(first, instr, placeholder)
    for x in items[1:]:
        keep_break = x.findall(".//" + qn("w:br")) and any(b.get(qn("w:type")) == "page" for b in x.findall(".//" + qn("w:br")))
        if keep_break or x.find(".//" + qn("w:sectPr")) is not None:
            for r in x.findall(qn("w:r")):
                if r.find(qn("w:br")) is None:
                    x.remove(r)
            continue
        x.getparent().remove(x)


SQL_DEMO = "SSMS, MarketLabVN30_Demo"

# =================================================================================================================
# Chapter 1
p = find("Bản thiết kế trước đó dự kiến một local API Gateway")
replace_in(p, "thao tác ghi duy nhất (đồng bộ một phiên) là biểu mẫu HTML có token và chống CSRF",
           "hai thao tác ghi (đồng bộ một phiên và nạp dữ liệu lịch sử) là biểu mẫu HTML có token và chống CSRF")
LOG["Cập nhật"].append("1.2.1: hai thao tác ghi qua biểu mẫu (đồng bộ phiên, backfill lịch sử) thay cho “thao tác ghi duy nhất”.")
p = find("Trường Dataset.DataKind quy định loại nguồn")
replace_in(p, "(mục 3.6)", "(mục 3.4)")
LOG["Cập nhật"].append("1.3.1, 5.5.4, 5.6: sửa tham chiếu “mục 3.6” (không tồn tại) thành “mục 3.4”.")
t3 = table_by_header("Phạm vi", "Đồng bộ cuối phiên")
set_row(t3, "Đồng bộ cuối phiên", ["DB MarketLabVN30_Live: 28.097 dòng OHLCV thật của 30 mã, 956 phiên từ 03/01/2023 đến 05/11/2026",
                                  "Nguồn KBS/vnstock 3.5.1; VPL chỉ có dữ liệu từ 13/05/2025; dữ liệu riêng tư, không đưa lên GitHub"])
LOG["Cập nhật"].append("Bảng 3: phạm vi Live 780 dòng/26 phiên → 28.097 dòng, 30 mã, 956 phiên 03/01/2023–05/11/2026; giới hạn VPL.")
p = find("Vũ trụ mã dùng trong phân tích nghiên cứu")
add_para(p._p, "Với database Live, giao diện và báo cáo ghi rõ “30 mã thuộc universe được cấu hình (tham chiếu VN30 06/2026)”: dữ liệu "
               "giá từ năm 2023 của 30 mã này không có nghĩa cả 30 mã đều thuộc VN30 tại mọi thời điểm từ 2023.")
LOG["Bổ sung"].append("1.4: một câu phân biệt universe cấu hình với thành phần VN30 lịch sử khi dữ liệu Live kéo về 2023.")

# =================================================================================================================
# Chapter 2: relationships from the real database, constraints of typical tables
cap = find("Hình 2.", "Caption Figure")
txt = find("Sơ đồ gốc cần được đọc theo cặp khóa ngoại")
p = add_para(cap._p, "Database MarketLabVN30_Demo trên SQL Server chưa có Database Diagram (thư mục Database Diagrams trống; tạo sơ đồ sẽ "
                     "thêm bảng hệ thống sysdiagrams vào database đang được kiểm thử có đúng 13 bảng). Vì vậy quan hệ PK/FK thực tế được "
                     "kiểm chứng bằng truy vấn danh mục hệ thống sys.foreign_keys trong SSMS: 16 khóa ngoại khớp với sơ đồ ở Hình 1.")
add_figure(p, trim_blank_bands(SSMS / "02_erd_relationships.png"), f"Hình 2a. Mười sáu quan hệ khóa ngoại giữa 13 bảng ({SQL_DEMO}).", 14.5)
LOG["Bổ sung"].append("2.1: ảnh SSMS 16 khóa ngoại (sys.foreign_keys) + ghi chú Demo không có Database Diagram; giữ nguyên Hình 1–2 của bản nền.")

p = find("Trên bảng DailyPrice, chỉ kiểm tra CHECK trực tiếp")
add_figure(p._p, trim_blank_bands(SSMS / "03_table_constraints.png"),
           f"Hình 2b. Ràng buộc PK, UNIQUE, FK và CHECK của Stock, Dataset, DailyPrice, ModelRun, Prediction ({SQL_DEMO}).", 14.5)
LOG["Bổ sung"].append("2.4: ảnh SSMS ràng buộc của 5 bảng tiêu biểu (17 nhóm ràng buộc).")

t19 = table_by_header("Bảng", "ops.EodConfig")
set_row(t19, "ops.SchemaVersion", [None, "Phiên bản schema (v1–v3)", None])
add_row(t19, ["ops.BackfillJob, BackfillFetch, BackfillStaging, BackfillReject, BackfillSession", "JobId; (JobId, Ticker, …)",
              "Nạp lịch sử: tham số job, điểm dừng theo mã × năm, vùng đệm giá đã kiểm tra, dòng bị từ chối, kết quả từng phiên",
              "Staging có CHECK OHLCV; phiên COMPLETE chỉ khi đủ mã"])
LOG["Cập nhật"].append("Bảng 19: schema Ops v1–v3, thêm một dòng cho nhóm bảng backfill.")

# =================================================================================================================
# Chapter 3
p = find("Các bước triển khai: chạy sql/all_in_one.sql")
add_figure(find("ORDER BY name;")._p, SSMS / "01_database_tables.png",
           f"Hình 2c. Object Explorer và kết quả truy vấn 13 bảng nghiệp vụ ({SQL_DEMO}).", 15.5)
LOG["Bổ sung"].append("3.1: ảnh SSMS Object Explorer (Tables) + truy vấn sys.tables: 13 bảng, số cột, số dòng.")

p = find("Cơ sở dữ liệu Live cập nhật giá cuối phiên qua thủ tục")
p2 = add_para(p._p, "Dữ liệu lịch sử của Live được nạp bằng chính quy trình này: giá từ nguồn được kiểm tra rồi đưa vào bảng đệm trong "
                    "database Ops, sau đó mỗi phiên được ghi bằng một transaction qua ops.usp_EodApplySession. Chỉ nhận dữ liệu từ "
                    "01/01/2023; cùng khóa cùng giá trị thì bỏ qua, cùng khóa khác giá trị thì đưa vào hàng đợi đối soát và giữ "
                    "nguyên giá đã lưu. Kết quả trên MarketLabVN30_Live: 28.097 dòng OHLCV của 30 mã, 956 phiên từ 03/01/2023 đến "
                    "05/11/2026; VPL chỉ có 373 phiên vì nguồn không có dữ liệu trước ngày 13/05/2025. 13 bảng nghiệp vụ không đổi "
                    "lược đồ; chỉ database Ops có thêm bảng phục vụ nạp lịch sử.")
add_figure(p2, trim_blank_bands(SSMS / "11_live_data_summary.png"),
           "Hình 2d. Thống kê tổng hợp dữ liệu thật 2023–2026 (SSMS, MarketLabVN30_Live, chỉ đọc, không hiển thị giá).", 14.5)
LOG["Bổ sung"].append("3.4: đoạn mô tả backfill trên SQL Server + ảnh SSMS thống kê Live (28.097 dòng, 30 mã, 956 phiên, theo năm, VPL).")

# =================================================================================================================
# Chapter 4: screenshots next to the SQL they show
add_figure(find("ORDER BY Ticker;", None)._p, trim_blank_bands(SSMS / "04_select_query.png"), f"Hình 2e. Kết quả Q01 – danh sách cổ phiếu ({SQL_DEMO}).", 14.5)
q03_end = [p for p in paras() if p.text.strip() == "ORDER BY s.Ticker;"][-1]
add_figure(q03_end._p, trim_blank_bands(SSMS / "05_join_query.png"), f"Hình 2f. Kết quả Q02 (INNER JOIN) và Q03 (LEFT JOIN) ({SQL_DEMO}).", 14.5)
q07_end = find("ORDER BY p.StockId, p.TradeDate;")
add_figure(q07_end._p, trim_blank_bands(SSMS / "06_groupby_having_subquery.png"), f"Hình 2g. Kết quả Q05 (GROUP BY), Q06 (HAVING) và Q07 (truy vấn lồng) ({SQL_DEMO}).", 14.5)
q10 = [p for p in paras() if p.text.strip() == "SELECT StockId FROM dbo.Prediction;"][-1]
add_figure(q10._p, trim_blank_bands(SSMS / "07_set_operations.png"), f"Hình 2h. Kết quả Q08 (UNION), Q09 (INTERSECT) và Q10 (EXCEPT, 0 dòng) ({SQL_DEMO}).", 14.5)
LOG["Bổ sung"].append("4.1: 4 ảnh SSMS ngay sau câu SQL tương ứng (Q01; Q02–Q03; Q05–Q07; Q08–Q10). Giữ nguyên 16 truy vấn của bản nền.")
p = find("vw_ModelPerformance sử dụng ngày đánh giá theo thời điểm hệ thống")
add_figure(p._p, SSMS / "08_views.png", f"Hình 2i. Bốn View trong Object Explorer và kết quả vw_ModelPerformance ({SQL_DEMO}).", 15.5)
p = find("Thủ tục chỉ tổng hợp dự báo đã có đủ giá")
add_figure(p._p, SSMS / "09_stored_procedures.png",
           f"Hình 2j. Bốn Stored Procedure và kết quả EXEC usp_GetModelPerformance (128 dòng, Accuracy 0,546875) ({SQL_DEMO}).", 15.5)
p = find("Hàm fn_EligiblePredictions chỉ trả về dự báo khi")
add_figure(p._p, SSMS / "10_functions.png", f"Hình 2k. Ba Function và ví dụ gọi fn_CalculateReturn, fn_EligiblePredictions ({SQL_DEMO}).", 15.5)
LOG["Bổ sung"].append("4.2–4.4: ảnh SSMS cho Views, Stored Procedures (EXEC chỉ đọc), Functions. Bảng tóm tắt và ví dụ rút gọn của bản nền giữ nguyên.")
p = find("Nhóm kiểm thử các ràng buộc PK, FK, CHECK và transaction")
replace_in(p, "trên database kiểm thử riêng", "trên database DEMO trong transaction có hoàn tác")
add_figure(p._p.getprevious(), trim_blank_bands(SSMS / "12_constraint_test.png"),
           f"Hình 2l. Kiểm thử CHECK: Volume âm bị từ chối (lỗi 547, CK_DailyPrice_Volume), giá trị và số transaction mở không đổi ({SQL_DEMO}).", 14.5)
LOG["Bổ sung"].append("4.5: ảnh SSMS ca kiểm thử CHECK (lỗi 547, rollback, Volume trước = sau).")
p = find("Theo hồ sơ kiểm thử bàn giao của nhóm")
set_text(p, "Bộ 44 ca SQL gốc và 16 truy vấn nghiệp vụ được chạy lại ngày 06/11/2026 trên MarketLabVN30_Demo: tất cả đạt và dữ liệu 13 "
            "bảng không thay đổi sau quá trình kiểm thử. Phần ứng dụng web, EOD và nạp lịch sử có 140/140 ca kiểm thử tự động đạt; lịch "
            "tự chạy theo giờ trên Windows vẫn chưa được bật nên chưa xác minh.")
LOG["Cập nhật"].append("4.5: 102 ca → 140/140; regression SQL chạy lại 06/11/2026.")

# =================================================================================================================
# Chapter 5: Web FINAL (6 pages), backfill, EOD
p = find("Ứng dụng web kết nối SQL Server bằng lớp xử lý Python phía máy chủ")
replace_in(p, "Các nghiệp vụ nạp giá cuối phiên chạy qua worker độc lập;",
           "Các nghiệp vụ nạp giá cuối phiên và nạp dữ liệu lịch sử chạy qua worker độc lập;")
t21 = table_by_header("Đường dẫn", "marketlab_app/web_app.py")
set_row(t21, "marketlab_app/templates/*.html", ["10 template Jinja2: base, macros, 6 trang, 2 trang job, trang lỗi"])
set_row(t21, "marketlab_app/eod/", ["service.py (EOD), backfill.py (nạp lịch sử), backup.py, coverage.py, normalize.py, providers.py, opsstore.py"])
set_row(t21, "sql/13_*.sql, 14_*.sql, 15_*.sql", ["Migration EOD, database Ops (v1–v3), preflight, rollback"])
set_row(t21, "scripts/*.ps1", ["Setup, Start, Stop, Run-MarketLab-EOD, Backfill-MarketLab, Install-MarketLab-EODTask"])
set_row(t21, "tests/product/", ["140 ca kiểm thử"])
LOG["Cập nhật"].append("Bảng 21: template, module backfill, script Backfill-MarketLab, 140 ca kiểm thử.")
p = find("Giao diện có năm khu vực")
set_text(p, "Giao diện có sáu trang chức năng: Tổng quan, Lịch sử OHLCV, Dự báo & hiệu năng, So sánh mô hình, Vận hành EOD và Backfill "
            "lịch sử. Trạng thái bộ lọc nằm trên địa chỉ trang nên tải lại không làm mất bộ lọc. Đầu trang luôn hiện nhãn LIVE hoặc "
            "DEMO và phạm vi dữ liệu. Ảnh dưới đây được chụp tự động bằng Microsoft Edge từ ứng dụng đang chạy ngày 06/11/2026; ảnh LIVE "
            "đã làm mờ ô giá, khối lượng và biểu đồ giá.")
p = find("Trang tổng quan hiển thị ngày giá mới nhất")
set_text(p, "Trang tổng quan hiển thị số mã có giá, số phiên có dữ liệu, phạm vi ngày thực tế, số dòng DailyPrice, giá mới nhất kèm trạng "
            "thái độ mới, tình trạng thiếu dữ liệu, phiên đồng bộ thành công gần nhất và lần nạp lịch sử. Với Live: 30 mã, 956 phiên, "
            "03/01/2023 → 05/11/2026, 28.097 dòng, không có phiên thiếu ngoài giới hạn VPL. Khi dataset chưa có ModelRun, thẻ dự báo hiển "
            "thị “—” kèm giải thích thay vì số 0.")
replace_figure("Hình 4.", WEB / "01_live_dashboard_1440.png", "Hình 4. Trang Tổng quan của database Live sau khi nạp dữ liệu 2023–2026.", 15.5, 1250)
remove_figure("Hình 5.")
h = find("5.3.2. Giá và biểu đồ", "Heading 3")
set_text(h, "5.3.2. Tra cứu lịch sử OHLCV")
p = find("Người dùng nhập mã (có gợi ý từ danh sách mã của dataset)")
set_text(p, "Người dùng chọn một trong 30 mã và khoảng ngày; ở chế độ Live, máy chủ từ chối ngày bắt đầu trước 01/01/2023 trước khi truy "
            "vấn. Mặc định trang hiện 12 tháng gần nhất; có nút chọn nhanh 3 tháng đến toàn bộ. Biểu đồ gồm Close (đường) và Volume (cột), "
            "có chú giải đơn vị, tooltip và phóng to theo đoạn; phiên thiếu giá không được nối hay nội suy. Bảng OHLCV bên dưới lấy từ "
            "cùng truy vấn tham số hóa theo mã, dataset và khoảng ngày, có sắp xếp, phân trang và xuất CSV.")
replace_figure("Hình 6.", WEB / "03_live_ohlcv_2023_all_1440.png", "Hình 5. Lịch sử OHLCV của FPT 03/01/2023–05/11/2026 (956 phiên).", 15.5)
remove_figure("Hình 7.")
replace_figure("Hình 8.", WEB / "12_demo_forecast_1440.png", "Hình 6. Trang Dự báo và hiệu năng tại as_of 01/07/2026.", 15.5)
replace_figure("Hình 9.", WEB / "11_demo_compare_1440.png", "Hình 7. So sánh run 1 và 2 trên 128 quan sát chung.", 15.5)
p = find("Trang vận hành phân biệt bốn mốc ngày")
replace_in(p, "Biểu mẫu Dry run / Sync ghi rõ phạm vi ghi;", "Nhật ký chỉ gồm các lần chạy EOD hằng ngày. Biểu mẫu Dry run / Sync ghi rõ phạm vi ghi;")
cap10 = replace_figure("Hình 10.", WEB / "08_live_eod_ops_1440.png", "Hình 8. Trạng thái và nhật ký đồng bộ cuối phiên.", 15.5, 1250)
h = after(cap10, clone_para(T_H3, "5.3.6. Backfill lịch sử"))
p = add_para(h, "Trang Backfill lịch sử theo dõi các lần nạp dữ liệu 2023–2026: khoảng ngày, trạng thái, số phiên đã xử lý, số dòng thêm "
                "mới, không đổi, thiếu, trước lịch sử nguồn và xung đột; kết quả tải từng mã theo năm; độ phủ của từng mã truy vấn trực "
                "tiếp DailyPrice × TradingDay. Biểu mẫu Dry run / Backfill / Tiếp tục yêu cầu token, chống CSRF và xác nhận trước khi ghi.")
add_figure(p, WEB / "07_live_backfill_1440.png", "Hình 9. Trang Backfill lịch sử của database Live.", 15.5, 1250)
h = find("5.3.6. Hiển thị trên thiết bị nhỏ và trạng thái lỗi", "Heading 3")
set_text(h, "5.3.7. Hiển thị trên thiết bị nhỏ và trạng thái lỗi")
p = find("Giao diện được kiểm tra ở bốn kích thước 1440×900, 1366×768")
replace_in(p, "1366×768", "1280×800")
LOG["Cập nhật"].append("5.3: năm → sáu trang chức năng; mô tả Tổng quan, Lịch sử OHLCV (sàn 01/01/2023, 12 tháng mặc định, CSV), EOD; khung 1280×800.")
LOG["Bổ sung"].append("5.3.6: trang Backfill lịch sử (Hình 9).")
LOG["Loại bỏ"].append("Hình 5 cũ (Tổng quan REAL 780 dòng) và Hình 7 cũ (bảng OHLCV DEMO03): gộp vào ảnh Web FINAL mới, giảm số ảnh giao diện.")
LOG["Cập nhật"].append("Hình 4, 6, 8, 9, 10 cũ: thay bằng ảnh Web FINAL chụp 06/11/2026 (Tổng quan Live, Lịch sử OHLCV FPT 2023–2026, Dự báo, So sánh, Vận hành EOD).")

t22 = table_by_header("Route", "/ops/jobs/")
add_row(t22, ["/backfill, /backfill/run", "GET, POST (form)", "ds, job; csrf, ops_token, start_date, end_date, action",
              "ops.BackfillJob/Session; khởi chạy nạp lịch sử (nền)", "200, 303, 401, 403, 409, 422"])
add_row(t22, ["/market/export.csv", "GET", "ds, t, f, to", "Cùng bộ lọc và sàn ngày, tối đa 5.000 dòng", "200, 422"])
LOG["Cập nhật"].append("Bảng 22: thêm route /backfill, /backfill/run và /market/export.csv.")

p = find("Toàn bộ phiên được ghi qua ops.usp_EodApplySession")
replace_in(p, "(mục 3.6)", "(mục 3.4)")
p = find("Đối với cơ sở dữ liệu MarketLabVN30_Live, nhóm sử dụng nguồn KBS qua vnstock")
set_text(p, "Đối với cơ sở dữ liệu MarketLabVN30_Live, nhóm sử dụng nguồn KBS qua vnstock cho 30 mã thuộc universe được cấu hình "
            "(tham chiếu VN30 tháng 06/2026). Đợt đồng bộ ban đầu đến ngày 05/11/2026 ghi nhận 780 dòng OHLCV thuộc 26 phiên; sau đó "
            "dữ liệu được nạp lùi về 2023 (mục 5.5.7). Chạy lại cùng một phiên không tạo dữ liệu trùng: phiên 05/11/2026 chạy lại cho "
            "0 dòng mới, 30 dòng không đổi; trường hợp thiếu nến hoặc sai giá bị từ chối trước khi ghi.")
p = find("Kết quả này chứng minh quy trình cập nhật dữ liệu đã vận hành")
h = after(p._p, clone_para(T_H3, "5.5.7. Nạp dữ liệu lịch sử 2023–2026"))
p = add_para(h, "Quy trình nạp lịch sử tái sử dụng các bước của EOD: lấy nến ngày từ nguồn theo từng mã và từng năm, kiểm tra OHLCV, "
                "lưu vào bảng đệm của database Ops, rồi ghi từng phiên bằng ops.usp_EodApplySession. Trước khi ghi, hệ thống sao lưu "
                "database Live và Ops, kiểm tra bản sao lưu bằng cách khôi phục thử. Ngày nghỉ và cuối tuần không bị tính là thiếu; "
                "phiên thiếu mã được ghi nhận là chưa đủ, không bao giờ được tính là đủ 30 mã. Nếu bị gián đoạn, lần chạy sau tiếp tục "
                "từ điểm dừng mà không tải lại toàn bộ.")
tbl = table_after(p, table_by_header("Trạng thái", "DRY_RUN_OK"), [
    ["Chỉ tiêu", "Kết quả ngày 06/11/2026", "Ghi chú", "Trạng thái"],
    ["Dòng OHLCV / mã / phiên", "28.097 / 30 / 956", "03/01/2023 → 05/11/2026", "Đạt"],
    ["Dòng thêm mới / không đổi", "27.317 / 780", "780 dòng có sẵn giữ nguyên giá trị", "Đạt"],
    ["Phiên thiếu, dòng bị từ chối, xung đột", "0 / 0 / 0", "Hàng đợi đối soát trống", "Đạt"],
    ["Giới hạn nguồn", "VPL: 583 phiên không có dữ liệu", "Nguồn chỉ có VPL từ 13/05/2025; không nội suy", "Ghi nhận"],
    ["Chạy lại cửa sổ 01–06/2023", "0 dòng mới / 3.509 không đổi", "Không nhân bản dữ liệu", "Đạt"],
    ["Dòng có TradeDate < 01/01/2023", "0", "Sàn lịch sử được áp dụng", "Đạt"],
], "Bảng 24a. Kết quả nạp dữ liệu lịch sử trên MarketLabVN30_Live")
LOG["Bổ sung"].append("5.5.7: quy trình nạp lịch sử 2023–2026 (đoạn ngắn) + Bảng kết quả (28.097 / 27.317 / 780 / 0 thiếu / VPL / chạy lại / sàn 2023).")
LOG["Cập nhật"].append("5.5.6: kết quả EOD ghi rõ giai đoạn 780 dòng ban đầu và chạy lại 05/11/2026; trỏ sang 5.5.7.")

p = find("Các thay đổi SQL được trình bày ở mục 2.5")
replace_in(p, "và 3.6 (migration, trigger, thủ tục)", "và 3.4 (migration, trigger, thủ tục)")
t28 = table_by_header("Thuộc tính", "ProviderMeta")
set_row(t28, "TriggerKind", [None, "CLI, SCHEDULER, WEB, TEST, BACKFILL (API cho các run lịch sử)"])
code_end = find("powershell -ExecutionPolicy Bypass -File scripts\\Run-MarketLab-EOD.ps1 -Date 2026-11-05 -DryRun")
add_code(code_end._p, ["powershell -ExecutionPolicy Bypass -File scripts\\Backfill-MarketLab.ps1 -StartDate 2023-01-01 -EndDate latest -DryRun"])
p = find("Giao diện được kiểm tra ở bốn kích thước, bao gồm màn hình máy tính")
set_text(p, "Bộ kiểm thử tự động của phần mở rộng có 140 ca và đạt 140/140, gồm kiểm thử đơn vị, tích hợp với database cô lập (trong "
            "đó có nạp lịch sử, chạy lại, xung đột, gián đoạn và hoàn tác), giao diện máy chủ và trình duyệt Edge. Giao diện được kiểm tra "
            "ở bốn kích thước, hai chế độ và sáu trang: 48/48 màn hình không lỗi. Số liệu trên trang được đối chiếu trực tiếp với SQL "
            "Server: DEMO 26/26 và LIVE 38/38 phép kiểm tra khớp.")
p = find("Giao diện được tinh chỉnh để sử dụng trên desktop và thiết bị nhỏ")
replace_in(p, "biểu đồ giá, dự báo, so sánh mô hình và vận hành EOD.", "lịch sử OHLCV, dự báo, so sánh mô hình, vận hành EOD và nạp lịch sử.")
t29 = table_by_header("Phút", "Chuyển sang REAL_PRIVATE")
set_row(t29, "3:30", ["Chuyển sang LIVE: Tổng quan, Lịch sử OHLCV, Backfill", "30 mã, 28.097 dòng 2023–2026; VPL từ 13/05/2025"])
LOG["Cập nhật"].append("5.6–5.10: TriggerKind BACKFILL, lệnh Backfill-MarketLab, kết quả kiểm thử 140/140 – 48/48 – 26/26 – 38/38, kịch bản demo.")

# =================================================================================================================
# Conclusion, appendix
p = find("Phần mở rộng đưa bài tập lớn từ demo SSMS")
set_text(p, "Phần mở rộng đưa bài tập lớn từ demo SSMS sang một ứng dụng chạy cục bộ: ứng dụng web dựng trang ở máy chủ từ SQL Server với "
            "sáu trang chức năng; tác vụ cuối phiên và quy trình nạp lịch sử đã đưa 28.097 dòng giá thật của 30 mã (956 phiên, "
            "03/01/2023–05/11/2026) vào database Live với transaction theo từng phiên, chạy lại không tạo trùng và nhật ký đầy đủ. Kiến "
            "trúc cuối bỏ lớp API Gateway để giảm bề mặt và độ phức tạp mà không mất chức năng.")
t30 = table_by_header("Yêu cầu", "Không API Gateway")
set_row(t30, "Ứng dụng web 5 khu vực, khớp SQL", ["Đối chiếu tự động DEMO 26/26, LIVE 38/38; 48/48 màn hình ở 4 kích thước", None])
for r in t30.rows:
    if r.cells[0].text.strip() == "Ứng dụng web 5 khu vực, khớp SQL":
        set_text(r.cells[0].paragraphs[0], "Ứng dụng web 6 trang, khớp SQL")
set_row(t30, "EOD với nguồn thật, idempotent, rollback", ["Chạy lại 05/11/2026: 0 dòng mới; PARTIAL/FAILED không ghi; 140/140 ca kiểm thử", None])
add_row(t30, ["Dữ liệu OHLCV thật 2023–2026", "28.097 dòng, 30 mã, 956 phiên; VPL từ 13/05/2025; 0 xung đột", "Đã kiểm chứng"], like_row=1)
LOG["Cập nhật"].append("Kết luận và Bảng 27: sáu trang, 28.097 dòng 2023–2026, 140/140, đối chiếu 26/26 – 38/38; thêm dòng dữ liệu 2023–2026.")
p = find("Giới hạn thứ nhất là tính hoàn chỉnh của nguồn dữ liệu")
replace_in(p, "nên không tái dựng được chính xác tất cả thay đổi thành phần lịch sử.",
           "nên không tái dựng được chính xác tất cả thay đổi thành phần lịch sử. Nguồn KBS không có dữ liệu VPL trước 13/05/2025.")
p = find("Giới hạn thứ hai là môi trường triển khai")
replace_in(p, "Quyền đẩy nhánh và tạo pull request lên GitHub bị chặn trong môi trường làm việc nên mã nguồn mới chỉ có trên nhánh cục bộ.",
           "Nhánh mã nguồn mới chưa được đẩy lên GitHub vì việc công bố cần chủ repository phê duyệt.")
p = find("Hướng phát triển: (1) bật và theo dõi lịch tự động")
replace_in(p, "(5) chụp bổ sung ảnh SSMS cho các ví dụ Chương 3–4; (6) chỉ sau đó", "(5) chỉ sau đó")
LOG["Loại bỏ"].append("Hướng phát triển: bỏ mục “chụp bổ sung ảnh SSMS” vì đã thực hiện.")
t31 = table_by_header("Tệp", "tests/product/")
set_row(t31, "sql/13_*.sql, 14_*.sql, 15_*.sql", ["Migration EOD, database Ops (v1–v3), preflight, rollback", None])
set_row(t31, "tests/product/", ["140 ca kiểm thử", "140 PASS"])
set_row(t31, "report/final/assets/screens/", ["Ảnh giao diện (screens/, web_final/) + manifest", None])
add_row(t31, ["report/final/evidence/ssms/", "12 ảnh SSMS thật + 12 script SQL + manifest", "Có, chụp 06/11/2026"])
p = find("SELECT COUNT(*) AS PriceRows FROM dbo.DailyPrice;")
replace_in(p, "Live 780", "Live 28097")
LOG["Cập nhật"].append("Phụ lục A: 140 ca, thư mục ảnh SSMS, số dòng Live 28097.")

# =================================================================================================================
# Figures and tables numbered in document order; static lists replaced by Word fields
fig_n = tab_n = 0
for p in paras():
    if p.style.name == "Caption Figure" and re.match(r"Hình \d+[a-z]?\.", p.text.strip()):
        fig_n += 1
        set_text(p, re.sub(r"^Hình \d+[a-z]?\.", f"Hình {fig_n}.", p.text.strip()))
    elif p.style.name == "Caption Table" and re.match(r"Bảng \d+[a-z]?\.", p.text.strip()):
        tab_n += 1
        set_text(p, re.sub(r"^Bảng \d+[a-z]?\.", f"Bảng {tab_n}.", p.text.strip()))
static_list_to_field("MỤC LỤC", "DANH MỤC HÌNH VẼ", 'TOC \\o "1-3" \\h \\z \\u', "Mục lục sẽ được Word cập nhật.")
static_list_to_field("DANH MỤC HÌNH VẼ", "DANH MỤC BẢNG BIỂU", 'TOC \\h \\z \\t "Caption Figure,1"', "Danh mục hình sẽ được Word cập nhật.")
static_list_to_field("DANH MỤC BẢNG BIỂU", "CHƯƠNG 1:", 'TOC \\h \\z \\t "Caption Table,1"', "Danh mục bảng sẽ được Word cập nhật.")
LOG["Cập nhật"].append(f"Đánh số lại theo thứ tự xuất hiện: {fig_n} hình, {tab_n} bảng; mục lục, danh mục hình, danh mục bảng thành trường Word.")
LOG["Giữ lại"] += [
    "Bìa, form PTIT, lời nói đầu, toàn bộ Chương 2 (13 bảng, đặc tả thuộc tính, chuẩn hóa 3NF, ràng buộc) và cách trình bày SQL ngắn theo mẫu.",
    "16 truy vấn Q01–Q16, 4 View, 4 Stored Procedure (bảng tóm tắt + 2 ví dụ EXEC), 3 Function, ví dụ kiểm thử CHECK của bản nền.",
    "Hình 1 (ERD thiết kế), Hình 2 (nhóm chức năng), Hình 3 (kiến trúc).",
    "Không đưa lại log lỗi dài, hash, bảng kết quả kỹ thuật thừa hay phần kiểm thử lặp lại đã được cắt giảm ở bản nền.",
]
doc.save(OUT)
(ROOT / "var" / "report_build" / "CHANGELOG_CHUAN_HOA.json").write_text(__import__("json").dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
print("saved", OUT, "figures", fig_n, "tables", tab_n)
