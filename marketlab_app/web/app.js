// MarketLab VN30 dashboard. Every number shown comes from the local API (SQL Server); no mock data.
import { priceVolumeChart, fmtNum } from "./charts.js";

const $ = (id) => document.getElementById(id);
const TABS = ["overview", "market", "forecast", "compare", "ops"];
const TICKER_RE = /^[A-Za-z0-9]{1,20}$/;
const state = { meta: null, datasets: [], datasetId: null, runs: [], selectedRun: null,
  price: { offset: 0, limit: 50, sort: "date", order: "desc" }, pred: { offset: 0, limit: 50 }, ops: { offset: 0, limit: 15 },
  loaded: {}, busy: false };

class ApiError extends Error {
  constructor(status, code, message, details) { super(message); this.status = status; this.code = code; this.details = details; }
}

async function api(path, init) {
  let res;
  try {
    res = await fetch(path, { headers: { Accept: "application/json", ...(init?.headers || {}) }, ...init });
  } catch {
    throw new ApiError(0, "NETWORK", "Không kết nối được API cục bộ (server đã dừng?). Kiểm tra scripts\\Start-MarketLab.ps1.");
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
    if (c === null || c === undefined || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}

function setState(container, kind, message) {
  container.replaceChildren(el("div", { class: `state ${kind}`, role: kind === "loading" ? "status" : null }, message));
}
const HINTS = { DB_UNAVAILABLE: "SQL Server không truy cập được: kiểm tra dịch vụ MSSQLSERVER rồi bấm Thử lại.",
  NETWORK: "Server cục bộ không phản hồi.", MODE_DATASET_MISMATCH: "Sửa MARKETLAB_MODE / MARKETLAB_SQL_DATABASE trong .env rồi khởi động lại.",
  OPS_UNAVAILABLE: "Database ops chưa sẵn sàng (python -m marketlab_app.deploy ops-db).",
  INVALID_OPS_TOKEN: "Token sai hoặc thiếu: mở .env trên máy chủ, sao chép MARKETLAB_OPS_TOKEN.",
  TOO_MANY_AUTH_FAILURES: "Đã nhập sai token quá 5 lần: chờ 10 phút." };
function showError(container, err, retry) {
  const msg = err instanceof ApiError ? `${err.code}: ${err.message}` : String(err);
  container.replaceChildren(el("div", { class: "state error", role: "alert" },
    el("strong", {}, "Lỗi · "), msg,
    err?.code && HINTS[err.code] ? el("div", { class: "hint" }, HINTS[err.code]) : null,
    err?.details ? el("div", { class: "hint" }, JSON.stringify(err.details)) : null,
    retry ? el("div", {}, el("button", { type: "button", class: "retry", onclick: retry }, "Thử lại")) : null));
}
const dash = (v) => (v === null || v === undefined || v === "" ? "—" : String(v));
const fmtDate = (v) => (v ? String(v).slice(0, 10) : "—");
const fmtTime = (v) => (v ? String(v).replace("T", " ").slice(0, 19) + " UTC" : "—");
const pct = (v) => (v === null || v === undefined || !isFinite(Number(v)) ? "—" : `${fmtNum(Number(v) * 100, 2)}%`);

const STATUS_CLASS = { SUCCESS: "good", DRY_RUN_OK: "info", NO_SESSION: "info", SKIPPED: "warning", PARTIAL: "serious",
  FAILED: "critical", RUNNING: "info", ELIGIBLE: "good", PENDING: "warning", MISSING_ENDPOINT: "serious",
  PENDING_REVIEW: "warning", APPROVED_UPDATE: "good", REJECTED: "critical", INSERTED: "good", UNCHANGED: "info",
  WOULD_INSERT: "info", MISSING: "serious", CONFLICT: "critical", NOT_WRITTEN: "warning",
  CURRENT: "good", BEHIND: "warning", SYNTHETIC_FIXED: "info", UNKNOWN: "serious", ALREADY_SUCCEEDED: "good" };
const STATUS_TEXT = { CURRENT: "Đã cập nhật", BEHIND: "Có thể chậm", SYNTHETIC_FIXED: "Mô phỏng cố định", UNKNOWN: "Chưa rõ",
  ELIGIBLE: "Đã chấm", PENDING: "Chưa trưởng thành", MISSING_ENDPOINT: "Thiếu giá endpoint" };
const badge = (s, cls, text) => el("span", { class: `badge ${cls || STATUS_CLASS[s] || "info"}` }, text ?? STATUS_TEXT[s] ?? s ?? "—");

function table(columns, rows, opts = {}) {
  if (!rows.length) return el("div", { class: "state" }, opts.empty || "Không có dữ liệu cho bộ lọc này.");
  const head = el("tr", {}, columns.map((c) => {
    const sorted = opts.sortKey && opts.sortKey === c.sort;
    const th = el("th", { class: [c.num ? "num" : "", c.sort ? "sortable" : ""].join(" "), scope: "col",
      "aria-sort": c.sort ? (sorted ? (opts.sortOrder === "asc" ? "ascending" : "descending") : "none") : null });
    if (c.sort && opts.onSort) {
      th.append(el("button", { type: "button", class: "th-sort", onclick: () => opts.onSort(c.sort) },
        c.label, el("span", { "aria-hidden": "true" }, sorted ? (opts.sortOrder === "asc" ? " ▲" : " ▼") : " ⇅")));
    } else th.append(c.label);
    return th;
  }));
  const body = rows.map((r) => {
    const tr = el("tr", {}, columns.map((c, i) => {
      const v = c.render ? c.render(r) : dash(r[c.key]);
      return i === 0 ? el("th", { scope: "row", class: c.num ? "num" : "" }, v) : el("td", { class: c.num ? "num" : "" }, v);
    }));
    if (opts.onRow) {
      tr.classList.add("clickable");
      tr.tabIndex = 0;
      tr.addEventListener("click", () => opts.onRow(r, tr));
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); opts.onRow(r, tr); } });
    }
    if (opts.selected && opts.selected(r)) { tr.classList.add("selected"); tr.setAttribute("aria-selected", "true"); }
    return tr;
  });
  return el("table", {}, opts.caption ? el("caption", { class: "sr-only" }, opts.caption) : null, el("thead", {}, head), el("tbody", {}, body));
}

