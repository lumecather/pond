// The chart on the trade page: candles, volume, rule levels, trade markers.
// Candles come from /api/chart/; trade.js sends the current price as a "pond:price" event,
// which moves the last candle without waiting for the next reload.
(() => {
  const box = document.getElementById("chart");
  if (!box || !window.LightweightCharts) return;
  const LC = window.LightweightCharts;
  const { tokenId, pro } = box.dataset;
  const msg = document.getElementById("chart-msg");
  const info = document.getElementById("candle-info");
  const pick = document.getElementById("chart-pick");
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  const tzShift = -new Date().getTimezoneOffset() * 60; // the library treats time as UTC
  const SECONDS = { "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400 };
  const NAMES = { "15m": "15 minutes", "1h": "1 hour", "4h": "4 hours", "1d": "1 day" };

  const chart = LC.createChart(box, {
    autoSize: true,
    layout: { background: { type: "solid", color: "transparent" }, textColor: v("--muted"), fontFamily: "system-ui, sans-serif", fontSize: 12 },
    grid: { vertLines: { visible: false }, horzLines: { color: v("--line") } },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false, rightOffset: 4 },
    crosshair: { mode: LC.CrosshairMode.Normal },
    localization: { locale: "en-US" },
  });
  const candles = chart.addSeries(LC.CandlestickSeries, {
    upColor: v("--up"), downColor: v("--down"), wickUpColor: v("--up"), wickDownColor: v("--down"), borderVisible: false,
  });
  const volume = chart.addSeries(LC.HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "", lastValueVisible: false, priceLineVisible: false });
  volume.priceScale().applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
  const ma = pro === "1" ? chart.addSeries(LC.LineSeries, { color: v("--water"), lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }) : null;
  const markers = LC.createSeriesMarkers(candles, []);

  const store = {  // localStorage can be unavailable (private windows, some embedded browsers)
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* not important */ } },
  };
  let tf = store.get("chart-tf");
  if (!SECONDS[tf]) tf = "1h";
  let lines = [];
  let bar = null;      // the last (still open) candle
  let fitted = null;
  let loading = false;
  let request = 0;     // bumps on every load, so an answer for an old timeframe is ignored

  // how many decimals to show: 9.26 -> 2, 0.0000093 -> 9
  const precisionFor = (p) => Math.min(12, Math.max(2, Math.ceil(-Math.log10(p)) + 3));
  const fmt = (p) => p.toLocaleString("en-US", { maximumFractionDigits: precisionFor(p) });
  const sma = (rows, n) => rows.map((r, i) => i < n - 1 ? null : { time: r.time, value: rows.slice(i - n + 1, i + 1).reduce((s, x) => s + x.close, 0) / n }).filter(Boolean);
  const clock = (s) => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}:${String(sec).padStart(2, "0")}`;
  };

  // the line above the chart: how long the current candle has left
  function showTimer() {
    if (!bar || loading) return;
    const left = bar.time - tzShift + SECONDS[tf] - Math.floor(Date.now() / 1000);
    const move = bar.open ? (bar.close - bar.open) / bar.open * 100 : 0;
    const sign = move > 0 ? "+" : "";
    info.innerHTML = left > 0
      ? `1 candle = ${NAMES[tf]}. The current one closes in <b>${clock(left)}</b>; so far the price moved <b class="${move > 0 ? "up" : move < 0 ? "down" : ""}">${sign}${move.toFixed(2)} %</b>`
      : `1 candle = ${NAMES[tf]}. Waiting for the next candle…`;
  }
  setInterval(showTimer, 1000);

  async function load() {
    const mine = ++request;
    const wanted = tf;
    loading = true;
    if (!bar) info.textContent = "Loading candles…";
    box.classList.add("loading");
    let data;
    try {
      data = await (await fetch(`/api/chart/?token=${tokenId}&tf=${wanted}`)).json();
    } catch {
      data = { ok: false, error: "No connection to the app server. Retrying in a few seconds." };
    }
    if (mine !== request) return;  // the user switched timeframe meanwhile; a newer load is on its way
    loading = false;
    box.classList.remove("loading");
    if (!data.ok || !data.candles.length) {
      msg.textContent = data.error || "No candles yet.";
      msg.hidden = false;
      if (!bar) info.textContent = "";
      return;
    }
    msg.hidden = true;
    const rows = data.candles.map((c) => ({ ...c, time: c.time + tzShift }));
    bar = { ...rows[rows.length - 1] };
    const precision = precisionFor(bar.close);
    candles.applyOptions({ priceFormat: { type: "price", precision, minMove: 1 / 10 ** precision } });
    candles.setData(rows);
    volume.setData(rows.map((c) => ({ time: c.time, value: c.volume, color: (c.close >= c.open ? v("--up") : v("--down")) + "55" })));
    if (ma) ma.setData(sma(rows, 20));

    lines.forEach((l) => candles.removePriceLine(l));
    lines = data.levels.map((l) => candles.createPriceLine({
      price: l.price, title: l.title, lineWidth: 1, axisLabelVisible: true,
      lineStyle: l.kind === "avg" ? LC.LineStyle.Dotted : LC.LineStyle.Dashed,
      color: l.kind === "buy" ? v("--up") : l.kind === "sell" ? v("--bobber") : v("--muted"),
    }));

    // a trade marker goes on the candle the trade fell into
    const first = rows[0].time;
    markers.setMarkers(data.trades.filter((t) => t.time + tzShift >= first).map((t) => {
      const at = [...rows].reverse().find((r) => r.time <= t.time + tzShift);
      return t.side === "buy"
        ? { time: at.time, position: "belowBar", shape: "arrowUp", color: v("--up"), text: "buy" }
        : { time: at.time, position: "aboveBar", shape: "arrowDown", color: v("--bobber"), text: "sell" };
    }));
    if (fitted !== tf) { chart.timeScale().fitContent(); fitted = tf; }
    showTimer();
  }

  // live price: move the last candle, and start a new one when its time is up
  document.addEventListener("pond:price", (e) => {
    const p = e.detail.usd;
    if (!p || !bar || loading) return;
    const now = Math.floor(Date.now() / 1000) + tzShift;
    const start = now - (now % SECONDS[tf]);
    if (start > bar.time) bar = { time: start, open: bar.close, high: Math.max(bar.close, p), low: Math.min(bar.close, p), close: p, volume: 0 };
    else bar = { ...bar, close: p, high: Math.max(bar.high, p), low: Math.min(bar.low, p) };
    candles.update(bar);
    showTimer();
  });

  document.querySelectorAll("[data-tf]").forEach((b) => {
    b.classList.toggle("on", b.dataset.tf === tf);
    b.addEventListener("click", () => {
      if (b.dataset.tf === tf) return;
      tf = b.dataset.tf;
      bar = null;
      store.set("chart-tf", tf);
      document.querySelectorAll("[data-tf]").forEach((x) => x.classList.toggle("on", x === b));
      load();
    });
  });

  // clicking the chart suggests a rule at that price (it creates nothing by itself)
  const link = pick.querySelector("a");
  pick.querySelector("button").addEventListener("click", () => (pick.hidden = true));
  chart.subscribeClick((p) => {
    if (!p.point || !bar) return;
    const price = candles.coordinateToPrice(p.point.y);
    if (!price || price <= 0) return;
    const below = price < bar.close;
    link.href = `/rules/?token=${tokenId}&price=${price.toFixed(precisionFor(price))}&trigger=${below ? "below" : "above"}`;
    link.textContent = `Set a rule: when it ${below ? "drops below" : "rises above"} $${fmt(price)} →`;
    pick.hidden = false;
  });

  load();
  setInterval(() => { if (!document.hidden && !loading) load(); }, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
})();
