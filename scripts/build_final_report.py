"""Build report/final/MarketLabVN30_FINAL.docx from a COPY of the team's 44-page template (never modified).

uv run --with python-docx python scripts/build_final_report.py
Then scripts/Finalize-Report.ps1 lets Microsoft Word update the TOC / list-of-figures / list-of-tables fields and export PDF.
Cover, styles, margins, headers/footers, Chapters 1-4 structure and the 13-table design are kept; statements that the
template marked as "planned / not verified" are updated only where this repository holds evidence (see
report/final/CLAIMS_EVIDENCE_MATRIX.md). Chapter 5 is rewritten for the final architecture (server-side web application,
no API gateway), Appendix B (instructions for an AI tool) is replaced by a claim-to-evidence table.
"""
from __future__ import annotations

import json
import re
import shutil
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "report" / "team" / "MarketLabVN30_BaoCao_CHI_TIET_GIU_FORM_GOC.docx"
OUT = ROOT / "report" / "final" / "MarketLabVN30_FINAL.docx"
SCREENS = ROOT / "report" / "final" / "assets" / "screens"
MANIFEST = {m["file"].split("/")[-1]: m for m in json.loads((SCREENS / "screens_manifest.json").read_text(encoding="utf-8"))}
WEB_FINAL = ROOT / "report" / "final" / "assets" / "web_final"
WEB_MANIFEST = {m["file"].split("/")[-1]: m for m in json.loads((WEB_FINAL / "manifest.json").read_text(encoding="utf-8"))}
SHA = "762c784"            # web application commit described by this report (final commit SHA is in QA_REPORT.md)

shutil.copyfile(TEMPLATE, OUT)
doc = Document(str(OUT))
body = doc.element.body

# ---------------------------------------------------------------------------------------------------------------
# styles: separate caption styles for real Word lists of figures / tables; front-matter headings out of the TOC
st = doc.styles
for name in ("Caption Figure", "Caption Table"):
    if name not in [s.name for s in st]:
        s = st.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = st["Caption Local"]
        s.quick_style = True
if "Heading Unnumbered" not in [s.name for s in st]:
    s = st.add_style("Heading Unnumbered", WD_STYLE_TYPE.PARAGRAPH)
    s.base_style = st["Heading 1"]
    ppr = s.element.get_or_add_pPr()
    ol = OxmlElement("w:outlineLvl")
    ol.set(qn("w:val"), "9")
    ppr.append(ol)


def paras():
    return doc.paragraphs


def find(prefix: str, style: str | None = None, start: int = 0):
    for i, p in enumerate(paras()):
        if i >= start and p.text.strip().startswith(prefix) and (style is None or p.style.name == style):
            return i, p
    raise KeyError(prefix)


def set_text(p, text: str):
    runs = p.runs
    if not runs:
        p.add_run(text)
        return
    # keep the formatting of the first run that carries text (template cells start with an empty, unformatted <w:r/>)
    keep = next((r for r in runs if r._r.find(qn("w:t")) is not None), runs[0])
    keep.text = text
    for r in runs:
        if r is not keep:
            r._r.getparent().remove(r._r)


def remove_between(start_el, end_el):
    """Remove body children from start_el (inclusive) up to end_el (exclusive)."""
    el = start_el
    while el is not None and el is not end_el:
        nxt = el.getnext()
        el.getparent().remove(el)
        el = nxt


def before_chapter(heading_p):
    """Anchor for content that belongs at the end of the previous chapter: skip back over the page-break paragraph."""
    el = heading_p._p.getprevious()
    while el is not None and el.tag == qn("w:p") and not "".join(el.itertext()).strip() and             any(b.get(qn("w:type")) == "page" for b in el.iter(qn("w:br"))):
        el = el.getprevious()
    return el


def after_table_gap(el):
    """Give a paragraph that directly follows a table some air (the template's tables are followed by spaced text)."""
    prev = el.getprevious()
    if prev is not None and prev.tag == qn("w:tbl"):
        from docx.text.paragraph import Paragraph
        Paragraph(el, None).paragraph_format.space_before = Pt(8)


class Cursor:
    def __init__(self, anchor_el):
        self.el = anchor_el

    def _place(self, el):
        self.el.addnext(el)
        self.el = el
        return el

    def para(self, text: str = "", style: str = "Normal", align=None, italic=False, size=None, indent=True):
        p = doc.add_paragraph(style=style)
        for i, part in enumerate(re.split(r"(\*\*[^*]+\*\*)", text)):
            if not part:
                continue
            bold = part.startswith("**") and part.endswith("**")
            r = p.add_run(part[2:-2] if bold else part)
            r.bold = bold or None
            if italic:
                r.italic = True
            if size:
                r.font.size = Pt(size)
        if align == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == "left":
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif style == "Normal" and not italic:
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if indent:
                p.paragraph_format.first_line_indent = Cm(0.75)
        el = self._place(p._p)
        after_table_gap(el)
        return el

    def heading(self, text, level):
        return self.para(text, f"Heading {level}")

    def bullets(self, items):
        for it in items:
            self.para(it, "List Bullet")

    def code(self, lines):
        for k, ln in enumerate(lines):
            p = doc.add_paragraph(style="Code Local")
            p.add_run(ln if ln else " ")
            if len(lines) <= 12 and k < len(lines) - 1:   # short blocks stay on one page
                p.paragraph_format.keep_with_next = True
            after_table_gap(self._place(p._p))

    def cap_table(self, text):
        return self.para(text, "Caption Table")

    def cap_fig(self, text, keep_next=False):
        el = self.para(text, "Caption Figure")
        if keep_next:
            from docx.text.paragraph import Paragraph
            Paragraph(el, None).paragraph_format.keep_with_next = True
        return el

    def image(self, path: Path, width_cm: float, max_height_cm: float = 20.5):
        """Insert a picture that always fits on one A4 page (tall full-page screenshots are scaled down)."""
        from PIL import Image as _Img
        with _Img.open(path) as im:
            w_px, h_px = im.size
        if width_cm * h_px / w_px > max_height_cm:
            width_cm = max_height_cm * w_px / h_px
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.first_line_indent = Cm(0)
        p.add_run().add_picture(str(path), width=Cm(width_cm))
        el = self._place(p._p)
        after_table_gap(el)
        return el

    def table(self, headers, rows, widths_cm):
        t = doc.add_table(rows=1 + len(rows), cols=len(headers))
        t.style = st["Table Grid"]
        tbl = t._tbl
        tblPr = tbl.tblPr
        # schema order inside w:tblPr: tblStyle, tblW, jc, ..., tblLayout, tblCellMar, tblLook
        jc = OxmlElement("w:jc")
        jc.set(qn("w:val"), "center")
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        look = tblPr.find(qn("w:tblLook"))
        tblW = tblPr.find(qn("w:tblW"))
        (tblW if tblW is not None else tblPr.find(qn("w:tblStyle"))).addnext(jc)
        if look is not None:
            look.addprevious(layout)
        else:
            tblPr.append(layout)
        widths = [Cm(w) for w in widths_cm]
        for gi, gc in enumerate(tbl.tblGrid.findall(qn("w:gridCol"))):
            gc.set(qn("w:w"), str(int(widths[gi].twips)))
        for ri, row in enumerate(t.rows):
            values = headers if ri == 0 else rows[ri - 1]
            if ri == 0:
                trPr = row._tr.get_or_add_trPr()
                h = OxmlElement("w:tblHeader")
                h.set(qn("w:val"), "true")
                trPr.append(h)
            cant = OxmlElement("w:cantSplit")
            row._tr.get_or_add_trPr().insert(0, cant)
            for ci, cell in enumerate(row.cells):
                cell.width = widths[ci]
                tcPr = cell._tc.get_or_add_tcPr()
                # schema order inside w:tcPr: tcW, ..., shd, ..., vAlign
                if ri == 0:
                    shd = OxmlElement("w:shd")
                    shd.set(qn("w:val"), "clear")
                    shd.set(qn("w:color"), "auto")
                    shd.set(qn("w:fill"), "DDE5ED")
                    tcPr.append(shd)
                va = OxmlElement("w:vAlign")
                va.set(qn("w:val"), "center")
                tcPr.append(va)
                p = cell.paragraphs[0]
                pf = p.paragraph_format
                pf.space_before = Pt(1)
                pf.space_after = Pt(1)
                pf.line_spacing = 1.1
                pf.first_line_indent = Cm(0)
                for part in re.split(r"(\*\*[^*]+\*\*)", str(values[ci])):
                    if not part:
                        continue
                    b = part.startswith("**") and part.endswith("**")
                    r = p.add_run(part[2:-2] if b else part)
                    r.font.name = "Times New Roman"
                    r.font.size = Pt(10)
                    r.bold = True if (ri == 0 or b) else None
        return self._place(tbl)


REDACTION_VI = {
    "none": "không",
    "none (synthetic data)": "không (dữ liệu mô phỏng)",
    "price/volume cells, chart and tooltip blurred": "làm mờ ô giá, khối lượng, biểu đồ và tooltip",
    "price/volume cells blurred": "làm mờ ô giá và khối lượng",
    "chart and price/volume cells blurred": "làm mờ biểu đồ, ô giá và khối lượng",
    "none needed (counts and statuses only)": "không cần (chỉ có số đếm và trạng thái)",
    "none needed (per-ticker outcome only)": "không cần (chỉ có kết quả từng mã)",
    "none needed (counts, dates, statuses only)": "không cần (chỉ có số đếm, ngày và trạng thái)",
    "none needed": "không cần",
}
CROP_DIR = ROOT / "var" / "report_build"
MAX_DESKTOP_PX = 1250   # tall full-page captures are cut to the top part so a figure never fills a whole page


def crop_top(path: Path, max_h: int) -> tuple[Path, bool]:
    from PIL import Image as _Img
    with _Img.open(path) as im:
        if im.size[1] <= max_h:
            return path, False
        CROP_DIR.mkdir(parents=True, exist_ok=True)
        out = CROP_DIR / f"top_{path.name}"
        im.crop((0, 0, im.size[0], max_h)).save(out)
        return out, True


def source_note(cur: Cursor, text: str):
    p = doc.add_paragraph(style="Normal")
    r = p.add_run(text)
    r.italic = True
    r.font.size = Pt(9.5)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.first_line_indent = Cm(0)
    cur._place(p._p)


def screen(cur: Cursor, fname: str, caption: str, width_cm: float = 15.5):
    """Real screenshot + short caption (goes to the list of figures) + a source line: route, mode, viewport, time, redaction."""
    folder = WEB_FINAL if fname in WEB_MANIFEST else SCREENS
    m = WEB_MANIFEST.get(fname) or MANIFEST[fname]
    img, cropped = crop_top(folder / fname, MAX_DESKTOP_PX) if m["viewport"].startswith("1440") else (folder / fname, False)
    cur.image(img, width_cm, max_height_cm=17.5)
    cur.cap_fig(f"{caption}.", keep_next=True)
    when = m["captured_at"].replace("T", " ")[:16]
    note = (f"Nguồn: ảnh chụp tự động {when}, {m['data_mode']}, route {m['route']}, khung {m['viewport'].replace('x', '×')}"
            f"{', phần đầu trang' if cropped else ''}; che dữ liệu: {REDACTION_VI[m['redaction']]}.")
    source_note(cur, note)


def side_by_side(cur: Cursor, items, height_cm: float, crop_px: int | None = None):
    """Two (or more) tall phone screenshots next to each other in a borderless table; each cell has its own caption."""
    from PIL import Image as _Img
    t = doc.add_table(rows=1, cols=len(items))
    t.alignment = 1
    for cell, (path, cap, note) in zip(t.rows[0].cells, items):
        if crop_px:
            path, _ = crop_top(path, crop_px)
        with _Img.open(path) as im:
            w, h = im.size
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.add_run().add_picture(str(path), height=Cm(height_cm), width=Cm(height_cm * w / h))
        c = cell.add_paragraph(cap, style="Caption Figure")
        c.paragraph_format.first_line_indent = Cm(0)
        n = cell.add_paragraph()
        n.paragraph_format.first_line_indent = Cm(0)
        n.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = n.add_run(note)
        r.italic = True
        r.font.size = Pt(9)
    cant = OxmlElement("w:cantSplit")
    t.rows[0]._tr.get_or_add_trPr().append(cant)
    cur._place(t._tbl)


def toc_field(p_el, instr: str, placeholder: str):
    """Replace paragraph content with a complex field Word will compute (TOC / list of captions)."""
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


# ===============================================================================================================
# Cover and preface
_, p = find("Mở rộng: Web UI")
set_text(p, "Mở rộng: Ứng dụng web cục bộ kết nối SQL Server – Cập nhật dữ liệu cuối phiên (EOD)")
_, p = find("So với bản báo cáo đầu tiên")
set_text(p, "So với bản báo cáo đầu tiên, phiên bản này trình bày chi tiết hơn từng thực thể, phụ thuộc hàm, loại ràng buộc và ví dụ "
            "truy vấn, theo cách trình bày của các báo cáo tham khảo trong lớp: yêu cầu nghiệp vụ, mô hình ERD, chi tiết bảng, cài đặt "
            "SQL Server, minh họa câu lệnh kèm kết quả chạy và kiểm thử. Ngoài phần cơ sở dữ liệu, nhóm xây dựng một ứng dụng web chạy "
            "cục bộ: các trang được dựng trên máy chủ Python và đọc trực tiếp SQL Server, cùng một tác vụ đồng bộ dữ liệu giá cuối phiên "
            "(EOD) có kiểm tra trước khi ghi, transaction toàn vẹn và nhật ký vận hành.")