function pager(container, total, offset, limit, go) {
  container.replaceChildren();
  if (!total) return;
  const from = offset + 1, to = Math.min(total, offset + limit);
  container.append(el("span", { "aria-live": "polite" }, `${fmtNum(from, 0)}–${fmtNum(to, 0)} / ${fmtNum(total, 0)}`),
    el("button", { type: "button", disabled: offset === 0, onclick: () => go(Math.max(0, offset - limit)) }, "‹ Trước"),
    el("button", { type: "button", disabled: to >= total, onclick: () => go(offset + limit) }, "Sau ›"));
}

const card = (k, v, s, extra) => el("div", { class: "card" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v), extra || null, s ? el("div", { class: "s" }, s) : null);
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== "")).toString();
const currentDataset = () => state.datasets.find((d) => d.DatasetId === state.datasetId);
const shortUnit = (u) => (u && u.length > 28 ? u.split(/[;(]/)[0].trim() : u);

// ---- URL state (refresh / deep link keeps tab, dataset and filters) ------------------------------------
function readHash() {
  return Object.fromEntries(new URLSearchParams(location.hash.slice(1)));
}
function writeHash() {
  const h = { tab: activeTab(), ds: state.datasetId, t: $("mTicker").value.trim().toUpperCase(), f: $("mFrom").value, to: $("mTo").value,
    run: state.selectedRun, asof: $("fAsOf").value !== state.meta?.today_vn ? $("fAsOf").value : "" };
  history.replaceState(null, "", `#${qs(h)}`);
}

// ---------------------------------------------------------------------------------------------------
async function boot() {
  wireTabs();
  const h = readHash();
  if (TABS.includes(h.tab)) selectTab(h.tab, false);   // show the deep-linked tab at once; data loads after boot
  try {
    state.meta = await api("/api/meta");
  } catch (e) {
    $("modeBadge").textContent = "API lỗi"; $("modeBadge").className = "scope error";
    showError($("overviewCards"), e, () => location.reload()); return;
  }
  const m = state.meta;
  $("modeBadge").textContent = m.label;
  $("modeBadge").className = `scope ${m.data_scope.toLowerCase().replace(/_/g, "-")}`;
  document.body.dataset.scope = m.data_scope;
  $("disclaimer").textContent = m.disclaimer;
  $("inferenceNotice").textContent = m.inference.message;
  const peers = (m.peers || []).filter((p) => !location.origin.startsWith(p.url));
  if (peers.length) {
    $("peers").hidden = false;
    $("peers").replaceChildren(el("span", {}, "Chuyển chế độ:"), ...peers.map((p) => el("a", { href: `${p.url}/` }, p.label)));
  }
  $("footer").textContent = `${m.data_scope} · database ${m.database} trên SQL Server ${m.server_label} · ngày VN ${m.today_vn} · `
    + "mọi số liệu đọc trực tiếp từ SQL Server; không có dữ liệu giả lập ở chế độ REAL_PRIVATE / RESEARCH_READ_ONLY.";
  $("fAsOf").value = h.asof || m.today_vn;
  $("cAsOf").value = m.today_vn;
  $("oDate").value = m.today_vn;
  if (h.t) $("mTicker").value = h.t;
  if (h.f) $("mFrom").value = h.f;
  if (h.to) $("mTo").value = h.to;
  if (h.run) state.selectedRun = Number(h.run);
  try {
    state.datasets = (await api("/api/datasets")).items;
  } catch (e) {
    showError($("overviewCards"), e, () => location.reload()); $("datasetSelect").replaceChildren(el("option", {}, "—")); return;
  }
  const sel = $("datasetSelect");
  sel.replaceChildren(...state.datasets.map((d) => el("option", { value: d.DatasetId }, `${d.DatasetCode} (${d.DataKind})`)));
  if (!state.datasets.length) { setState($("overviewCards"), "", "Database không có dataset nào."); return; }
  state.datasetId = state.datasets.some((d) => d.DatasetId === Number(h.ds)) ? Number(h.ds) : state.datasets[0].DatasetId;
  sel.value = String(state.datasetId);
  sel.addEventListener("change", () => {
    state.datasetId = Number(sel.value); state.loaded = {}; state.selectedRun = null;
    $("mTicker").value = ""; $("mFrom").value = ""; $("mTo").value = "";
    writeHash(); loadTab(activeTab());
  });
  wireForms();
  loadTab(activeTab());   // never override a tab the user picked while datasets were loading
}

function wireTabs() {
  const btns = [...document.querySelectorAll('.tabs [role="tab"]')];
  btns.forEach((b, i) => {
    b.addEventListener("click", () => selectTab(b.dataset.tab, true));
    b.addEventListener("keydown", (e) => {
      const k = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: btns.length - 1 }[e.key];
      if (k === undefined) return;
      e.preventDefault();
      const t = btns[(k + btns.length) % btns.length];
      t.focus(); selectTab(t.dataset.tab, true);
    });
  });
}
function selectTab(tab, write) {
  document.querySelectorAll('.tabs [role="tab"]').forEach((x) => {
    const on = x.dataset.tab === tab;
    x.setAttribute("aria-selected", String(on)); x.tabIndex = on ? 0 : -1;
    if (on) x.scrollIntoView({ block: "nearest", inline: "nearest" });
  });
  document.querySelectorAll(".tab-panel").forEach((p) => { p.hidden = p.id !== `tab-${tab}`; });
  if (write && state.meta) writeHash();
  loadTab(tab);
}
const activeTab = () => document.querySelector('.tabs [aria-selected="true"]').dataset.tab;

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
    const d = o.dataset, f = o.freshness, eod = o.eod;
    cards.replaceChildren(
      card("Giá mới nhất trong DB", fmtDate(d.LastPriceDate), f.message, badge(f.status)),
      card("Số mã có giá", fmtNum(d.StocksWithPrices, 0), `${fmtNum(d.TradingDays, 0)} phiên lịch · ${fmtDate(d.FirstTradingDay)} → ${fmtDate(d.LastTradingDay)}`),
      card("Số dòng giá (dbo.DailyPrice)", fmtNum(d.PriceRows, 0), `ObservedThrough ${fmtDate(d.ObservedThrough)}`),
      o.eligible_predictions === null
        ? card("Dự báo đủ điều kiện", "—", "Dataset chưa có ModelRun: chưa cấu hình mô hình tạo dự báo, không có gì để chấm.")
        : card("Dự báo đủ điều kiện", fmtNum(o.eligible_predictions, 0), `trên ${fmtNum(d.Predictions, 0)} dự báo · ${fmtNum(d.ModelRuns, 0)} run · as_of ${o.as_of}`),
      eod ? card("Phiên đồng bộ thành công gần nhất", fmtDate(eod.last_successful_trade_date),
        eod.last_run ? `Lần chạy gần nhất: #${eod.last_run.EodRunId} · ${eod.last_run.Status}${eod.last_run.IsDryRun ? " (dry run)" : ""} · phiên ${fmtDate(eod.last_run.SessionDate)}` : "Chưa có lần chạy",
        eod.pending_reconciliation ? badge("PENDING_REVIEW", "warning", `${eod.pending_reconciliation} giá chờ đối soát`) : null)
        : card("Đồng bộ EOD", "Không áp dụng", state.meta.eod.reason),
    );
    $("provenance").replaceChildren(el("dl", { class: "facts" },
      ...[["Phạm vi dữ liệu", state.meta.data_scope], ["Dataset", `${d.DatasetCode} (${d.DataKind})`], ["Thị trường", `${d.MarketCode} · ${d.CurrencyCode}`],
        ["Price basis", `${d.PriceBasis}: giá đóng cửa nguồn như được lưu; không phải giá điều chỉnh tổng lợi suất`],
        ["Đơn vị giá", d.PriceUnit], ["Nguồn / lineage", d.ProvenanceNote], ["Manifest", d.ManifestPath],
        ["Tính thời gian", `${f.kind}. Phiên ngày làm việc dự kiến gần nhất: ${f.expected_latest_session} (không tính nghỉ lễ).`],
      ].flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v ?? "—")])));
  } catch (e) { showError(cards, e, () => { state.loaded.overview = false; loadTab("overview"); }); }
  try {
    const l = await api(`/api/prices/latest?${qs({ dataset_id: state.datasetId })}`);
    $("latestHint").textContent = `${l.price_basis} · EOD, không realtime · ObservedThrough ${fmtDate(l.observed_through)}`;
    $("latestTable").replaceChildren(table([
      { key: "Ticker", label: "Mã" }, { label: "Phiên", render: (r) => fmtDate(r.TradeDate) },
      { label: "Close", num: true, render: (r) => fmtNum(r.ClosePrice, 4) },
      { label: "Phiên trước", render: (r) => fmtDate(r.PreviousDate) },
      { label: "Thay đổi Close nguồn", num: true, render: (r) => (r.SourceCloseChangePct === null ? "—" : `${fmtNum(r.SourceCloseChangePct, 2)}%`) },
      { label: "Volume", num: true, render: (r) => fmtNum(r.Volume, 0) },
    ], l.items, { empty: "Dataset chưa có giá nào.", caption: "Giá gần nhất của từng mã (vw_LatestStockPrice)" }));
  } catch (e) { showError($("latestTable"), e, () => { state.loaded.overview = false; loadTab("overview"); }); }
}

