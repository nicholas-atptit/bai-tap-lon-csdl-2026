// MarketLab VN30 dashboard. Every number shown comes from the local API (SQL Server); no mock data.
import { priceVolumeChart, fmtNum } from "./charts.js";

const $ = (id) => document.getElementById(id);
const state = { meta: null, datasets: [], datasetId: null, runs: [], selectedRun: null,
  price: { offset: 0, limit: 50, sort: "date", order: "desc" }, pred: { offset: 0, limit: 50 }, ops: { offset: 0, limit: 15 },
  loaded: {} };

class ApiError extends Error {
  constructor(status, code, message, details) { super(message); this.status = status; this.code = code; this.details = details; }
}

async function api(path, init) {
  let res;
  try {
    res = await fetch(path, { headers: { Accept: "application/json", ...(init?.headers || {}) }, ...init });
  } catch (e) {
    throw new ApiError(0, "NETWORK", "Không kết nối được API cục bộ (server đã dừng?)");
  }
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const err = body?.error || {};
    throw new ApiError(res.status, err.code || `HTTP_${res.status}`, err.message || res.statusText, err.details);
  }
  return body;
}

function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}

function setState(container, kind, message) {
  container.replaceChildren(el("div", { class: `state ${kind}` }, message));
}
function showError(container, err) {
  const msg = err instanceof ApiError ? `${err.code}: ${err.message}` : String(err);
  container.replaceChildren(el("div", { class: "state error", role: "alert" }, msg,
    err?.details ? el("div", { class: "hint" }, JSON.stringify(err.details)) : null));
}
const dash = (v) => (v === null || v === undefined || v === "" ? "—" : String(v));
const fmtDate = (v) => (v ? String(v).slice(0, 10) : "—");
const fmtTime = (v) => (v ? String(v).replace("T", " ").slice(0, 19) + " UTC" : "—");
const pct = (v) => (v === null || v === undefined || !isFinite(Number(v)) ? "—" : `${fmtNum(Number(v) * 100, 2)}%`);

const STATUS_CLASS = { SUCCESS: "good", DRY_RUN_OK: "info", NO_SESSION: "info", SKIPPED: "warning", PARTIAL: "serious",
  FAILED: "critical", RUNNING: "info", ELIGIBLE: "good", PENDING: "warning", MISSING_ENDPOINT: "serious",
  PENDING_REVIEW: "warning", APPROVED_UPDATE: "good", REJECTED: "critical", INSERTED: "good", UNCHANGED: "info",
  WOULD_INSERT: "info", MISSING: "serious", CONFLICT: "critical", NOT_WRITTEN: "warning" };
const badge = (s, cls) => el("span", { class: `badge ${cls || STATUS_CLASS[s] || "info"}` }, s ?? "—");

function table(columns, rows, opts = {}) {
  if (!rows.length) return el("div", { class: "state" }, opts.empty || "Không có dữ liệu cho bộ lọc này.");
  const head = el("tr", {}, columns.map((c) => {
    const th = el("th", { class: [c.num ? "num" : "", c.sort ? "sortable" : ""].join(" "), scope: "col" }, c.label);
    if (c.sort && opts.onSort) {
      th.addEventListener("click", () => opts.onSort(c.sort));
      if (opts.sortKey === c.sort) th.append(opts.sortOrder === "asc" ? " ▲" : " ▼");
    }
    return th;
  }));
  const body = rows.map((r) => {
    const tr = el("tr", { class: opts.onRow ? "clickable" : "" }, columns.map((c) => {
      const v = c.render ? c.render(r) : dash(r[c.key]);
      return el("td", { class: c.num ? "num" : "" }, v);
    }));
    if (opts.onRow) tr.addEventListener("click", () => opts.onRow(r, tr));
    if (opts.selected && opts.selected(r)) tr.classList.add("selected");
    return tr;
  });
  return el("table", {}, el("thead", {}, head), el("tbody", {}, body));
}