_, p = find("Phần SQL Server và các số liệu")
set_text(p, "Mọi số liệu trong báo cáo được lấy từ mã nguồn, log và cơ sở dữ liệu trên máy của nhóm, kèm ngày chạy. Các kết quả được "
            "phân thành ba loại: đã chạy và kiểm chứng (ví dụ 44 ca kiểm thử SQL, 140 ca kiểm thử tự động của phần mở rộng, 28.097 dòng giá "
            "OHLCV thật từ 03/01/2023 đến 05/11/2026 được nạp); chưa kiểm chứng (ví dụ lịch tự động 16:10 của Windows Task Scheduler); và chưa triển khai (mô hình tạo "
            "dự báo mới). Dữ liệu mô phỏng, dữ liệu nghiên cứu riêng và dữ liệu đồng bộ thật được tách thành các cơ sở dữ liệu khác nhau "
            "và được ghi nhãn rõ trên giao diện lẫn trong báo cáo.")

# Table of contents / lists as Word fields
i_toc, p_toc = find("MỤC LỤC", "Heading 1")
i_fig, p_fig = find("DANH MỤC HÌNH VẼ", "Heading 1")
i_tab, p_tab = find("DANH MỤC BẢNG BIỂU", "Heading 1")
i_ch1, p_ch1 = find("CHƯƠNG 1", "Heading 1")
for hp in (p_toc, p_fig, p_tab):
    hp.style = st["Heading Unnumbered"]
remove_between(paras()[i_toc + 2]._p, p_fig._p)
toc_field(paras()[i_toc + 1]._p, 'TOC \\o "1-3" \\h \\z \\u', "Mục lục sẽ được Word cập nhật.")
_, p_fig = find("DANH MỤC HÌNH VẼ", "Heading Unnumbered")
i_fig = [x._p for x in paras()].index(p_fig._p)
_, p_tab = find("DANH MỤC BẢNG BIỂU", "Heading Unnumbered")
remove_between(paras()[i_fig + 2]._p, p_tab._p)
toc_field(paras()[i_fig + 1]._p, 'TOC \\h \\z \\t "Caption Figure,1"', "Danh mục hình sẽ được Word cập nhật.")
i_tab = [x._p for x in paras()].index(p_tab._p)
_, p_ch1 = find("CHƯƠNG 1", "Heading 1")
remove_between(paras()[i_tab + 2]._p, p_ch1._p)
toc_field(paras()[i_tab + 1]._p, 'TOC \\h \\z \\t "Caption Table,1"', "Danh mục bảng sẽ được Word cập nhật.")

# ===============================================================================================================
# Chapter 1
_, p = find("Phiên bản CSDL ban đầu được thiết kế")
set_text(p, "Phiên bản CSDL ban đầu được thiết kế để chạy trên SQL Server và trình diễn bằng SSMS: người dùng thao tác trực tiếp với "
            "SELECT, EXEC và các kịch bản kiểm thử. Cách làm này phù hợp để kiểm chứng lược đồ nhưng không thuận tiện khi cần tra cứu "
            "theo nhiều mã, xem lịch sử giá hay theo dõi đồng bộ dữ liệu. Phiên bản mở rộng vì vậy bổ sung một ứng dụng web chạy trên máy "
            "cục bộ (máy chủ Python dựng trang HTML từ SQL Server) và một tác vụ nhập giá cuối phiên có kiểm tra trước khi ghi.")
i, p = find("1.2.1. Yêu cầu mở rộng")
nxt = paras()[i + 1]
set_text(nxt, "Ứng dụng web cung cấp bảng dữ liệu và biểu đồ theo bộ lọc: chọn dataset, mã, khoảng ngày hoặc ngày tham chiếu đánh giá. "
              "Mọi trang được dựng ở máy chủ Python bằng truy vấn tham số hóa tới các view, function và stored procedure sẵn có; trình "
              "duyệt chỉ nhận HTML và không kết nối SQL Server. Giao diện không sửa bảng nghiệp vụ, không tính lại chỉ tiêu bằng logic khác "
              "SQL và không cho nhập câu SQL tùy ý.")
nxt2 = paras()[i + 2]
set_text(nxt2, "Bản thiết kế trước đó dự kiến một local API Gateway (FastAPI trả JSON, có Swagger). Trong bản cuối, nhóm bỏ lớp này: "
               "không còn REST endpoint dành cho giao diện và không còn trang Swagger. FastAPI chỉ được dùng làm framework HTTP để dựng "
               "trang bằng Jinja2; thao tác ghi duy nhất (đồng bộ một phiên) là biểu mẫu HTML có token và chống CSRF. Lý do: ít bề mặt tấn "
               "công hơn, một tiến trình duy nhất dễ chạy trên Windows và số liệu hiển thị đi thẳng từ SQL Server.")
nxt3 = paras()[i + 3]
set_text(nxt3, "Tác vụ cuối phiên (End-of-Day – EOD) chỉ nhập thêm giá thực, không huấn luyện hay tạo dự báo. Nguồn đã dùng là KBS qua thư "
               "viện vnstock; phiên bản thư viện, cách điều chỉnh giá, quyền sử dụng và thời điểm dữ liệu xuất hiện được kiểm tra trên máy "
               "chạy (mục 5.5). Dữ liệu mới chỉ ảnh hưởng tới việc chấm những dự báo đã có khi ngày mục tiêu trưởng thành.")
_, p = find("Trường Dataset.DataKind quy định loại nguồn")
set_text(p, "Trường Dataset.DataKind quy định loại nguồn: SYNTHETIC cho bộ mô phỏng và REAL_PRIVATE cho dữ liệu thật riêng tư. Thuộc tính "
            "Stock.IsSynthetic phải phù hợp loại dataset. Nếu nhà cung cấp trả đơn vị hoặc quy tắc điều chỉnh không khớp PriceUnit/PriceBasis "
            "đã lưu, hệ thống từ chối thay vì tự quy đổi. ObservedThrough là giới hạn ngày quan sát hợp lệ; việc tăng mốc này khi đồng bộ "
            "cuối phiên được hiện thực bằng migration sql/13_eod_extension.sql: chỉ dataset REAL_PRIVATE, chỉ theo chiều tăng và chỉ bên "
            "trong thủ tục ops.usp_EodApplySession (mục 3.6).")
# Tables 1-2: the template's 1 cm "Mã" column wraps "M01" onto two lines; widen it to 1.15 cm, taking the space from column 2
for t in doc.tables[1:3]:
    if t.rows[0].cells[0].text.strip() != "Mã":
        continue
    for row in t.rows:
        tcs = row._tr.findall(qn("w:tc"))
        w0, w1 = (tc.tcPr.find(qn("w:tcW")) for tc in tcs[:2])
        delta = 652 - int(w0.get(qn("w:w")))
        if delta > 0:
            w0.set(qn("w:w"), "652")
            w1.set(qn("w:w"), str(int(w1.get(qn("w:w"))) - delta))
# Table 3 rows
t3 = None
for t in doc.tables:
    if t.rows[0].cells[0].text.strip() == "Phạm vi" and "Đồng bộ cuối phiên" in t._tbl.xml:
        t3 = t
for row in t3.rows:
    c0 = row.cells[0].text.strip()
    if c0 == "Đồng bộ cuối phiên":
        set_text(row.cells[1].paragraphs[0], "DB MarketLabVN30_Live: 28.097 giá OHLCV thật của 30 mã, 956 phiên 03/01/2023–05/11/2026 (backfill lịch sử 06/11/2026 + EOD hằng ngày)")
        set_text(row.cells[2].paragraphs[0], "Nguồn KBS/vnstock 3.5.1; sàn lịch sử 01/01/2023; dữ liệu riêng tư, không đưa lên GitHub; chạy lại không thêm dòng")
    if c0 == "Dự báo mới mỗi ngày":
        set_text(row.cells[1].paragraphs[0], "Không có model artifact hay inference pipeline")
        set_text(row.cells[2].paragraphs[0], "Chưa triển khai; hệ thống chỉ quản lý và chấm các dự báo đã có")
_, p = find("Vũ trụ mã dùng trong phân tích nghiên cứu")
cur = Cursor(p._p)
cur.para("Ứng dụng web phục vụ một database tại một thời điểm và hiển thị nhãn phạm vi dữ liệu ở đầu mọi trang. Máy chủ từ chối phục vụ "
         "(HTTP 503) nếu loại dataset trong database không khớp chế độ đã cấu hình, không tự chuyển chế độ.")
cur.cap_table("Bảng 3a. Ba phạm vi dữ liệu và cách hệ thống xử lý")
cur.table(["Phạm vi", "Database", "Nội dung", "Đồng bộ EOD", "Nhãn trên giao diện"], [
    ["DEMO_OFFLINE", "MarketLabVN30_Demo", "8 mã mô phỏng, 280 giá, 258 dự báo", "Tắt", "Vàng – DỮ LIỆU MÔ PHỎNG"],
    ["REAL_PRIVATE", "MarketLabVN30_Live", "30 mã thuộc universe cấu hình (tham chiếu VN30 06/2026), 28.097 giá KBS từ 03/01/2023", "Có (PowerShell, Task Scheduler, form web)", "Đỏ – DỮ LIỆU THẬT RIÊNG TƯ"],
    ["RESEARCH_READ_ONLY", "MarketLabVN30_Research_20261027", "30 mã, 1.200 giá, 1.200 dự báo nghiên cứu", "Tắt (chưa migrate)", "Tím – CHỈ ĐỌC"],
], [4.1, 4.1, 3.7, 2.4, 2.4])
cur.para("Quy tắc thời gian: ngày phiên luôn là ngày lịch Asia/Ho_Chi_Minh, không suy từ ngày UTC; giá là dữ liệu cuối phiên, không phải "
         "realtime. Quy tắc nguồn và bản quyền: dữ liệu KBS truy xuất qua vnstock chịu điều kiện của bên thứ ba, quyền phân phối chưa xác "
         "định, nên chỉ lưu trong database riêng trên máy; ảnh giao diện REAL trong báo cáo đã làm mờ các ô giá và biểu đồ giá.")

# ===============================================================================================================
# Chapter 2: add 2.5 ops database
_, p3 = find("CHƯƠNG 3", "Heading 1")
cur = Cursor(before_chapter(p3))
cur.heading("2.5. Cơ sở dữ liệu vận hành tách biệt MarketLabVN30_Ops", 2)
cur.para("Nhật ký đồng bộ cuối phiên không được đưa vào 13 bảng nghiệp vụ. Bộ kiểm thử gốc sql/08_validation_tests.sql có ca "
         "“Schema thirteen tables” khẳng định toàn database có đúng 13 bảng; nếu thêm bảng nhật ký vào cùng database thì ca này mất ý nghĩa. "
         "Vì vậy các bảng vận hành nằm trong database riêng MarketLabVN30_Ops (schema ops), mỗi dòng mang khóa (DatabaseName, DatasetId) để "
         "một database Ops phục vụ được nhiều database nghiệp vụ. Database nghiệp vụ chỉ nhận thêm schema ops chứa một stored procedure, "
         "không thêm bảng.")
cur.cap_table("Bảng 18a. Các bảng của database vận hành MarketLabVN30_Ops (không thuộc 13 bảng nghiệp vụ)")
cur.table(["Bảng", "Khóa chính", "Vai trò", "Ràng buộc đáng chú ý"], [
    ["ops.SchemaVersion", "Version", "Phiên bản schema (v1, v2)", "—"],
    ["ops.EodConfig", "(DatabaseName, DatasetId)", "Nguồn, chỉ số universe, ngày snapshot, mốc giờ cutoff", "RequireCompleteUniverse = 1"],
    ["ops.EodRun", "EodRunId (IDENTITY)", "Một lần đồng bộ: ngày phiên, trạng thái, số mã yêu cầu/nhận/thêm/không đổi/từ chối, mã lỗi",
     "CHECK: SUCCESS chỉ khi đủ mã, không dry run, thêm + không đổi = yêu cầu"],
    ["ops.EodRunItem", "(EodRunId, Ticker)", "Kết quả từng mã: INSERTED, UNCHANGED, MISSING, REJECTED, CONFLICT…", "FK → EodRun"],
    ["ops.PriceReconciliation", "ReconId", "Giá đã chốt bị nguồn thay đổi, chờ người duyệt", "PENDING_REVIEW / APPROVED_UPDATE / REJECTED"],
    ["ops.PriceLoadLineage", "(DatabaseName, DatasetId, StockId, TradeDate)", "Dòng giá nào được lần đồng bộ nào thêm", "FK → EodRun"],
    ["ops.EvaluationSnapshot", "(EodRunId, RunId)", "Chỉ tiêu dự báo đánh giá lại sau mỗi lần đồng bộ", "FK → EodRun"],
], [4.3, 3.6, 4.7, 4.1])

# ===============================================================================================================
# Chapter 3
_, p = find("Các bước thực hiện trên SSMS")
cur = Cursor(p._p.getprevious())
cur.para("Kết quả chạy thực tế trên máy của nhóm ngày 06/11/2026 (sqlcmd, Windows Authentication, instance mặc định):")
cur.code(["Version     | Edition                             | DatabaseName       | CompatLevel",
          "17.0.1145.4 | Standard Developer Edition (64-bit) | MarketLabVN30_Demo | 170",
          "ObjectType: SQL_STORED_PROCEDURE 4 | SQL_SCALAR_FUNCTION 2 | SQL_INLINE_TABLE_VALUED_FUNCTION 1",
          "            VIEW 4 | SQL_TRIGGER 10"])