// ---------------------------------------------------------------------------------------------------
async function initMarket() {
  setState($("chart"), "loading", "Đang tải danh sách mã…");
  try {
    const s = await api(`/api/stocks?${qs({ dataset_id: state.datasetId, limit: 500 })}`);
    $("tickerList").replaceChildren(...s.items.map((x) => el("option", { value: x.Ticker }, `${x.PriceRows} phiên có giá`)));
    state.tickers = new Set(s.items.map((x) => x.Ticker));
    const first = s.items.find((x) => x.PriceRows > 0);
    if (first && !$("mTicker").value) $("mTicker").value = first.Ticker;
    if (first) loadMarket(); else setState($("chart"), "", "Dataset chưa có giá để vẽ.");
  } catch (e) { showError($("chart"), e, () => { state.loaded.market = false; loadTab("market"); }); }
}

function validateMarket() {
  const t = $("mTicker").value.trim().toUpperCase(), f = $("mFrom").value, to = $("mTo").value;
  if (!TICKER_RE.test(t)) return "Mã chỉ gồm 1–20 chữ cái/chữ số.";
  if (state.tickers && !state.tickers.has(t)) return `${t} không thuộc dataset đang chọn.`;
  if (f && to && f > to) return "Từ ngày phải nhỏ hơn hoặc bằng Đến ngày.";
  return "";
}

