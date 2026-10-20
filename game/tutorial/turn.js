/* Pulse the US or PRC column for whose turn it is. */
(function () {
  let lastSide = "";
  let fetching = false;

  function readGame() {
    const el = document.querySelector(".topbar");
    if (!el) return null;
    const m = el.textContent.match(/game\s+([0-9a-f]+)\s+·\s+rev\s+(\d+)/i);
    return m ? { id: m[1], rev: Number(m[2]) } : null;
  }

  function prcCol() {
    return document.querySelector(".side-col-prc") || document.querySelector(".side-col");
  }

  function usCol() {
    return document.querySelector(".right-col");
  }

  function clear() {
    document.body.classList.remove("afwip-turn-us", "afwip-turn-prc");
    document.querySelectorAll(".afwip-turn-active").forEach((el) => {
      el.classList.remove("afwip-turn-active");
    });
    lastSide = "";
  }

  function applySide(side) {
    if (side !== "US" && side !== "PRC") {
      clear();
      return;
    }
    if (side === lastSide
        && document.body.classList.contains(side === "US" ? "afwip-turn-us" : "afwip-turn-prc")) {
      // Re-assert classes if React replaced the columns.
      const col = side === "PRC" ? prcCol() : usCol();
      if (col && col.classList.contains("afwip-turn-active")) return;
    }
    lastSide = side;
    document.body.classList.toggle("afwip-turn-us", side === "US");
    document.body.classList.toggle("afwip-turn-prc", side === "PRC");
    const us = usCol();
    const prc = prcCol();
    if (us) us.classList.toggle("afwip-turn-active", side === "US");
    if (prc) prc.classList.toggle("afwip-turn-active", side === "PRC");
  }

  function sideFromView(view) {
    if (!view || view.terminal) return "";
    const phase = view.status && view.status.phase;
    const active = view.status && view.status.active_side;
    // During player turns, pulse whose TURN it is — not who is answering a
    // mid-turn response or missile-defense window on the other side's turn.
    if (phase === "PLAYER_TURN") {
      return active === "US" || active === "PRC" ? active : "";
    }
    // Setup / other phases: light whoever just acted while Continue is up.
    if (view.watch_pending && Array.isArray(view.event_log)) {
      for (let i = view.event_log.length - 1; i >= 0; i--) {
        const ev = view.event_log[i];
        if (ev && ev.type === "decision" && (ev.side === "US" || ev.side === "PRC")) {
          return ev.side;
        }
      }
    }
    if (view.decision && (view.decision.side === "US" || view.decision.side === "PRC")) {
      return view.decision.side;
    }
    return active === "US" || active === "PRC" ? active : "";
  }

  function applyView(view) {
    applySide(sideFromView(view));
  }

  async function poll() {
    const game = readGame();
    if (!game) {
      clear();
      return;
    }
    if (fetching) return;
    fetching = true;
    try {
      const res = await fetch("/api/games/" + game.id);
      if (!res.ok) return;
      applyView(await res.json());
    } catch (e) {
      /* next tick */
    } finally {
      fetching = false;
    }
  }

  function hookApply() {
    if (typeof window.__afwipApply !== "function" || window.__afwipApply.__turn) return;
    const inner = window.__afwipApply;
    function wrapped(view) {
      const out = inner(view);
      try { applyView(view); } catch (e) {}
      return out;
    }
    wrapped.__turn = true;
    window.__afwipApply = wrapped;
  }

  setInterval(() => {
    hookApply();
    poll();
  }, 500);
  hookApply();
  poll();
})();
