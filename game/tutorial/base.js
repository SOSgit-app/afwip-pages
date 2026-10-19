/* Cover a destroyed airbase. The engine never removes the base; all three
   victory-point damage boxes filled is the wrecked state, and those boxes
   stay filled for the campaign. */
(function () {
  const layer = document.createElement("div");
  layer.id = "base-x-layer";
  document.body.appendChild(layer);

  let damage = { US: 0, PRC: 0 };
  let gameId = null;
  let pulling = false;
  let held = false;

  function readGame() {
    const el = document.querySelector(".topbar");
    if (!el) return null;
    const m = el.textContent.match(/game\s+([0-9a-f]+)/i);
    return m ? m[1] : null;
  }

  function zone(side) {
    const svg = document.querySelector(".board-svg");
    if (!svg) return null;
    const label = side === "US" ? "US AIRBASE" : "PRC AIRBASE";
    const text = [...svg.querySelectorAll("text")].find(function (el) {
      return (el.textContent || "").trim() === label;
    });
    if (!text || !text.parentElement) return null;
    let best = null;
    let bestArea = 0;
    text.parentElement.querySelectorAll("rect").forEach(function (rect) {
      const box = rect.getBoundingClientRect();
      const area = box.width * box.height;
      if (area > bestArea) {
        best = box;
        bestArea = area;
      }
    });
    return best && best.width > 24 && best.height > 24 ? best : null;
  }

  function mark(side, box) {
    const el = document.createElement("div");
    el.className = "base-x";
    el.style.left = box.left + "px";
    el.style.top = box.top + "px";
    el.style.width = box.width + "px";
    el.style.height = box.height + "px";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", String(box.width));
    svg.setAttribute("height", String(box.height));
    const pad = Math.min(box.width, box.height) * 0.08;
    const weight = Math.max(12, Math.min(box.width, box.height) * 0.14);
    function line(x1, y1, x2, y2) {
      const stroke = document.createElementNS("http://www.w3.org/2000/svg", "line");
      stroke.setAttribute("x1", String(x1));
      stroke.setAttribute("y1", String(y1));
      stroke.setAttribute("x2", String(x2));
      stroke.setAttribute("y2", String(y2));
      stroke.setAttribute("stroke-width", String(weight));
      svg.appendChild(stroke);
    }
    line(pad, pad, box.width - pad, box.height - pad);
    line(box.width - pad, pad, pad, box.height - pad);
    el.appendChild(svg);
    layer.appendChild(el);
  }

  function paint() {
    layer.replaceChildren();
    ["US", "PRC"].forEach(function (side) {
      if ((damage[side] || 0) < 3) return;
      const box = zone(side);
      if (box) mark(side, box);
    });
  }

  async function pull() {
    if (held) return;
    const id = readGame();
    if (!id) {
      gameId = null;
      damage = { US: 0, PRC: 0 };
      return;
    }
    if (pulling) return;
    pulling = true;
    try {
      const res = await fetch("/api/games/" + id);
      if (!res.ok) return;
      const view = await res.json();
      const boxes = (view.status && view.status.base_damage) || {};
      gameId = id;
      damage = { US: Number(boxes.US) || 0, PRC: Number(boxes.PRC) || 0 };
    } catch (e) {
    } finally {
      pulling = false;
    }
  }

  window.__afwipBaseMark = function (next, hold) {
    damage = { US: Number(next.US) || 0, PRC: Number(next.PRC) || 0 };
    held = hold !== false;
    paint();
  };

  setInterval(function () {
    pull();
    paint();
  }, 400);
})();
