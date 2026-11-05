// Dependency-free SVG charts. Close (line) and Volume (bars) are two panels with their own y-axis sharing one
// x-axis and one crosshair/tooltip (no dual axis). All text is set through textContent.
const NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
  if (parent) parent.appendChild(n);
  return n;
}

function niceTicks(min, max, count = 5) {
  if (!(isFinite(min) && isFinite(max))) return [];
  if (min === max) { const d = Math.abs(min) * 0.05 || 1; min -= d; max += d; }
  const span = max - min;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) out.push(+v.toPrecision(12));
  return out;
}

const nf = (d) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: d });
export function fmtNum(v, digits = 2) {
  return v === null || v === undefined || !isFinite(Number(v)) ? "—" : nf(digits).format(Number(v));
}
function compact(v) {
  return new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

export function priceVolumeChart(container, points, opts) {
  container.replaceChildren();
  const tooltip = opts.tooltip;
  const width = Math.max(320, container.clientWidth || 800);
  const m = { l: 64, r: 16, t: 22, b: 26 };
  const hClose = 240, hVol = 110, gap = 34;
  const height = m.t + hClose + gap + hVol + m.b;
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img",
    "aria-label": `Giá đóng cửa và khối lượng ${opts.ticker}, ${points.length} phiên` }, container);
  const iw = width - m.l - m.r;
  const n = points.length;
  const band = iw / n;                      // band scale: every session owns one slot; marks stay inside the axis
  const x = (i) => m.l + band * (i + 0.5);
  const closes = points.map((p) => Number(p.ClosePrice));
  const vols = points.map((p) => Number(p.Volume));
  let cMin = Math.min(...closes), cMax = Math.max(...closes);
  const pad = (cMax - cMin) * 0.08 || Math.abs(cMax) * 0.02 || 1;
  cMin -= pad; cMax += pad;
  const yC = (v) => m.t + hClose - ((v - cMin) / (cMax - cMin)) * hClose;
  const vMax = Math.max(...vols, 1);
  const vTop = m.t + hClose + gap;
  const yV = (v) => vTop + hVol - (v / vMax) * hVol;

  // panel labels (single series per panel: the title names it, no legend box)
  svgEl("text", { x: m.l, y: m.t - 8, class: "panel-label" }, svg).textContent = `Close (${opts.unit})`;
  svgEl("text", { x: m.l, y: vTop - 8, class: "panel-label" }, svg).textContent = "Volume (cổ phiếu)";

  const axis = svgEl("g", { class: "axis" }, svg);
  for (const t of niceTicks(cMin, cMax, 5)) {
    if (t < cMin || t > cMax) continue;
    svgEl("line", { x1: m.l, x2: width - m.r, y1: yC(t), y2: yC(t), class: "gridline" }, axis);
    svgEl("text", { x: m.l - 6, y: yC(t) + 4, "text-anchor": "end" }, axis).textContent = fmtNum(t, 2);
  }
  for (const t of niceTicks(0, vMax, 3)) {
    if (t > vMax) continue;
    svgEl("line", { x1: m.l, x2: width - m.r, y1: yV(t), y2: yV(t), class: "gridline" }, axis);
    svgEl("text", { x: m.l - 6, y: yV(t) + 4, "text-anchor": "end" }, axis).textContent = compact(t);
  }
  svgEl("line", { x1: m.l, x2: width - m.r, y1: vTop + hVol, y2: vTop + hVol, class: "baseline" }, axis);
  const labelEvery = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 90))));
  const labelIdx = points.map((_, i) => i).filter((i) => i % labelEvery === 0);
  if (labelIdx[labelIdx.length - 1] !== n - 1) {
    if (labelIdx.length && x(n - 1) - x(labelIdx[labelIdx.length - 1]) < 80) labelIdx.pop();   // avoid collision with the last date
    labelIdx.push(n - 1);
  }
  for (const i of labelIdx) {
    svgEl("text", { x: x(i), y: height - 8, "text-anchor": n > 1 && i === 0 ? "start" : n > 1 && i === n - 1 ? "end" : "middle" }, axis)
      .textContent = String(points[i].TradeDate).slice(0, 10);
  }

  // volume bars: 2px gap between adjacent bars, 4px rounded top anchored to the baseline
  const bw = Math.max(1, Math.min(18, band - 2));   // 2px surface gap between adjacent bars
  const bars = svgEl("g", {}, svg);
  const barEls = points.map((p, i) => {
    const h = Math.max(0, vTop + hVol - yV(vols[i]));
    const r = Math.min(4, bw / 2, h);
    const x0 = x(i) - bw / 2, y0 = vTop + hVol - h;
    const d = h <= 0 ? `M${x0},${vTop + hVol}h${bw}` :
      `M${x0},${vTop + hVol}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + bw - r}Q${x0 + bw},${y0} ${x0 + bw},${y0 + r}V${vTop + hVol}Z`;
    return svgEl("path", { d, class: "bar" }, bars);
  });

  // close line, 2px
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${yC(closes[i]).toFixed(1)}`).join("");
  svgEl("path", { d: path, class: "line" }, svg);
  if (n === 1) svgEl("circle", { cx: x(0), cy: yC(closes[0]), r: 4, class: "marker" }, svg);

  // hover layer: crosshair spans both panels, snaps to the nearest session
  const cross = svgEl("line", { y1: m.t, y2: vTop + hVol, class: "crosshair", visibility: "hidden" }, svg);
  const marker = svgEl("circle", { r: 4.5, class: "marker", visibility: "hidden" }, svg);
  const hit = svgEl("rect", { x: m.l - 6, y: m.t, width: iw + 12, height: vTop + hVol - m.t, fill: "transparent", tabindex: 0,
    "aria-label": "Di chuột hoặc dùng phím mũi tên để xem từng phiên" }, svg);
  let active = -1;
  function show(i, clientX, clientY) {
    if (i < 0 || i >= n) return;
    if (active >= 0) barEls[active].classList.remove("active");
    active = i;
    barEls[i].classList.add("active");
    const p = points[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    marker.setAttribute("cx", x(i)); marker.setAttribute("cy", yC(closes[i])); marker.setAttribute("visibility", "visible");
    tooltip.replaceChildren();
    const d = document.createElement("div"); d.className = "t-date"; d.textContent = `${opts.ticker} · ${String(p.TradeDate).slice(0, 10)}`;
    tooltip.appendChild(d);
    for (const [label, value] of [["Close", fmtNum(p.ClosePrice, 4)], ["Open", fmtNum(p.OpenPrice, 4)], ["High", fmtNum(p.HighPrice, 4)],
      ["Low", fmtNum(p.LowPrice, 4)], ["Volume", fmtNum(p.Volume, 0)]]) {
      const row = document.createElement("div"); row.className = "t-row";
      const a = document.createElement("span"); a.textContent = label;
      const b = document.createElement("strong"); b.textContent = value;
      row.append(a, b); tooltip.appendChild(row);
    }
    const note = document.createElement("div"); note.className = "t-note";
    note.textContent = `Đơn vị: ${opts.unit}. Basis: ${opts.basis} (EOD, không realtime, không phải total return).`;
    tooltip.appendChild(note);
    tooltip.hidden = false;
    const rect = svg.getBoundingClientRect();
    const px = clientX ?? rect.left + (x(i) / width) * rect.width;
    const py = clientY ?? rect.top + 40;
    const tw = tooltip.offsetWidth;
    tooltip.style.left = `${Math.min(window.innerWidth - tw - 8, px + 14)}px`;
    tooltip.style.top = `${Math.max(8, py - 20)}px`;
  }
  function hide() {
    tooltip.hidden = true;
    cross.setAttribute("visibility", "hidden"); marker.setAttribute("visibility", "hidden");
    if (active >= 0) barEls[active].classList.remove("active");
  }
  hit.addEventListener("pointermove", (ev) => {
    const rect = svg.getBoundingClientRect();
    const sx = ((ev.clientX - rect.left) / rect.width) * width;
    const i = Math.floor((sx - m.l) / band);
    show(Math.max(0, Math.min(n - 1, i)), ev.clientX, ev.clientY);
  });
  hit.addEventListener("pointerleave", hide);
  hit.addEventListener("blur", hide);
  hit.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowRight") show(Math.min(n - 1, active + 1));
    else if (ev.key === "ArrowLeft") show(Math.max(0, active < 0 ? n - 1 : active - 1));
    else if (ev.key === "Escape") hide();
  });
  return svg;
}