async function loadMarket() {
  const err = validateMarket();
  $("marketMsg").textContent = err;
  if (err) return;
  const ticker = $("mTicker").value.trim().toUpperCase();
  $("mTicker").value = ticker;
  writeHash();
  const d = currentDataset();
  const p = { dataset_id: state.datasetId, ticker, date_from: $("mFrom").value, date_to: $("mTo").value };
  setState($("chart"), "loading", "Đang tải chuỗi giá…");
  try {
    const s = await api(`/api/prices/series?${qs(p)}`);
    const pts = s.points;
    const range = pts.length ? `${fmtDate(pts[0].TradeDate)} → ${fmtDate(pts[pts.length - 1].TradeDate)}` : "";
    $("chartTitle").textContent = `${s.ticker} · ${d.DatasetCode} · ${range}`;
    $("chartHint").textContent = `${s.note} ${s.sessions} phiên lịch` + (s.sessions_without_price.length ? `, ${s.sessions_without_price.length} phiên thiếu giá (vạch gạch).` : ", không phiên nào thiếu giá.");
    if (!pts.length) setState($("chart"), "", "Không có phiên nào trong khoảng ngày đã chọn.");
    else priceVolumeChart($("chart"), pts, { ticker: s.ticker, datasetCode: d.DatasetCode, unit: s.price_unit, unitShort: shortUnit(s.price_unit),
      basis: s.price_basis, tooltip: $("tooltip") });
  } catch (e) { showError($("chart"), e, loadMarket); }
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
      { key: "Ticker", label: "Mã", sort: "ticker" }, { label: "Phiên", sort: "date", render: (x) => fmtDate(x.TradeDate) },
      { label: "Open", num: true, render: (x) => fmtNum(x.OpenPrice, 4) }, { label: "High", num: true, render: (x) => fmtNum(x.HighPrice, 4) },
      { label: "Low", num: true, render: (x) => fmtNum(x.LowPrice, 4) }, { label: "Close", num: true, sort: "close", render: (x) => fmtNum(x.ClosePrice, 4) },
      { label: "Volume", num: true, sort: "volume", render: (x) => fmtNum(x.Volume, 0) }, { label: "Nạp lúc", render: (x) => fmtTime(x.LoadedAt) },
    ], r.items, { caption: `Bảng OHLCV ${p.ticker}`, sortKey: pr.sort, sortOrder: pr.order, onSort: (k) => {
      if (pr.sort === k) pr.order = pr.order === "asc" ? "desc" : "asc"; else { pr.sort = k; pr.order = "desc"; }
      pr.offset = 0; loadPriceTable();
    } }));
    pager($("pricePager"), r.total, r.offset, r.limit, (o) => { pr.offset = o; loadPriceTable(); });
  } catch (e) { showError($("priceTable"), e, loadPriceTable); $("pricePager").replaceChildren(); }
}