cur.cap_table("Bảng 18b. Số dòng 13 bảng nghiệp vụ trong hai database (truy vấn sys.partitions ngày 06/11/2026)")
counts = [("Market", 1, 1), ("Industry", 2, 0), ("Stock", 8, 30), ("Dataset", 1, 1), ("TradingDay", 42, 956), ("DailyPrice", 280, 28097),
          ("StockIndex", 1, 1), ("IndexMembership", 8, 30), ("ForecastModel", 2, 0), ("TargetDefinition", 1, 0), ("ModelRun", 2, 0),
          ("ForecastOrigin", 34, 0), ("Prediction", 258, 0)]
cur.table(["Bảng", "MarketLabVN30_Demo (SYNTHETIC)", "MarketLabVN30_Live (REAL_PRIVATE)"], [[a, str(b), str(c)] for a, b, c in counts],
          [5.0, 5.5, 5.5])
_, p = find("Các bước thực hiện trên SSMS")
set_text(p, "Các bước thực hiện trên SSMS: mở file all_in_one.sql, kiểm tra đúng instance và database demo, chạy toàn bộ bằng F5; xác nhận "
            "tên bảng và view; chạy preflight; tiếp tục demo. Không chạy script triển khai mới lên database nghiên cứu. Trong báo cáo này "
            "kết quả SQL được trích nguyên văn từ log sqlcmd (có ngày chạy); ảnh chụp giao diện SSMS chưa được đưa vào (danh sách ảnh cần "
            "chụp bổ sung ở Phụ lục A.1).")
_, p = find("Ví dụ chỉ minh họa cấu trúc tham số")
set_text(p, "Kết quả chạy thực tế trên MarketLabVN30_Demo (06/11/2026): ghi lại đúng thanh giá đã lưu của DEMO01 ngày 19/02/2025 với "
            "Close khác (26,0) bị từ chối với lỗi 51012; ghi lại giá giống hệt không phát sinh dòng mới; số dòng trước và sau đều 280, "
            "không còn transaction mở.")
cur = Cursor(p._p)
cur.code(["ErrorNumber | ErrorMessage",
          "51012       | Khoa gia da ton tai voi gia tri khac. Can @AllowUpdate=1.",
          "RowsBefore | RowsAfter | StoredClose | OpenTransactions",
          "280        | 280       | 25.728800   | 0"])
_, p = find("Thủ tục nhận mã phương pháp, dataset, horizon")
cur = Cursor(p._p)
cur.code(["EXEC dbo.usp_GetModelPerformance 'demo_baseline',1,5,'20250101','20251231','20260701';",
          "-- Kết quả 06/11/2026:",
          "RunId | ModelCode     | HorizonSessions | EvaluationAsOf | EvaluatedRows | Accuracy    | BrierScore",
          "1     | demo_baseline | 5               | 2026-07-01     | 128           | .5468750000 | 0.25"])
_, p = find("@ToDate='2026-01-01',@AsOfDate='2026-07-01';")
cur = Cursor(p._p)
cur.code(["-- Kết quả 06/11/2026:",
          "RunId | ModelCode     | CommonObservations | EvaluationAsOf | Accuracy    | BrierScore",
          "1     | demo_baseline | 128                | 2026-07-01     | .5468750000 | 0.25",
          "2     | demo_model_b  | 128                | 2026-07-01     | .2187500000 | 0.41143295204780556"])
_, p = find("-- Kết quả số học kỳ vọng: 10.00000000")
set_text(p, "-- Kết quả chạy 06/11/2026: ReturnPct = 10.00000000; fn_CheckPredictionDirection(0,0) = 1")
_, p = find("FROM dbo.vw_ModelPerformance;", "Code Local")
cur = Cursor(p._p)
cur.code(["-- Kết quả vw_ModelPerformance ngày 06/11/2026 (demo):",
          "RunId | EvaluatedRows | Accuracy | Brier   | LogLoss",
          "1     | 128           | .546875  | .250000 | .693147",
          "2     | 128           | .218750  | .411433 | 1.050525"])

_, p4 = find("CHƯƠNG 4", "Heading 1")
cur = Cursor(before_chapter(p4))
cur.heading("3.6. Mở rộng SQL cho cập nhật cuối phiên", 2)
cur.para("Phần mở rộng không sửa 13 bảng, khóa, CHECK hay các trigger khác. Ba script migration có preflight và rollback được áp dụng "
         "cho database REAL_PRIVATE mới (MarketLabVN30_Live) và database Ops; database demo và database nghiên cứu không bị migrate.")
cur.cap_table("Bảng 20a. Các script migration của phần mở rộng")
cur.table(["Script", "Áp lên", "Nội dung", "Rollback"], [
    ["13_eod_preflight.sql", "DB nghiệp vụ", "Chỉ đọc: 13 bảng, ràng buộc trusted, trigger bật, compat ≥ 130, backup gần nhất", "—"],
    ["13_eod_extension.sql", "DB nghiệp vụ REAL_PRIVATE", "Schema ops + ops.usp_EodApplySession; nới tr_Dataset_Guard cho đúng một trường hợp", "13_eod_extension_rollback.sql (khôi phục nguyên văn trigger gốc)"],
    ["14_ops_database.sql", "MarketLabVN30_Ops", "6 bảng nhật ký + SchemaVersion v1", "14_ops_database_rollback.sql (cần xác nhận)"],
    ["15_ops_schema_v2.sql", "MarketLabVN30_Ops", "Cho phép TriggerKind = 'WEB' (form web thay REST)", "15_ops_schema_v2_rollback.sql"],
], [3.8, 3.4, 5.8, 3.7])
cur.para("Trigger tr_Dataset_Guard gốc cấm thay đổi ObservedThrough của dataset đã có giá hoặc ModelRun. Bản sửa giữ nguyên quy tắc đó và "
         "chỉ thêm một ngoại lệ: dataset REAL_PRIVATE, các cột ngữ nghĩa khác không đổi, ngày mới lớn hơn ngày cũ và đang chạy trong thủ "
         "tục EOD (đánh dấu bằng SESSION_CONTEXT). Mọi thay đổi khác vẫn bị từ chối với lỗi 51007; ca “TRIGGER immutable dataset” của bộ 44 "
         "ca vẫn PASS sau migration.")
cur.code(["AND NOT (o.DataKind='REAL_PRIVATE' AND i.DataKind='REAL_PRIVATE'",
          "     AND NOT EXISTS(SELECT i.MarketId,i.DataKind,i.PriceBasis,i.PriceUnit",
          "                    EXCEPT SELECT o.MarketId,o.DataKind,o.PriceBasis,o.PriceUnit)",
          "     AND i.ObservedThrough>o.ObservedThrough",
          "     AND CONVERT(nvarchar(64),SESSION_CONTEXT(N'MarketLab.EodRunRef')) IS NOT NULL))",
          "THROW 51007,N'Ngu nghia dataset da su dung la bat bien; tao dataset moi.',1;"])
cur.para("Thủ tục ops.usp_EodApplySession ghi một phiên cho toàn bộ universe theo nguyên tắc tất cả hoặc không có gì: kiểm tra đủ và đúng "
         "danh sách mã, lấy khóa ứng dụng theo dataset, từ chối nếu giá đã lưu khác giá nguồn, thêm TradingDay (trigger lịch bảo vệ "
         "horizon đã lưu), tăng ObservedThrough rồi gọi dbo.usp_InsertDailyPrice với AllowUpdate = 0 cho từng mã. Bất kỳ lỗi nào cũng "
         "ROLLBACK toàn bộ; chế độ dry run chạy đủ các bước trên rồi ROLLBACK.")
cur.code(["BEGIN TRANSACTION;",
          "EXEC @Lock=sys.sp_getapplock @Resource=@Resource,@LockMode='Exclusive',",
          "     @LockOwner='Transaction',@LockTimeout=0;",
          "IF @Lock<0 THROW 51144,N'Another EOD job holds this dataset lock.',1;",
          "IF EXISTS(/* giá đã lưu khác giá nguồn */ ...) THROW 51145,N'...',1;",
          "IF NOT EXISTS(SELECT 1 FROM dbo.TradingDay WHERE DatasetId=@DatasetId AND TradeDate=@SessionDate)",
          "   INSERT dbo.TradingDay(DatasetId,TradeDate) VALUES(@DatasetId,@SessionDate);",
          "IF @SessionDate>@ObservedBefore BEGIN",
          "   EXEC sys.sp_set_session_context @key=N'MarketLab.EodRunRef',@value=@EodRunRef;",
          "   UPDATE dbo.Dataset SET ObservedThrough=@SessionDate WHERE DatasetId=@DatasetId; END;",
          "-- vòng lặp: EXEC dbo.usp_InsertDailyPrice ..., @AllowUpdate=0",
          "IF @DryRun=1 ROLLBACK; ELSE COMMIT;"])
cur.para("Trên MarketLabVN30_Live vẫn đúng 13 bảng, schema ops chỉ có một procedure. Rollback được kiểm thử tự động trên bản sao demo: "
         "trigger trở lại nguyên văn; áp lại migration hai lần không lỗi (idempotent).")

# ===============================================================================================================
# Chapter 4
t21 = None
for t in doc.tables:
    if t.rows[0].cells[0].text.strip() == "Mã" and "Q16" in t._tbl.xml:
        t21 = t
rerun = {"Q01": 8, "Q02": 8, "Q03": 0, "Q04": 8, "Q05": 2, "Q06": 8, "Q07": 136, "Q08": 8, "Q09": 8, "Q10": 0, "Q11": 0, "Q12": 40,
         "Q13": 5, "Q14": 1, "Q15": 2, "Q16": 0}
grid = t21._tbl.tblGrid
newcol = deepcopy(grid.findall(qn("w:gridCol"))[-1])
grid.append(newcol)
for ri, row in enumerate(t21.rows):
    tc = deepcopy(row.cells[-1]._tc)
    row._tr.append(tc)
    cell = row.cells[-1]
    set_text(cell.paragraphs[0], "Demo chạy lại 06/11" if ri == 0 else str(rerun[row.cells[0].text.strip()]))
_, p = find("Bảng 21. Danh sách 16 truy vấn")
set_text(p, "Bảng 21. Danh sách 16 truy vấn: số dòng lịch sử và kết quả chạy lại ngày 06/11/2026")
_, p = find("Số dòng Demo và Thật trong Bảng 21")
set_text(p, "Cột Demo và Thật được kế thừa từ báo cáo gốc. Cột cuối là kết quả chạy lại toàn bộ sql/07_business_queries.sql trên "
            "MarketLabVN30_Demo ngày 06/11/2026 bằng scripts/run_public_regression.py (log tests/runs/public_20261105T175220966677Z/"
            "query_Q01–Q16.log): cả 16 truy vấn chạy không lỗi và khớp số dòng lịch sử của demo. Số 0 ở Q03, Q10, Q11 và Q16 là kết quả "
            "hợp lệ của điều kiện lọc trên bộ mô phỏng (mọi mã có ngành, mọi mã có dự báo, không ticker chứa “A”, không phiên thiếu giá).")
_, p = find("Giải thích: LEFT JOIN khiến mã không có IndustryId")
cur = Cursor(p._p.getprevious())
cur.code(["-- Kết quả Q01 trên demo (06/11/2026, 8 dòng; trích 3 dòng đầu):",
          "StockId | Ticker | CompanyName        | IndustryId | IsSynthetic",
          "1       | DEMO01 | Công ty mô phỏng 1 | 1          | 1",
          "2       | DEMO02 | Công ty mô phỏng 2 | 1          | 1",
          "3       | DEMO03 | Công ty mô phỏng 3 | 1          | 1"])
_, p = find("Ví dụ không nên hiển thị đơn vị VNĐ")
cur = Cursor(p._p.getprevious())
cur.code(["-- Kết quả Q02 trên demo (06/11/2026, 8 dòng; trích):",
          "Ticker | TradeDate  | ClosePrice | PriceUnit",
          "DEMO01 | 2025-02-19 | 25.728800  | Đơn vị mô phỏng",
          "DEMO08 | 2025-02-19 | 38.909600  | Đơn vị mô phỏng"])
_, p = find("Bộ kiểm thử tại sql/08_validation_tests.sql gồm 44 ca")
set_text(p, "Bộ kiểm thử tại sql/08_validation_tests.sql gồm 44 ca SQL khác nhau: ca hợp lệ, ca cố tình vi phạm ràng buộc và tình huống "
            "ROLLBACK. Lịch sử của repo ghi 44 ca × 4 database = 176 lượt PASS (không phải 176 ca độc lập). Trong lần hoàn thiện này, "
            "ngày 06/11/2026 nhóm chạy lại: (1) trên MarketLabVN30_Demo bằng scripts/run_public_regression.py – kết quả PASS|44, 16 truy "
            "vấn, 2 lần live demo, hash toàn bộ 13 bảng trước bằng sau; (2) trên một bản sao demo đã áp migration 13 – 44/44 PASS, chứng "
            "minh phần mở rộng không làm yếu thiết kế gốc.")
_, p = find("Trong bài demo SQL, không được coi lỗi CHECK")
cur = Cursor(p._p)
cur.para("Kết quả thực tế của phần 4–5 trong sql/09_live_demo.sql (log live_demo_1.log ngày 06/11/2026):")
cur.code(["ExpectedError | ConstraintEvidence",
          "547 | The UPDATE statement conflicted with the CHECK constraint \"CK_DailyPrice_Volume\" ...",
          "Stage BEFORE: Volume 11000 | DURING: 11001 | AFTER ROLLBACK: 11000",
          "Result         | PriceHashBefore (SHA-256)  | PriceHashAfter            | OpenTransactions",
          "LIVE_DEMO_PASS | A627B1D3...45AA7731        | A627B1D3...45AA7731       | 0"])