function pager(container, total, offset, limit, go) {
  container.replaceChildren();
  if (!total) return;
  const from = offset + 1, to = Math.min(total, offset + limit);
  container.append(`${fmtNum(from, 0)}–${fmtNum(to, 0)} / ${fmtNum(total, 0)}`,
    el("button", { type: "button", disabled: offset === 0, onclick: () => go(Math.max(0, offset - limit)) }, "‹ Trước"),
    el("button", { type: "button", disabled: to >= total, onclick: () => go(offset + limit) }, "Sau ›"));
}

const card = (k, v, s) => el("div", { class: "card" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v), s ? el("div", { class: "s" }, s) : null);
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== "")).toString();
const currentDataset = () => state.datasets.find((d) => d.DatasetId === state.datasetId);

// ---------------------------------------------------------------------------------------------------
async function boot() {
  wireTabs();
  try {
    state.meta = await api("/api/meta");
  } catch (e) {
    $("modeBadge").textContent = "API lỗi"; $("modeBadge").className = "mode error";
    showError($("overviewCards"), e); return;
  }
  const m = state.meta;
  $("modeBadge").textContent = m.label;
  $("modeBadge").className = `mode ${m.mode === "DEMO_OFFLINE" ? "demo" : "real"}`;
  $("disclaimer").textContent = m.disclaimer;
  $("inferenceNotice").textContent = m.inference.message;
  $("footer").textContent = `Chế độ ${m.mode} · database ${m.database} trên ${m.server} · ngày VN ${m.today_vn} · `
    + "Kết quả dựa trên SQL Server cục bộ; không hiển thị dữ liệu giả lập ở chế độ REAL_PRIVATE.";
  for (const id of ["fAsOf", "cAsOf"]) $(id).value = m.today_vn;
  $("oDate").value = m.today_vn;
  try {
    const ds = await api("/api/datasets");
    state.datasets = ds.items;
  } catch (e) {
    showError($("overviewCards"), e); $("datasetSelect").replaceChildren(el("option", {}, "—")); return;
  }
  const sel = $("datasetSelect");
  sel.replaceChildren(...state.datasets.map((d) => el("option", { value: d.DatasetId }, `${d.DatasetCode} (${d.DataKind})`)));
  if (!state.datasets.length) { setState($("overviewCards"), "", "Database không có dataset nào."); return; }
  state.datasetId = state.datasets[0].DatasetId;
  sel.addEventListener("change", () => { state.datasetId = Number(sel.value); state.loaded = {}; state.selectedRun = null; loadTab(activeTab()); });
  wireForms();
  loadTab(activeTab());   // the user may have switched tab while datasets were loading
}

function wireTabs() {
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    document.querySelectorAll(".tab-panel").forEach((p) => { p.hidden = p.id !== `tab-${b.dataset.tab}`; });
    loadTab(b.dataset.tab);
  }));
}
const activeTab = () => document.querySelector('.tabs button[aria-selected="true"]').dataset.tab;

function loadTab(tab) {
  if (!state.datasetId || state.loaded[tab]) return;
  state.loaded[tab] = true;
  ({ overview: loadOverview, market: initMarket, forecast: loadRuns, compare: initCompare, ops: loadOps })[tab]();
}

