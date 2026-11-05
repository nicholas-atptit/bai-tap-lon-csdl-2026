// Dependency-free SVG charts. Close (line) and Volume (bars) are two panels with their own y-axis sharing one
// x-axis (band scale) and one crosshair/tooltip (no dual axis). Sessions that exist in the dataset calendar but have
// no stored price (ClosePrice === null) break the line and get a hatched marker on the axis; they are never interpolated.
// All text is set through textContent.
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
  const step0 = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) out.push(+v.toPrecision(12));
  return out;
}

const nf = (d) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: d });
export function fmtNum(v, digits = 2) {
  return v === null || v === undefined || v === "" || !isFinite(Number(v)) ? "—" : nf(digits).format(Number(v));
}
const compact = (v) => new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 }).format(v);
const has = (v) => v !== null && v !== undefined && isFinite(Number(v));

export function priceVolumeChart(container, points, opts) {
  container.replaceChildren();
  const tooltip = opts.tooltip;
  const width = Math.max(300, container.clientWidth || 800);
  const narrow = width < 520;
  const m = { l: narrow ? 46 : 64, r: 12, t: 24, b: 28 };
  const hClose = narrow ? 190 : 240, hVol = narrow ? 90 : 110, gap = 36;
  const height = m.t + hClose + gap + hVol + m.b;
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img",
    "aria-label": `${opts.ticker} · ${opts.datasetCode}: Close và Volume, ${points.length} phiên lịch` }, container);
  svgEl("title", {}, svg).textContent = `${opts.ticker} — Close (${opts.basis}) và Volume theo phiên`;
  const iw = width - m.l - m.r;
  const n = points.length;
  const band = iw / n;
  const x = (i) => m.l + band * (i + 0.5);
  const closes = points.map((p) => (has(p.ClosePrice) ? Number(p.ClosePrice) : null));
  const vols = points.map((p) => (has(p.Volume) ? Number(p.Volume) : null));
  const known = closes.filter((v) => v !== null);
  let cMin = Math.min(...known), cMax = Math.max(...known);
  const pad = (cMax - cMin) * 0.08 || Math.abs(cMax) * 0.02 || 1;
  cMin -= pad; cMax += pad;
  const yC = (v) => m.t + hClose - ((v - cMin) / (cMax - cMin)) * hClose;
  const vMax = Math.max(...vols.filter((v) => v !== null), 1);
  const vTop = m.t + hClose + gap;
  const yV = (v) => vTop + hVol - (v / vMax) * hVol;

  svgEl("text", { x: m.l, y: m.t - 9, class: "panel-label" }, svg).textContent = `Close · ${opts.basis} (${opts.unitShort})`;
  svgEl("text", { x: m.l, y: vTop - 9, class: "panel-label" }, svg).textContent = "Volume (cổ phiếu)";

  const axis = svgEl("g", { class: "axis" }, svg);
  for (const t of niceTicks(cMin, cMax, narrow ? 4 : 5)) {
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
  const labelEvery = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 92))));
  const labelIdx = points.map((_, i) => i).filter((i) => i % labelEvery === 0);
  if (labelIdx[labelIdx.length - 1] !== n - 1) {
    if (labelIdx.length && x(n - 1) - x(labelIdx[labelIdx.length - 1]) < 84) labelIdx.pop();
    labelIdx.push(n - 1);
  }
  for (const i of labelIdx) {
    svgEl("text", { x: x(i), y: height - 8, "text-anchor": n > 1 && i === 0 ? "start" : n > 1 && i === n - 1 ? "end" : "middle" }, axis)
      .textContent = String(points[i].TradeDate).slice(0, 10);
  }

  // volume bars: 2px gap, 4px rounded tops anchored to the baseline; missing sessions -> hatched stub
  const bw = Math.max(1, Math.min(18, band - 2));
  const bars = svgEl("g", {}, svg);
  const barEls = points.map((p, i) => {
    const x0 = x(i) - bw / 2;
    if (vols[i] === null) {
      return svgEl("rect", { x: x0, y: vTop + hVol - 8, width: bw, height: 8, class: "missing" }, bars);
    }
    const h = Math.max(0, vTop + hVol - yV(vols[i]));
    const r = Math.min(4, bw / 2, h);
    const y0 = vTop + hVol - h;
    const d = h <= 0 ? `M${x0},${vTop + hVol}h${bw}` :
      `M${x0},${vTop + hVol}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + bw - r}Q${x0 + bw},${y0} ${x0 + bw},${y0 + r}V${vTop + hVol}Z`;
    return svgEl("path", { d, class: "bar" }, bars);
  });

  // close line, 2px, broken at sessions without a stored price
  let path = "", pen = false;
  closes.forEach((c, i) => {
    if (c === null) { pen = false; return; }
    path += `${pen ? "L" : "M"}${x(i).toFixed(1)},${yC(c).toFixed(1)}`;
    pen = true;
  });
  svgEl("path", { d: path, class: "line" }, svg);
  closes.forEach((c, i) => {   // isolated points (neighbours missing) would be invisible without a dot
    if (c !== null && (i === 0 || closes[i - 1] === null) && (i === n - 1 || closes[i + 1] === null)) {
      svgEl("circle", { cx: x(i), cy: yC(c), r: 3.5, class: "marker" }, svg);
    }
  });
  closes.forEach((c, i) => {
    if (c === null) svgEl("line", { x1: x(i), x2: x(i), y1: m.t, y2: m.t + hClose, class: "gapline" }, svg);
  });

  const cross = svgEl("line", { y1: m.t, y2: vTop + hVol, class: "crosshair", visibility: "hidden" }, svg);
  const marker = svgEl("circle", { r: 4.5, class: "marker", visibility: "hidden" }, svg);
  const hit = svgEl("rect", { x: m.l, y: m.t, width: iw, height: vTop + hVol - m.t, fill: "transparent", tabindex: 0,
    role: "button", "aria-label": "Biểu đồ: di chuột hoặc dùng phím mũi tên trái/phải để đọc từng phiên" }, svg);
  let active = -1;
  function row(label, value) {
    const r = document.createElement("div"); r.className = "t-row";
    const a = document.createElement("span"); a.textContent = label;
    const b = document.createElement("strong"); b.textContent = value;
    r.append(a, b); return r;
  }
  function show(i, clientX, clientY) {
    if (i < 0 || i >= n) return;
    if (active >= 0) barEls[active].classList.remove("active");
    active = i;
    barEls[i].classList.add("active");
    const p = points[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    if (closes[i] !== null) {
      marker.setAttribute("cx", x(i)); marker.setAttribute("cy", yC(closes[i])); marker.setAttribute("visibility", "visible");
    } else marker.setAttribute("visibility", "hidden");
    tooltip.replaceChildren();
    const d = document.createElement("div"); d.className = "t-date";
    d.textContent = `${opts.ticker} · ${String(p.TradeDate).slice(0, 10)}`;
    tooltip.appendChild(d);
    if (closes[i] === null) {
      const w = document.createElement("div"); w.className = "t-warn";
      w.textContent = "Phiên có trong lịch dataset nhưng chưa có giá lưu cho mã này (không nội suy).";
      tooltip.appendChild(w);
    } else {
      tooltip.append(row("Close", fmtNum(p.ClosePrice, 4)), row("Open", fmtNum(p.OpenPrice, 4)), row("High", fmtNum(p.HighPrice, 4)),
        row("Low", fmtNum(p.LowPrice, 4)), row("Volume", fmtNum(p.Volume, 0)));
    }
    const note = document.createElement("div"); note.className = "t-note";
    note.textContent = `${opts.datasetCode} · ${opts.basis} · đơn vị: ${opts.unit}. EOD, không realtime, không phải total return.`;
    tooltip.appendChild(note);
    tooltip.hidden = false;
    const rect = svg.getBoundingClientRect();
    const px = clientX ?? rect.left + (x(i) / width) * rect.width;
    const py = clientY ?? rect.top + 40;
    const tw = tooltip.offsetWidth;
    tooltip.style.left = `${Math.max(8, Math.min(window.innerWidth - tw - 8, px + 14))}px`;
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
    show(Math.max(0, Math.min(n - 1, Math.floor((sx - m.l) / band))), ev.clientX, ev.clientY);
  });
  hit.addEventListener("pointerleave", hide);
  hit.addEventListener("blur", hide);
  hit.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowRight") { ev.preventDefault(); show(Math.min(n - 1, active + 1)); }
    else if (ev.key === "ArrowLeft") { ev.preventDefault(); show(Math.max(0, active < 0 ? n - 1 : active - 1)); }
    else if (ev.key === "Escape") hide();
  });
  return svg;
}