_, p = find("Trên 600 quan sát chung, baseline có Brier")
cur = Cursor(p._p)
cur.para("Tái xác minh ngày 06/11/2026 (chỉ đọc) trên MarketLabVN30_Research_20261027: dbo.usp_CompareModels '1,2' cho khoảng ngày gốc "
         "01–30/09/2025, as_of 01/07/2026 trả 600 quan sát chung, Accuracy 0,5800000000 và 0,5683333333, Brier 0,24766643 và "
         "0,25236224; log loss tính trên cùng tập giao bằng công thức của vw_ModelPerformance là 0,688478 và 0,698052 – khớp Bảng 22.")
_, p = find("So với một hệ quản trị dữ liệu CRUD thông thường")
set_text(p, "So với một hệ quản trị dữ liệu CRUD thông thường, bài toán này tập trung vào mốc thời gian, độ trưởng thành của dự báo và "
            "sự đồng nhất giữa nguồn. Ưu điểm là các quy tắc nằm trong SQL (khóa, CHECK, trigger, stored procedure) chứ không chỉ ở giao "
            "diện; nhờ vậy ứng dụng web và tác vụ EOD kế thừa nguyên các bảo vệ đó. Hạn chế: dữ liệu mô phỏng nhỏ, chưa thử trên SQL "
            "Server Express/2016.")
_, p = find("Các báo cáo mẫu của nhóm quản lý rạp chiếu phim")
set_text(p, "Các báo cáo mẫu của lớp minh họa DDL, truy vấn và kết quả bằng ảnh SSMS. Báo cáo này dùng output nguyên văn của sqlcmd và log "
            "có ngày chạy làm bằng chứng; ảnh giao diện SSMS là phần cần chụp bổ sung (Phụ lục A.1). Không có ảnh nào trong báo cáo được "
            "dựng giả.")
cur = Cursor(p._p)
cur.heading("4.5. Kiểm thử tự động phần mở rộng", 2)
cur.para("Phần mở rộng có bộ kiểm thử Python chạy bằng lệnh uv run pytest tests/product. Kiểm thử tích hợp tạo database cô lập tên "
         "MarketLabVN30_IT_* (gắn nhãn INTEGRATION_TEST và chỉ xóa đúng các database này sau khi chạy) và dùng một bộ cung cấp dữ liệu "
         "giả chỉ trong kiểm thử; bằng chứng với nguồn thật được trình bày riêng ở mục 5.5.")
cur.cap_table("Bảng 22a. Kết quả bộ kiểm thử phần mở rộng ngày 06/11/2026 (140 ca, 89,8 giây)")
cur.table(["Nhóm", "Tệp", "Số ca", "Nội dung chính", "Kết quả"], [
    ["Unit", "test_unit_normalize_calendar.py", "30", "Chuẩn hóa OHLCV, độ chính xác decimal(19,6), múi giờ VN, phiên/cuối tuần/nghỉ lễ", "PASS"],
    ["Unit", "test_unit_provider_bridge.py", "8", "Subprocess nguồn: timeout, lỗi import, lỗi từng mã, câu trả lời “dữ liệu trống”", "PASS"],
    ["Unit", "test_unit_backfill.py", "11", "Chia chunk theo năm, phiên hoàn chỉnh mới nhất theo giờ VN, MISSING/NO_HISTORY, sàn 2023", "PASS"],
    ["Integration EOD", "test_integration_eod.py", "23", "PARTIAL/FAILED không ghi; rollback giữa lô; khóa bận; idempotent; đối soát; dry run; backfill", "PASS"],
    ["Integration SQL", "test_integration_sql_regression.py", "5", "44 ca gốc + 16 truy vấn sau migration; rollback; preflight", "PASS"],
    ["Integration backfill", "test_integration_backfill.py", "17", "Sàn 2023, dry run, PARTIAL trung thực, chạy lại idempotent, xung đột vào đối soát, resume, nguồn sập, rollback một phiên, khóa, backup", "PASS"],
    ["Web (server-side)", "test_web.py", "31", "Route, validation, CSRF/token/khóa, job EOD, HTTP 503, đối chiếu HTML ↔ SQL", "PASS"],
    ["Web backfill", "test_web_backfill.py", "7", "Trang /backfill, form có bảo vệ, sàn 2023 trên trang và CSV, nhật ký EOD tách phiên backfill", "PASS"],
    ["E2E trình duyệt", "test_e2e_ui.py", "8", "Microsoft Edge: 6 trang, phóng to biểu đồ, bàn phím, 4 viewport, form EOD và backfill", "PASS"],
], [2.6, 4.6, 1.3, 6.4, 1.5])
cur.para("Ngoài ra: 11 unit test gốc của repo OK; gate công bố scripts/check_publication.py vẫn FAIL vì danh sách cho phép công bố "
         "(allowlist) chưa đăng ký các tệp mới – đây là quy trình duyệt trước khi công bố, khác phạm vi với 140 ca kiểm thử và không có "
         "nghĩa các ca đó thất bại. Các con số 88, 100 và 102 ở những phiên bản trước không còn dùng cho bản cuối.")

# ===============================================================================================================
# Chapter 5 – rewritten
i5, p5 = find("CHƯƠNG 5", "Heading 1")
_, pk = find("KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN", "Heading 1")
remove_between(p5._p.getnext(), pk._p)
set_text(p5, "CHƯƠNG 5: ỨNG DỤNG WEB CỤC BỘ VÀ CẬP NHẬT DỮ LIỆU CUỐI PHIÊN")
cur = Cursor(p5._p)
cur.heading("5.1. Mục tiêu và kiến trúc triển khai", 2)
cur.para("Mục tiêu của phần mở rộng là đưa cơ sở dữ liệu từ mức trình diễn bằng SSMS sang một ứng dụng dùng được hằng ngày trên máy "
         "Windows: tra cứu giá, xem dự báo và chỉ tiêu, so sánh mô hình và cập nhật giá sau mỗi phiên, trong khi toàn bộ quy tắc nghiệp vụ "
         "vẫn nằm ở SQL Server. Kiến trúc cuối gồm hai luồng độc lập: Trình duyệt → Ứng dụng web Python → SQL Server; và EOD Worker → SQL "
         "Server + database Ops. Backfill lịch sử (mục 5.5.7) dùng chính luồng EOD Worker, không tạo đường nạp dữ liệu thứ hai.")
cur.image(ROOT / "report" / "final" / "assets" / "architecture_final.png", 15.5)
cur.cap_fig("Hình 3. Kiến trúc cuối của MarketLab VN30 (sơ đồ thiết kế của nhóm).")
cur.para("So với bản thiết kế trước, lớp local API Gateway (REST JSON và Swagger) đã được gỡ bỏ theo quyết định của nhóm. Máy chủ chạy "
         "truy vấn và trả trang HTML hoàn chỉnh; chính sách bảo mật nội dung (CSP) đặt connect-src 'none' nên trình duyệt không thể tự "
         "gọi dữ liệu. Các route /api/docs, /api/openapi.json và mọi /api/* trả HTTP 404 (Hình 15). Lớp truy cập dữ liệu (queries.py, "
         "db.py) và toàn bộ worker EOD được giữ nguyên khi đổi kiến trúc.")
cur.heading("5.2. Công nghệ và cấu trúc mã nguồn", 2)
cur.cap_table("Bảng 23. Công nghệ sử dụng (phiên bản ghim trong uv.lock)")
cur.table(["Thành phần", "Công nghệ / phiên bản", "Vai trò"], [
    ["CSDL", "SQL Server 2025 Standard Developer 17.0.1145.4", "13 bảng nghiệp vụ, view, function, procedure, trigger; database Ops"],
    ["Kết nối", "pyodbc 5.2.0 + ODBC Driver 18 for SQL Server", "Truy vấn tham số hóa, timeout, Windows Authentication"],
    ["Ứng dụng web", "Python 3.12.10, FastAPI 0.115.12, uvicorn 0.34.2, Jinja2 3.1.6", "Dựng trang HTML phía máy chủ; bind 127.0.0.1"],
    ["Giao diện", "HTML/CSS, JavaScript không framework", "Vẽ biểu đồ SVG từ dữ liệu nhúng; không gọi mạng"],
    ["Nguồn EOD", "vnstock 3.5.1 (interpreter riêng), nguồn KBS", "Lấy nến ngày qua subprocess cô lập"],
    ["Vận hành", "PowerShell, Windows Task Scheduler", "Khởi động, đồng bộ thủ công, lịch (mặc định tắt)"],
    ["Kiểm thử", "pytest 8.3.5, Playwright 1.52 + Microsoft Edge", "Unit, integration, web, E2E"],
], [2.8, 6.2, 7.6])
cur.cap_table("Bảng 24. Cấu trúc mã nguồn chính trên nhánh feature/marketlab-working-product")
cur.table(["Đường dẫn", "Nội dung"], [
    ["marketlab_app/web_app.py", "Ứng dụng web: route, kiểm tra đầu vào, bảo mật, CSRF, job EOD và backfill, xuất CSV"],
    ["marketlab_app/templates/*.html", "10 template Jinja2: base, macros, 6 trang, 2 trang job, trang lỗi"],
    ["marketlab_app/queries.py, db.py", "Truy vấn tham số hóa tới view/function/procedure; ánh xạ lỗi SQL"],
    ["marketlab_app/eod/", "service.py (điều phối), backfill.py, backup.py, coverage.py, normalize.py, calendar.py, providers.py, kbs_bridge.py, opsstore.py"],
    ["marketlab_app/web/", "styles.css, charts.js, enhance.js"],
    ["sql/13_*.sql – 16_*.sql", "Migration EOD, database Ops (v1–v3: backfill), preflight, rollback"],
    ["scripts/*.ps1", "Setup, Start, Stop, Run-MarketLab-EOD, Backfill-MarketLab, Install-MarketLab-EODTask"],
    ["tests/product/", "140 ca kiểm thử"],
], [5.4, 11.2])

cur.heading("5.3. Giao diện ứng dụng web", 2)
cur.para("Giao diện có sáu khu vực (Tổng quan, Lịch sử OHLCV, Dự báo & hiệu năng, So sánh mô hình, Vận hành EOD, Backfill lịch sử), chuyển qua thanh điều hướng bằng liên kết thật; trạng thái bộ lọc nằm trên địa chỉ trang nên tải lại "
         "hay đánh dấu trang không làm mất bộ lọc. Đầu trang luôn hiện nhãn phạm vi dữ liệu, ô chọn dataset và liên kết chuyển sang instance "
         "chế độ khác; nhãn LIVE (đỏ) hoặc DEMO (vàng) nằm cả ở đầu trang lẫn cạnh tiêu đề. Tất cả ảnh dưới đây được chụp tự động bằng "
         "Microsoft Edge từ ứng dụng đang chạy ngày 06/11/2026; ảnh LIVE đã làm mờ ô giá, khối lượng, biểu đồ và tooltip.")
cur.heading("5.3.1. Tổng quan", 3)
cur.para("Trang tổng quan hiển thị số mã có giá, số phiên có dữ liệu, phạm vi ngày thực tế (MIN → MAX TradeDate), số dòng DailyPrice, "
         "ngày giá mới nhất kèm trạng thái độ mới (Đã cập nhật / Có thể chậm / Mô phỏng cố định – luôn có chữ, không chỉ dùng màu), tình "
         "trạng dữ liệu (số mã-phiên thiếu so với lịch phiên kể từ nến đầu tiên của từng mã), phiên đồng bộ thành công gần nhất, job "
         "backfill chính, số dự báo đủ điều kiện và số giá chờ đối soát. Với LIVE, dòng universe ghi rõ “30 mã thuộc universe được cấu "
         "hình (tham chiếu VN30 06/2026)”, không phải thành phần VN30 lịch sử. Khối “Nguồn, đơn vị & giới hạn” trình bày PriceBasis, PriceUnit và ghi chú nguồn của dataset. Khi dataset chưa có "
         "ModelRun (database Live), thẻ dự báo hiển thị “—” kèm giải thích thay vì số 0.")
screen(cur, "02_demo_dashboard_1440.png", "Hình 4. Trang Tổng quan với dữ liệu mô phỏng")
screen(cur, "01_live_dashboard_1440.png", "Hình 5. Trang Tổng quan với dữ liệu thật riêng tư sau backfill")
cur.heading("5.3.2. Tra cứu lịch sử OHLCV", 3)
cur.para("Người dùng nhập mã (gợi ý 30 mã kèm số phiên có giá), khoảng ngày rồi bấm Xem; ở LIVE ô ngày có giới hạn dưới 01/01/2023 và máy "
         "chủ từ chối (HTTP 422) mọi khoảng bắt đầu trước mốc đó trước khi truy vấn. Không chọn ngày thì trang hiện 12 tháng gần nhất đã "
         "lưu; các nút khoảng nhanh 3T, 6T, 1N, 2N, Tất cả đổi khoảng ngày bằng liên kết. Biểu đồ gồm hai khung dùng chung trục thời gian: "
         "Close (đường) và Volume (cột), mỗi khung một trục giá trị; chú giải ghi PriceBasis SOURCE_CLOSE và đơn vị; kéo chuột ngang để "
         "phóng to một đoạn, tooltip và phím mũi tên đọc từng phiên. Phiên có trong lịch dataset nhưng thiếu giá được để trống và đánh "
         "dấu, không nối đường. Dòng nguồn ghi KBS qua vnstock, job backfill và thời điểm tải. Bảng OHLCV bên dưới chứa cùng số liệu, "
         "sắp xếp theo cột, phân trang 50 dòng và có nút xuất CSV (tối đa 5.000 dòng, cùng bộ lọc và sàn ngày).")