// ---------------------------------------------------------------------------------------------------
async function loadOverview() {
  const cards = $("overviewCards");
  setState(cards, "loading", "Đang tải tổng quan…");
  setState($("latestTable"), "loading", "Đang tải giá gần nhất…");
  try {
    const o = await api(`/api/overview?${qs({ dataset_id: state.datasetId })}`);
    const d = o.dataset;
    const eod = o.eod;
    cards.replaceChildren(
      card("Chế độ / nguồn", state.meta.mode, `${d.DataKind} · ${d.MarketCode} · ${d.PriceBasis}`),
      card("Dataset", d.DatasetCode, d.ProvenanceNote),
      card("Đơn vị giá", d.PriceUnit, "Không quy đổi, không điều chỉnh tổng lợi suất"),
      card("Quan sát đến (ObservedThrough)", fmtDate(d.ObservedThrough), `Giá mới nhất trong DB: ${fmtDate(d.LastPriceDate)} · hôm nay (VN): ${o.freshness.today_vn}`),
      card("Số mã có giá", fmtNum(d.StocksWithPrices, 0), `${fmtNum(d.TradingDays, 0)} phiên lịch (${fmtDate(d.FirstTradingDay)} → ${fmtDate(d.LastTradingDay)})`),
      card("Số dòng giá", fmtNum(d.PriceRows, 0), "dbo.DailyPrice"),
      card("Dự báo đủ điều kiện", fmtNum(o.eligible_predictions, 0), `trên ${fmtNum(d.Predictions, 0)} dự báo · ${fmtNum(d.ModelRuns, 0)} run · as_of ${o.as_of}`),
      eod ? card("EOD gần nhất", eod.last_run ? el("span", {}, badge(eod.last_run.Status), " ", fmtDate(eod.last_run.SessionDate)) : "Chưa chạy",
        `Phiên thành công gần nhất: ${fmtDate(eod.last_successful_trade_date)} · nến provider mới nhất: ${fmtDate(eod.last_provider_candle_date)} · chờ đối soát: ${eod.pending_reconciliation}`)
        : card("EOD", "Không áp dụng", state.meta.eod.reason),
    );
  } catch (e) { showError(cards, e); }
  try {
    const l = await api(`/api/prices/latest?${qs({ dataset_id: state.datasetId })}`);
    $("latestHint").textContent = `${l.price_unit} · ${l.price_basis} · EOD (không realtime)`;
    $("latestTable").replaceChildren(table([
      { key: "Ticker", label: "Mã" }, { label: "Ngày", render: (r) => fmtDate(r.TradeDate) },
      { label: "Close", num: true, render: (r) => fmtNum(r.ClosePrice, 4) },
      { label: "Phiên trước", render: (r) => fmtDate(r.PreviousDate) },
      { label: "Thay đổi Close nguồn", num: true, render: (r) => (r.SourceCloseChangePct === null ? "—" : `${fmtNum(r.SourceCloseChangePct, 2)}%`) },
      { label: "Volume", num: true, render: (r) => fmtNum(r.Volume, 0) },
    ], l.items, { empty: "Dataset chưa có giá nào." }));
  } catch (e) { showError($("latestTable"), e); }
}

// ---------------------------------------------------------------------------------------------------
async function initMarket() {
  try {
    const s = await api(`/api/stocks?${qs({ dataset_id: state.datasetId, limit: 500 })}`);
    $("tickerList").replaceChildren(...s.items.map((x) => el("option", { value: x.Ticker }, `${x.PriceRows} phiên`)));
    const first = s.items.find((x) => x.PriceRows > 0);
    const d = currentDataset();
    if (first && !$("mTicker").value) $("mTicker").value = first.Ticker;
    if (d?.LastPriceDate && !$("mTo").value) $("mTo").value = String(d.LastPriceDate).slice(0, 10);
    if (first) loadMarket(); else setState($("chart"), "", "Dataset chưa có giá để vẽ.");
  } catch (e) { showError($("chart"), e); }
}

async function loadMarket() {
  const ticker = $("mTicker").value.trim().toUpperCase();
  const p = { dataset_id: state.datasetId, ticker, date_from: $("mFrom").value, date_to: $("mTo").value };
  setState($("chart"), "loading", "Đang tải chuỗi giá…");
  try {
    const s = await api(`/api/prices/series?${qs(p)}`);
    $("chartTitle").textContent = `${s.ticker}: giá đóng cửa và khối lượng`;
    $("chartHint").textContent = s.note;
    if (!s.points.length) setState($("chart"), "", "Không có phiên nào trong khoảng ngày đã chọn.");
    else priceVolumeChart($("chart"), s.points, { ticker: s.ticker, unit: s.price_unit, basis: s.price_basis, tooltip: $("tooltip") });
  } catch (e) { showError($("chart"), e); }
  loadPriceTable();
}