// ---------------------------------------------------------------------------------------------------
async function loadRuns() {
  setState($("runTable"), "loading", "Đang tải danh sách run…");
  setState($("predTable"), "", "Chọn một run trong bảng trên để xem dự báo.");
  const d = currentDataset();
  try {
    const [r, perf] = await Promise.all([
      api(`/api/models?${qs({ dataset_id: state.datasetId })}`),
      api(`/api/performance?${qs({ dataset_id: state.datasetId, as_of: $("fAsOf").value })}`),
    ]);
    state.runs = r.items;
    const byRun = Object.fromEntries(perf.items.map((x) => [x.RunId, x]));
    const totalElig = perf.items.reduce((a, x) => a + x.EvaluatedRows, 0);
    $("perfCaption").textContent = r.items.length
      ? `Dataset ${d.DatasetCode} · as_of ${perf.as_of} · ${fmtNum(totalElig, 0)} quan sát đủ điều kiện (tổng các run). ${perf.rules} Chỉ tiêu mỗi run dùng tập đủ điều kiện của riêng run đó; muốn so sánh công bằng hãy dùng tab So sánh mô hình.`
      : "";
    $("runTable").replaceChildren(table([
      { key: "RunId", label: "Run", num: true }, { key: "RunCode", label: "Mã run" }, { key: "ModelCode", label: "Mô hình" },
      { key: "TargetCode", label: "Mục tiêu" }, { key: "HorizonSessions", label: "Horizon", num: true },
      { label: "Threshold", num: true, render: (x) => fmtNum(x.Threshold, 4) },
      { label: "Dự báo", num: true, render: (x) => fmtNum(byRun[x.RunId]?.TotalPredictions, 0) },
      { label: "Đã chấm", num: true, render: (x) => fmtNum(byRun[x.RunId]?.EvaluatedRows, 0) },
      { label: "Chưa trưởng thành", num: true, render: (x) => fmtNum(byRun[x.RunId]?.PendingNotMatured, 0) },
      { label: "Thiếu endpoint", num: true, render: (x) => fmtNum(byRun[x.RunId]?.MissingEndpoint, 0) },
      { label: "Accuracy", num: true, render: (x) => pct(byRun[x.RunId]?.Accuracy) },
      { label: "Brier", num: true, render: (x) => fmtNum(byRun[x.RunId]?.BrierScore, 4) },
      { label: "Log loss", num: true, render: (x) => fmtNum(byRun[x.RunId]?.NaturalLogLoss, 4) },
      { key: "EvaluationClass", label: "Loại đánh giá" },
    ], r.items, { empty: "Dataset này chưa có ModelRun / dự báo. " + state.meta.inference.message, caption: "Danh sách run và chỉ tiêu",
      onRow: (x) => { state.selectedRun = x.RunId; state.pred.offset = 0; markRun(); writeHash(); loadPredictions(); },
      selected: (x) => x.RunId === state.selectedRun }));
    if (r.items.length) {
      if (!r.items.some((x) => x.RunId === state.selectedRun)) state.selectedRun = r.items[0].RunId;
      markRun(); loadPredictions();
    }
  } catch (e) { showError($("runTable"), e, loadRuns); }
}
function markRun() {
  document.querySelectorAll("#runTable tbody tr").forEach((tr, i) => {
    const on = state.runs[i]?.RunId === state.selectedRun;
    tr.classList.toggle("selected", on); tr.setAttribute("aria-selected", String(on));
  });
}

async function loadPredictions() {
  const run = state.runs.find((x) => x.RunId === state.selectedRun);
  if (!run) return;
  const t = $("fTicker").value.trim();
  $("predMsg").textContent = t && !TICKER_RE.test(t) ? "Mã chỉ gồm chữ cái/chữ số." : "";
  if ($("predMsg").textContent) return;
  $("predTitle").textContent = `Dự báo của run ${run.RunId} · ${run.RunCode} · horizon ${run.HorizonSessions} · ngưỡng ${fmtNum(run.Threshold, 4)}`;
  const p = { run_id: run.RunId, as_of: $("fAsOf").value, ticker: t, status: $("fStatus").value, limit: state.pred.limit, offset: state.pred.offset };
  setState($("predTable"), "loading", "Đang tải dự báo…");
  try {
    const r = await api(`/api/predictions?${qs(p)}`);
    $("predTable").replaceChildren(table([
      { key: "Ticker", label: "Mã" }, { label: "OriginDate", render: (x) => fmtDate(x.OriginDate) },
      { label: "TargetDate", render: (x) => fmtDate(x.TargetDate) },
      { label: "ProbabilityPositive", num: true, render: (x) => fmtNum(x.ProbabilityPositive, 4) },
      { label: "Dự đoán (p ≥ ngưỡng)", num: true, render: (x) => (x.PredictedLabel ? "1 (tăng)" : "0") },
      { label: "Nhãn thực", num: true, render: (x) => (x.ActualLabel === null ? "— (chưa chấm)" : x.ActualLabel ? "1" : "0") },
      { label: "Thay đổi Close nguồn", num: true, render: (x) => (x.ActualSourceCloseReturnPct === null ? "—" : `${fmtNum(x.ActualSourceCloseReturnPct, 2)}%`) },
      { label: "Trạng thái tại as_of", render: (x) => badge(x.EvaluationStatus) },
    ], r.items, { caption: "Dự báo của run đã chọn" }));
    $("predTable").append(el("p", { class: "hint" }, `${r.note}. as_of = ${r.as_of}. "—" nghĩa là chưa có nhãn (chưa trưởng thành hoặc thiếu giá), không phải 0.`));
    pager($("predPager"), r.total, r.offset, r.limit, (o) => { state.pred.offset = o; loadPredictions(); });
  } catch (e) { showError($("predTable"), e, loadPredictions); $("predPager").replaceChildren(); }
}

// ---------------------------------------------------------------------------------------------------
async function initCompare() {
  const box = $("compareRuns");
  setState(box, "loading", "Đang tải run…");
  setState($("compareResult"), "", "Chọn run, khoảng ngày gốc và as_of rồi bấm So sánh. Hệ thống gọi dbo.usp_CompareModels và chỉ chấm trên các quan sát mà mọi run đều có.");
  try {
    const r = await api(`/api/models?${qs({ dataset_id: state.datasetId })}`);
    state.compareRuns = r.items;
    if (!r.items.length) { setState(box, "", "Không có run nào để so sánh. " + state.meta.inference.message); $("compareForm").querySelector("button[type=submit]").disabled = true; return; }
    box.replaceChildren(...r.items.map((x) => el("label", {}, el("input", { type: "checkbox", value: x.RunId, checked: true }),
      ` #${x.RunId} ${x.ModelCode} · ${x.TargetCode}`)));
    const firsts = r.items.map((x) => x.FirstOrigin).filter(Boolean).sort();
    const lasts = r.items.map((x) => x.LastOrigin).filter(Boolean).sort();
    if (firsts.length) $("cFrom").value = String(firsts[0]).slice(0, 10);
    if (lasts.length) $("cTo").value = String(lasts[lasts.length - 1]).slice(0, 10);
  } catch (e) { showError(box, e, () => { state.loaded.compare = false; loadTab("compare"); }); }
}