screen(cur, "05_demo_ohlcv_zoom_tooltip_1440.png", "Hình 6. Biểu đồ Close/Volume đã phóng to và tooltip OHLCV")
screen(cur, "03_live_ohlcv_2023_all_1440.png", "Hình 7. Lịch sử OHLCV thật của FPT 03/01/2023–05/11/2026 (956 phiên)")
cur.heading("5.3.3. Dự báo và hiệu năng", 3)
cur.para("Trang liệt kê các ModelRun với mô hình, mục tiêu, horizon và ngưỡng; với ngày tham chiếu as_of do người dùng chọn, máy chủ gọi "
         "dbo.fn_EligiblePredictions(as_of) và tính Accuracy, Brier, log loss bằng đúng công thức của vw_ModelPerformance. Mỗi run có số dự "
         "báo đã chấm, chưa trưởng thành và thiếu giá endpoint. Bảng dự báo hiển thị OriginDate, TargetDate, ProbabilityPositive, nhãn dự "
         "đoán, nhãn thực (“—” khi chưa chấm, không phải 0) và trạng thái tại as_of. Khung thông báo nhắc rằng hệ thống chưa cấu hình mô "
         "hình tạo dự báo mới và kết quả không phải khuyến nghị đầu tư.")
screen(cur, "12_demo_forecast_1440.png", "Hình 8. Trang Dự báo và hiệu năng tại as_of 01/07/2026")
cur.heading("5.3.4. So sánh mô hình", 3)
cur.para("Người dùng chọn 2–8 run, khoảng ngày gốc và as_of; máy chủ gọi dbo.usp_CompareModels nên chỉ so trên giao các bộ (StockId, "
         "OriginDate, TargetDate) đủ điều kiện của mọi run, và chỉ chấp nhận run cùng dataset, cùng định nghĩa mục tiêu. Log loss được tính "
         "thêm trên đúng tập giao đó. Tiêu đề kết quả ghi dataset, mục tiêu, cửa sổ ngày, as_of và số quan sát chung.")
screen(cur, "11_demo_compare_1440.png", "Hình 9. So sánh run 1 và 2 trên 128 quan sát chung")
cur.para("Database LIVE chưa có ModelRun, nên hai trang Dự báo và So sánh ở LIVE chỉ hiển thị trạng thái rỗng kèm giải thích “Chưa cấu hình "
         "mô hình tạo dự báo mới”, không vẽ biểu đồ hay điểm số giả; chỉ tiêu của dataset khác không được diễn giải thành chỉ tiêu của dữ "
         "liệu LIVE.")
cur.heading("5.3.5. Vận hành dữ liệu cuối phiên", 3)
cur.para("Trang vận hành phân biệt bốn mốc ngày: ngày được yêu cầu gần nhất, phiên đồng bộ thành công gần nhất, ObservedThrough của "
         "dataset và nến mới nhất nguồn đã trả. Nhật ký EOD có lọc theo trạng thái, phân trang và chi tiết từng run (kết quả từng mã, nguồn, "
         "quyết định lịch phiên, ObservedThrough trước/sau, đánh giá lại). Bảng kiểm tra lịch phiên so số dòng giá mỗi phiên với universe kỳ "
         "vọng; bảng đối soát liệt kê giá đã chốt bị nguồn thay đổi. Biểu mẫu Dry run / Sync ghi rõ phạm vi ghi; ở DEMO_OFFLINE và "
         "RESEARCH_READ_ONLY các nút bị khóa. Nhật ký mặc định chỉ gồm các lần chạy EOD hằng ngày; 956 phiên do backfill ghi được xem ở "
         "trang riêng hoặc khi tích “Gồm cả phiên backfill lịch sử”. Hình 11–12 chụp trước khi bổ sung tab Backfill (giao diện năm tab), "
         "luồng biểu mẫu và trang kết quả không đổi.")
screen(cur, "08_live_eod_ops_1440.png", "Hình 10. Trạng thái và nhật ký đồng bộ cuối phiên")
screen(cur, "12_real_eod_job_result_1440.png", "Hình 11. Kết quả dry run thực hiện qua biểu mẫu web", 14.5)
screen(cur, "13_real_ops_run_detail_1440.png", "Hình 12. Chi tiết một lần đồng bộ (kết quả từng mã)", 14.5)
cur.heading("5.3.6. Backfill lịch sử", 3)
cur.para("Trang Backfill lịch sử hiển thị job chính (cửa sổ, trạng thái, tiến độ phiên, số dòng thêm mới và không đổi, mã-phiên thiếu "
         "hoặc trước lịch sử nguồn, dòng bị từ chối, xung đột, backup đã xác minh), danh sách mọi job (kể cả dry run), kết quả theo trạng "
         "thái phiên, các phiên cần chú ý, bảng tải nguồn theo mã với checkpoint mã × năm và bảng độ phủ theo mã truy vấn trực tiếp "
         "DailyPrice × TradingDay. Biểu mẫu Dry run / Backfill thật / Tiếp tục job dở dang yêu cầu token, CSRF, ô xác nhận và hộp thoại "
         "xác nhận; chỉ một job chạy tại một thời điểm.")
screen(cur, "07_live_backfill_1440.png", "Hình 12a. Trang Backfill lịch sử trên MarketLabVN30_Live")
cur.heading("5.3.7. Hiển thị trên thiết bị nhỏ và trạng thái lỗi", 3)
cur.para("Giao diện được kiểm tra ở bốn kích thước 1440×900, 1280×800, 768×1024 và 390×844: không tràn ngang trang; bảng rộng cuộn trong "
         "khung với cột đầu cố định và gợi ý “Vuốt ngang”; thẻ chỉ tiêu hai cột trên điện thoại. Bộ lọc sai được kiểm tra ở máy chủ và trả "
         "trang có thông báo (HTTP 422); mất kết nối SQL Server trả trang HTTP 503 có nút Thử lại.")
screen(cur, "13_live_ohlcv_390.png", "Hình 13. Trang Lịch sử OHLCV trên điện thoại", 5.6)
screen(cur, "06_live_history_floor_422_1440.png", "Hình 14. Từ chối khoảng ngày trước 01/01/2023 ở chế độ LIVE", 14.5)

cur.heading("5.4. Xử lý phía máy chủ và bảo mật", 2)
cur.cap_table("Bảng 25. Các route của ứng dụng web (không có REST JSON cho giao diện)")
cur.table(["Route", "Phương thức", "Tham số chính", "Truy vấn SQL / xử lý", "Mã HTTP"], [
    ["/", "GET", "ds", "Dataset, fn_EligiblePredictions(hôm nay), vw_LatestStockPrice, ops.EodRun", "200, 404, 503"],
    ["/market", "GET", "ds, t, f, to, sort, order, page", "DailyPrice (tham số hóa, LIVE ≥ 01/01/2023), lịch TradingDay cho biểu đồ", "200, 422, 503"],
    ["/market/export.csv", "GET", "ds, t, f, to", "Cùng bộ lọc và sàn ngày, ≤ 5.000 dòng, tải tệp CSV", "200, 422"],
    ["/forecast", "GET", "ds, as_of, run, t, status, page", "ModelRun, fn_EligiblePredictions(as_of), Prediction", "200, 404, 422"],
    ["/compare", "GET", "ds, runs (2–8), f, to, as_of", "dbo.usp_CompareModels + log loss trên tập giao", "200, 409, 422"],
    ["/ops", "GET", "ds, status, page, run", "ops.EodRun, EodRunItem, PriceReconciliation, kiểm tra lịch", "200, 404, 422"],
    ["/ops/eod", "POST (form)", "csrf, ops_token, session_date, action, confirm_sync", "Khởi chạy EOD Worker (nền)", "303, 401, 403, 409, 422, 429"],
    ["/ops/jobs/{id}", "GET", "—", "Trạng thái job, tự làm mới 2 giây", "200, 404"],
    ["/backfill", "GET", "ds, job", "ops.BackfillJob/Fetch/Session/Reject; độ phủ DailyPrice × TradingDay", "200, 404"],
    ["/backfill/run", "POST (form)", "csrf, ops_token, start_date, end_date, tickers, action, confirm_write", "Khởi chạy backfill (nền)", "303, 401, 403, 409, 422, 429"],
    ["/backfill/jobs/{id}", "GET", "—", "Tiến độ job backfill, tự làm mới 3 giây", "200, 404"],
    ["/health", "GET", "—", "Văn bản “ok” cho script khởi động (không phải API dữ liệu)", "200"],
], [2.4, 2.0, 4.0, 6.0, 2.3])
cur.para("Mọi tham số được kiểm tra kiểu và miền (mã 1–20 ký tự chữ/số, ngày ISO, khoảng ngày hợp lệ, trang ≥ 1, cột sắp xếp trong danh "
         "sách cho phép) rồi đưa vào truy vấn bằng tham số, không ghép chuỗi. Lỗi SQL được ánh xạ thành mã nghiệp vụ, chẳng hạn lỗi 51020 "
         "thành HTTP 409 và lỗi 51021 thành HTTP 422, kèm thông báo dễ hiểu; trang lỗi không hiển thị chuỗi kết nối.")
cur.code(["@app.get(\"/forecast\", response_class=HTMLResponse)",
          "def forecast(request, ds=None, as_of=None, run=None, t=None, status=None, page=None):",
          "    with connect(settings) as c:",
          "        ctx = base_context(request, c, \"forecast\", ds)   # kiểm tra chế độ ↔ loại dataset",
          "        aso = parse_date(as_of, \"as_of\") or today_vn()",
          "        runs = queries.model_runs(c, ctx[\"ds\"][\"DatasetId\"])",
          "        perf = {p[\"RunId\"]: p for p in queries.performance(c, aso, ctx[\"ds\"][\"DatasetId\"])}",
          "        ...",
          "    return render(\"forecast.html\", ctx)"])
cur.cap_table("Bảng 26. Biện pháp bảo vệ của ứng dụng web cục bộ")
cur.table(["Rủi ro", "Biện pháp", "Kiểm thử"], [
    ["Truy cập từ mạng LAN", "Chỉ bind 127.0.0.1; Host header phải là loopback (421)", "test_security_headers_host_and_origin"],
    ["Giả mạo yêu cầu (CSRF)", "Cookie ml_csrf HttpOnly SameSite=Strict + trường ẩn; kiểm Origin, Sec-Fetch-Site", "test_real_ops_form_csrf_token…"],
    ["Đoán token", "So sánh hằng thời gian; sai 5 lần/10 phút → 429", "cùng test, E2E"],
    ["Ghi nhầm dữ liệu thật", "Ô xác nhận bắt buộc cho Sync; hộp xác nhận; dry run mặc định; một job tại một thời điểm", "CONFIRMATION_REQUIRED"],
    ["Script lạ trong trang", "CSP default-src 'self', connect-src 'none', form-action 'self'; Jinja2 tự escape", "CSP header test"],
    ["Lộ bí mật", "Token chỉ ở .env máy chủ; ô mật khẩu không được điền lại; không có trong HTML, URL, log", "kiểm tra nội dung trang"],
    ["Chế độ sai database", "Từ chối phục vụ khi loại dataset không khớp chế độ (503)", "test_mode_mismatch_is_refused"],
], [3.6, 7.6, 5.4])
screen(cur, "16_api_docs_404.png", "Hình 15. Route /api/docs đã gỡ trả trang 404 của ứng dụng", 14.0)

cur.heading("5.5. Quy trình cập nhật dữ liệu cuối phiên (EOD) đã triển khai", 2)
cur.para("Worker chạy độc lập với ứng dụng web và được kích hoạt bằng PowerShell (scripts/Run-MarketLab-EOD.ps1), Windows Task Scheduler "
         "hoặc biểu mẫu web. Mỗi lần chạy ghi một dòng ops.EodRun ở trạng thái RUNNING bằng transaction riêng trước khi làm gì khác, nên "
         "lỗi ở bất kỳ bước nào cũng được ghi nhận.")
cur.heading("5.5.1. Bước 1 – Xác định phiên và universe", 3)
cur.para("Ngày phiên là ngày lịch Asia/Ho_Chi_Minh. Ngày tương lai hoặc hôm nay trước mốc 16:10 → SKIPPED; thứ Bảy, Chủ nhật → NO_SESSION. "
         "Ngày thường được đối chiếu với chuỗi chỉ số VN30 do chính nguồn trả: có nến ngày đó → có phiên; có nến sau đó nhưng không có nến "
         "ngày đó → NO_SESSION (ví dụ 02/09/2026: nguồn có nến 28/08 và 03/09); chưa có nến nào sau đó → SKIPPED (dữ liệu chưa có). Universe "
         "là các mã thuộc IndexMembership VN30 hiệu lực tại 30/06/2026 – một snapshot cố định, không phải thành phần VN30 hiện hành.")
cur.heading("5.5.2. Bước 2 – Lấy dữ liệu từ nguồn", 3)
cur.para("vnstock không còn phát hành trên PyPI nên được cài trong một interpreter riêng; worker gọi interpreter đó với cờ -I để chạy "
         "kbs_bridge.py trong tiến trình con, có giới hạn thời gian, thử lại có độ trễ tăng dần (1–2–4 giây) và khoảng cách tối thiểu giữa "
         "các lần gọi. Khi kiểm tra thực tế, nhóm phát hiện nguồn KBS điều chỉnh hồi tố giá lịch sử: giá FPT 09/2025 thấp hơn khoảng 9% so "
         "với bản trích xuất trước nhưng Volume giữ nguyên. Ngoài ra, sau nửa đêm giờ Việt Nam, tham số end của nguồn trở thành không bao "
         "gồm ngày cuối; worker vì vậy xin dữ liệu tới ngày D+1 rồi bỏ các nến sau ngày D.")