async function loadPriceTable() {
  const pr = state.price;
  const p = { dataset_id: state.datasetId, ticker: $("mTicker").value.trim().toUpperCase(), date_from: $("mFrom").value,
    date_to: $("mTo").value, sort: pr.sort, order: pr.order, limit: pr.limit, offset: pr.offset };
  setState($("priceTable"), "loading", "Đang tải bảng giá…");
  try {
    const r = await api(`/api/prices?${qs(p)}`);
    $("priceTable").replaceChildren(table([
      { key: "Ticker", label: "Mã", sort: "ticker" }, { label: "Ngày", sort: "date", render: (x) => fmtDate(x.TradeDate) },
      { label: "Open", num: true, render: (x) => fmtNum(x.OpenPrice, 4) }, { label: "High", num: true, render: (x) => fmtNum(x.HighPrice, 4) },
      { label: "Low", num: true, render: (x) => fmtNum(x.LowPrice, 4) }, { label: "Close", num: true, sort: "close", render: (x) => fmtNum(x.ClosePrice, 4) },
      { label: "Volume", num: true, sort: "volume", render: (x) => fmtNum(x.Volume, 0) }, { label: "Nạp lúc", render: (x) => fmtTime(x.LoadedAt) },
    ], r.items, { sortKey: pr.sort, sortOrder: pr.order, onSort: (k) => {
      if (pr.sort === k) pr.order = pr.order === "asc" ? "desc" : "asc"; else { pr.sort = k; pr.order = "desc"; }
      pr.offset = 0; loadPriceTable();
    } }));
    pager($("pricePager"), r.total, r.offset, r.limit, (o) => { pr.offset = o; loadPriceTable(); });
  } catch (e) { showError($("priceTable"), e); $("pricePager").replaceChildren(); }
}

// ---------------------------------------------------------------------------------------------------
async function loadRuns() {
  setState($("runTable"), "loading", "Đang tải danh sách run…");
  setState($("predTable"), "", "Chọn một run để xem dự báo.");
  try {
    const [r, perf] = await Promise.all([
      api(`/api/models?${qs({ dataset_id: state.datasetId })}`),
      api(`/api/performance?${qs({ dataset_id: state.datasetId, as_of: $("fAsOf").value })}`),
    ]);
    state.runs = r.items;
    const byRun = Object.fromEntries(perf.items.map((x) => [x.RunId, x]));
    $("runTable").replaceChildren(table([
      { key: "RunId", label: "Run", num: true }, { key: "RunCode", label: "Mã run" }, { key: "ModelCode", label: "Mô hình" },
      { key: "TargetCode", label: "Mục tiêu" }, { key: "HorizonSessions", label: "Horizon", num: true },
      { label: "Threshold", num: true, render: (x) => fmtNum(x.Threshold, 4) },
      { label: "Dự báo", num: true, render: (x) => fmtNum(byRun[x.RunId]?.TotalPredictions, 0) },
      { label: "Đủ điều kiện", num: true, render: (x) => fmtNum(byRun[x.RunId]?.EvaluatedRows, 0) },
      { label: "Chưa trưởng thành", num: true, render: (x) => fmtNum(byRun[x.RunId]?.PendingNotMatured, 0) },
      { label: "Thiếu endpoint", num: true, render: (x) => fmtNum(byRun[x.RunId]?.MissingEndpoint, 0) },
      { label: "Accuracy", num: true, render: (x) => pct(byRun[x.RunId]?.Accuracy) },
      { label: "Brier", num: true, render: (x) => fmtNum(byRun[x.RunId]?.BrierScore, 4) },
      { label: "Log loss", num: true, render: (x) => fmtNum(byRun[x.RunId]?.NaturalLogLoss, 4) },
      { key: "EvaluationClass", label: "Loại đánh giá" },
    ], r.items, { empty: "Dataset này chưa có ModelRun/dự báo. " + state.meta.inference.message,
      onRow: (x) => { state.selectedRun = x.RunId; state.pred.offset = 0; loadRuns.mark(); loadPredictions(); },
      selected: (x) => x.RunId === state.selectedRun }));
    $("runTable").append(el("p", { class: "hint" }, `Chỉ số tại as_of ${perf.as_of}. ${perf.rules}`));
    if (!state.selectedRun && r.items.length) { state.selectedRun = r.items[0].RunId; loadRuns.mark(); loadPredictions(); }
  } catch (e) { showError($("runTable"), e); }
}
loadRuns.mark = () => document.querySelectorAll("#runTable tbody tr").forEach((tr, i) => tr.classList.toggle("selected", state.runs[i]?.RunId === state.selectedRun));

