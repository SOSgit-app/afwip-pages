/* Board motion: slide tokens when they Move. Other engage FX are disabled. */
(function () {
  const SVG = "http://www.w3.org/2000/svg";
  const layer = document.createElementNS(SVG, "svg");
  layer.id = "engage-layer";
  layer.setAttribute("aria-hidden", "true");
  document.body.append(layer);

  const tokens = new Map(); // last settled board positions (from)
  let watermark = -1;
  let game = null;
  let pulling = false;
  let boardEpoch = 0;
  const recentHit = new Map();
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function gameId() {
    const el = document.querySelector(".topbar");
    if (!el) return null;
    const match = el.textContent.match(/game\s+([0-9a-f]+)/i);
    return match ? match[1] : null;
  }

  function fit() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    layer.setAttribute("viewBox", "0 0 " + w + " " + h);
    layer.setAttribute("width", String(w));
    layer.setAttribute("height", String(h));
  }
  fit();
  window.addEventListener("resize", fit);

  function board() {
    return document.querySelector(".board-svg");
  }
  function center(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 && r.height < 2) return null;
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  function labeled(text) {
    const svg = board();
    if (!svg) return null;
    const node = [...svg.querySelectorAll("text")].find((el) => (el.textContent || "").trim() === text);
    return node ? center(node) : null;
  }
  function snapshot() {
    const svg = board();
    if (!svg) return;
    const next = new Map();
    svg.querySelectorAll("title").forEach((title) => {
      const match = (title.textContent || "").match(/#(\d+)/);
      if (!match) return;
      const g = title.parentElement;
      const at = g ? center(g) : null;
      if (at) next.set(match[1], at);
    });
    // Only replace settled positions when we are not mid-ingest; callers that
    // need a fresh "after" point use liveToken() instead.
    if (!next.size) return;
    tokens.clear();
    next.forEach((at, uid) => tokens.set(uid, at));
  }

  function captureLive() {
    const map = new Map();
    const svg = board();
    if (!svg) return map;
    svg.querySelectorAll("title").forEach((title) => {
      const match = (title.textContent || "").match(/#(\d+)/);
      if (!match) return;
      const g = title.parentElement;
      const at = g ? center(g) : null;
      if (at) map.set(match[1], at);
    });
    return map;
  }

  function tokenAt(uid) {
    return uid ? tokens.get(String(uid)) || null : null;
  }
  function tokenTitle(uid) {
    const svg = board();
    if (!svg) return null;
    return [...svg.querySelectorAll("title")].find((title) => {
      const match = (title.textContent || "").match(/#(\d+)/);
      return match && match[1] === String(uid);
    }) || null;
  }
  function liveToken(uid) {
    const title = tokenTitle(uid);
    return title && title.parentElement ? center(title.parentElement) : null;
  }
  function baseAt(name) {
    if (name === "US_AIRBASE") return labeled("US AIRBASE");
    if (name === "PRC_AIRBASE") return labeled("PRC AIRBASE");
    return null;
  }
  function cyberAt(side) {
    const svg = board();
    if (!svg) return null;
    const anchor = labeled(side === "PRC" ? "PRC AIRBASE" : "US AIRBASE");
    const boxes = [...svg.querySelectorAll("rect")].filter((rect) => {
      const w = parseFloat(rect.getAttribute("width") || "0");
      return w >= 14 && w <= 16 && (rect.getAttribute("fill") || "").toLowerCase() === "#ffd166";
    });
    if (!boxes.length) {
      const word = [...svg.querySelectorAll("text")].find((el) => (el.textContent || "").includes("CYBER"));
      return word ? center(word) : anchor;
    }
    let best = boxes[0];
    if (anchor) {
      best = boxes.reduce((a, b) => {
        const da = Math.hypot(center(a).x - anchor.x, center(a).y - anchor.y);
        const db = Math.hypot(center(b).x - anchor.x, center(b).y - anchor.y);
        return da <= db ? a : b;
      });
    }
    return center(best);
  }

  function el(name, attrs) {
    const node = document.createElementNS(SVG, name);
    for (const key in attrs) node.setAttribute(key, attrs[key]);
    return node;
  }
  function gone(node, ms) {
    window.setTimeout(() => node.remove(), ms);
  }
  function dur(ms) {
    return reduce ? Math.min(ms, 160) : ms;
  }

  function glide(ms, draw) {
    const start = performance.now();
    const total = dur(ms);
    function step(now) {
      const t = Math.min(1, (now - start) / total);
      draw(t);
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  function burst(at, hit) {
    const rings = hit ? 3 : 1;
    for (let i = 0; i < rings; i++) {
      const ring = el("circle", {
        cx: at.x, cy: at.y, r: 4,
        class: hit ? "engage-burst" : "engage-miss",
      });
      layer.append(ring);
      const max = hit ? 26 + i * 8 : 14;
      window.setTimeout(() => {
        glide(420, (t) => {
          ring.setAttribute("r", String(4 + (max - 4) * t));
          ring.setAttribute("opacity", String(1 - t));
        });
        gone(ring, dur(460));
      }, reduce ? 0 : i * 50);
    }
  }

  function missile(from, to, hit) {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const angle = Math.atan2(dy, dx) * 180 / Math.PI;
    const trail = el("line", {
      x1: from.x, y1: from.y, x2: from.x, y2: from.y, class: "engage-trail",
    });
    layer.append(trail);
    const head = el("g", {});
    head.append(el("polygon", { points: "-18,-5 16,0 -18,5 -11,0", class: "engage-missile" }));
    head.append(el("polygon", { points: "-18,-3.4 -30,0 -18,3.4", class: "engage-flame" }));
    layer.append(head);
    glide(560, (t) => {
      const e = t * t * (3 - 2 * t);
      const x = from.x + dx * e;
      const y = from.y + dy * e;
      trail.setAttribute("x2", String(x));
      trail.setAttribute("y2", String(y));
      head.setAttribute("transform", "translate(" + x + " " + y + ") rotate(" + angle + ")");
      if (t === 1) {
        head.remove();
        glide(200, (u) => trail.setAttribute("opacity", String(1 - u)));
        gone(trail, dur(220));
        burst(to, hit);
      }
    });
  }

  function sensor(from, to) {
    const line = el("line", {
      x1: from.x, y1: from.y, x2: from.x, y2: from.y, class: "engage-sensor",
    });
    layer.append(line);
    const ms = dur(420);
    const start = performance.now();
    function step(now) {
      const t = Math.min(1, (now - start) / ms);
      line.setAttribute("x2", from.x + (to.x - from.x) * t);
      line.setAttribute("y2", from.y + (to.y - from.y) * t);
      if (t < 1) requestAnimationFrame(step);
      else {
        glide(260, (u) => line.setAttribute("opacity", String(1 - u)));
        gone(line, dur(280));
        const ring = el("circle", { cx: to.x, cy: to.y, r: 8, class: "engage-ring" });
        layer.append(ring);
        glide(480, (u) => {
          ring.setAttribute("r", String(8 + 18 * u));
          ring.setAttribute("opacity", String(1 - u));
        });
        gone(ring, dur(500));
      }
    }
    requestAnimationFrame(step);
  }

  function jag(from, to) {
    const parts = [from.x + "," + from.y];
    const segs = 6;
    for (let i = 1; i < segs; i++) {
      const t = i / segs;
      const x = from.x + (to.x - from.x) * t + (Math.random() - 0.5) * 26;
      const y = from.y + (to.y - from.y) * t + (Math.random() - 0.5) * 22;
      parts.push(x + "," + y);
    }
    parts.push(to.x + "," + to.y);
    return parts.join(" ");
  }
  function bolt(from, to, thenBurst) {
    const line = el("polyline", { points: jag(from, to), class: "engage-bolt" });
    layer.append(line);
    glide(720, (t) => {
      const flick = t < 0.15 || (t > 0.35 && t < 0.7) ? 1 : 0.2;
      line.setAttribute("opacity", String(t > 0.92 ? 1 - (t - 0.92) / 0.08 : flick));
    });
    gone(line, dur(740));
    if (thenBurst) window.setTimeout(() => burst(to, true), dur(460));
  }
  function cyber(side) {
    const at = cyberAt(side);
    if (!at) return;
    const left = { x: at.x - 48, y: at.y };
    const right = { x: at.x + 48, y: at.y };
    bolt(left, right, false);
    window.setTimeout(() => bolt(right, left, false), reduce ? 0 : 180);
  }
  function shield(at) {
    const arc = el("path", {
      d: "M " + (at.x - 16) + " " + (at.y + 8) +
        " Q " + at.x + " " + (at.y - 22) + " " + (at.x + 16) + " " + (at.y + 8) +
        " Q " + at.x + " " + (at.y + 6) + " " + (at.x - 16) + " " + (at.y + 8),
      class: "engage-shield",
    });
    layer.append(arc);
    glide(700, (t) => arc.setAttribute("opacity", String(t < 0.2 ? t / 0.2 : 1 - (t - 0.2) / 0.8)));
    gone(arc, dur(720));
  }

  function interpret(rows) {
    // Board FX: token movement slides only. No acquire sensors, missiles,
    // bolts, shields, bursts, or spawn slides.
    // US decisions use "Move … #uid -> band". PRC / fogged moves usually
    // arrive as token_moved ("… #uid moves" / data.uid) — still slide those.
    const effects = [];
    const seen = new Set();
    rows.forEach((row) => {
      const text = row.text || "";
      let uid = null;
      const labeled = text.match(/Move\s+.*?\#(\d+)\s*->\s*\S+/i);
      if (labeled) {
        uid = labeled[1];
      } else if (row.type === "t-token_moved") {
        if (row.data && row.data.uid != null) uid = String(row.data.uid);
        else {
          const moved = text.match(/#(\d+)\s+moves\b/i);
          if (moved) uid = moved[1];
        }
      } else {
        const moved = text.match(/#(\d+)\s+moves\b/i);
        if (moved) uid = moved[1];
      }
      if (!uid || seen.has(uid)) return;
      seen.add(uid);
      effects.push({ kind: "move", uid: uid });
    });
    return effects;
  }

  function pieceGroup(uid) {
    const title = tokenTitle(uid);
    return title && title.parentElement ? title.parentElement : null;
  }

  function slideOffset(from, to) {
    // Map screen-space from/to into the board SVG so a translate parks the
    // token (already painted at `to`) back over `from`.
    const svg = board();
    const ctm = svg && svg.getScreenCTM();
    if (!ctm || !from || !to) return null;
    const inv = ctm.inverse();
    function user(point) {
      const pt = svg.createSVGPoint();
      pt.x = point.x;
      pt.y = point.y;
      return pt.matrixTransform(inv);
    }
    const start = user(from);
    const end = user(to);
    return { dx: start.x - end.x, dy: start.y - end.y };
  }

  function parkPiece(uid, from, to) {
    // React already put the chip on the destination band; offset it so the
    // player never sees a one-frame teleport before the slide.
    const g = pieceGroup(uid);
    const off = slideOffset(from, to);
    if (!g || !off) return false;
    g.setAttribute("transform", "translate(" + off.dx + " " + off.dy + ")");
    return true;
  }

  function clearPark(uid) {
    const g = pieceGroup(uid);
    if (g) g.removeAttribute("transform");
  }

  function parkSlides(effects) {
    effects.forEach((fx) => {
      if ((fx.kind === "move" || fx.kind === "spawn") && fx.from && fx.to) {
        parkPiece(fx.uid, fx.from, fx.to);
      }
    });
  }

  function clearParkedSlides(effects) {
    effects.forEach((fx) => {
      if ((fx.kind === "move" || fx.kind === "spawn") && fx.uid != null) {
        clearPark(fx.uid);
      }
    });
  }

  function slidePiece(uid, from, to) {
    const g = pieceGroup(uid);
    const off = slideOffset(from, to);
    if (!g || !off) return;
    const dx = off.dx;
    const dy = off.dy;
    const distance = Math.hypot(to.x - from.x, to.y - from.y);
    const ms = dur(Math.min(980, 460 + distance * 0.4));
    window.__afwipLastSlide = { uid: String(uid), at: performance.now() };
    g.setAttribute("transform", "translate(" + dx + " " + dy + ")");
    const trail = el("line", {
      x1: from.x, y1: from.y, x2: to.x, y2: to.y, class: "engage-move",
    });
    layer.append(trail);
    glide(ms, (t) => {
      const e = 1 - Math.pow(1 - t, 3);
      g.setAttribute("transform", "translate(" + (dx * (1 - e)) + " " + (dy * (1 - e)) + ")");
      trail.setAttribute("opacity", String(0.85 * (1 - t)));
      if (t === 1) g.removeAttribute("transform");
    });
    gone(trail, ms + 40);
  }

  function screened(fx) {
    const duel = window.__afwipDuel;
    if (!duel || performance.now() - duel.at > 20000) return false;
    // Spawn must run like move: parkSlides parked a transform that only
    // slidePiece clears. Skipping Personnel Recovery (same uid as the kill)
    // left the chip translated off Band A / clipped — "back but invisible".
    if (fx.kind === "move" || fx.kind === "spawn" || fx.kind === "cyber") {
      return false;
    }
    const ids = [fx.from, fx.to, fx.uid].filter((id) => id != null).map(String);
    return ids.some((id) => id === String(duel.from) || id === String(duel.to));
  }

  function play(effects) {
    const now = performance.now();
    const sparked = new Set();
    effects.forEach((fx) => {
      if (screened(fx)) {
        if ((fx.kind === "move" || fx.kind === "spawn") && fx.uid != null) {
          clearPark(fx.uid);
        }
        return;
      }
      if (fx.kind === "missile") {
        const from = tokenAt(fx.from);
        const to = tokenAt(fx.to);
        if (!from || !to) return;
        if (fx.hit) recentHit.set(fx.to, now);
        missile(from, to, fx.hit);
      } else if (fx.kind === "base") {
        const from = tokenAt(fx.from);
        const to = baseAt(fx.base);
        if (!from || !to) return;
        missile(from, to, true);
      } else if (fx.kind === "sensor") {
        const to = tokenAt(fx.to);
        const from = fx.from ? tokenAt(fx.from) : cyberAt(fx.side);
        if (!from || !to) return;
        sensor(from, to);
      } else if (fx.kind === "bolt") {
        const from = cyberAt(fx.side);
        const to = tokenAt(fx.to);
        if (!from || !to) return;
        recentHit.set(fx.to, now);
        bolt(from, to, true);
      } else if (fx.kind === "cyber") {
        // Intentionally no-op: cyber animation removed.
      } else if (fx.kind === "shield") {
        const at = tokenAt(fx.to);
        if (at) shield(at);
      } else if (fx.kind === "move" || fx.kind === "spawn") {
        if (fx.from && fx.to) slidePiece(fx.uid, fx.from, fx.to);
      } else if (fx.kind === "burst") {
        const at = tokenAt(fx.to);
        if (!at) return;
        recentHit.set(fx.to, now);
        burst(at, true);
      }
    });
  }

  function dieOpen() {
    const die = document.getElementById("die-overlay");
    return !!(die && !die.hidden);
  }
  function runWhenClear(effects) {
    const started = performance.now();
    // Moves/spawns are already parked at origin — play ASAP. Other FX still
    // wait a beat so React can finish layout before missiles/sensors fire.
    const onlySlide = effects.length > 0 && effects.every(
      (fx) => fx.kind === "move" || fx.kind === "spawn"
    );
    const settleMs = onlySlide ? 0 : 280;
    function tick() {
      // Keep movers parked if React replaces the <g> during the wait.
      parkSlides(effects);
      if (dieOpen()) {
        const die = document.getElementById("die-overlay");
        const watch = new MutationObserver(() => {
          if (die.hidden) {
            watch.disconnect();
            parkSlides(effects);
            play(effects);
          }
        });
        watch.observe(die, { attributes: true, attributeFilter: ["hidden"] });
        window.setTimeout(() => {
          watch.disconnect();
          if (!dieOpen()) {
            parkSlides(effects);
            play(effects);
          } else {
            // Die still open — do not leave parked transforms stuck off-band.
            clearParkedSlides(effects);
          }
        }, 20000);
        return;
      }
      if (performance.now() - started < settleMs) {
        requestAnimationFrame(tick);
        return;
      }
      play(effects);
    }
    requestAnimationFrame(tick);
  }

  function rowsFromView(view) {
    return ((view && view.event_log) || []).map((ev) => ({
      text: (ev.message || "").replace(/\s+/g, " ").trim(),
      type: "t-" + (ev.type || ""),
      side: ev.side || "US",
      step: ev.step || 0,
      data: ev.data || {},
    }));
  }

  function homeFor(side) {
    return baseAt(side === "PRC" ? "PRC_AIRBASE" : "US_AIRBASE")
      || labeled(side === "PRC" ? "PRC AIRBASE" : "US AIRBASE");
  }

  function settlePositions() {
    const live = captureLive();
    if (!live.size) return;
    tokens.clear();
    live.forEach((at, uid) => tokens.set(uid, at));
  }

  function bindEffects(fresh) {
    const effects = interpret(fresh).map((fx) => {
      if (fx.kind === "move") {
        const from = tokenAt(fx.uid);
        const to = liveToken(fx.uid);
        return Object.assign({}, fx, { from: from, to: to });
      }
      if (fx.kind === "spawn") {
        const to = liveToken(fx.uid);
        const from = homeFor(fx.side);
        return Object.assign({}, fx, { from: from, to: to });
      }
      return fx;
    }).filter((fx) => {
      if (fx.kind !== "move" && fx.kind !== "spawn") return true;
      if (!fx.from || !fx.to) return false;
      return Math.hypot(fx.to.x - fx.from.x, fx.to.y - fx.from.y) > 8;
    });
    // One slide per token if several move lines land in the same step.
    const seenUid = new Set();
    return effects.filter((fx) => {
      if (fx.kind !== "move" && fx.kind !== "spawn") return true;
      if (seenUid.has(fx.uid)) return false;
      seenUid.add(fx.uid);
      return true;
    });
  }

  function ingest(view) {
    const rows = rowsFromView(view);
    if (!rows.length) {
      settlePositions();
      return;
    }
    const maxStep = rows.reduce((max, row) => Math.max(max, row.step), 0);
    if (watermark < 0) {
      watermark = maxStep;
      settlePositions();
      return;
    }
    if (maxStep < watermark) {
      watermark = maxStep;
      settlePositions();
      return;
    }
    const fresh = rows.filter((row) => row.step > watermark);
    if (!fresh.length) return;
    watermark = maxStep;
    const epoch = ++boardEpoch;
    // __afwipApply only setStates — React paints later. Watch the board DOM and
    // park movers in that mutation turn (before the browser paints) so the chip
    // never flashes on the destination, then slide.
    let finished = false;
    function finish() {
      if (finished || epoch !== boardEpoch) return;
      const effects = bindEffects(fresh);
      // Wait until live positions actually differ from the settled map.
      if (!effects.length) return;
      finished = true;
      if (obs) obs.disconnect();
      parkSlides(effects);
      runWhenClear(effects);
      window.setTimeout(settlePositions, reduce ? 200 : 900);
    }
    let obs = null;
    const svg = board();
    if (svg && typeof MutationObserver !== "undefined") {
      obs = new MutationObserver(() => {
        try { finish(); } catch (e) { /* ignore */ }
      });
      obs.observe(svg, { childList: true, subtree: true });
    }
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (epoch !== boardEpoch) return;
        if (!finished) {
          // No move/spawn distance yet (or no MO) — settle other steps / retry once.
          finish();
          if (!finished) {
            if (obs) obs.disconnect();
            settlePositions();
          }
        }
      });
    });
  }

  function hookApply() {
    if (typeof window.__afwipApply !== "function" || window.__afwipApply.__engage) return;
    const inner = window.__afwipApply;
    function wrapped(view) {
      const out = inner(view);
      try {
        if (view && view.event_log) ingest(view);
      } catch (e) {}
      return out;
    }
    wrapped.__engage = true;
    window.__afwipApply = wrapped;
  }

  async function tick() {
    hookApply();
    const id = gameId();
    if (!id) {
      game = null;
      watermark = -1;
      tokens.clear();
      return;
    }
    if (id !== game) {
      game = id;
      watermark = -1;
      tokens.clear();
    }
    if (pulling) return;
    pulling = true;
    try {
      const res = await fetch("/api/games/" + id);
      if (!res.ok) return;
      ingest(await res.json());
    } catch (e) {
    } finally {
      pulling = false;
    }
    const cutoff = performance.now() - 4000;
    recentHit.forEach((at, uid) => {
      if (at < cutoff) recentHit.delete(uid);
    });
  }

  // Keep a settled baseline when the player is interacting; do not overwrite
  // pre-move positions on a tight timer (that raced the slide).
  document.addEventListener("pointerdown", () => {
    if (!dieOpen()) settlePositions();
  }, true);
  setInterval(tick, 280);

  window.__afwipEngage = {
    interpret: interpret, play: play, snapshot: snapshot,
    cyberAt: cyberAt, baseAt: baseAt, missile: missile, cyber: cyber,
    ingest: ingest,
  };
})();