async function runCompare() {
  const ids = [...document.querySelectorAll("#compareRuns input:checked")].map((x) => Number(x.value));
  const out = $("compareResult");
  const f = $("cFrom").value, to = $("cTo").value, a = $("cAsOf").value;
  const msg = ids.length < 2 || ids.length > 8 ? "Chọn từ 2 đến 8 run." : !f || !to || !a ? "Nhập đủ khoảng ngày gốc và as_of." : f > to ? "Ngày gốc từ phải ≤ đến." : "";
  $("compareMsg").textContent = msg;
  if (msg) return;
  setState(out, "loading", "Đang gọi dbo.usp_CompareModels…");
  try {
    const r = await api(`/api/models/compare?${qs({ run_ids: ids.join(","), date_from: f, date_to: to, as_of: a })}`);
    const runs = (state.compareRuns || []).filter((x) => ids.includes(x.RunId));
    const targets = [...new Set(runs.map((x) => x.TargetCode))].join(", ");
    out.replaceChildren(
      el("p", { class: "caption" }, `Dataset ${currentDataset().DatasetCode} · mục tiêu ${targets} · ngày gốc ${r.date_from} → ${r.date_to} · as_of ${r.as_of} · `
        + `${fmtNum(r.rows[0]?.CommonObservations, 0)} quan sát chung cho cả ${r.rows.length} run.`),
      table([
        { key: "RunId", label: "Run", num: true }, { key: "ModelCode", label: "Mô hình" },
        { label: "Số quan sát giao", num: true, render: (x) => fmtNum(x.CommonObservations, 0) },
        { label: "Accuracy", num: true, render: (x) => pct(x.Accuracy) }, { label: "Brier", num: true, render: (x) => fmtNum(x.BrierScore, 4) },
        { label: "Log loss", num: true, render: (x) => fmtNum(x.NaturalLogLoss, 4) },
        { label: "Cửa sổ gốc thực tế", render: (x) => `${fmtDate(x.FirstOrigin)} → ${fmtDate(x.LastOrigin)}` },
      ], r.rows, { caption: "So sánh run trên tập quan sát giao" }), el("p", { class: "hint" }, r.note));
  } catch (e) { showError(out, e, runCompare); }
}

// ---------------------------------------------------------------------------------------------------
async function loadOps() {
  const m = state.meta, eodOn = m.eod.enabled;
  $("oDry").disabled = $("oSync").disabled = $("oToken").disabled = !eodOn || state.busy;
  $("opsScope").textContent = eodOn
    ? `Phạm vi ghi: database ${m.database} · dataset ${currentDataset().DatasetCode} · nguồn ${m.eod.config[0]?.SourceCode} · universe ${m.eod.config[0]?.IndexCode} snapshot ${m.eod.config[0]?.UniverseAsOf}. Dry run kiểm tra trong SQL Server rồi ROLLBACK.`
    : `Đồng bộ bị tắt: ${m.eod.reason}.`;
  if (!eodOn) setState($("opsJob"), "", `Không thể chạy đồng bộ ở chế độ ${m.data_scope}.`);
  loadCalendarCheck();
  if (m.data_scope === "DEMO_OFFLINE" || !eodOn) {
    $("opsCards").replaceChildren(card("Nhật ký EOD", "Không áp dụng", m.eod.reason));
    setState($("opsRuns"), "", `${m.data_scope}: database này không được đồng bộ EOD nên không có nhật ký.`);
    setState($("reconTable"), "", "Không áp dụng.");
    return;
  }
  setState($("opsCards"), "loading", "Đang tải trạng thái…");
  try {
    const s = await api(`/api/ops/last-status?${qs({ dataset_id: state.datasetId })}`);
    $("opsCards").replaceChildren(
      card("Ngày yêu cầu gần nhất", fmtDate(s.last_requested_date), s.last_run ? `run #${s.last_run.EodRunId} · ${s.last_run.ErrorCode || ""}${s.last_run.IsDryRun ? " · dry run" : ""}` : "chưa có run", s.last_run ? badge(s.last_run.Status) : null),
      card("Phiên đồng bộ thành công gần nhất", fmtDate(s.last_successful_trade_date), "Status = SUCCESS (không tính dry run)"),
      card("Dataset ObservedThrough", fmtDate(s.dataset_observed_through), `Giá mới nhất trong DB: ${fmtDate(s.last_price_date)}`),
      card("Nến provider mới nhất đã thấy", fmtDate(s.last_provider_candle_date), `Hôm nay (VN): ${s.today_vn}`),
      card("Giá đã chốt chờ đối soát", fmtNum(s.pending_reconciliation, 0), "nguồn thay đổi giá đã lưu (KBS điều chỉnh hồi tố); không tự ghi đè",
        s.pending_reconciliation ? badge("PENDING_REVIEW") : badge("SUCCESS", "good", "Không có")),
    );
  } catch (e) { showError($("opsCards"), e, loadOps); }
  loadOpsRuns();
  loadRecon();
}