async function loadPredictions() {
  const run = state.runs.find((x) => x.RunId === state.selectedRun);
  if (!run) return;
  $("predTitle").textContent = `Dự báo của run ${run.RunId} (${run.RunCode})`;
  const p = { run_id: run.RunId, as_of: $("fAsOf").value, ticker: $("fTicker").value.trim(), status: $("fStatus").value,
    limit: state.pred.limit, offset: state.pred.offset };
  setState($("predTable"), "loading", "Đang tải dự báo…");
  try {
    const r = await api(`/api/predictions?${qs(p)}`);
    $("predTable").replaceChildren(table([
      { key: "Ticker", label: "Mã" }, { label: "OriginDate", render: (x) => fmtDate(x.OriginDate) },
      { label: "TargetDate", render: (x) => fmtDate(x.TargetDate) },
      { label: "ProbabilityPositive", num: true, render: (x) => fmtNum(x.ProbabilityPositive, 4) },
      { label: "Dự đoán (p ≥ ngưỡng)", num: true, render: (x) => (x.PredictedLabel ? "1 (tăng)" : "0") },
      { label: "Nhãn thực", num: true, render: (x) => (x.ActualLabel === null ? "—" : x.ActualLabel ? "1" : "0") },
      { label: "Thay đổi Close nguồn", num: true, render: (x) => (x.ActualSourceCloseReturnPct === null ? "—" : `${fmtNum(x.ActualSourceCloseReturnPct, 2)}%`) },
      { label: "Trạng thái tại as_of", render: (x) => badge(x.EvaluationStatus) },
    ], r.items));
    $("predTable").append(el("p", { class: "hint" }, `${r.note}. as_of = ${r.as_of}.`));
    pager($("predPager"), r.total, r.offset, r.limit, (o) => { state.pred.offset = o; loadPredictions(); });
  } catch (e) { showError($("predTable"), e); $("predPager").replaceChildren(); }
}

// ---------------------------------------------------------------------------------------------------
async function initCompare() {
  const box = $("compareRuns");
  setState(box, "loading", "Đang tải run…");
  try {
    const r = await api(`/api/models?${qs({ dataset_id: state.datasetId })}`);
    if (!r.items.length) { setState(box, "", "Không có run nào để so sánh. " + state.meta.inference.message); return; }
    box.replaceChildren(...r.items.map((x) => el("label", {}, el("input", { type: "checkbox", value: x.RunId, checked: true }),
      `#${x.RunId} ${x.ModelCode} · ${x.TargetCode}`)));
    const firsts = r.items.map((x) => x.FirstOrigin).filter(Boolean).sort();
    const lasts = r.items.map((x) => x.LastOrigin).filter(Boolean).sort();
    if (firsts.length) $("cFrom").value = String(firsts[0]).slice(0, 10);
    if (lasts.length) $("cTo").value = String(lasts[lasts.length - 1]).slice(0, 10);
  } catch (e) { showError(box, e); }
}

