// Progressive enhancement only. Pages are fully rendered by the Python server; this script makes NO network request
// (CSP connect-src 'none'): it draws the chart from data embedded in the page, auto-submits the dataset picker,
// asks for confirmation before EOD actions and shows a loading indicator during navigation.
import { priceVolumeChart } from "./charts.js";

const $ = (id) => document.getElementById(id);

let zoom = null;   // [first, last] index into the embedded points, or null for the full range

function drawChart() {
  const holder = $("chart"), data = $("chartData");
  if (!holder || !data) return;
  const d = JSON.parse(data.textContent);
  if (!d.points || !d.points.length) return;
  const pts = zoom ? d.points.slice(zoom[0], zoom[1] + 1) : d.points;
  const offset = zoom ? zoom[0] : 0;
  priceVolumeChart(holder, pts, { ticker: d.ticker, datasetCode: d.datasetCode, unit: d.unit, unitShort: d.unitShort,
    basis: d.basis, tooltip: $("tooltip"),
    onZoom: (a, b) => { zoom = [offset + a, offset + b]; drawChart(); } });
  const state = $("zoomState"), reset = $("zoomReset");
  if (state) {
    state.textContent = zoom
      ? `Đang phóng to: ${String(pts[0].TradeDate).slice(0, 10)} → ${String(pts[pts.length - 1].TradeDate).slice(0, 10)} (${pts.length} phiên)`
      : "Kéo chuột ngang trên biểu đồ để phóng to · ←/→ đọc từng phiên";
  }
  if (reset) reset.hidden = !zoom;
}

function wireBackfillForm() {
  const f = $("backfillForm");
  if (!f) return;
  f.addEventListener("submit", (e) => {
    const action = e.submitter?.value;
    const write = action === "RUN" || action === "RESUME";
    if (write && !$("bConfirm").checked) { e.preventDefault(); alert("Tích ô xác nhận trước khi ghi thật."); return; }
    const where = `${f.dataset.database} / ${f.dataset.dataset}`;
    const range = action.startsWith("RESUME") ? "job chưa hoàn tất gần nhất" : `${$("bStart").value} → ${$("bEnd").value || "latest"}`;
    const q = write
      ? `GHI THẬT dữ liệu lịch sử (${range}) vào ${where}?
Backup + xác minh trước khi ghi; mỗi phiên một transaction; giá đã lưu khác nguồn chỉ vào hàng đợi đối soát.`
      : `DRY RUN (${range}) cho ${where}?
Kiểm tra trong SQL Server rồi ROLLBACK, không ghi dữ liệu nghiệp vụ.`;
    if (!window.confirm(q)) { e.preventDefault(); return; }
    f.querySelectorAll("button[type=submit]").forEach((b) => { b.disabled = true; });
    const keep = document.createElement("input");
    keep.type = "hidden"; keep.name = "action"; keep.value = action;
    f.appendChild(keep);
    busy();
  });
}

function busy() {
  const bar = $("navProgress");
  if (bar) bar.hidden = false;
  document.body.classList.add("is-loading");
}

function wire() {
  if (!$("tooltip")) {
    const t = document.createElement("div");
    t.id = "tooltip"; t.className = "tooltip"; t.setAttribute("role", "tooltip"); t.hidden = true;
    document.body.appendChild(t);
  }
  const sel = $("datasetSelect");
  if (sel) sel.addEventListener("change", () => { busy(); sel.form.requestSubmit(); });

  document.querySelectorAll("form").forEach((f) => {
    if (f.id === "opsForm" || f.id === "backfillForm") return;
    f.addEventListener("submit", busy);
  });
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[href]");
    if (a && !a.target && !e.ctrlKey && !e.metaKey && a.origin === location.origin && !a.hash) busy();
  });

  const ops = $("opsForm");
  if (ops) {
    ops.addEventListener("submit", (e) => {
      const action = e.submitter?.value;
      const date = $("oDate").value;
      const where = `${ops.dataset.database} / ${ops.dataset.dataset}`;
      if (action === "SYNC" && !$("oConfirm").checked) {
        e.preventDefault();
        alert("Tích ô xác nhận trước khi ghi thật.");
        return;
      }
      const q = action === "SYNC"
        ? `GHI THẬT phiên ${date} vào ${where}?\nTransaction all-or-nothing, có nhật ký. Chạy lại cùng dữ liệu không thêm dòng.`
        : `DRY RUN phiên ${date} cho ${where}?\nKiểm tra trong SQL Server rồi ROLLBACK, không ghi dữ liệu.`;
      if (!window.confirm(q)) { e.preventDefault(); return; }
      ops.querySelectorAll("button[type=submit]").forEach((b) => { b.disabled = true; });
      // the clicked button's name/value must still be submitted: keep it via a hidden input
      const keep = document.createElement("input");
      keep.type = "hidden"; keep.name = "action"; keep.value = action;
      ops.appendChild(keep);
      busy();
    });
  }
  // never keep the token around (also after back/forward cache restores)
  window.addEventListener("pageshow", () => {
    for (const id of ["oToken", "bToken"]) { const t = $(id); if (t) t.value = ""; }
    if ($("navProgress")) $("navProgress").hidden = true;
  });

  const reset = $("zoomReset");
  if (reset) reset.addEventListener("click", () => { zoom = null; drawChart(); });
  wireBackfillForm();
  drawChart();
  let timer;
  window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(drawChart, 200); });
}

wire();