async function loadOpsRuns() {
  setState($("opsRuns"), "loading", "Đang tải nhật ký…");
  try {
    const r = await api(`/api/ops/runs?${qs({ dataset_id: state.datasetId, status: $("oStatus").value, limit: state.ops.limit, offset: state.ops.offset })}`);
    $("opsRuns").replaceChildren(table([
      { key: "EodRunId", label: "#", num: true }, { label: "Phiên", render: (x) => fmtDate(x.SessionDate) },
      { label: "Trạng thái", render: (x) => el("span", {}, badge(x.Status), x.IsDryRun ? " dry run" : "") },
      { key: "ErrorCode", label: "Mã" }, { key: "TriggerKind", label: "Kích hoạt" },
      { label: "Yêu cầu", num: true, render: (x) => fmtNum(x.RequestedCount, 0) }, { label: "Nhận", num: true, render: (x) => fmtNum(x.ReceivedCount, 0) },
      { label: "Thêm", num: true, render: (x) => fmtNum(x.InsertedCount, 0) }, { label: "Không đổi", num: true, render: (x) => fmtNum(x.UnchangedCount, 0) },
      { label: "Từ chối", num: true, render: (x) => fmtNum(x.RejectedCount, 0) },
      { label: "Bắt đầu", render: (x) => fmtTime(x.StartedAtUtc) }, { label: "Thời gian", num: true, render: (x) => (x.DurationMs < 1000 ? `${fmtNum(x.DurationMs, 0)} ms` : `${fmtNum(x.DurationMs / 1000, 1)} s`) },
    ], r.items, { empty: "Không có lần chạy nào khớp bộ lọc.", caption: "Nhật ký EOD", onRow: (x) => loadRunDetail(x.EodRunId) }));
    pager($("opsPager"), r.total, r.offset, r.limit, (o) => { state.ops.offset = o; loadOpsRuns(); });
  } catch (e) { showError($("opsRuns"), e, loadOpsRuns); }
}

async function loadRunDetail(id) {
  const box = $("opsRunDetail");
  setState(box, "loading", `Đang tải run #${id}…`);
  try {
    const r = await api(`/api/ops/runs/${id}`);
    const pm = r.ProviderMeta || {};
    box.replaceChildren(
      el("h3", {}, `Run #${r.EodRunId} · phiên ${fmtDate(r.SessionDate)} · `, badge(r.Status), r.ErrorCode ? ` ${r.ErrorCode}` : ""),
      el("p", {}, r.Message || ""),
      el("p", { class: "hint" }, `Kích hoạt ${r.TriggerKind}${r.IsDryRun ? " (dry run)" : ""} · bắt đầu ${fmtTime(r.StartedAtUtc)} · kết thúc ${fmtTime(r.FinishedAtUtc)} · `
        + `ObservedThrough ${fmtDate(r.ObservedThroughBefore)} → ${fmtDate(r.ObservedThroughAfter)} · nguồn ${pm.provider?.package || "—"} ${pm.provider?.package_version || ""} (${pm.provider?.source || "—"}) · lịch: ${pm.calendar?.decision || "—"}`),
      table([{ key: "Ticker", label: "Mã" }, { label: "Kết quả", render: (x) => badge(x.Outcome) }, { key: "Detail", label: "Chi tiết" }], r.items,
        { empty: "Không có chi tiết theo mã (run dừng trước khi tải dữ liệu, ví dụ cuối tuần/ngày tương lai/lỗi cấu hình).", caption: "Kết quả từng mã" }),
      r.evaluation.length ? table([{ key: "RunCode", label: "Đánh giá lại sau EOD: run" }, { label: "as_of", render: (x) => fmtDate(x.AsOfDate) },
        { label: "Đã chấm", num: true, render: (x) => fmtNum(x.EligibleRows, 0) }, { label: "Accuracy", num: true, render: (x) => pct(x.Accuracy) },
        { label: "Brier", num: true, render: (x) => fmtNum(x.BrierScore, 4) }], r.evaluation)
        : el("p", { class: "hint" }, "Không có snapshot đánh giá: dataset không có ModelRun hoặc run không SUCCESS."),
    );
    box.scrollIntoView({ block: "nearest" });
  } catch (e) { showError(box, e, () => loadRunDetail(id)); }
}

async function loadCalendarCheck() {
  setState($("calendarCheck"), "loading", "Đang kiểm tra lịch phiên…");
  try {
    const r = await api(`/api/ops/calendar-check?${qs({ dataset_id: state.datasetId, limit: 30 })}`);
    $("calendarCheck").replaceChildren(table([
      { label: "Phiên", render: (x) => fmtDate(x.TradeDate) }, { label: "Dòng giá", num: true, render: (x) => fmtNum(x.PriceRows, 0) },
      { label: "Kỳ vọng", num: true, render: (x) => fmtNum(x.ExpectedRows, 0) },
      { label: "Thiếu", num: true, render: (x) => (x.MissingRows > 0 ? badge("x", x.AfterObservedThrough ? "info" : "serious", `${x.MissingRows} thiếu`) : "0") },
      { label: "Sau ObservedThrough", render: (x) => (x.AfterObservedThrough ? "có (lịch tương lai)" : "không") },
    ], r.items, { empty: "Dataset chưa có lịch phiên.", caption: "Kiểm tra lịch phiên" }), el("p", { class: "hint" }, `Universe kỳ vọng: ${r.universe_source}. Thiếu dòng chỉ được báo cáo, không tự điền.`));
  } catch (e) { showError($("calendarCheck"), e, loadCalendarCheck); }
}