async function runCompare() {
  const ids = [...document.querySelectorAll("#compareRuns input:checked")].map((x) => x.value);
  const out = $("compareResult");
  if (ids.length < 2 || ids.length > 8) { setState(out, "error", "Chọn từ 2 đến 8 run."); return; }
  setState(out, "loading", "Đang gọi dbo.usp_CompareModels…");
  try {
    const r = await api(`/api/models/compare?${qs({ run_ids: ids.join(","), date_from: $("cFrom").value, date_to: $("cTo").value, as_of: $("cAsOf").value })}`);
    out.replaceChildren(table([
      { key: "RunId", label: "Run", num: true }, { key: "ModelCode", label: "Mô hình" },
      { label: "Số quan sát giao", num: true, render: (x) => fmtNum(x.CommonObservations, 0) },
      { label: "Accuracy", num: true, render: (x) => pct(x.Accuracy) }, { label: "Brier", num: true, render: (x) => fmtNum(x.BrierScore, 4) },
      { label: "Log loss", num: true, render: (x) => fmtNum(x.NaturalLogLoss, 4) },
      { label: "Cửa sổ gốc", render: (x) => `${fmtDate(x.FirstOrigin)} → ${fmtDate(x.LastOrigin)}` },
      { label: "as_of", render: (x) => fmtDate(x.EvaluationAsOf) },
    ], r.rows), el("p", { class: "hint" }, r.note));
  } catch (e) { showError(out, e); }
}

// ---------------------------------------------------------------------------------------------------
async function loadOps() {
  const eodOn = state.meta.eod.enabled;
  $("oDry").disabled = $("oSync").disabled = !eodOn;
  $("oToken").disabled = !eodOn;
  if (!eodOn) setState($("opsJob"), "", `Đồng bộ bị tắt: ${state.meta.eod.reason}`);
  loadCalendarCheck();
  if (state.meta.mode === "DEMO_OFFLINE") {
    $("opsCards").replaceChildren(card("Nhật ký EOD", "Không áp dụng", state.meta.eod.reason));
    setState($("opsRuns"), "", "DEMO_OFFLINE không ghi nhật ký EOD (không đồng bộ dữ liệu thật vào CSDL mô phỏng).");
    setState($("reconTable"), "", "Không áp dụng ở DEMO_OFFLINE.");
    return;
  }
  setState($("opsCards"), "loading", "Đang tải trạng thái…");
  try {
    const s = await api(`/api/ops/last-status?${qs({ dataset_id: state.datasetId })}`);
    $("opsCards").replaceChildren(
      card("Ngày yêu cầu gần nhất", fmtDate(s.last_requested_date), s.last_run ? `run #${s.last_run.EodRunId} · ${s.last_run.Status}${s.last_run.IsDryRun ? " (dry run)" : ""}` : "chưa có run"),
      card("Phiên đồng bộ thành công gần nhất", fmtDate(s.last_successful_trade_date), "Status = SUCCESS"),
      card("Dataset ObservedThrough", fmtDate(s.dataset_observed_through), `Giá mới nhất trong DB: ${fmtDate(s.last_price_date)}`),
      card("Nến provider mới nhất đã thấy", fmtDate(s.last_provider_candle_date), `Hôm nay (VN): ${s.today_vn}`),
      card("Chờ đối soát", fmtNum(s.pending_reconciliation, 0), "giá đã chốt bị nguồn thay đổi"),
    );
  } catch (e) { showError($("opsCards"), e); }
  loadOpsRuns();
  loadRecon();
}

async function loadOpsRuns() {
  setState($("opsRuns"), "loading", "Đang tải nhật ký…");
  try {
    const r = await api(`/api/ops/runs?${qs({ dataset_id: state.datasetId, limit: state.ops.limit, offset: state.ops.offset })}`);
    $("opsRuns").replaceChildren(table([
      { key: "EodRunId", label: "#", num: true }, { label: "Phiên", render: (x) => fmtDate(x.SessionDate) },
      { label: "Trạng thái", render: (x) => el("span", {}, badge(x.Status), x.IsDryRun ? " dry" : "") },
      { key: "ErrorCode", label: "Mã lỗi" }, { key: "TriggerKind", label: "Nguồn kích hoạt" },
      { label: "Yêu cầu", num: true, render: (x) => fmtNum(x.RequestedCount, 0) }, { label: "Nhận", num: true, render: (x) => fmtNum(x.ReceivedCount, 0) },
      { label: "Thêm", num: true, render: (x) => fmtNum(x.InsertedCount, 0) }, { label: "Không đổi", num: true, render: (x) => fmtNum(x.UnchangedCount, 0) },
      { label: "Từ chối", num: true, render: (x) => fmtNum(x.RejectedCount, 0) },
      { label: "Bắt đầu", render: (x) => fmtTime(x.StartedAtUtc) }, { label: "Thời gian", num: true, render: (x) => `${fmtNum(x.DurationMs / 1000, 1)} s` },
    ], r.items, { empty: "Chưa có lần chạy EOD nào.", onRow: (x) => loadRunDetail(x.EodRunId) }));
    pager($("opsPager"), r.total, r.offset, r.limit, (o) => { state.ops.offset = o; loadOpsRuns(); });
  } catch (e) { showError($("opsRuns"), e); }
}