cur.heading("5.5.3. Bước 3 – Kiểm tra trước khi ghi", 3)
cur.para("Mỗi nến phải có giá hữu hạn, dương, High ≥ max(Open, Close, Low), Low ≤ min(Open, Close, High), Volume là số nguyên không âm, "
         "tối đa 6 chữ số thập phân; nhãn ngày được đổi theo múi giờ Việt Nam; hai nến khác nhau cùng ngày bị từ chối. Thiếu bất kỳ mã nào "
         "→ PARTIAL; có mã sai → FAILED; cả hai trường hợp không ghi dòng nào và không tự điền giá.")
cur.heading("5.5.4. Bước 4 – Ghi bằng transaction và tính idempotent", 3)
cur.para("Toàn bộ phiên được ghi qua ops.usp_EodApplySession (mục 3.6). Chạy lại cùng dữ liệu cho SUCCESS với 0 dòng thêm và 30 dòng "
         "không đổi. Nếu nguồn đổi một giá đã chốt, lần chạy FAILED (CONFLICT_REQUIRES_RECONCILIATION), không ghi gì, và giá mới được đưa "
         "vào ops.PriceReconciliation chờ người duyệt qua dòng lệnh; hệ thống không tự cập nhật giá lịch sử.")
cur.heading("5.5.5. Bước 5 – Nhật ký, trạng thái và mã thoát", 3)
cur.cap_table("Bảng 27. Ý nghĩa trạng thái EOD và mã thoát của Run-MarketLab-EOD.ps1")
cur.table(["Trạng thái", "Ý nghĩa", "Có ghi dữ liệu?", "Mã thoát"], [
    ["SUCCESS", "Đủ universe, hợp lệ, đã commit (có thể 0 dòng mới khi chạy lại)", "Có", "0"],
    ["DRY_RUN_OK", "Đã kiểm tra trong SQL Server rồi ROLLBACK", "Không", "0"],
    ["NO_SESSION", "Cuối tuần hoặc ngày nghỉ theo bằng chứng của nguồn", "Không", "0"],
    ["SKIPPED", "Ngày tương lai, trước 16:10, dữ liệu chưa có, khóa bận", "Không", "10"],
    ["PARTIAL", "Thiếu ít nhất một mã", "Không", "20"],
    ["FAILED", "Lỗi cấu hình/nguồn/kiểm tra/SQL hoặc xung đột giá đã chốt", "Không", "30"],
], [2.6, 8.6, 2.6, 2.0])
cur.heading("5.5.6. Bước 6 – Kết quả với dữ liệu thật", 3)
cur.para("Database MarketLabVN30_Live được tạo mới (không phải database nghiên cứu), seed 30 mã từ tệp snapshot VN30 06/2026 có ghi nguồn "
         "HOSE. Ngày 05/11/2026 (22:56–23:11 giờ Việt Nam) và 06/11/2026, nhóm chạy đồng bộ thật với nguồn KBS qua vnstock 3.5.1:")
cur.cap_table("Bảng 28. Các lần đồng bộ thật trên MarketLabVN30_Live (trích ops.EodRun; chỉ số đếm)")
cur.table(["Run", "Phiên", "Kích hoạt", "Kết quả", "Nhận/Yêu cầu", "Thêm", "Không đổi"], [
    ["1", "04/11/2026", "PowerShell, dry run", "DRY_RUN_OK", "30/30", "0 (sẽ thêm 30)", "0"],
    ["2–26", "01/10–04/11/2026", "Backfill 25 ngày thường", "25 × SUCCESS", "30/30", "750", "0"],
    ["27", "05/11/2026", "PowerShell", "SUCCESS", "30/30", "30", "0"],
    ["28", "05/11/2026", "Chạy lại", "SUCCESS", "30/30", "0", "30"],
    ["29", "01/11/2026", "PowerShell", "NO_SESSION (cuối tuần)", "—", "0", "0"],
    ["30", "02/09/2026", "PowerShell", "NO_SESSION (nghỉ theo nguồn)", "—", "0", "0"],
    ["31, 34", "06/11/2026", "PowerShell", "SKIPPED (ngày tương lai)", "—", "0", "0"],
    ["36", "03/11/2026", "PowerShell, interpreter sai", "FAILED (exit 30)", "—", "0", "0"],
    ["37", "05/11/2026", "Dry run lúc 00:24", "PARTIAL – lỗi biên end của nguồn", "10/30", "0", "0"],
    ["38", "05/11/2026", "Dry run sau khi sửa", "DRY_RUN_OK", "30/30", "0", "30"],
    ["39", "05/11/2026", "Biểu mẫu web (WEB)", "DRY_RUN_OK", "30/30", "0", "30"],
], [1.4, 2.8, 3.4, 3.8, 1.9, 2.0, 1.6])
cur.para("Kết quả của giai đoạn đồng bộ ban đầu: 780 dòng giá của 30 mã trên 26 phiên, ObservedThrough 05/11/2026, 780 dòng lineage; "
         "các lần chạy lại và dry run không làm thay đổi số dòng (mục 5.5.7 mở rộng lịch sử về 2023). Giá ACB ngày 04/11/2026 trong database trùng khớp nến lấy độc lập bằng vnstock 4.0.9 trước khi đồng "
         "bộ. Run #37 cho thấy cơ chế an toàn hoạt động: dữ liệu nguồn thiếu nên lần chạy báo PARTIAL và không ghi, thay vì báo SUCCESS.")
cur.heading("5.5.7. Backfill lịch sử 01/01/2023 → phiên hoàn chỉnh mới nhất", 3)
cur.para("Để có dữ liệu lịch sử đủ dài, nhóm mở rộng chính EOD Worker thành tác vụ backfill: nguồn KBS → kiểm tra từng nến bằng cùng quy "
         "tắc → bảng staging ops.BackfillStaging trong database Ops (checkpoint theo mã × năm) → ops.usp_EodApplySession, mỗi phiên một "
         "transaction. Sàn lịch sử 01/01/2023 được áp ở cấu hình, dòng lệnh, staging, trang web và tệp CSV. EndDate “latest” là nến chỉ "
         "số VN30 cuối cùng không muộn hơn hôm nay sau 16:10 (hoặc hôm qua). Một ngày là phiên khi có nến VN30 hoặc có nến của ít nhất "
         "một nửa số mã, nên thứ Bảy, Chủ nhật và ngày lễ không bị tính là thiếu. Phiên trước ObservedThrough được ghi cho các mã có nến "
         "hợp lệ và đánh dấu PARTIAL nếu thiếu mã (không bao giờ tính là đủ 30/30); phiên sau ObservedThrough vẫn theo quy tắc toàn bộ "
         "hoặc không ghi. Cùng khóa cùng giá trị → không đổi; cùng khóa khác giá trị → đưa vào hàng đợi đối soát, giá đã lưu không bị ghi "
         "đè. Trước khi ghi thật, hệ thống tự backup COPY_ONLY database Live và Ops với CHECKSUM, RESTORE VERIFYONLY và khôi phục thử vào "
         "database tạm để so số dòng. Database nghiệp vụ không đổi lược đồ; chỉ database Ops thêm bảng (sql/16_ops_schema_v3_backfill.sql).")
cur.cap_table("Bảng 28a. Dry run và backfill thật trên MarketLabVN30_Live ngày 06/11/2026 (trích ops.BackfillJob; chỉ số đếm)")
cur.table(["Job", "Loại", "Cửa sổ", "Phiên", "Thêm (dự kiến)", "Không đổi", "Thiếu", "Trước lịch sử nguồn", "Xung đột"], [
    ["1", "Dry run", "2023-01-01 → 2026-11-05", "956", "27.317", "780", "583", "0", "0"],
    ["2", "Dry run (sau sửa bridge)", "2023-01-01 → 2026-11-05", "955", "27.288", "780", "0", "582", "0"],
    ["3", "Dry run (lịch hợp)", "2023-01-01 → 2026-11-05", "956", "27.317", "780", "0", "583", "0"],
    ["4", "Ghi thật", "2023-01-01 → 2026-11-05", "956", "27.317", "780", "0", "583", "0"],
    ["5", "Chạy lại để kiểm chứng", "2023-01-01 → 2023-06-30", "121", "0", "3.509", "0", "121", "0"],
], [1.0, 2.9, 3.3, 1.5, 1.9, 1.7, 1.3, 1.9, 1.5])
cur.para("Ba lần dry run cho thấy cơ chế kiểm tra hoạt động với dữ liệu thật. Lần 1: VPL năm 2023–2024 bị nguồn trả lỗi “Dữ liệu trống” "
         "nên bị xếp nhầm là thiếu; bridge được sửa để nhận diện câu trả lời rỗng tường minh của nguồn, khác với lỗi mạng. Lần 2: chuỗi "
         "chỉ số VN30 năm 2025 trả 248 thay vì 249 nến (thiếu 04/04/2025) dù cả 30 mã có nến ngày đó, nên lịch phiên được đổi thành hợp "
         "của nến tham chiếu và nến của đa số mã. Lần 3 khớp lần ghi thật.")
cur.cap_table("Bảng 28b. Kết quả kiểm tra sau backfill (SQL Server, 06/11/2026)")
cur.table(["Kiểm tra", "Kết quả"], [
    ["Tổng dòng OHLCV / phiên", "28.097 dòng (780 có sẵn + 27.317 mới); 956 phiên; 03/01/2023 → 05/11/2026"],
    ["Theo năm (phiên / dòng)", "2023: 249 / 7.221 · 2024: 250 / 7.250 · 2025: 249 / 7.386 · 2026: 208 / 6.240"],
    ["Thiếu theo mã", "0 mã-phiên thiếu; VPL có dữ liệu từ 13/05/2025, 583 phiên trước đó là “trước lịch sử nguồn”"],
    ["Dòng trước 01/01/2023; khóa trùng; vi phạm OHLC", "0; 0; 0"],
    ["Dòng thiếu lineage; TradingDay cuối tuần", "0; 0"],
    ["780 dòng có sẵn", "SHA-256 giá trị và LoadedAt trước = sau backfill"],
    ["Chạy lại cửa sổ 01–06/2023", "0 dòng mới, 3.509 không đổi, SHA-256 trước = sau"],
    ["Biến động Close liên tiếp lớn nhất", "7,06% (biên độ HOSE ±7%); không có bước nhảy > 7,5%"],
    ["Số bảng nghiệp vụ; ObservedThrough", "13; 05/11/2026 (không đổi)"],
], [6.0, 10.6])
cur.para("Độ phủ được báo trung thực là PARTIAL_COVERAGE vì VPL không có lịch sử trước 13/05/2025 ở nguồn; hệ thống không nội suy hay dựng "
         "nến cho khoảng đó. Báo cáo chi tiết theo mã nằm ở docs/BACKFILL_COVERAGE_REPORT.md (chỉ có số đếm, ngày và hash). Sau backfill, "
         "worker EOD hằng ngày tiếp tục hoạt động: phiên 05/11/2026 chạy lại SUCCESS với 0 dòng mới, phiên 06/11/2026 trước 16:10 trả "
         "SKIPPED BEFORE_CUTOFF.")
cur.heading("5.6. Thay đổi SQL và database vận hành", 2)
cur.para("Các thay đổi SQL được trình bày ở mục 2.5 (database Ops) và 3.6 (migration, trigger, thủ tục). Bảng dưới đây mô tả cột của "
         "ops.EodRun, bảng trung tâm của nhật ký.")
cur.cap_table("Bảng 29. Thuộc tính bảng ops.EodRun")
cur.table(["Thuộc tính", "Kiểu", "Ý nghĩa"], [
    ["EodRunId", "BIGINT IDENTITY, PK", "Mã lần chạy"],
    ["RunRef / BatchRef", "VARCHAR(36)", "Mã tham chiếu (UNIQUE) và mã lô backfill"],
    ["DatabaseName, DatasetId", "SYSNAME, INT", "Database và dataset được đồng bộ"],
    ["SessionDate", "DATE", "Ngày phiên (Asia/Ho_Chi_Minh)"],
    ["TriggerKind", "VARCHAR(20) CHECK", "CLI, SCHEDULER, WEB, TEST, BACKFILL (API cho các run lịch sử)"],
    ["IsDryRun, Status", "BIT, VARCHAR(20) CHECK", "RUNNING, SUCCESS, DRY_RUN_OK, NO_SESSION, SKIPPED, PARTIAL, FAILED"],
    ["Requested/Received/Inserted/Unchanged/RejectedCount", "INT ≥ 0", "Số mã yêu cầu, nhận, thêm, không đổi, từ chối"],
    ["StartedAtUtc, FinishedAtUtc", "DATETIME2(3)", "Thời điểm UTC; RUNNING khi chưa kết thúc"],
    ["ErrorCode, Message", "VARCHAR(60), NVARCHAR(2000)", "Mã lỗi bắt buộc với FAILED/PARTIAL/SKIPPED/NO_SESSION; thông điệp đã khử bí mật"],
    ["ObservedThroughBefore/After, ProviderLastCandleDate", "DATE", "Mốc quan sát trước/sau và nến mới nhất của nguồn"],
    ["ProviderMeta", "NVARCHAR(4000)", "JSON: phiên bản vnstock, cửa sổ yêu cầu, quyết định lịch phiên"],
], [5.6, 4.0, 7.0])
cur.heading("5.7. Cài đặt, khởi chạy và lịch thực thi trên Windows", 2)
cur.para("Lần đầu chạy script cài đặt (tạo môi trường Python theo uv.lock, tạo .env, sinh token ngẫu nhiên, kiểm tra kết nối); sau đó một "
         "lệnh khởi động ứng dụng tại http://127.0.0.1:8000/. Script kiểm tra môi trường Python, thư viện, cấu hình, ODBC, kết nối và cổng "
         "trước khi chạy.")
