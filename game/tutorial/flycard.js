/* When a card is played or a squadron is shot down, flash its art over the
   board and glide it into the spent pile, shot-down pile, or home airbase. */
(function () {
  window.__afwipCardFlyActive = true;

  const fly = document.createElement("div");
  fly.id = "card-fly";
  fly.hidden = true;
  const kicker = document.createElement("p");
  kicker.className = "card-fly-kicker";
  kicker.hidden = true;
  const img = document.createElement("img");
  img.alt = "";
  fly.appendChild(kicker);
  fly.appendChild(img);
  document.body.appendChild(fly);

  let game = null;
  let watermark = null;
  let busy = false;
  let queue = [];
  let pending = null;
  let pulling = false;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function gameId() {
    const el = document.querySelector(".topbar");
    if (!el) return null;
    const match = el.textContent.match(/game\s+([0-9a-f]+)/i);
    return match ? match[1] : null;
  }

  function dieBusy() {
    const die = document.getElementById("die-overlay");
    if (die && !die.hidden) return true;
    return !!document.querySelector(".roll-prompt");
  }

  function cardIdFromSrc(src) {
    const match = (src || "").match(/\/art\/cards\/(\d+)\./);
    return match ? Number(match[1]) : null;
  }

  function artUrl(cardId) {
    return cardId == null ? "" : "/art/cards/" + cardId + ".jpg";
  }

  function sideRoot(side) {
    // Use the full side column — NOT .roster-stack. That stack is only the
    // shot-down / capture panels; US spent lives under the Hand panel, so
    // aiming at roster-stack made enablers fly into Shot down.
    if (side === "PRC") {
      return document.querySelector(".side-col-prc")
        || document.querySelector(".side-col");
    }
    return document.querySelector(".right-col");
  }

  function panelByHeading(root, re) {
    if (!root) return null;
    return [...root.querySelectorAll(".panel")].find((panel) => {
      const h = panel.querySelector("h2");
      return h && re.test(h.textContent || "");
    }) || null;
  }

  function rectOf(el) {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (r.width < 2 && r.height < 2) return null;
    return r;
  }

  function spentRect(side) {
    const root = sideRoot(side);
    if (!root) return null;
    const spent = root.querySelector(".spent-block");
    if (spent) {
      const cells = spent.querySelectorAll(".card-cell.spent");
      return rectOf(cells[cells.length - 1] || spent.querySelector(".card-row") || spent);
    }
    // First spent card: Spent block is not mounted yet — aim at the Hand panel.
    const hand = panelByHeading(root, /hand|enabler/i);
    if (hand) {
      const row = hand.querySelector(".card-row");
      return rectOf(row || hand);
    }
    return null;
  }

  function shotDownRect(side) {
    const root = sideRoot(side);
    if (!root) return null;
    // Prefer the capture/trophy panel; fall back to a roster-stack inside the column.
    const panel = panelByHeading(root, /shot down|captures|troph/i)
      || root.querySelector(".roster-stack .panel")
      || root.querySelector(".roster-stack");
    if (!panel) return null;
    const trophies = panel.querySelectorAll(".trophy");
    return rectOf(trophies[trophies.length - 1] || panel.querySelector(".trophy-row") || panel);
  }

  function squadronRect(side, cardId) {
    const root = sideRoot(side);
    const panel = panelByHeading(root, /squadron/i);
    if (!panel) return rectOf(root);
    if (cardId != null) {
      const hit = [...panel.querySelectorAll("img")].find((node) => {
        return cardIdFromSrc(node.getAttribute("src") || "") === cardId;
      });
      if (hit) return rectOf(hit.closest(".card-cell") || hit);
    }
    const cells = panel.querySelectorAll(".card-cell");
    return rectOf(cells[cells.length - 1] || panel.querySelector(".card-row") || panel);
  }

  function boardHomeRect(side) {
    const svg = document.querySelector(".board-svg");
    if (!svg) return boardCenterRect();
    const label = side === "PRC" ? "PRC AIRBASE" : "US AIRBASE";
    const text = [...svg.querySelectorAll("text")].find((node) => {
      return (node.textContent || "").trim() === label;
    });
    if (text) return rectOf(text);
    const hot = svg.querySelector(side === "PRC" ? "rect.home-pick-prc" : "rect.home-pick");
    return rectOf(hot) || boardCenterRect();
  }

  function boardCenterRect(reveal) {
    // reveal=true: large middle-of-board hold so enabler plays read as "this
    // card just hit the table" — not the usual corner hover preview.
    const board = document.querySelector(".board-wrap") || document.querySelector(".board-panel");
    const r = rectOf(board);
    if (!r) {
      const w = reveal ? 280 : 180;
      const h = w * 1.35;
      return {
        left: window.innerWidth / 2 - w / 2,
        top: window.innerHeight / 2 - h / 2,
        width: w,
        height: h,
      };
    }
    const w = reveal
      ? Math.min(320, Math.max(220, r.width * 0.34))
      : Math.min(200, Math.max(140, r.width * 0.22));
    const h = w * 1.35;
    return {
      left: r.left + (r.width - w) / 2,
      top: r.top + (r.height - h) / 2,
      width: w,
      height: h,
    };
  }

  function previewRect() {
    const node = document.querySelector(".choice-card-preview img")
      || document.querySelector("#live-card-preview img");
    return rectOf(node);
  }

  function targetRect(move) {
    if (move.dest === "spent") return spentRect(move.side) || boardCenterRect();
    if (move.dest === "shotdown") return shotDownRect(move.side) || boardCenterRect();
    if (move.dest === "squadron") return squadronRect(move.side, move.cardId) || boardHomeRect(move.side);
    return boardHomeRect(move.side);
  }

  function place(rect, width, height) {
    fly.style.left = Math.round(rect.left + (rect.width - width) / 2) + "px";
    fly.style.top = Math.round(rect.top + (rect.height - height) / 2) + "px";
    fly.style.width = Math.round(width) + "px";
    fly.style.height = Math.round(height) + "px";
  }

  function wait(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function waitFrames(n) {
    return new Promise((resolve) => {
      let left = n;
      function tick() {
        left -= 1;
        if (left <= 0) resolve();
        else requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });
  }

  async function animate(move) {
    const src = move.src || artUrl(move.cardId);
    if (!src) return;
    const enablerPlay = move.dest === "spent";
    document.body.classList.add("afwip-card-fly");
    if (enablerPlay) document.body.classList.add("afwip-enabler-reveal");
    img.src = src;
    img.alt = (move.name || "Enabler") + " card";
    fly.classList.toggle("is-prc", move.side === "PRC");
    fly.classList.toggle("is-us", move.side === "US");
    if (enablerPlay) {
      kicker.hidden = false;
      kicker.textContent = (move.side || "") + (move.side ? " " : "") + "plays enabler";
    } else {
      kicker.hidden = true;
      kicker.textContent = "";
    }
    // Enablers always open in the board center so PRC/US plays read clearly.
    const start = enablerPlay ? boardCenterRect(true) : (previewRect() || boardCenterRect(false));
    const holdW = enablerPlay
      ? Math.max(220, start.width || 260)
      : Math.max(160, start.width || 180);
    const holdH = enablerPlay
      ? Math.max(300, start.height || holdW * 1.35)
      : Math.max(210, start.height || holdW * 1.35);
    fly.hidden = false;
    fly.classList.remove("settle", "show");
    fly.style.transition = "none";
    place(start, holdW, holdH);
    await waitFrames(2);
    fly.classList.add("show");
    if (reduce) {
      await wait(enablerPlay ? 700 : 280);
      fly.classList.add("settle");
      await wait(160);
      fly.hidden = true;
      fly.classList.remove("show", "settle", "is-prc", "is-us");
      kicker.hidden = true;
      document.body.classList.remove("afwip-card-fly", "afwip-enabler-reveal");
      return;
    }
    // Hold the reveal long enough to read the card before it flies to spent.
    await wait(enablerPlay ? 1400 : 420);
    // Let React finish painting the destination pile before we aim at it.
    await waitFrames(3);
    const end = targetRect(move);
    const endW = Math.max(36, Math.min(72, end.width || 48));
    const endH = Math.max(48, Math.min(96, end.height || endW * 1.35));
    fly.style.transition = "";
    kicker.hidden = true;
    place(end, endW, endH);
    await wait(680);
    fly.classList.add("settle");
    await wait(180);
    fly.hidden = true;
    fly.classList.remove("show", "settle", "is-prc", "is-us");
    kicker.hidden = true;
    document.body.classList.remove("afwip-card-fly", "afwip-enabler-reveal");
  }

  async function drain() {
    if (busy) return;
    busy = true;
    try {
      while (queue.length) {
        if (dieBusy()) {
          await wait(200);
          continue;
        }
        const move = queue.shift();
        await animate(move);
      }
    } finally {
      busy = false;
    }
  }

  function enqueue(move) {
    if (!move || (!move.cardId && !move.src)) return;
    const key = move.step + ":" + move.dest + ":" + (move.cardId || move.src);
    if (queue.some((item) => item.key === key)) return;
    move.key = key;
    queue.push(move);
    drain();
  }

  function resolveCardId(play, view) {
    if (play.cardId) return play.cardId;
    if (pending && pending.cardId && Date.now() - pending.at < 8000) return pending.cardId;
    if (play.name && view && view.hands) {
      for (let i = 0; i < view.hands.length; i++) {
        const hand = view.hands[i];
        const cards = (hand.spent || []).concat(hand.cards || []);
        const hit = cards.find((card) => card.name === play.name);
        if (hit) return hit.card_id;
      }
    }
    if (pending && pending.src && Date.now() - pending.at < 8000) {
      return cardIdFromSrc(pending.src);
    }
    return null;
  }

  function asPlay(ev) {
    if (!ev || ev.type !== "decision") return null;
    const data = ev.data || {};
    const msg = ev.message || "";
    const played = msg.match(/Play enabler:\s*(.+)$/i);
    const respond = msg.match(/respond:\s*(.+)$/i);
    if (data.kind === "play_enabler" || played || respond) {
      return {
        step: ev.step,
        dest: "spent",
        side: ev.side || "US",
        cardId: data.card_id || null,
        name: ((played || respond || ["", ""])[1] || "").trim(),
      };
    }
    // No fly-to-airbase on activate — board motion is token slides only.
    return null;
  }

  function asShotDown(ev) {
    if (!ev || ev.type !== "squadron_destroyed") return null;
    const cardId = ev.data && ev.data.card_id;
    if (cardId == null) return null;
    const victim = ev.side || "US";
    return {
      step: ev.step,
      dest: "shotdown",
      side: victim === "PRC" ? "US" : "PRC",
      cardId: cardId,
      name: "",
    };
  }

  function collect(view) {
    const events = view.event_log || [];
    const maxStep = events.reduce((max, ev) => Math.max(max, ev.step || 0), 0);
    if (watermark == null) {
      watermark = maxStep;
      return;
    }
    events.forEach((ev) => {
      if ((ev.step || 0) <= watermark) return;
      const play = asPlay(ev);
      if (play) {
        const cardId = resolveCardId(play, view);
        enqueue({
          step: play.step,
          dest: play.dest === "board" ? "board" : "spent",
          side: play.side,
          cardId: cardId,
          name: play.name || "",
          src: artUrl(cardId) || (pending && pending.src) || "",
        });
        return;
      }
      const kill = asShotDown(ev);
      if (kill) enqueue(kill);
    });
    watermark = Math.max(watermark, maxStep);
  }

  // Remember the card the player just clicked so activate (no public card_id) still flies.
  document.addEventListener("pointerdown", (event) => {
    const btn = event.target.closest && event.target.closest(".choice-btn");
    if (!btn) return;
    const preview = document.querySelector(".choice-card-preview img");
    const src = preview ? preview.getAttribute("src") || "" : "";
    pending = {
      at: Date.now(),
      label: (btn.textContent || "").replace(/\s+/g, " ").trim(),
      src: src,
      cardId: cardIdFromSrc(src),
    };
  }, true);

  function hookApply() {
    if (typeof window.__afwipApply !== "function" || window.__afwipApply.__flycard) return;
    const inner = window.__afwipApply;
    function wrapped(view) {
      const out = inner(view);
      try {
        if (view && view.event_log) collect(view);
      } catch (e) {}
      return out;
    }
    wrapped.__flycard = true;
    window.__afwipApply = wrapped;
  }

  async function tick() {
    hookApply();
    const id = gameId();
    if (!id) {
      game = null;
      watermark = null;
      queue = [];
      return;
    }
    if (id !== game) {
      game = id;
      watermark = null;
      queue = [];
      pending = null;
    }
    if (pulling) return;
    pulling = true;
    try {
      const res = await fetch("/api/games/" + id);
      if (!res.ok) return;
      collect(await res.json());
    } catch (e) {
    } finally {
      pulling = false;
      if (queue.length) drain();
    }
  }

  setInterval(tick, 400);
})();
