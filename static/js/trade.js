// Trade page: live price, trade preview, protection against double clicks.
(() => {
  const form = document.getElementById("trade-form");
  const priceEl = document.getElementById("price");
  if (!form || !priceEl) return;
  const tokenId = form.token.value;
  const { symbol, native } = form.dataset;
  const haveToken = parseFloat(form.dataset.haveToken) || 0;
  const haveNative = parseFloat(form.dataset.haveNative) || 0;
  const FEE = 0.003;
  const isLive = form.dataset.mode === "live";
  const limit = parseFloat(form.dataset.limit) || 0;
  let armed = false; // live mode: the first click only "arms" the button
  const POLL = 10000;
  let price = parseFloat(priceEl.dataset.price) || null;   // in the network coin
  let usd = parseFloat(priceEl.dataset.usd) || null;       // in dollars
  let updated = price ? Date.now() : null;
  let failed = false;

  const digits = (p) => Math.min(12, Math.max(2, Math.ceil(-Math.log10(Math.abs(p) || 1)) + 3));
  const fmt = (p) => p.toLocaleString("en-US", { maximumFractionDigits: p >= 1000 ? 0 : digits(p) });
  const dollars = (p) => `$${fmt(p)}`;

  // ---- live price
  const livePrice = document.getElementById("live-price");
  const liveNative = document.getElementById("live-native");
  const live = document.getElementById("live");
  const liveText = document.getElementById("live-text");

  const tick = () => {
    if (!updated) return;
    const s = Math.round((Date.now() - updated) / 1000);
    live.classList.toggle("stale", failed || s > 45);
    liveText.textContent = failed ? "no connection, retrying…" : s < 3 ? "price updated just now" : `price updated ${s}s ago`;
  };

  async function poll() {
    if (document.hidden) return;
    try {
      const d = await (await fetch(`/api/price/?token=${tokenId}`)).json();
      if (!d.ok) throw new Error(d.error);
      const before = usd ?? price;
      price = d.price; usd = d.price_usd; updated = Date.now(); failed = false;
      const now = usd ?? price;
      if (livePrice) {
        livePrice.textContent = usd ? dollars(usd) : `${fmt(price)} ${native}`;
        if (before && now !== before) {
          livePrice.classList.remove("flash-up", "flash-down");
          void livePrice.offsetWidth; // restart the animation
          livePrice.classList.add(now > before ? "flash-up" : "flash-down");
        }
      }
      if (liveNative) liveNative.textContent = fmt(price);
      live.classList.add("beat"); setTimeout(() => live.classList.remove("beat"), 600);
      document.dispatchEvent(new CustomEvent("pond:price", { detail: { usd, price } }));
      preview();
    } catch { failed = true; }
    tick();
  }
  setInterval(poll, POLL);
  setInterval(tick, 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });

  // ---- preview: what the trade will give you
  const box = document.getElementById("preview");
  const submit = document.getElementById("submit");
  const num = (v) => parseFloat(String(v).replace(",", ".").replace(/\s/g, ""));

  // fromUser: the user changed the form. Only then does an armed live confirmation reset;
  // the price poll that calls this every 10 s must not cancel it.
  function preview(fromUser = false) {
    const side = form.side.value;
    if (fromUser && armed) { armed = false; submit.classList.remove("armed"); }
    form.querySelectorAll("[data-side]").forEach((el) => (el.hidden = el.dataset.side !== side));
    if (!armed) submit.textContent = (side === "buy" ? "Buy " : "Sell ") + symbol;
    submit.classList.toggle("sell", side === "sell");
    let text = "", bad = false;
    if (price) {
      if (side === "buy") {
        const a = num(form.amount.value);
        if (a > 0) {
          text = `You get ≈ ${fmt(a * (1 - FEE) / price)} ${symbol}` + (usd ? ` · worth about ${dollars(a * usd / price)}` : "");
          if (a > haveNative) { text = `Not enough: the balance is ${fmt(haveNative)} ${native}`; bad = true; }
          else if (limit && a > limit) { text = `Above the single-buy limit of ${fmt(limit)} ${native}`; bad = true; }
        }
      } else {
        const sold = haveToken * (parseInt(form.percent.value) || 0) / 100;
        if (sold > 0) text = `You sell ${fmt(sold)} ${symbol} → get ≈ ${fmt(sold * price * (1 - FEE))} ${native}` + (usd ? ` (about ${dollars(sold * usd)})` : "");
        else { text = `You have no ${symbol} to sell`; bad = true; }
      }
    }
    box.textContent = text;
    box.hidden = !text;
    box.classList.toggle("bad", bad);
    submit.disabled = bad;
  }
  form.addEventListener("input", () => preview(true));
  form.addEventListener("change", () => preview(true));
  form.querySelectorAll("[data-set]").forEach((b) => b.addEventListener("click", () => { form.amount.value = b.dataset.set; preview(true); }));

  // one submission only: a second click won't create a second trade
  form.addEventListener("submit", (e) => {
    if (form.dataset.sent) return e.preventDefault();
    if (isLive && !armed) {
      e.preventDefault();
      armed = true;
      submit.classList.add("armed");
      submit.textContent = "Click again: this is real money";
      return;
    }
    if (isLive) form.confirm.value = "1";
    form.dataset.sent = "1";
    submit.textContent = form.side.value === "buy" ? "Buying…" : "Selling…";
    submit.classList.add("busy");
  });

  preview();
  tick();
})();