async function loadRunDetail(id) {
  const box = $("opsRunDetail");
  setState(box, "loading", `Đang tải run #${id}…`);
  try {
    const r = await api(`/api/ops/runs/${id}`);
    box.replaceChildren(
      el("h3", {}, `Run #${r.EodRunId} — `, badge(r.Status), ` ${r.ErrorCode || ""}`),
      el("p", {}, r.Message || ""),
      el("p", { class: "hint" }, `ObservedThrough ${fmtDate(r.ObservedThroughBefore)} → ${fmtDate(r.ObservedThroughAfter)} · provider: ${r.ProviderMeta?.provider?.package || "—"} ${r.ProviderMeta?.provider?.package_version || ""} · lịch: ${r.ProviderMeta?.calendar?.decision || "—"}`),
      table([{ key: "Ticker", label: "Mã" }, { label: "Kết quả", render: (x) => badge(x.Outcome) }, { key: "Detail", label: "Chi tiết" }], r.items,
        { empty: "Không có chi tiết theo mã (run dừng trước khi tải dữ liệu)." }),
      r.evaluation.length ? table([{ key: "RunCode", label: "Đánh giá lại sau EOD: run" }, { label: "as_of", render: (x) => fmtDate(x.AsOfDate) },
        { label: "Đủ điều kiện", num: true, render: (x) => fmtNum(x.EligibleRows, 0) }, { label: "Accuracy", num: true, render: (x) => pct(x.Accuracy) },
        { label: "Brier", num: true, render: (x) => fmtNum(x.BrierScore, 4) }], r.evaluation) : el("p", { class: "hint" }, "Không có snapshot đánh giá (không có ModelRun trong dataset hoặc run không SUCCESS)."),
    );
  } catch (e) { showError(box, e); }
}

async function loadCalendarCheck() {
  setState($("calendarCheck"), "loading", "Đang kiểm tra lịch phiên…");
  try {
    const r = await api(`/api/ops/calendar-check?${qs({ dataset_id: state.datasetId, limit: 30 })}`);
    $("calendarCheck").replaceChildren(table([
      { label: "Phiên", render: (x) => fmtDate(x.TradeDate) }, { label: "Dòng giá", num: true, render: (x) => fmtNum(x.PriceRows, 0) },
      { label: "Kỳ vọng", num: true, render: (x) => fmtNum(x.ExpectedRows, 0) },
      { label: "Thiếu", num: true, render: (x) => (x.MissingRows > 0 ? badge(`${x.MissingRows} thiếu`, x.AfterObservedThrough ? "info" : "serious") : "0") },
      { label: "Sau ObservedThrough", render: (x) => (x.AfterObservedThrough ? "có (lịch tương lai)" : "không") },
    ], r.items, { empty: "Dataset chưa có lịch phiên." }), el("p", { class: "hint" }, `Universe kỳ vọng: ${r.universe_source}. Thiếu dòng chỉ được báo cáo, không tự điền.`));
  } catch (e) { showError($("calendarCheck"), e); }
}

