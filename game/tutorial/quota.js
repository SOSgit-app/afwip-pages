/* Picked / required counter while drafting or revealing enabler cards. */
(function () {
  let quota = null;

  function gameId() {
    const el = document.querySelector(".topbar");
    if (!el) return null;
    const match = el.textContent.match(/game\s+([0-9a-f]+)/i);
    return match ? match[1] : null;
  }

  function paint() {
    const prompt = document.querySelector(".prompt");
    if (!prompt || !quota) {
      const stale = document.querySelector(".pick-quota");
      if (stale) stale.remove();
      return;
    }
    let badge = prompt.querySelector(".pick-quota");
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "pick-quota";
      prompt.appendChild(badge);
    }
    const text = quota.picked + "/" + quota.needed;
    if (badge.textContent !== text) badge.textContent = text;
  }

  let pulling = false;
  async function tick() {
    paint();
    const id = gameId();
    if (!id) {
      quota = null;
      paint();
      return;
    }
    if (pulling) return;
    pulling = true;
    try {
      const res = await fetch("/api/games/" + id);
      if (!res.ok) return;
      const view = await res.json();
      const decision = view.decision;
      const counted = decision && (decision.node_type === "ENABLER_PICK" || decision.node_type === "INTEL_REVEAL");
      if (counted && decision.picked != null && decision.needed != null) {
        quota = { picked: decision.picked, needed: decision.needed };
      } else {
        quota = null;
      }
    } catch (e) {
    } finally {
      pulling = false;
      paint();
    }
  }

  const root = document.getElementById("root");
  if (root) {
    new MutationObserver(paint).observe(root, { childList: true, subtree: true });
  }
  setInterval(tick, 400);
})();
