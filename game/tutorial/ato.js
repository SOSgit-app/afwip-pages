/* Mid-board popup when an ATO cycle ends and the next one begins. */
(function () {
  const overlay = document.createElement("div");
  overlay.id = "ato-overlay";
  overlay.hidden = true;
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "ato-title");
  overlay.innerHTML = [
    '<div class="ato-card">',
    '  <p class="ato-kicker" id="ato-kicker">ATO cycle</p>',
    '  <h2 class="ato-title" id="ato-title">Next ATO begins</h2>',
    '  <p class="ato-body" id="ato-body"></p>',
    '  <button type="button" id="ato-continue">Continue</button>',
    "</div>",
  ].join("");
  document.body.appendChild(overlay);

  const kicker = overlay.querySelector("#ato-kicker");
  const title = overlay.querySelector("#ato-title");
  const body = overlay.querySelector("#ato-body");
  const button = overlay.querySelector("#ato-continue");

  let openKey = null;
  let placed = false;
  let dismissing = false;
  const dismissed = new Set();

  function boardRect() {
    const board =
      document.querySelector(".board-wrap")
      || document.querySelector(".board-panel")
      || document.querySelector(".board-svg");
    if (!board) return null;
    return board.getBoundingClientRect();
  }

  function place() {
    const r = boardRect();
    if (!r || r.width < 40 || r.height < 40) {
      // Fall back to the play area under the coach dock.
      const top = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--live-h")) || 0;
      overlay.style.left = "0";
      overlay.style.top = top + "px";
      overlay.style.width = "100%";
      overlay.style.height = Math.max(120, window.innerHeight - top) + "px";
      return;
    }
    overlay.style.left = Math.max(0, r.left) + "px";
    overlay.style.top = Math.max(0, r.top) + "px";
    overlay.style.width = r.width + "px";
    overlay.style.height = r.height + "px";
  }

  function parseCycle(note) {
    const blob = [(note && note.now) || "", (note && note.suggest) || "", (note && note.title) || ""].join(" ");
    const ended = blob.match(/ATO\s+(\d+)\s+ended/i);
    const begins = blob.match(/ATO\s+(\d+)\s+of\s+(\d+)/i);
    return {
      closed: ended ? Number(ended[1]) : null,
      next: begins ? Number(begins[1]) : null,
      total: begins ? Number(begins[2]) : null,
    };
  }

  function fill(note) {
    const cycle = parseCycle(note || {});
    const closed = cycle.closed;
    const next = cycle.next;
    const total = cycle.total;
    kicker.textContent = closed != null ? ("ATO " + closed + " complete") : "ATO cycle";
    if (next != null && total != null) {
      title.textContent = "ATO " + next + " of " + total + " begins";
    } else if (next != null) {
      title.textContent = "ATO " + next + " begins";
    } else {
      title.textContent = (note && note.title) || "Next ATO begins";
    }
    body.textContent =
      "Both sides passed in a row, so this cycle is over. "
      + "Aircraft still in the air return to their squadron cards, "
      + "end-of-cycle points are scored, and the board clears. "
      + "You will draft again for the next ATO.";
  }

  function isOpen() {
    return !overlay.hidden;
  }

  function hide() {
    overlay.hidden = true;
    openKey = null;
    document.body.classList.remove("afwip-ato-alert");
    if (placed) {
      window.removeEventListener("resize", place);
      placed = false;
    }
  }

  function show(note, key) {
    if (isOpen() && openKey === key) {
      place();
      return;
    }
    openKey = key;
    fill(note);
    place();
    overlay.hidden = false;
    document.body.classList.add("afwip-ato-alert");
    if (!placed) {
      window.addEventListener("resize", place);
      placed = true;
    }
    // Stop the auto-watch timer so this popup is not skipped.
    if (typeof window.__afwipClearWatchTimer === "function") {
      window.__afwipClearWatchTimer();
    }
    try { button.focus(); } catch (e) { /* ignore */ }
  }

  function maybeShow(note, game) {
    if (!note || note.concept !== "new_ato") {
      return false;
    }
    const id = game && game.id ? game.id : "game";
    const cycle = parseCycle(note);
    const closed = cycle.closed != null ? cycle.closed : "x";
    const key = id + ":ato-closed:" + closed;
    // One mid-board alert per closed cycle (not again on the posture pick).
    if (dismissed.has(key)) return false;
    if (openKey === key && isOpen()) {
      place();
      return true;
    }
    show(note, key);
    return true;
  }

  async function dismiss() {
    if (dismissing || !isOpen()) return;
    dismissing = true;
    try {
      if (openKey) dismissed.add(openKey);
      hide();
      // Closing pass hold → advance into ATO-2 setup. Posture-only beat: no-op.
      if (typeof window.__afwipAdvanceWatch === "function") {
        await window.__afwipAdvanceWatch();
      }
    } finally {
      dismissing = false;
    }
  }

  button.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    dismiss();
  });
  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay) dismiss();
  });
  document.addEventListener("keydown", (ev) => {
    if (!isOpen()) return;
    if (ev.key === "Escape" || ev.key === "Enter") {
      ev.preventDefault();
      dismiss();
    }
  });

  window.__afwipAtoAlert = {
    maybeShow: maybeShow,
    isOpen: isOpen,
    hide: hide,
  };
})();
