/* Live tutorial dock. The player is the US side. The bar says why the
   current choice matters, and the first time each idea appears it also
   teaches the rule. Dice are handled by die.js. */
(function () {
  const KEY = "afwip_live";
  let note = null;
  let seen = new Set();
  let gameId = null;
  let fromTutorial = false;
  let lastRev = null;
  let lastSig = null;
  let pacedFor = null;

  const dock = document.createElement("section");
  dock.id = "live-coach";
  dock.hidden = true;
  dock.innerHTML = [
    '<div class="live-top">',
    '  <div class="live-brand">Tutorial</div>',
    '  <div class="live-title" id="live-title"></div>',
    '  <div class="live-spacer"></div>',
    '  <button type="button" id="live-next" class="primary">Got it</button>',
    '  <button type="button" id="live-hide">Hide</button>',
    '</div>',
    '<div class="live-body">',
    '  <div class="live-art" id="live-art"></div>',
    '  <div class="live-copy">',
    '    <p class="live-suggest" id="live-suggest"></p>',
    '    <p class="live-why" id="live-why"></p>',
    '    <p class="live-now" id="live-now"></p>',
    '    <p class="live-lesson" id="live-lesson"></p>',
    '    <p class="live-look" id="live-look"></p>',
    '    <p class="live-just" id="live-just"></p>',
    '    <p class="live-hint" id="live-hint"></p>',
    '  </div>',
    '</div>'
  ].join("");
  document.body.append(dock);

  const art = dock.querySelector("#live-art");
  const title = dock.querySelector("#live-title");
  const suggest = dock.querySelector("#live-suggest");
  // Tutorial: PRC turns auto-advance on a look window. Pause freezes.
  const WATCH_SPEED_KEY = "afwip.live.watchSpeed";
  const WATCH_SPEEDS = { slow: 8000, medium: 5000, fast: 3000 };
  function readWatchSpeed() {
    try {
      const v = localStorage.getItem(WATCH_SPEED_KEY);
      if (v && WATCH_SPEEDS[v]) return v;
    } catch (e) {}
    return "medium";
  }
  function watchStepMs() {
    return WATCH_SPEEDS[readWatchSpeed()] || WATCH_SPEEDS.medium;
  }
  function watchSpeedLabel() {
    const sec = Math.round(watchStepMs() / 1000);
    return sec + " second" + (sec === 1 ? "" : "s");
  }
  let watchPending = false;
  let watchTimer = null;
  let watchTimerRev = null;
  let watchAdvancing = false;
  let watchPaused = false;

  const pauseBtn = document.createElement("button");
  pauseBtn.id = "live-pause";
  pauseBtn.type = "button";
  pauseBtn.hidden = true;
  document.body.append(pauseBtn);
  const speedSel = document.createElement("select");
  speedSel.id = "live-watch-speed";
  speedSel.setAttribute("aria-label", "Watch speed");
  speedSel.hidden = true;
  [["slow", "Slow"], ["medium", "Medium"], ["fast", "Fast"]].forEach(([value, label]) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    speedSel.append(opt);
  });
  speedSel.value = readWatchSpeed();
  document.body.append(speedSel);
  const why = dock.querySelector("#live-why");
  const now = dock.querySelector("#live-now");
  const lesson = dock.querySelector("#live-lesson");
  const look = dock.querySelector("#live-look");
  const just = dock.querySelector("#live-just");
  const hint = dock.querySelector("#live-hint");
  const nextBtn = dock.querySelector("#live-next");

  function wanted() {
    try { return localStorage.getItem(KEY) === "1"; } catch (e) { return false; }
  }
  function setWanted(on) {
    try { localStorage.setItem(KEY, on ? "1" : "0"); } catch (e) {}
  }
  function readGame() {
    const el = document.querySelector(".topbar");
    if (!el) return null;
    const m = el.textContent.match(/game\s+([0-9a-f]+)\s+·\s+rev\s+(\d+)/i);
    return m ? { id: m[1], rev: Number(m[2]) } : null;
  }
  function rolling() {
    return !!document.querySelector(".roll-prompt");
  }
  function dieNote(data) {
    return !!(data && data.suggest && data.suggest.indexOf("Click the die") === 0);
  }
  function quotedPick(text) {
    if (!text || text.indexOf('Pick "') !== 0) return "";
    const end = text.indexOf('". ');
    return end > 6 ? text.slice(6, end) : "";
  }
  function setWatchPaused(on) {
    watchPaused = !!on;
    paintPauseBtn();
    if (watchPaused) clearWatchTimer();
    else scheduleWatchAdvance(true);
  }
  function paintPauseBtn() {
    if (!watchPending) {
      pauseBtn.hidden = true;
      speedSel.hidden = true;
      pauseBtn.textContent = "Pause";
      pauseBtn.title = "";
      pauseBtn.classList.remove("is-paused");
      return;
    }
    pauseBtn.hidden = false;
    speedSel.hidden = false;
    speedSel.value = readWatchSpeed();
    speedSel.title = "Look time between their steps (" + watchSpeedLabel() + ")";
    pauseBtn.classList.toggle("is-paused", watchPaused);
    if (watchPaused) {
      pauseBtn.textContent = "Resume";
      pauseBtn.title = "Resume watching the other side";
    } else {
      pauseBtn.textContent = "Pause";
      pauseBtn.title = "Pause — currently " + watchSpeedLabel() + " between their steps";
    }
  }
  function clearWatchTimer() {
    if (watchTimer != null) {
      window.clearTimeout(watchTimer);
      watchTimer = null;
    }
    watchTimerRev = null;
  }
  function scheduleWatchAdvance(force) {
    if (!watchPending || watchPaused || rolling()) {
      if (!watchPending || watchPaused) clearWatchTimer();
      return;
    }
    if (watchAdvancing) return;
    const game = readGame();
    const rev = game ? game.rev : null;
    // Keep the look window — do not restart it on every coach refresh.
    if (!force && watchTimer != null && watchTimerRev === rev) return;
    clearWatchTimer();
    watchTimerRev = rev;
    watchTimer = window.setTimeout(() => {
      watchTimer = null;
      watchTimerRev = null;
      advanceWatch();
    }, watchStepMs());
  }
  async function advanceWatch() {
    const game = readGame();
    if (!game || typeof window.__afwipApply !== "function") return;
    if (watchAdvancing || watchPaused || rolling()) return;
    watchAdvancing = true;
    clearWatchTimer();
    clearWatchHits();
    try {
      const res = await fetch("/api/games/" + game.id + "/watch", { method: "POST" });
      if (!res.ok) return;
      const view = await res.json();
      window.__afwipApply(view);
      watchPending = !!view.watch_pending;
      paintPauseBtn();
      lastSig = null;
      if (wanted()) await refresh(true);
      else placeChrome();
    } catch (e) {
      return;
    } finally {
      watchAdvancing = false;
    }
    // Schedule after clearing watchAdvancing — otherwise the next step never arms.
    if (watchPending && !watchPaused && !rolling()) scheduleWatchAdvance(true);
  }
  function hintFor(data) {
    if (data.hold === "watch") {
      if (watchPaused) return "Paused — click Resume when you are ready.";
      return "Watching their turn — about " + watchSpeedLabel() + " per step. Pause anytime.";
    }
    if (dieNote(data) || rolling()) return "Click the die.";
    const label = quotedPick(data.suggest || "");
    const buttons = [...document.querySelectorAll(".choice-btn")];
    if (label && buttons.some((b) => (b.textContent || "").trim() === label)) {
      return "Use the suggestion, then click that choice on the right.";
    }
    if (!buttons.length) return "The next choice appears on the right.";
    return "Click one of your choices on the right.";
  }
  let recovering = false;
  async function recoverDie(game) {
    if (!game || recovering) return;
    recovering = true;
    try {
      const res = await fetch("/api/games/" + game.id);
      if (res.status === 404) {
        title.textContent = "This match stopped";
        suggest.textContent = "This game is no longer running.";
        suggest.hidden = false;
        why.textContent = "";
        now.textContent = "";
        lesson.textContent = "The board is the last view of it. Click New game, then Tutorial, to start again.";
        lesson.hidden = false;
        look.textContent = "";
        look.hidden = true;
        just.textContent = "";
        just.hidden = true;
        watchPending = false;
        clearWatchTimer();
        paintPauseBtn();
        nextBtn.hidden = true;
        hint.textContent = "Click New game, then Tutorial.";
        dock.hidden = false;
        document.body.classList.add("afwip-live");
        note = null;
        lastSig = "gone";
        fit();
        return;
      }
      if (!res.ok) return;
      const view = await res.json();
      if (view.roll_pending && typeof window.__afwipApply === "function") {
        window.__afwipApply(view);
        lastSig = null;
      }
    } catch (e) {
      return;
    } finally {
      recovering = false;
    }
  }
  function lessonFirst(data) {
    if (seen.has(data.concept)) return false;
    if (data.concept === "roll" && (seen.has("initiative") || seen.has("cyber") || seen.has("intel") || seen.has("acquire") || seen.has("shoot"))) {
      seen.add("roll");
      saveSeen();
      return false;
    }
    return true;
  }
  function viewSig(game) {
    const prompt = document.querySelector(".prompt");
    const choices = [...document.querySelectorAll(".choice-btn")].map((b) => (b.textContent || "").trim()).join("~");
    return [game.id, game.rev, rolling() ? "roll" : "play", prompt ? prompt.textContent.trim() : "", choices].join("|");
  }
  function loadSeen(id) {
    try {
      return new Set(JSON.parse(sessionStorage.getItem("afwip_seen_" + id) || "[]"));
    } catch (e) { return new Set(); }
  }
  function saveSeen() {
    if (!gameId) return;
    try { sessionStorage.setItem("afwip_seen_" + gameId, JSON.stringify([...seen])); } catch (e) {}
  }
  const cardPreview = document.createElement("div");
  cardPreview.id = "live-card-preview";
  cardPreview.hidden = true;
  const cardPreviewImg = document.createElement("img");
  cardPreview.append(cardPreviewImg);
  document.body.append(cardPreview);

  let pinnedWatchCard = null; // stay over the board while Continue holds an enabler play

  function showCard(src, alt) {
    cardPreviewImg.src = src;
    cardPreviewImg.alt = alt;
    cardPreview.hidden = false;
  }
  function hideCard() {
    cardPreview.hidden = true;
  }
  function restorePinnedCard() {
    if (pinnedWatchCard) showCard(pinnedWatchCard.src, pinnedWatchCard.alt);
    else hideCard();
  }
  function figure(src, alt, zoom) {
    const img = document.createElement("img");
    img.src = src;
    img.alt = alt;
    img.addEventListener("load", fit);
    if (zoom) {
      img.className = "live-card";
      img.addEventListener("mouseenter", () => showCard(src, alt));
      img.addEventListener("mouseleave", restorePinnedCard);
    }
    return img;
  }
  function fit() {
    if (dock.hidden) {
      document.documentElement.style.removeProperty("--live-h");
    } else {
      document.documentElement.style.setProperty("--live-h", dock.offsetHeight + "px");
    }
    placeChrome();
  }
  function syncViewerSide() {
    const badge = document.querySelector(".topbar .side-us, .topbar .side-prc");
    const side = badge && /^(US|PRC)$/.test((badge.textContent || "").trim())
      ? badge.textContent.trim()
      : "US";
    document.body.classList.toggle("afwip-viewer-us", side === "US");
    document.body.classList.toggle("afwip-viewer-prc", side === "PRC");
    const prcCol = document.querySelector(".side-col-prc");
    if (prcCol) {
      document.documentElement.style.setProperty("--prc-col", Math.round(prcCol.getBoundingClientRect().width) + "px");
    }
  }
  function render(data, first) {
    title.textContent = data.title;
    suggest.textContent = data.suggest || "";
    suggest.hidden = !data.suggest;
    watchPending = data.hold === "watch";
    paintPauseBtn();
    why.textContent = data.why || "";
    why.hidden = !why.textContent;
    // Continue holds: yellow suggest + topbar status carry the fact.
    // Keep #live-now off so the dock does not repeat the same sentence.
    now.textContent = "";
    now.hidden = true;
    if (data.hold === "watch") dock.classList.add("live-watch");
    else dock.classList.remove("live-watch");
    syncWatchStatus(data);
    if (watchPending) scheduleWatchAdvance(false);
    else clearWatchTimer();
    lesson.textContent = "";
    lesson.hidden = true;
    look.textContent = "";
    look.hidden = true;
    just.textContent = "";
    just.hidden = true;
    hint.textContent = "";
    hint.hidden = true;
    hideCard();
    pinnedWatchCard = null;
    art.replaceChildren();
    (data.cards || []).slice(0, 2).forEach((id) => {
      art.append(figure("/art/cards/" + id + ".jpg", "Card " + id, true));
    });
    (data.tokens || []).slice(0, 2).forEach((slug) => {
      art.append(figure("/art/tokens/" + slug + ".jpg", slug));
    });
    // PRC (or any AI) enabler/response: pin the card over the board until Continue.
    if (
      data.hold === "watch"
      && (data.concept === "enabler_play" || data.concept === "response")
      && data.cards
      && data.cards[0]
    ) {
      pinnedWatchCard = {
        src: "/art/cards/" + data.cards[0] + ".jpg",
        alt: data.title || "Enabler",
      };
      showCard(pinnedWatchCard.src, pinnedWatchCard.alt);
    }
    nextBtn.hidden = true;
    if (first && data.concept) {
      seen.add(data.concept);
      if (data.concept === "initiative" || data.concept === "cyber" || data.concept === "intel" || data.concept === "acquire" || data.concept === "shoot" || data.concept === "roll") {
        seen.add("roll");
      }
      saveSeen();
    }
    if (dieNote(data) && !rolling()) recoverDie(readGame());
    dock.classList.remove("first");
    fit();
    markPick();
    markWatchHits(data);
    // React may paint new spawn tokens a tick later — re-apply a few times.
    if (data.hold === "watch") {
      [80, 200, 450, 900].forEach((ms) => {
        window.setTimeout(() => markWatchHits(data), ms);
      });
    }
  }

  let trailHold = null; // { from, to, side } while Continue is up
  let trailTimer = null;

  function clearWatchHits() {
    document.querySelectorAll(".live-watch-hit").forEach((el) => {
      el.classList.remove("live-watch-hit");
    });
    clearWatchTrail();
    document.body.classList.remove("afwip-watch-hit");
  }

  function clearWatchTrail() {
    trailHold = null;
    if (trailTimer) {
      window.clearInterval(trailTimer);
      trailTimer = null;
    }
    document.querySelectorAll(".live-watch-trail").forEach((el) => el.remove());
  }

  function trailLayer() {
    // Fixed overlay (not inside React's board SVG) so re-renders cannot wipe it.
    let layer = document.getElementById("live-watch-trail-layer");
    if (layer) return layer;
    layer = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    layer.id = "live-watch-trail-layer";
    layer.setAttribute("aria-hidden", "true");
    document.body.append(layer);
    return layer;
  }

  function fitTrailLayer() {
    const layer = trailLayer();
    const w = window.innerWidth;
    const h = window.innerHeight;
    layer.setAttribute("viewBox", "0 0 " + w + " " + h);
    layer.setAttribute("width", String(w));
    layer.setAttribute("height", String(h));
  }

  function bandScreenCenter(band, side) {
    const rect = boardBandRect(band, side);
    if (!rect) return null;
    const box = rect.getBoundingClientRect();
    if (box.width < 2 && box.height < 2) return null;
    return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
  }

  function drawWatchTrail(fromBand, toBand, side) {
    if (!fromBand || !toBand || fromBand === toBand) return;
    fitTrailLayer();
    const layer = trailLayer();
    const from = bandScreenCenter(fromBand, side);
    const to = bandScreenCenter(toBand, side);
    if (!from || !to) return;
    layer.replaceChildren();
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "live-watch-trail");
    g.setAttribute("pointer-events", "none");
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
    marker.setAttribute("id", "live-watch-trail-head");
    marker.setAttribute("viewBox", "0 0 10 10");
    marker.setAttribute("refX", "9");
    marker.setAttribute("refY", "5");
    marker.setAttribute("markerWidth", "8");
    marker.setAttribute("markerHeight", "8");
    marker.setAttribute("orient", "auto");
    const tip = document.createElementNS("http://www.w3.org/2000/svg", "path");
    tip.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
    tip.setAttribute("class", "live-watch-trail-head");
    marker.appendChild(tip);
    defs.appendChild(marker);
    g.appendChild(defs);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(from.x));
    line.setAttribute("y1", String(from.y));
    line.setAttribute("x2", String(to.x));
    line.setAttribute("y2", String(to.y));
    line.setAttribute("class", "live-watch-trail-line");
    line.setAttribute("marker-end", "url(#live-watch-trail-head)");
    g.appendChild(line);
    const origin = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    origin.setAttribute("cx", String(from.x));
    origin.setAttribute("cy", String(from.y));
    origin.setAttribute("r", "8");
    origin.setAttribute("class", "live-watch-trail-origin");
    g.appendChild(origin);
    layer.appendChild(g);
  }

  function holdWatchTrail(fromBand, toBand, side) {
    trailHold = { from: fromBand, to: toBand, side: side };
    drawWatchTrail(fromBand, toBand, side);
    if (trailTimer) window.clearInterval(trailTimer);
    // Keep redrawing: React board paints and window resizes move band rects.
    trailTimer = window.setInterval(() => {
      if (!trailHold) return;
      drawWatchTrail(trailHold.from, trailHold.to, trailHold.side);
    }, 250);
  }

  function sideRoot(side) {
    if (side === "PRC") {
      return document.querySelector(".side-col-prc") || document.querySelector(".side-col");
    }
    if (side === "US") {
      return document.querySelector(".right-col");
    }
    return null;
  }

  function viewerSide() {
    return document.body.classList.contains("afwip-viewer-prc") ? "PRC" : "US";
  }

  function watchSideFromData(data) {
    // Banner text is what the student reads — trust it over a stale/wrong field.
    const sug = (data.suggest || "").replace(/\s+/g, " ").trim();
    const named = sug.match(/^(US|PRC)\b/);
    if (named) return named[1];
    if (data.watch_side === "US" || data.watch_side === "PRC") return data.watch_side;
    if (/\bYour aircraft\b/i.test(sug) || /\bYou /i.test(sug.slice(0, 24))) {
      return viewerSide();
    }
    return viewerSide();
  }

  function boardTokenEl(uid) {
    const svg = document.querySelector(".board-svg");
    if (!svg || uid == null) return null;
    const title = [...svg.querySelectorAll("title")].find((node) => {
      const match = (node.textContent || "").match(/#(\d+)/);
      return match && match[1] === String(uid);
    });
    return title && title.parentElement ? title.parentElement : null;
  }

  function boardTokensByTitle(regex) {
    const svg = document.querySelector(".board-svg");
    if (!svg || !regex) return [];
    return [...svg.querySelectorAll("title")]
      .filter((node) => regex.test(node.textContent || ""))
      .map((node) => node.parentElement)
      .filter(Boolean);
  }

  function boardWinchesterEls(side) {
    return boardTokensByTitle(/Winchester/i).filter((el) => {
      if (!side) return true;
      const text = (el.querySelector("title") && el.querySelector("title").textContent) || "";
      return text.indexOf("(" + side + ")") !== -1;
    });
  }

  function largestRect(root) {
    if (!root) return null;
    const rects = [...root.querySelectorAll("rect")];
    rects.sort((a, b) => {
      const aa = parseFloat(a.getAttribute("width") || 0) * parseFloat(a.getAttribute("height") || 0);
      const bb = parseFloat(b.getAttribute("width") || 0) * parseFloat(b.getAttribute("height") || 0);
      return bb - aa;
    });
    return rects[0] || null;
  }

  function boardBandRect(band, side) {
    const svg = document.querySelector(".board-svg");
    if (!svg || !band) return null;
    const labels = {
      US_STANDOFF: "STAND OFF",
      PRC_STANDOFF: "STAND OFF",
      US_AIRBASE: "US AIRBASE",
      PRC_AIRBASE: "PRC AIRBASE",
      US_CONTINGENCY_LOCATION: "CONTINGENCY LOC.",
    };
    const name = labels[band];
    if (name) {
      let texts = [...svg.querySelectorAll("text")].filter(
        (t) => (t.textContent || "").trim() === name
      );
      if (band.endsWith("STANDOFF") && texts.length > 1) {
        texts.sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
        texts = [band.startsWith("US") ? texts[texts.length - 1] : texts[0]];
      }
      return largestRect(texts[0] && texts[0].parentElement);
    }
    // Center bands: US numerals 1..5 are upright at the top (Band A = blue 1).
    // PRC numerals are rotate(180) at the bottom and inverted (same column's
    // PRC "1" is US Band E). Match the acting side's numeral, not the first "1".
    const m = /^BAND_([A-E])$/.exec(band);
    if (m) {
      const usNum = m[1].charCodeAt(0) - 64;
      const forPrc = side === "PRC";
      const want = String(forPrc ? 6 - usNum : usNum);
      const candidates = [...svg.querySelectorAll("text")].filter(
        (t) => (t.textContent || "").trim() === want
      );
      const label = candidates.find((t) => {
        const rotated = /rotate\s*\(\s*180/i.test(t.getAttribute("transform") || "");
        return forPrc ? rotated : !rotated;
      }) || candidates[0];
      return largestRect(label && label.parentElement);
    }
    return null;
  }

  function slugTitleRegex(slug) {
    if (!slug) return null;
    const core = String(slug).replace(/-(us|prc)$/i, "").replace(/-/g, "[-\\s]?");
    try {
      return new RegExp(core, "i");
    } catch (e) {
      return null;
    }
  }

  function markWatchHits(data) {
    clearWatchHits();
    if (!data || data.hold !== "watch") return;
    // Batch skips (whole draft / all intel peeks) — no single thing to point at.
    if (/skip ahead|every peek|intel cards now|finish their draft|chosen everything|picking enabler|picking and placing squadron|choosing a posture|initiative bid/i.test(data.suggest || "")) {
      return;
    }
    document.body.classList.add("afwip-watch-hit");
    const side = watchSideFromData(data);
    const root = sideRoot(side);
    const cards = data.cards || [];
    const tokens = data.tokens || [];
    const labels = data.watch_labels || [];
    const bands = data.watch_bands || [];
    const uids = data.watch_uids || [];
    let hits = 0;

    function hit(el) {
      if (!el || el.classList.contains("live-watch-hit")) return;
      // Never blink the coach art strip — students need the board piece.
      if (el.closest && (el.closest("#live-coach") || el.closest("#live-art"))) return;
      el.classList.add("live-watch-hit");
      // Board counters: outer <g> wraps an inner face/fog <g> that holds the body rect.
      // title is a sibling of that inner g — so ":scope > rect" misses the tile.
      if (el.closest && el.closest(".board-svg") && el.tagName === "g") {
        let body = el.querySelector(":scope > g > rect");
        if (!body) {
          const rects = [...el.querySelectorAll("rect")];
          body = rects.sort((a, b) => {
            const aa = parseFloat(a.getAttribute("width") || 0) * parseFloat(a.getAttribute("height") || 0);
            const bb = parseFloat(b.getAttribute("width") || 0) * parseFloat(b.getAttribute("height") || 0);
            return bb - aa;
          })[0];
        }
        if (body) body.classList.add("live-watch-hit", "live-watch-hit-body");
      }
      hits += 1;
    }

    function imgsIn(scope, sel) {
      return [...(scope || document).querySelectorAll(sel)].filter((img) => {
        return !(img.closest && (img.closest("#live-coach") || img.closest("#live-art")));
      });
    }

    // Board counters first (spawn / Winchester / kill) — SVG groups, not banner imgs.
    uids.forEach((uid) => hit(boardTokenEl(uid)));
    tokens.forEach((slug) => {
      const re = slugTitleRegex(slug);
      if (re) boardTokensByTitle(re).forEach((el) => hit(el));
    });
    labels.forEach((lab) => {
      if (!lab || lab === "(hidden)" || lab === "(Hidden)") return;
      // "US_STANDOFF" is a band, not a token name.
      if (/^(US|PRC)_/.test(lab) || /^BAND_/.test(lab)) return;
      try {
        boardTokensByTitle(new RegExp(lab.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i")).forEach((el) => hit(el));
      } catch (e) { /* ignore */ }
    });
    if (!hits && (/Winchester/i.test(data.suggest || "") || data.concept === "winchester")) {
      boardWinchesterEls(side).forEach((el) => hit(el));
    }

    bands.forEach((band) => {
      const rect = boardBandRect(band, side);
      if (rect) hit(rect);
      document.querySelectorAll(".board-svg rect.home-pick, .board-svg rect.home-pick-hot").forEach((r) => {
        const cls = r.getAttribute("class") || "";
        if (band.indexOf("AIRBASE") !== -1 && cls.indexOf("home-pick") !== -1) hit(r);
      });
    });

    const trail = data.watch_trail || [];
    if (trail.length >= 2 && data.hold === "watch") {
      holdWatchTrail(trail[0], trail[1], side);
    }

    cards.forEach((id) => {
      const sel = 'img[src*="/art/cards/' + id + '.jpg"]';
      const scoped = root ? imgsIn(root, sel) : [];
      (scoped.length ? scoped : imgsIn(document, sel)).forEach((img) => {
        hit(img.closest(".card-cell") || img.closest(".card-thumb") || img);
      });
    });

    tokens.forEach((slug) => {
      const sel = 'img[src*="/art/tokens/' + slug + '.jpg"]';
      imgsIn(document, sel).forEach((img) => {
        hit(img.closest(".trophy") || img.closest(".token-pop") || img);
      });
    });

    // Nothing on the board → pulse that side's column (never the banner art).
    if (!hits && root) hit(root);
  }

  let scrolledPick = "";
  function suggestedLabel() {
    if (dock.hidden) return "";
    const text = suggest.textContent || "";
    if (!text.startsWith('Pick "')) return "";
    const end = text.indexOf('". ');
    return end > 6 ? text.slice(6, end) : "";
  }
  function markPick() {
    const label = suggestedLabel();
    const buttons = [...document.querySelectorAll(".choice-btn")];
    const match = label
      ? buttons.find((b) => (b.textContent || "").trim() === label)
      : null;
    buttons.forEach((b) => {
      const on = b === match;
      if (b.classList.contains("live-pick") !== on) b.classList.toggle("live-pick", on);
      const lock = !!(match && !on);
      if (b.disabled !== lock) b.disabled = lock;
      if (b.classList.contains("live-lock") !== lock) b.classList.toggle("live-lock", lock);
    });
    if (!match) {
      scrolledPick = "";
      return;
    }
    if (label === scrolledPick) return;
    scrolledPick = label;
    const scroller = match.closest(".choices-scroll");
    if (!scroller) return;
    const top = match.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
    scroller.scrollTop = Math.max(0, top - 16);
  }

  let pauseSyncing = false;
  async function syncPauseBtn() {
    // Keep Pause visible with watch_pending even when the coach dock is hidden.
    const game = readGame();
    if (!game || !fromTutorial) {
      watchPending = false;
      clearWatchTimer();
      paintPauseBtn();
      return;
    }
    if (pauseSyncing) return;
    pauseSyncing = true;
    try {
      const res = await fetch("/api/games/" + game.id);
      if (!res.ok) return;
      const view = await res.json();
      watchPending = !!view.watch_pending;
      paintPauseBtn();
      if (watchPending) scheduleWatchAdvance(false);
      else clearWatchTimer();
    } catch (e) {
      return;
    } finally {
      pauseSyncing = false;
      placeChrome();
    }
  }

  async function refresh(force) {
    if (!wanted()) {
      dock.hidden = true;
      document.body.classList.remove("afwip-live");
      clearWatchHits();
      hideCard();
      syncWatchStatus(null);
      watchPending = false;
      clearWatchTimer();
      paintPauseBtn();
      fit();
      await syncPauseBtn();
      return;
    }
    const game = readGame();
    if (!game) {
      dock.hidden = true;
      document.body.classList.remove("afwip-live");
      hideCard();
      syncWatchStatus(null);
      watchPending = false;
      clearWatchTimer();
      paintPauseBtn();
      fit();
      return;
    }
    if (game.id !== gameId) {
      gameId = game.id;
      seen = loadSeen(gameId);
      lastRev = null;
      lastSig = null;
      note = null;
      pacedFor = null;
    }
    if (pacedFor !== game.id) {
      try {
        const paced = await fetch("/api/games/" + game.id + "/pace", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ on: true }),
        });
        if (paced.ok) pacedFor = game.id;
      } catch (e) { /* the next refresh tries again */ }
    }
    const roll = rolling();
    const sig = viewSig(game);
    if (!force && sig === lastSig) {
      if (dieNote(note) && !roll) recoverDie(game);
      return;
    }
    let data;
    try {
      const res = await fetch("/api/games/" + game.id + "/coach");
      if (!res.ok) return;
      data = await res.json();
    } catch (e) { return; }
    if (note && data.concept !== note.concept) {
      seen.add(note.concept);
      if (note.concept === "initiative" || note.concept === "cyber" || note.concept === "intel" || note.concept === "acquire" || note.concept === "shoot" || note.concept === "roll") {
        seen.add("roll");
      }
      saveSeen();
    }
    if (!force && !roll && note && note.concept === data.concept && note.suggest === data.suggest && note.now === data.now) {
      lastSig = sig;
      if (dieNote(data)) recoverDie(game);
      else hint.textContent = hintFor(data);
      return;
    }
    lastRev = data.revision;
    lastSig = sig;
    note = data;
    const first = lessonFirst(data);
    dock.hidden = false;
    document.body.classList.add("afwip-live");
    render(data, first);
  }

  // While their turn is paced, ignore choice clicks so a queued/stale click cannot
  // submit Pass / end turn underneath the hold.
  document.addEventListener("click", (ev) => {
    if (!watchPending) return;
    const btn = ev.target && ev.target.closest && ev.target.closest(".choice-btn");
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    ev.stopImmediatePropagation();
  }, true);

  pauseBtn.addEventListener("click", () => {
    setWatchPaused(!watchPaused);
    placeChrome();
  });
  speedSel.addEventListener("change", () => {
    const next = speedSel.value;
    if (!WATCH_SPEEDS[next]) return;
    try { localStorage.setItem(WATCH_SPEED_KEY, next); } catch (e) {}
    paintPauseBtn();
    if (watchPending && !watchPaused) scheduleWatchAdvance(true);
    placeChrome();
    if (wanted() && note && note.hold === "watch") {
      hint.textContent = hintFor(note);
    }
  });
  nextBtn.addEventListener("click", () => {
    if (!note) return;
    seen.add(note.concept);
    saveSeen();
    render(note, false);
  });
  dock.querySelector("#live-hide").addEventListener("click", () => {
    setWanted(false);
    dock.hidden = true;
    document.body.classList.remove("afwip-live");
    hideCard();
    syncWatchStatus(null);
    clearWatchTimer();
    fit();
    markPick();
  });

  const offer = document.createElement("button");
  offer.id = "live-offer";
  offer.type = "button";
  offer.textContent = "Unhide tutorial";
  offer.hidden = true;
  offer.addEventListener("click", () => {
    setWanted(true);
    offer.hidden = true;
    refresh(true);
  });
  document.body.append(offer);

  const manual = document.createElement("button");
  manual.id = "game-manual";
  manual.type = "button";
  manual.textContent = "Game Manual";
  manual.hidden = true;
  const sheet = document.createElement("div");
  sheet.id = "manual-sheet";
  sheet.hidden = true;
  sheet.innerHTML = '<iframe title="Game Manual" src="about:blank"></iframe>';
  const frame = sheet.querySelector("iframe");
  let manualLoaded = false;
  function openManual() {
    if (!manualLoaded) {
      frame.src = "/tutorial.html?embed=1&v=search";
      manualLoaded = true;
    }
    sheet.hidden = false;
  }
  function closeManual() {
    sheet.hidden = true;
  }
  manual.addEventListener("click", openManual);
  sheet.addEventListener("click", (event) => {
    if (event.target === sheet) closeManual();
  });
  window.addEventListener("message", (event) => {
    if (event.origin !== location.origin) return;
    if (event.data && event.data.type === "afwip-manual-close") closeManual();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeManual();
  });
  document.body.append(manual, sheet);

  const drafts = document.createElement("button");
  drafts.id = "example-drafts";
  drafts.type = "button";
  drafts.textContent = "Example drafts";
  drafts.title = "Standard posture: cyber, base strike, and air control";
  drafts.hidden = true;
  drafts.addEventListener("click", () => {
    if (window.__afwipExampleDrafts) window.__afwipExampleDrafts();
  });
  document.body.append(drafts);

  const back = document.createElement("button");
  back.id = "game-back";
  back.type = "button";
  back.textContent = "Undo";
  back.title = "Undo the last card";
  back.hidden = true;
  back.addEventListener("click", async () => {
    const game = readGame();
    if (!game || typeof window.__afwipApply !== "function") return;
    back.disabled = true;
    try {
      const res = await fetch("/api/games/" + game.id + "/undo", { method: "POST" });
      if (!res.ok) return;
      window.__afwipApply(await res.json());
    } catch (e) {
      return;
    } finally {
      back.disabled = false;
    }
  });
  document.body.append(back);

  // Mirror the choice-panel prompt into the topbar (left of Undo) so the sticky
  // header no longer covers the selection list while scrolling.
  const gamePrompt = document.createElement("div");
  gamePrompt.id = "game-prompt";
  gamePrompt.hidden = true;
  document.body.append(gamePrompt);

  const watchStatus = document.createElement("div");
  watchStatus.id = "game-watch-status";
  watchStatus.hidden = true;
  document.body.append(watchStatus);

  function syncWatchStatus(data) {
    if (!data || data.hold !== "watch" || !data.now) {
      watchStatus.hidden = true;
      watchStatus.textContent = "";
      watchStatus.className = "";
      document.body.classList.remove("afwip-watch-status");
      return;
    }
    const side = (data.watch_side || "").toUpperCase();
    watchStatus.className = side === "US" || side === "PRC" ? "side-" + side.toLowerCase() : "";
    let text = data.now;
    const left = data.watch_continues_remaining;
    if (
      typeof left === "number"
      && left > 0
      && text.indexOf("left") < 0
      && text.indexOf("until you can act again") < 0
      && text.indexOf("until your turn") < 0
    ) {
      text += " · " + left + (left === 1 ? " step" : " steps") + " left";
    }
    watchStatus.textContent = text;
    watchStatus.title = text;
    watchStatus.hidden = false;
    document.body.classList.add("afwip-watch-status");
  }

  const detailsBtn = document.createElement("button");
  detailsBtn.id = "game-details";
  detailsBtn.type = "button";
  detailsBtn.textContent = "Game Details";
  detailsBtn.title = "Campaign, ATO, VP, cyber, mission, and posture";
  detailsBtn.hidden = true;
  detailsBtn.setAttribute("aria-expanded", "false");
  document.body.append(detailsBtn);

  const detailsPanel = document.createElement("div");
  detailsPanel.id = "game-details-panel";
  detailsPanel.hidden = true;
  detailsPanel.innerHTML = [
    '<div class="game-details-head">',
    '  <h2>Game Details</h2>',
    '  <button type="button" id="game-details-close" aria-label="Close">Close</button>',
    '</div>',
    '<div class="game-details-body" id="game-details-body"></div>',
  ].join("");
  document.body.append(detailsPanel);
  const detailsBody = detailsPanel.querySelector("#game-details-body");
  const detailsClose = detailsPanel.querySelector("#game-details-close");

  function syncGamePrompt() {
    const src = document.querySelector(".choices-scroll > .prompt");
    if (!src) {
      gamePrompt.hidden = true;
      gamePrompt.replaceChildren();
      gamePrompt.dataset.sig = "";
      return;
    }
    const sig = src.innerHTML;
    if (gamePrompt.dataset.sig !== sig) {
      gamePrompt.innerHTML = sig;
      gamePrompt.dataset.sig = sig;
    }
    gamePrompt.hidden = false;
  }

  function syncGameDetails() {
    const src = document.querySelector(".left-col .status-strip, .status-strip");
    if (!src) {
      detailsBody.replaceChildren();
      detailsBody.dataset.sig = "";
      return;
    }
    const sig = src.innerHTML;
    if (detailsBody.dataset.sig !== sig) {
      const clone = src.cloneNode(true);
      clone.classList.add("status-strip");
      detailsBody.replaceChildren(clone);
      detailsBody.dataset.sig = sig;
    }
  }

  function placeDetailsPanel() {
    if (detailsPanel.hidden || detailsBtn.hidden) return;
    const r = detailsBtn.getBoundingClientRect();
    const width = Math.min(520, Math.max(280, window.innerWidth - 24));
    let left = r.left;
    if (left + width > window.innerWidth - 12) left = window.innerWidth - width - 12;
    if (left < 12) left = 12;
    detailsPanel.style.left = Math.round(left) + "px";
    detailsPanel.style.top = Math.round(r.bottom + 8) + "px";
    detailsPanel.style.width = Math.round(width) + "px";
  }

  function setDetailsOpen(open) {
    detailsPanel.hidden = !open;
    detailsBtn.setAttribute("aria-expanded", open ? "true" : "false");
    detailsBtn.classList.toggle("is-open", open);
    if (open) {
      syncGameDetails();
      placeDetailsPanel();
    }
  }

  detailsBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    setDetailsOpen(detailsPanel.hidden);
  });
  detailsClose.addEventListener("click", (event) => {
    event.stopPropagation();
    setDetailsOpen(false);
  });
  document.addEventListener("click", (event) => {
    if (detailsPanel.hidden) return;
    if (detailsPanel.contains(event.target) || detailsBtn.contains(event.target)) return;
    setDetailsOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setDetailsOpen(false);
  });

  function newGameButton() {
    return [...document.querySelectorAll(".topbar button")].find(
      (b) => (b.textContent || "").trim() === "New game"
    );
  }
  function clearPin(el) {
    el.style.top = "";
    el.style.left = "";
    el.style.right = "";
    el.style.bottom = "";
    el.style.height = "";
    el.style.position = "";
  }
  function placeChrome() {
    const btn = newGameButton();
    if (!btn) {
      manual.hidden = true;
      drafts.hidden = true;
      back.hidden = true;
      gamePrompt.hidden = true;
      watchStatus.hidden = true;
      detailsBtn.hidden = true;
      setDetailsOpen(false);
      watchPending = false;
      clearWatchTimer();
      paintPauseBtn();
      document.body.classList.remove("afwip-manual", "afwip-unhide", "afwip-watch-status");
      return;
    }
    const bar = btn.closest(".topbar") || btn.parentElement;
    manual.hidden = false;
    drafts.hidden = false;
    back.hidden = false;
    detailsBtn.hidden = false;
    syncGamePrompt();
    syncGameDetails();
    const row = [];
    if (!pauseBtn.hidden) row.push(pauseBtn);
    if (!speedSel.hidden) row.push(speedSel);
    if (!watchStatus.hidden) row.push(watchStatus);
    if (!offer.hidden) {
      row.push(offer);
      document.body.classList.add("afwip-unhide");
    } else {
      document.body.classList.remove("afwip-unhide");
    }
    if (!gamePrompt.hidden) row.push(gamePrompt);
    row.push(detailsBtn, back, drafts, manual);
    // Sit in the topbar beside New game so scrolling the board cannot drag them.
    row.forEach((el) => {
      clearPin(el);
      if (el.parentElement !== bar || el.nextSibling !== btn) bar.insertBefore(el, btn);
    });
    document.body.classList.add("afwip-manual");
    document.documentElement.style.setProperty("--manual-w", "0px");
    placeDetailsPanel();
  }
  window.addEventListener("resize", () => {
    placeChrome();
    placeDetailsPanel();
  });

  function leaveTutorial() {
    fromTutorial = false;
    setWanted(false);
    dock.hidden = true;
    watchPending = false;
    clearWatchTimer();
    paintPauseBtn();
    document.body.classList.remove("afwip-live");
    hideCard();
    syncWatchStatus(null);
    fit();
    markPick();
  }
  function otherGame(btn) {
    const label = (btn.textContent || "").replace(/\s+/g, " ").trim();
    if (btn.classList.contains("start")) return true;
    if (label === "Join Game" || label === "New game") return true;
    return label.indexOf("Tournament Play") === 0;
  }

  setInterval(() => {
    if (!fromTutorial && wanted()) leaveTutorial();
    const game = readGame();
    offer.hidden = !(game && fromTutorial && !wanted());
    placeChrome();
    syncViewerSide();
    if (wanted()) refresh(false);
    else if (fromTutorial && game && watchPending) syncPauseBtn();
    markPick();
  }, 400);

  const board = document.getElementById("root");
  if (board) {
    new MutationObserver(() => markPick()).observe(board, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
  }

  document.addEventListener("click", (event) => {
    const choice = event.target.closest && event.target.closest(".choice-btn");
    if (!choice) return;
    const label = suggestedLabel();
    if (!label) return;
    const buttons = [...document.querySelectorAll(".choice-btn")];
    const match = buttons.find((b) => (b.textContent || "").trim() === label);
    if (!match || choice === match) return;
    event.preventDefault();
    event.stopPropagation();
  }, true);

  document.addEventListener("click", (event) => {
    const btn = event.target.closest && event.target.closest("button");
    if (!btn) return;
    const label = (btn.textContent || "").replace(/\s+/g, " ").trim();
    if (btn.classList.contains("live-card") || label === "Tutorial") {
      fromTutorial = true;
      setWanted(true);
      return;
    }
    if (otherGame(btn)) leaveTutorial();
  }, true);
})();