cur.code(["powershell -ExecutionPolicy Bypass -File scripts\\Setup-MarketLab.ps1",
          "powershell -ExecutionPolicy Bypass -File scripts\\Start-MarketLab.ps1",
          "#   -> http://127.0.0.1:8000/   (DEMO_OFFLINE)",
          "powershell -ExecutionPolicy Bypass -File scripts\\Start-MarketLab.ps1 -Mode REAL_PRIVATE -Database MarketLabVN30_Live -Port 8001",
          "powershell -ExecutionPolicy Bypass -File scripts\\Run-MarketLab-EOD.ps1 -Date 2026-11-05 -DryRun",
          "powershell -ExecutionPolicy Bypass -File scripts\\Backfill-MarketLab.ps1 -StartDate 2023-01-01 -EndDate latest -DryRun",
          "powershell -ExecutionPolicy Bypass -File scripts\\Backfill-MarketLab.ps1 -Resume",
          "powershell -ExecutionPolicy Bypass -File scripts\\Stop-MarketLab.ps1 -Port 8000"])
cur.para("Script Install-MarketLab-EODTask.ps1 cài task Windows Task Scheduler ở trạng thái tắt, chạy thứ Hai–thứ Sáu lúc 16:10, 17:30 và "
         "19:30 giờ Việt Nam với tùy chọn -IfNeeded (bỏ qua phiên đã SUCCESS); chỉ bật được bằng -Enable khi đã có một lần chạy thủ công "
         "SUCCESS. Nhóm đã cài task ở trạng thái tắt và chạy thử một lần qua Task Scheduler (-RunNow): kết quả ALREADY_SUCCEEDED, mã thoát 0. "
         "Việc lịch tự chạy đúng 16:10 chưa được kiểm chứng (NOT VERIFIED) vì task chưa được bật.")
cur.heading("5.8. Kiểm thử và nghiệm thu phần mở rộng", 2)
cur.para("Ngoài bộ 140 ca ở mục 4.5, giao diện được kiểm tra bằng công cụ tự động mở từng trang trong Microsoft Edge ở hai chế độ và bốn "
         "kích thước, và số liệu hiển thị được đối chiếu trực tiếp với SQL.")
cur.cap_table("Bảng 30. Kiểm tra giao diện tự động (scripts/ui_audit.py, 06/11/2026)")
cur.table(["Kích thước", "Số màn hình", "Tràn ngang", "Lỗi console", "Request lỗi", "Trình duyệt tự gọi dữ liệu", "Kết quả"], [
    ["1440×900", "12", "0", "0", "0", "0", "PASS"], ["1280×800", "12", "0", "0", "0", "0", "PASS"],
    ["768×1024", "12", "0", "0", "0", "0", "PASS"], ["390×844", "12", "0", "0", "0", "0", "PASS"],
], [2.4, 2.0, 2.0, 2.0, 2.2, 3.6, 2.2])
cur.cap_table("Bảng 31. Đối chiếu số liệu trên trang với truy vấn SQL")
cur.table(["Hành trình", "Trang", "Đối chiếu SQL", "Kết quả"], [
    ["Đọc chỉ tiêu tổng quan", "/?ds=1", "COUNT DailyPrice, COUNT DISTINCT StockId, fn_EligiblePredictions → 280 / 8 / 256", "Khớp"],
    ["Lọc mã + ngày, sắp xếp", "/market?t=DEMO03&f=…&sort=close", "SELECT cùng điều kiện, ORDER BY ClosePrice → 10 dòng đúng thứ tự", "Khớp"],
    ["Biểu đồ", "/market", "Số điểm có giá = số dòng SQL; basis SOURCE_CLOSE", "Khớp"],
    ["Hiệu năng run 1", "/forecast?run=1&as_of=2026-07-01", "usp_GetModelPerformance → 128 dòng, Accuracy 0,546875", "Khớp"],
    ["So sánh run 1, 2", "/compare?runs=1&runs=2", "usp_CompareModels → 128 quan sát chung", "Khớp"],
    ["Trạng thái EOD (REAL)", "/ops", "ops.EodRun: phiên SUCCESS gần nhất, số run EOD hằng ngày", "Khớp"],
    ["Mã và khoảng ngày ngẫu nhiên (REAL)", "/market × 6", "6 cặp mã/khoảng chọn bằng seed 20261106: hash trang 1, tổng dòng, số điểm biểu đồ", "Khớp"],
    ["Sàn 2023 (REAL)", "/market, /market/export.csv", "f = 2022-06-01 → 422; CSV = SQL, không dòng nào trước 2023", "Khớp"],
    ["Độ phủ (REAL)", "/backfill", "Số dòng của 30 mã = COUNT theo mã", "Khớp (LIVE 38/38, DEMO 26/26)"],
    ["Dry run qua form (REAL)", "POST /ops/eod", "ops.EodRun #39 WEB DRY_RUN_OK; DailyPrice vẫn 780", "Khớp"],
], [3.4, 4.0, 7.0, 2.2])
cur.heading("5.9. Kết quả hoàn thiện giao diện", 2)
cur.para("Trước khi hoàn thiện, nhóm chạy kiểm tra giao diện có ghi ảnh và lập bảng lỗi theo mức độ; sau khi sửa, chạy lại cùng công cụ. "
         "Các lỗi chính đã xử lý được tóm tắt dưới đây (chi tiết trong docs/PRODUCT_UI_AUDIT.md và docs/PRODUCT_UI_QA.md).")
cur.cap_table("Bảng 32. Tổng hợp lỗi phát hiện và đã sửa")
cur.table(["Mã", "Mức", "Vấn đề", "Cách sửa", "Trạng thái"], [
    ["UI-01", "P0", "Trang Swagger không hiển thị (OpenAPI 3.1 so với Swagger UI 4)", "Sửa; sau đó gỡ toàn bộ Swagger theo kiến trúc cuối", "Đã xử lý"],
    ["EOD-01", "P1", "Sau nửa đêm nguồn coi end là không bao gồm → PARTIAL giả", "Xin tới D+1, bỏ nến sau D; test hồi quy", "Đã sửa, kiểm bằng dữ liệu thật"],
    ["SSR-01", "P1", "Form POST bị chặn do Origin: null khi Referrer-Policy no-referrer", "Referrer-Policy same-origin", "Đã sửa"],
    ["UI-04/05/06", "P1", "Số 0 thay cho thiếu dữ liệu; thẻ chỉ tiêu quá dài; thiếu chỉ báo độ mới", "“—” có giải thích; khối nguồn riêng; trạng thái độ mới", "Đã sửa"],
    ["UI-07", "P1", "Biểu đồ nối qua phiên thiếu giá", "Ngắt đường, đánh dấu phiên thiếu", "Đã sửa"],
    ["UI-08/09/12", "P1", "Mất bộ lọc khi tải lại; mobile chật; thiếu điều hướng bàn phím", "Bộ lọc trên URL; bố cục responsive; skip link, nhãn, focus", "Đã sửa"],
    ["UI-18", "P2", "Độ trễ 3–4 giây không đều ở lần tải đầu", "Thêm Server-Timing và log request chậm", "Chưa xác định nguyên nhân"],
], [1.8, 1.1, 5.4, 5.4, 2.9])
side_by_side(cur, [
    (ROOT / "tests" / "product_evidence" / "ui_audit" / "before" / "DEMO_390x844_market.png",
     "Hình 16. Trước khi hoàn thiện: trang giá trên điện thoại.",
     "Ảnh audit “before” 2026-11-06 00:02, giao diện commit da7b27b, phần đầu trang; bảng bị cắt cột, không có gợi ý cuộn."),
    (SCREENS / "08_demo_market_390x844.png",
     "Hình 17. Sau khi hoàn thiện: cùng trang trên điện thoại.",
     f"Ảnh {MANIFEST['08_demo_market_390x844.png']['captured_at'][:16].replace('T', ' ')}, ứng dụng web cuối, phần đầu trang; bảng cuộn trong khung, có gợi ý “Vuốt ngang”."),
], height_cm=12.5, crop_px=1350)
cur.heading("5.10. So sánh chế độ dữ liệu và kịch bản trình diễn", 2)
cur.cap_table("Bảng 33. Kịch bản trình diễn 5–7 phút")
cur.table(["Phút", "Thao tác", "Điểm cần nói"], [
    ["0:00", "Sơ đồ kiến trúc; mở /api/docs → 404", "Trình duyệt → ứng dụng web Python → SQL Server; không API Gateway"],
    ["0:45", "Trang Tổng quan (DEMO)", "Nhãn mô phỏng; 280 giá, 256 dự báo đủ điều kiện"],
    ["1:30", "Giá & biểu đồ: DEMO03, rê chuột, sắp xếp, lọc, F5", "Hai khung Close/Volume; EOD không realtime; bộ lọc trên URL"],
    ["2:15", "Dự báo: lọc “Chưa trưởng thành”", "fn_EligiblePredictions(as_of); “—” không phải 0; không có inference"],
    ["3:00", "So sánh run 1, 2", "usp_CompareModels: 128 quan sát chung"],
    ["3:30", "Chuyển sang LIVE: Tổng quan, Lịch sử OHLCV FPT “Tất cả”, tab Backfill", "28.097 giá KBS 2023–2026; VPL từ 13/05/2025; 0 xung đột"],
    ["4:00", "Vận hành EOD: run #37 và #39", "Bốn mốc ngày; PARTIAL không ghi; dry run qua form"],
    ["5:30", "Token sai; Sync không xác nhận", "INVALID_OPS_TOKEN; CONFIRMATION_REQUIRED"],
    ["6:00", "SSMS: COUNT(*) DailyPrice; TOP 5 ops.EodRun", "Số trên trang = SQL"],
], [1.4, 6.6, 8.6])

# ===============================================================================================================
# Conclusion
_, p = find("Phần mở rộng đề xuất Web UI, local REST API")
set_text(p, "Phần mở rộng đưa bài tập lớn từ demo SSMS sang một ứng dụng chạy cục bộ có thể dùng sau mỗi phiên: ứng dụng web dựng trang "
            "ở máy chủ từ SQL Server với sáu khu vực chức năng, và tác vụ đồng bộ cuối phiên cùng backfill lịch sử đã nạp 28.097 dòng giá "
            "thật của 30 mã từ 03/01/2023 đến 05/11/2026 với transaction theo từng phiên, chạy lại không tạo trùng và nhật ký đầy đủ. Kiến trúc cuối bỏ lớp API Gateway để giảm bề mặt và độ phức "
            "tạp mà không mất chức năng.")
cur = Cursor(p._p)
cur.cap_table("Bảng 34. Đối chiếu yêu cầu và kết quả")
cur.table(["Yêu cầu", "Kết quả", "Trạng thái"], [
    ["13 bảng 3NF, khóa, CHECK, trigger", "Giữ nguyên; 44/44 ca PASS trên demo và trên bản đã migrate", "Đã kiểm chứng"],
    ["16 truy vấn, 4 procedure, 3 function, 4 view", "Chạy lại 06/11/2026, khớp số dòng lịch sử", "Đã kiểm chứng"],
    ["Ứng dụng web 6 khu vực, khớp SQL", "Đối chiếu tự động DEMO 26/26, LIVE 38/38; 4 kích thước màn hình, 48/48 màn hình", "Đã kiểm chứng"],
    ["Không API Gateway, không Swagger", "/api/* và /api/docs trả 404; trình duyệt không gọi dữ liệu", "Đã kiểm chứng"],
    ["EOD với nguồn thật, idempotent, rollback", "Phiên 05/11/2026 chạy lại 0 dòng mới; PARTIAL/FAILED không ghi", "Đã kiểm chứng"],
    ["Backfill OHLCV thật 2023 → nay", "28.097 dòng, 956 phiên, 0 thiếu (trừ VPL trước niêm yết), 0 xung đột; chạy lại hash không đổi", "Đã kiểm chứng"],
    ["Lịch Task Scheduler 16:10 tự chạy", "Task cài ở trạng thái tắt; chạy thử -RunNow thành công", "Chưa kiểm chứng"],
    ["Migration database nghiên cứu", "Có preflight, backup, rollback; chưa áp dụng", "Chưa thực hiện"],
    ["Tạo dự báo mới hằng ngày", "Không có model artifact", "Chưa triển khai"],
], [5.0, 8.0, 3.6])
_, p = find("Giới hạn thứ hai là môi trường triển khai")
set_text(p, "Giới hạn thứ hai là môi trường triển khai. Hệ thống chỉ được kiểm chứng trên SQL Server 2025 Developer, chưa trên Express/2016. "
            "Lịch tự động 16:10 chưa được bật nên chưa có bằng chứng tự chạy; task chỉ chạy khi người dùng đã đăng nhập Windows. Lịch nghỉ "
            "được suy từ chuỗi chỉ số của chính nguồn và nến của đa số mã. Universe 30 mã là snapshot VN30 06/2026, chưa có thành phần VN30 "
            "tại từng thời điểm từ 2023. Nguồn KBS điều chỉnh hồi tố giá lịch sử nên chuỗi giá lưu có thể gãy tại sự kiện doanh "
            "nghiệp; cơ chế đối soát phát hiện thay đổi và cần người duyệt. Nhánh chưa được đẩy lên GitHub: cổng kiểm tra công bố "
            "(scripts/check_publication.py) chưa duyệt các tệp mới và việc công bố cần chủ repository phê duyệt; mã nguồn mới hiện có "
            "trên nhánh cục bộ.")