async function loadRecon() {
  try {
    const r = await api(`/api/ops/reconciliation?${qs({ dataset_id: state.datasetId, limit: 50 })}`);
    $("reconTable").replaceChildren(table([
      { key: "ReconId", label: "#", num: true }, { key: "Ticker", label: "Mã" }, { label: "Phiên", render: (x) => fmtDate(x.TradeDate) },
      { label: "Close đã lưu", num: true, render: (x) => fmtNum(x.StoredClose, 4) }, { label: "Close nguồn mới", num: true, render: (x) => fmtNum(x.ProviderClose, 4) },
      { key: "DetectedBy", label: "Phát hiện bởi" }, { label: "Trạng thái", render: (x) => badge(x.Status) },
    ], r.items, { empty: "Không có giá đã chốt nào bị nguồn thay đổi.", caption: "Đối soát" }),
    el("p", { class: "hint" }, "Duyệt bằng CLI: python -m marketlab_app.cli eod reconcile approve|reject --id N --reviewer … --note … (không tự cập nhật giá lịch sử)."));
  } catch (e) { showError($("reconTable"), e, loadRecon); }
}

async function startEod(dry) {
  const date = $("oDate").value, out = $("opsJob");
  const tokenInput = $("oToken");
  const token = tokenInput.value;
  if (!date) { setState(out, "error", "Chọn ngày phiên."); return; }
  if (!token) { setState(out, "error", "Nhập mã vận hành (MARKETLAB_OPS_TOKEN)."); tokenInput.focus(); return; }
  const ds = currentDataset().DatasetCode;
  const question = dry ? `DRY RUN phiên ${date} cho ${state.meta.database} / ${ds}?\nKiểm tra trong SQL Server rồi ROLLBACK, không ghi dữ liệu.`
    : `GHI THẬT phiên ${date} vào ${state.meta.database} / ${ds}?\nTransaction all-or-nothing, có nhật ký. Chạy lại cùng dữ liệu không thêm dòng.`;
  if (!window.confirm(question)) return;
  state.busy = true;
  $("oDry").disabled = $("oSync").disabled = true;
  setState(out, "loading", "Đang gửi yêu cầu…");
  try {
    const j = await api("/api/ops/eod", { method: "POST", headers: { "Content-Type": "application/json", "X-MarketLab-Ops-Token": token },
      body: JSON.stringify({ session_date: date, dry_run: dry, confirm: dry ? "DRY_RUN" : "SYNC" }) });
    tokenInput.value = "";
    let job = j;
    const t0 = Date.now();
    while (job.state === "RUNNING") {
      setState(out, "loading", `Job ${j.job_id.slice(0, 8)} đang chạy (${dry ? "dry run" : "ghi thật"}, phiên ${date})… ${Math.round((Date.now() - t0) / 1000)} s`);
      await new Promise((r) => setTimeout(r, 1500));
      job = await api(j.poll);
    }
    if (job.state === "ERROR") throw new ApiError(500, job.error.code, job.error.message);
    const r = job.result;
    out.replaceChildren(el("p", {}, badge(r.status), ` run #${r.eod_run_id} · phiên ${r.session_date}${r.error_code ? ` · ${r.error_code}` : ""} · thêm ${r.inserted}, không đổi ${r.unchanged}`
      + (r.would_insert !== null ? `, sẽ thêm ${r.would_insert}` : "") + ` / ${r.requested} mã`), el("p", {}, r.message),
      el("details", {}, el("summary", {}, "Kết quả JSON (không chứa token)"), el("pre", {}, JSON.stringify(r, null, 1))));
    state.ops.offset = 0;
    state.busy = false;
    loadOps();
  } catch (e) { showError(out, e); }
  finally {
    tokenInput.value = "";
    state.busy = false;
    $("oDry").disabled = $("oSync").disabled = !state.meta.eod.enabled;
  }
}

function wireForms() {
  $("marketForm").addEventListener("submit", (ev) => { ev.preventDefault(); state.price.offset = 0; loadMarket(); });
  $("mClear").addEventListener("click", () => {
    $("mFrom").value = ""; $("mTo").value = ""; $("marketMsg").textContent = ""; state.price = { ...state.price, offset: 0, sort: "date", order: "desc" }; loadMarket();
  });
  $("predForm").addEventListener("submit", (ev) => { ev.preventDefault(); state.pred.offset = 0; loadPredictions(); });
  $("fClear").addEventListener("click", () => { $("fTicker").value = ""; $("fStatus").value = ""; state.pred.offset = 0; loadPredictions(); });
  $("fAsOf").addEventListener("change", () => { if ($("fAsOf").value) { writeHash(); loadRuns(); } });
  $("compareForm").addEventListener("submit", (ev) => { ev.preventDefault(); runCompare(); });
  $("oDry").addEventListener("click", () => startEod(true));
  $("oSync").addEventListener("click", () => startEod(false));
  $("opsRefresh").addEventListener("click", () => loadOps());
  $("oStatus").addEventListener("change", () => { state.ops.offset = 0; loadOpsRuns(); });
  let t;
  window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(() => { if (activeTab() === "market" && $("mTicker").value && !validateMarket()) loadMarket(); }, 250); });
}

// A deep link pasted/edited in the same tab changes only the hash: re-read state (replaceState never fires this).
window.addEventListener("hashchange", () => location.reload());
boot();
