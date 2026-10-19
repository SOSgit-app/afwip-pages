/* One-at-a-time choice browser. Shows a single option with a title that
   names the kind of selection ("Squadron Pick", "Turn", ...), plus
   Previous / Next buttons and arrow-key paging. Card-backed options get a
   "See Preview" button that opens the art in a centered modal instead of
   the old hover preview that covered the board. */
(function () {
  let index = 0;
  let buttons = [];
  let lastSig = "";
  let jumpLabel = "";
  let lastActive = -1;

  // Prompt text -> short window title. First match wins.
  const TITLES = [
    [/draft squadron|squadron card/i, "Squadron Pick"],
    [/draft enabler|enabler card/i, "Enabler Pick"],
    [/mission/i, "Mission Pick"],
    [/posture/i, "Posture Pick"],
    [/your turn|choose an action/i, "Turn"],
    [/place squadron|airbase or contingency/i, "Squadron Placement"],
    [/generation band|spawn/i, "Spawn Band"],
    [/missile defense/i, "Missile Defense"],
    [/response card/i, "Response"],
    [/moves first|first player/i, "First Player"],
    [/reveal|opponent intel/i, "Intel Reveal"],
    [/sacrifice|bid for initiative/i, "Initiative Bid"],
    [/card option/i, "Card Option"],
    [/allocate|base-strike damage/i, "Damage Allocation"],
  ];

  function titleFromPrompt(text) {
    const raw = (text || "").replace(/\s+/g, " ").trim();
    for (let i = 0; i < TITLES.length; i++) {
      if (TITLES[i][0].test(raw)) return TITLES[i][1];
    }
    if (!raw) return "Selection";
    return raw.replace(/^Choose\s+/i, "").replace(/^Your turn\s*[—\-]\s*/i, "Turn · ");
  }

  function scroller() {
    return document.querySelector(".choices-scroll");
  }

  function promptText(panel) {
    const prompt = panel.querySelector(".prompt");
    if (!prompt) return "";
    const clone = prompt.cloneNode(true);
    const who = clone.querySelector(".who");
    if (who) who.remove();
    const quota = clone.querySelector(".pick-quota");
    if (quota) quota.remove();
    return (clone.textContent || "").replace(/\s+/g, " ").trim();
  }

  /* ---------- See Preview modal ---------- */

  function ensureModal() {
    let modal = document.getElementById("choice-preview-modal");
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "choice-preview-modal";
    modal.hidden = true;
    modal.innerHTML = [
      '<div class="choice-preview-card" role="dialog" aria-modal="true" aria-label="Card preview">',
      '  <button type="button" class="choice-preview-close" id="choice-preview-close">Close</button>',
      '  <img id="choice-preview-img" alt="Card preview" />',
      "</div>",
    ].join("");
    document.body.appendChild(modal);
    modal.addEventListener("click", (event) => {
      if (event.target === modal) hidePreview();
    });
    modal.querySelector("#choice-preview-close").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      hidePreview();
    });
    return modal;
  }

  function hidePreview() {
    const modal = document.getElementById("choice-preview-modal");
    if (!modal) return;
    modal.hidden = true;
    document.body.classList.remove("afwip-choice-preview");
  }

  function activeCardId() {
    const active = buttons[index];
    if (!active) return null;
    const cardId = active.getAttribute("data-card-id");
    if (!cardId || cardId === "undefined" || cardId === "null") return null;
    return cardId;
  }

  function showPreview() {
    const cardId = activeCardId();
    if (!cardId) return;
    const active = buttons[index];
    const modal = ensureModal();
    const img = modal.querySelector("#choice-preview-img");
    img.src = "/art/cards/" + cardId + ".jpg";
    img.alt = ((active.textContent || "").trim() || "Card") + " preview";
    modal.hidden = false;
    document.body.classList.add("afwip-choice-preview");
  }

  /* ---------- Pager chrome ---------- */

  function ensureChrome(panel) {
    let bar = panel.querySelector(".choice-pager");
    if (bar) return bar;
    bar = document.createElement("div");
    bar.className = "choice-pager";
    bar.innerHTML = [
      '<div class="choice-pager-title" id="choice-pager-title">Selection</div>',
      '<div class="choice-pager-nav">',
      '  <button type="button" class="choice-pager-btn" id="choice-pager-prev" aria-label="Previous option">&#9664; Previous</button>',
      '  <span class="choice-pager-count" id="choice-pager-count">0 / 0</span>',
      '  <button type="button" class="choice-pager-btn" id="choice-pager-next" aria-label="Next option">Next &#9654;</button>',
      "</div>",
      '<button type="button" class="choice-pager-btn choice-pager-preview" id="choice-pager-preview" hidden>See Preview</button>',
    ].join("");
    panel.insertBefore(bar, panel.firstChild);
    bar.querySelector("#choice-pager-prev").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      step(-1);
    });
    bar.querySelector("#choice-pager-next").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      step(1);
    });
    bar.querySelector("#choice-pager-preview").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      showPreview();
    });
    return bar;
  }

  function step(delta) {
    if (!buttons.length) return;
    index = (index + delta + buttons.length) % buttons.length;
    paint(true);
  }

  function goToLabel(label) {
    jumpLabel = (label || "").trim();
    paint(true);
  }

  function paint(force) {
    const panel = scroller();
    if (!panel) {
      buttons = [];
      lastSig = "";
      lastActive = -1;
      hidePreview();
      return;
    }
    panel.classList.add("choice-pager-on");
    const bar = ensureChrome(panel);
    const list = [...panel.querySelectorAll(".choice-btn")];
    const sig = list.map((btn) => (btn.textContent || "").trim()).join("~") + "|" + promptText(panel);
    if (!force && sig === lastSig && list.length === buttons.length) {
      // React may have swapped nodes without changing labels; keep the
      // active class on the current option.
      if (list[index] && !list[index].classList.contains("choice-pager-active")) {
        buttons = list;
        applyActive(panel, bar);
      }
      return;
    }
    if (sig !== lastSig) hidePreview();
    lastSig = sig;
    buttons = list;

    if (jumpLabel) {
      const hit = buttons.findIndex((btn) => (btn.textContent || "").trim() === jumpLabel);
      if (hit >= 0) index = hit;
      jumpLabel = "";
    } else {
      const suggested = buttons.findIndex((btn) => btn.classList.contains("live-pick"));
      if (suggested >= 0) index = suggested;
      else if (index >= buttons.length) index = 0;
    }
    if (index < 0) index = 0;
    applyActive(panel, bar);
  }

  function applyActive(panel, bar) {
    const title = bar.querySelector("#choice-pager-title");
    const count = bar.querySelector("#choice-pager-count");
    const prev = bar.querySelector("#choice-pager-prev");
    const next = bar.querySelector("#choice-pager-next");
    const previewBtn = bar.querySelector("#choice-pager-preview");
    title.textContent = titleFromPrompt(promptText(panel));
    const total = buttons.length;
    count.textContent = total ? index + 1 + " / " + total : "0 / 0";
    prev.disabled = total <= 1;
    next.disabled = total <= 1;
    previewBtn.hidden = !activeCardId();

    buttons.forEach((btn, i) => {
      btn.classList.toggle("choice-pager-active", i === index);
    });
    panel.querySelectorAll(".choice-group").forEach((group) => {
      group.classList.toggle("choice-pager-show", !!group.querySelector(".choice-pager-active"));
    });

    const active = buttons[index];
    if (active && index !== lastActive) {
      lastActive = index;
      // Keep the board highlight in sync with the shown option. React's
      // onFocus listens to focusin; this does not move keyboard focus.
      try {
        active.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
      } catch (err) {
        /* ignore */
      }
    }
  }

  document.addEventListener(
    "keydown",
    (event) => {
      if (event.key === "Escape") hidePreview();
      if (!scroller()) return;
      const tag = (event.target && event.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (document.body.classList.contains("afwip-choice-preview")) return;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") {
        event.preventDefault();
        step(1);
      } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        event.preventDefault();
        step(-1);
      }
    },
    true
  );

  function safePaint(force) {
    try {
      paint(force);
    } catch (err) {
      /* never let the pager take the game down */
    }
  }

  const root = document.getElementById("root");
  if (root) {
    new MutationObserver(() => safePaint(false)).observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "disabled"],
    });
  }
  setInterval(() => safePaint(false), 400);

  window.__afwipChoicePager = {
    sync: () => safePaint(true),
    goToLabel: goToLabel,
    next: () => step(1),
    prev: () => step(-1),
  };
})();