_, p = find("Hướng hoàn thiện ưu tiên gồm")
set_text(p, "Hướng phát triển: (1) bật và theo dõi lịch tự động sau khi được chủ dữ liệu đồng ý; (2) migrate database nghiên cứu sau khi "
            "sao lưu và duyệt; (3) bổ sung lịch nghỉ HOSE chính thức dạng máy đọc được; (4) quy trình duyệt đối soát trên giao diện; (5) "
            "chụp bổ sung ảnh SSMS cho các ví dụ Chương 3–4; (6) chỉ sau đó mới xem xét tích hợp mô hình tạo dự báo mới với ModelRun mới và "
            "kiểm soát rò rỉ dữ liệu tương lai.")

# References
_, p = find("[9] FastAPI Documentation")
set_text(p, "[9] FastAPI Documentation, “Templates”, https://fastapi.tiangolo.com/advanced/templates/ (truy cập 06/11/2026).")
_, p = find("[10] VNstock Documentation")
set_text(p, "[10] Repository vnstock, https://github.com/thinh-vu/vnstock (truy cập 06/11/2026); phiên bản dùng khi đồng bộ: 3.5.1, nguồn KBS.")
_, p = find("[13] Báo cáo gốc của nhóm")
cur = Cursor(p._p)
for ref in ["[14] Microsoft Learn, “OPENJSON (Transact-SQL)”, https://learn.microsoft.com/en-us/sql/t-sql/functions/openjson-transact-sql.",
            "[15] Microsoft Learn, “SESSION_CONTEXT (Transact-SQL)”, https://learn.microsoft.com/en-us/sql/t-sql/functions/session-context-transact-sql.",
            "[16] pyodbc Wiki, https://github.com/mkleehammer/pyodbc/wiki (truy cập 06/11/2026).",
            "[17] OWASP Foundation, “Cross Site Request Forgery (CSRF)”, https://owasp.org/www-community/attacks/csrf.",
            "[18] Playwright for Python, https://playwright.dev/python/docs/intro.",
            "[19] Microsoft Learn, “Task Scheduler for developers”, https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page.",
            f"[20] Mã nguồn và tài liệu phần mở rộng trên nhánh feature/marketlab-working-product (commit {SHA}), các tệp docs/PRODUCT_*.md và "
            "tests/product_evidence/."]:
    cur.para(ref, indent=False)   # same format as the template's [1]-[13]: justified, no first-line indent

# Appendix A
_, p = find("PHỤ LỤC A.")
set_text(p, "PHỤ LỤC A. DANH MỤC SCRIPT, BẰNG CHỨNG VÀ LỆNH ĐỐI CHIẾU")
_, pc = find("Bảng 27. Danh mục tệp cần có")
set_text(pc, "Bảng 35. Danh mục tệp trong hồ sơ nộp")
t27 = pc._p.getnext()
_, pa1 = find("A.1. Ảnh chụp minh chứng")
remove_between(t27, pa1._p)
cur = Cursor(pc._p)
cur.table(["Tệp", "Mục đích", "Trạng thái"], [
    ["sql/00–10, all_in_one.sql", "13 bảng, ràng buộc, đối tượng SQL, truy vấn, 44 ca kiểm thử, demo", "Có, chạy lại 06/11/2026"],
    ["sql/13_*.sql – 16_*.sql", "Migration EOD, database Ops (v1–v3), preflight, rollback", "Có, đã áp lên Live và Ops"],
    ["marketlab_app/", "Ứng dụng web, truy vấn, EOD Worker", "Có (nhánh cục bộ)"],
    ["scripts/*.ps1", "Cài đặt, khởi động, dừng, EOD, Task Scheduler", "Có, đã chạy"],
    ["tests/product/", "140 ca kiểm thử", "140 PASS"],
    ["tests/product_evidence/", "Log pytest/JUnit, regression, kiểm tra giao diện, đối chiếu", "Có"],
    ["report/final/assets/screens/, web_final/", "17 + 16 ảnh giao diện + manifest", "Có"],
    ["docs/PRODUCT_*.md, BACKFILL_*.md, FINAL_WEB_ACCEPTANCE.md", "Audit, runbook, hợp đồng dữ liệu EOD, backfill, nghiệm thu, QA, bằng chứng", "Có"],
], [5.0, 8.0, 3.6])
_, pa1 = find("A.1. Ảnh chụp minh chứng")
set_text(pa1, "A.1. Ảnh đã đưa vào báo cáo và ảnh cần chụp bổ sung")
_, pa2 = find("A.2. Các lệnh đối chiếu")
remove_between(pa1._p.getnext(), pa2._p)
cur = Cursor(pa1._p)
cur.para("Ảnh giao diện trong báo cáo (Hình 4–17) đều được chụp tự động bằng Microsoft Edge từ ứng dụng đang chạy; thông tin route, chế độ "
         "dữ liệu, kích thước và thời điểm chụp ghi trong report/final/assets/web_final/manifest.json và "
         "report/final/assets/screens/screens_manifest.json. Ảnh cần chụp bổ sung bằng tay "
         "(chưa có trong báo cáo):")
cur.bullets(["SSMS: Object Explorer của MarketLabVN30_Demo với 13 bảng và kết quả SELECT @@VERSION.",
             "SSMS: kết quả Q02, Q06/Q07 và usp_CompareModels (đã có output sqlcmd trong Chương 3–4).",
             "SSMS: lỗi CHECK Volume âm trong TRY/CATCH và số dòng trước/sau ROLLBACK.",
             "SSMS: SELECT TOP 10 * FROM MarketLabVN30_Ops.ops.EodRun ORDER BY EodRunId DESC (dữ liệu nhật ký, không có giá)."])
_, pa2 = find("A.2. Các lệnh đối chiếu")
nxt = pa2._p.getnext()
_, pb = find("PHỤ LỤC B.")
remove_between(nxt, pb._p)
cur = Cursor(pa2._p)
cur.code(["SELECT DB_NAME() AS DBName, @@VERSION AS SqlServerVersion;",
          "SELECT COUNT(*) AS PriceRows FROM dbo.DailyPrice;           -- Demo 280, Live 28097",
          "SELECT * FROM dbo.vw_ModelPerformance;",
          "SELECT TOP(20) EodRunId,SessionDate,TriggerKind,IsDryRun,Status,ErrorCode,",
          "       RequestedCount,ReceivedCount,InsertedCount,UnchangedCount",
          "FROM MarketLabVN30_Ops.ops.EodRun ORDER BY EodRunId DESC;",
          "-- PowerShell",
          "uv run pytest tests/product",
          "uv run python scripts/run_public_regression.py --server .",
          "uv run python scripts/verify_web_vs_sql.py --base-url http://127.0.0.1:8000 --out web_vs_sql.json"])

# Appendix B: replace AI-tool instructions with the claim/evidence table
_, pb = find("PHỤ LỤC B.")
set_text(pb, "PHỤ LỤC B. BẢNG TRUY VẾT TUYÊN BỐ – BẰNG CHỨNG")
rest = pb._p.getnext()
sect = body.find(qn("w:sectPr"))
remove_between(rest, sect)
cur = Cursor(pb._p)
cur.cap_table("Bảng 36. Các tuyên bố chính của báo cáo và nguồn kiểm chứng")
cur.table(["Tuyên bố", "Bằng chứng", "Trạng thái"], [
    ["13 bảng, 16 FK, 4 procedure, 3 function, 4 view, 10 trigger", "sys.objects trên MarketLabVN30_Demo 06/11/2026", "PASS"],
    ["44 ca SQL PASS; hash 13 bảng không đổi", "tests/product_evidence/logs/original_public_regression.log", "PASS"],
    ["44/44 sau migration 13", "test_integration_sql_regression.py", "PASS"],
    ["16 truy vấn khớp số dòng lịch sử", "tests/runs/public_20261105T175220966677Z/query_*.log", "PASS"],
    ["Bảng 22 (600 quan sát) tái lập được", "usp_CompareModels chỉ đọc trên DB nghiên cứu 06/11/2026", "PASS"],
    ["140 ca kiểm thử phần mở rộng", "tests/product_evidence/logs/pytest_final_web.xml", "PASS"],
    ["Giao diện 48/48 màn hình không lỗi", "tests/product_evidence/ui_audit/final_web/", "PASS"],
    ["Số liệu trang khớp SQL", "web_vs_sql_demo.json (26/26); web_vs_sql_real_summary.json (38/38)", "PASS"],
    ["28.097 giá thật 2023–2026, 0 xung đột", "ops.BackfillJob #4; docs/BACKFILL_COVERAGE_REPORT.md", "PASS"],
    ["Chạy lại không thêm dòng, hash không đổi", "ops.BackfillJob #5; EodRun 05/11/2026 0 dòng mới", "PASS"],
    ["Không dòng nào trước 01/01/2023", "COUNT TradeDate < 2023-01-01 = 0; test sàn lịch sử", "PASS"],
    ["Không còn API Gateway/Swagger", "Route 404; test_pages_render_and_no_api_or_swagger_surface", "PASS"],
    ["Lịch tự động 16:10", "Task ở trạng thái tắt", "NOT VERIFIED"],
    ["Migration DB nghiên cứu", "—", "NOT DONE"],
    ["Inference dự báo mới", "—", "NOT IMPLEMENTED"],
    ["EOD phiên 06/11/2026", "Chưa qua 16:10 lúc kiểm chứng", "NOT VERIFIED"],
    ["Đẩy nhánh / pull request", "Chưa đẩy: cổng công bố FAIL, chờ chủ repository duyệt", "BLOCKED"],
], [5.6, 7.6, 3.4])
cur.para("Chi tiết đầy đủ: report/final/CLAIMS_EVIDENCE_MATRIX.md và report/final/QA_REPORT.md.", align="left")

# ===============================================================================================================
# caption styles for the Word lists of figures / tables. Original numbers are kept (inserted tables use 3a, 18a, ...)
# so that in-text references such as "Bảng 22" stay valid.
fig_n = tab_n = 0
seen = []
for p in paras():
    if p.style.name in ("Caption Local", "Caption Figure", "Caption Table"):
        m = re.match(r"^(Hình|Bảng) ([0-9]+[a-z]?)\.", p.text.strip())
        if not m:
            continue
        seen.append(m.group(1) + " " + m.group(2))
        if m.group(1) == "Hình":
            fig_n += 1
            p.style = st["Caption Figure"]
        else:
            tab_n += 1
            p.style = st["Caption Table"]
assert len(seen) == len(set(seen)), [x for x in seen if seen.count(x) > 1]
# ===============================================================================================================
# table pagination pass (template tables and inserted ones): rows never split across pages, short tables stay in one
# piece with their caption, and text right after a table gets space before it.
for tbl in body.iter(qn("w:tbl")):
    if tbl.getparent() is not body:
        continue
    rows = tbl.findall(qn("w:tr"))
    first_cell_text = "".join(rows[0].itertext()).strip()
    if first_cell_text.startswith("Giảng viên") or not rows:
        continue                                  # cover table
    for k, tr in enumerate(rows):
        trPr = tr.find(qn("w:trPr"))
        if trPr is None:
            trPr = OxmlElement("w:trPr")
            tcfirst = tr.find(qn("w:tc"))
            tcfirst.addprevious(trPr)
        if trPr.find(qn("w:cantSplit")) is None:
            trPr.insert(0, OxmlElement("w:cantSplit"))
        if len(rows) <= 16 and k < len(rows) - 1:
            for pp in tr.iter(qn("w:p")):
                from docx.text.paragraph import Paragraph
                Paragraph(pp, None).paragraph_format.keep_with_next = True
    nxt = tbl.getnext()
    if nxt is not None and nxt.tag == qn("w:p") and "".join(nxt.itertext()).strip():
        after_table_gap(nxt)
# Chapter starts: the template ends each chapter with an empty paragraph holding a page break. When the preceding text fills
# a page exactly, that paragraph spills onto a blank page. Replace it with "page break before" on the chapter heading.
for p in paras():
    if p.style.name not in ("Heading 1", "Heading Unnumbered"):
        continue
    prev = p._p.getprevious()
    if prev is not None and prev.tag == qn("w:p") and not "".join(prev.itertext()).strip() and             any(br.get(qn("w:type")) == "page" for br in prev.iter(qn("w:br"))) and prev.find(qn("w:pPr") + "/" + qn("w:sectPr")) is None:
        prev.getparent().remove(prev)
        p.paragraph_format.page_break_before = True
    # the list-of-figures / list-of-tables fields replaced the paragraphs that carried the template's page breaks
    if p.text.strip().startswith(("CHƯƠNG", "KẾT LUẬN", "TÀI LIỆU", "PHỤ LỤC", "DANH MỤC HÌNH")):
        p.paragraph_format.page_break_before = True
for p in paras():                                   # a table caption always stays with its table
    if p.style.name == "Caption Table":
        p.paragraph_format.keep_with_next = True

doc.core_properties.title = "MarketLab VN30 – Báo cáo bài tập lớn (FINAL)"
doc.core_properties.comments = f"Built by scripts/build_final_report.py from the team template; web application commit {SHA}."
doc.save(str(OUT))
print(f"saved {OUT} figures={fig_n} tables={tab_n}")