async function loadRecon() {
  try {
    const r = await api(`/api/ops/reconciliation?${qs({ dataset_id: state.datasetId, limit: 50 })}`);
    $("reconTable").replaceChildren(table([
      { key: "ReconId", label: "#", num: true }, { key: "Ticker", label: "Mã" }, { label: "Ngày", render: (x) => fmtDate(x.TradeDate) },
      { label: "Close đã lưu", num: true, render: (x) => fmtNum(x.StoredClose, 4) }, { label: "Close nguồn mới", num: true, render: (x) => fmtNum(x.ProviderClose, 4) },
      { key: "DetectedBy", label: "Phát hiện bởi" }, { label: "Trạng thái", render: (x) => badge(x.Status) },
    ], r.items, { empty: "Không có giá đã chốt nào bị nguồn thay đổi." }),
    el("p", { class: "hint" }, "Duyệt bằng CLI: python -m marketlab_app.cli eod reconcile approve|reject --id N --reviewer … --note … (không tự cập nhật)."));
  } catch (e) { showError($("reconTable"), e); }
}

async function startEod(dry) {
  const date = $("oDate").value;
  const token = $("oToken").value;
  const out = $("opsJob");
  if (!date) { setState(out, "error", "Chọn ngày phiên."); return; }
  if (!token) { setState(out, "error", "Nhập mã vận hành (MARKETLAB_OPS_TOKEN). Mã không được lưu trên trình duyệt."); return; }
  const question = dry ? `Chạy DRY RUN cho phiên ${date}? (kiểm tra trong SQL Server rồi ROLLBACK, không ghi dữ liệu)`
    : `GHI THẬT dữ liệu phiên ${date} vào ${state.meta.database}? Thao tác có transaction all-or-nothing và được ghi nhật ký.`;
  if (!window.confirm(question)) return;
  $("oDry").disabled = $("oSync").disabled = true;
  setState(out, "loading", "Đang gửi yêu cầu…");
  try {
    const j = await api("/api/ops/eod", { method: "POST", headers: { "Content-Type": "application/json", "X-MarketLab-Ops-Token": token },
      body: JSON.stringify({ session_date: date, dry_run: dry, confirm: dry ? "DRY_RUN" : "SYNC" }) });
    let job = j;
    const t0 = Date.now();
    while (job.state === "RUNNING") {
      setState(out, "loading", `Job ${j.job_id.slice(0, 8)} đang chạy… ${Math.round((Date.now() - t0) / 1000)} s`);
      await new Promise((r) => setTimeout(r, 1500));
      job = await api(j.poll);
    }
    if (job.state === "ERROR") throw new ApiError(500, job.error.code, job.error.message);
    const r = job.result;
    out.replaceChildren(el("p", {}, badge(r.status), ` run #${r.eod_run_id} · phiên ${r.session_date} · ${r.error_code || ""} · thêm ${r.inserted}, không đổi ${r.unchanged}`
      + (r.would_insert !== null ? `, sẽ thêm ${r.would_insert}` : "") + ` / ${r.requested}`), el("p", {}, r.message),
      el("details", {}, el("summary", {}, "Kết quả JSON"), el("pre", {}, JSON.stringify(r, null, 1))));
    state.ops.offset = 0;
    loadOps();
  } catch (e) { showError(out, e); }
  finally { $("oDry").disabled = $("oSync").disabled = !state.meta.eod.enabled; }
}

function wireForms() {
  $("marketForm").addEventListener("submit", (ev) => { ev.preventDefault(); state.price.offset = 0; loadMarket(); });
  $("fApply").addEventListener("click", () => { state.pred.offset = 0; loadPredictions(); });
  $("fAsOf").addEventListener("change", () => { loadRuns(); });
  $("compareForm").addEventListener("submit", (ev) => { ev.preventDefault(); runCompare(); });
  $("oDry").addEventListener("click", () => startEod(true));
  $("oSync").addEventListener("click", () => startEod(false));
  $("opsRefresh").addEventListener("click", () => loadOps());
  let t;
  window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(() => { if (activeTab() === "market" && $("mTicker").value) loadMarket(); }, 250); });
}

boot();
