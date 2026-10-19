/* A clickable 3D die for every roll the game asks the player to reveal.
   The faces are already decided on the server. The tumble lands on them. */
(function () {
  const overlay = document.createElement("div");
  overlay.id = "die-overlay";
  overlay.hidden = true;
  overlay.innerHTML = [
    '<div class="die-card">',
    '  <div class="die-head">',
    '    <p class="die-kicker" id="die-kicker">Roll when ready</p>',
    '    <button type="button" id="die-cancel" hidden>Cancel</button>',
    '  </div>',
    '  <div class="die-row" id="die-row"></div>',
    '  <div class="die-why-list" id="die-why-list"></div>',
    '  <p class="die-why" id="die-why"></p>',
    '  <p class="die-result" id="die-result"></p>',
    '  <div class="die-actions">',
    '    <button type="button" id="die-roll">Roll</button>',
    '    <button type="button" id="die-continue" hidden>Continue</button>',
    '  </div>',
    '</div>'
  ].join("");
  document.body.append(overlay);
  const row = overlay.querySelector("#die-row");
  const whyList = overlay.querySelector("#die-why-list");
  const whyEl = overlay.querySelector("#die-why");
  const resultEl = overlay.querySelector("#die-result");
  const kicker = overlay.querySelector("#die-kicker");
  const cancelBtn = overlay.querySelector("#die-cancel");
  const rollBtn = overlay.querySelector("#die-roll");
  const continueBtn = overlay.querySelector("#die-continue");

  let phase = "idle";
  let seenPrompt = null;
  let currentDuel = null;
  let canceling = false;
  let activeDice = [];
  let autoTimer = null;

  function autoPlaying() {
    // Watch Agents topbar: when Auto is on the button label switches to Pause.
    return [...document.querySelectorAll(".topbar button")].some((btn) => {
      const label = (btn.textContent || "").replace(/\s+/g, " ").trim();
      return /^Pause\b/i.test(label);
    });
  }

  function autoDelay(kind) {
    const sel = [...document.querySelectorAll(".topbar select")].find((el) => {
      const text = ((el.selectedOptions[0] && el.selectedOptions[0].textContent) || el.value || "").toLowerCase();
      return text.indexOf("slow") >= 0 || text.indexOf("normal") >= 0 || text.indexOf("fast") >= 0;
    });
    const label = sel
      ? (((sel.selectedOptions[0] && sel.selectedOptions[0].textContent) || sel.value || "") + "").toLowerCase()
      : "normal";
    const base = label.indexOf("slow") >= 0 ? 1200 : label.indexOf("fast") >= 0 ? 150 : 500;
    return kind === "roll" ? Math.max(220, Math.round(base * 0.55)) : Math.max(480, Math.round(base * 1.35));
  }

  function clearAuto() {
    if (autoTimer != null) {
      window.clearTimeout(autoTimer);
      autoTimer = null;
    }
  }

  function scheduleAutoRoll() {
    clearAuto();
    if (!autoPlaying() || phase !== "idle") return;
    autoTimer = window.setTimeout(() => {
      autoTimer = null;
      if (phase === "idle" && autoPlaying()) roll(activeDice);
    }, autoDelay("roll"));
  }

  function scheduleAutoContinue() {
    clearAuto();
    if (!autoPlaying() || phase !== "settled") return;
    autoTimer = window.setTimeout(() => {
      autoTimer = null;
      if (phase === "settled" && autoPlaying()) finish();
    }, autoDelay("continue"));
  }

  const ART = {
    "F-22": ["f-22", "F-22"],
    "F-35A": ["f-35a", "F-35A"],
    "F-15C": ["f-15c", "F-15C"],
    "F-15E": ["f-15e", "F-15E"],
    "F-16C": ["f-16c", "F-16C"],
    "B-52": ["b-52", "B-52"],
    "EC-130": ["ec-130", "EC-130"],
    "Attack UAS (US)": ["attack-uas-us", "ATK UAS"],
    "Recon UAS (US)": ["recon-uas-us", "RCN UAS"],
    "AEW (US)": ["aew-us", "AEW"],
    "DDG 81": ["ddg-81", "DDG 81"],
    "DDG 115": ["ddg-115", "DDG 115"],
    "ADA (US)": ["ada-us", "ADA"],
    "J-20B": ["j-20b", "J-20B"],
    "JH-7": ["jh-7", "JH-7"],
    "J-10": ["j-10", "J-10"],
    "J-15": ["j-15", "J-15"],
    "J-16": ["j-16", "J-16"],
    "H-6K": ["h-6k", "H-6K"],
    "Attack UAS (PRC)": ["attack-uas-prc", "ATK UAS"],
    "Recon UAS (PRC)": ["recon-uas-prc", "RCN UAS"],
    "AEW (PRC)": ["aew-prc", "AEW"],
    "Dalian #105": ["dalian-105", "DALIAN"],
    "Nanning #162": ["nanning-162", "NANNING"],
    "Missile Boat Flotilla": ["flotilla", "FLOTILLA"],
    "Mid Range ADA (PRC)": ["mid-range-ada-prc", "ADA-M"],
    "Long Range ADA (PRC)": ["long-range-ada-prc", "ADA-L"],
  };

  function gameId() {
    const el = document.querySelector(".topbar");
    if (!el) return null;
    const m = el.textContent.match(/game\s+([0-9a-f]+)/i);
    return m ? m[1] : null;
  }

  function face() {
    return 1 + Math.floor(Math.random() * 4);
  }

  function cube(value) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "die-cube-btn";
    btn.setAttribute("aria-label", "Roll the die");
    const pyramid = document.createElement("span");
    pyramid.className = "die-pyramid";
    ["a", "b", "c", "d"].forEach((name) => {
      const side = document.createElement("span");
      side.className = "die-face die-" + name;
      const num = document.createElement("span");
      num.className = "die-num";
      num.textContent = value == null ? "?" : String(value);
      side.append(num);
      pyramid.append(side);
    });
    btn.append(pyramid);
    return { btn, cube: pyramid };
  }

  function paint(pyramid, n) {
    pyramid.querySelectorAll(".die-num").forEach((el) => {
      el.textContent = String(n);
    });
  }

  function purposeOf(ev, roll) {
    if (roll && roll.role === "hit") return "To hit";
    if (roll && roll.role === "damage") return "Damage";
    if (roll && roll.role === "acquire") return "Spot";
    const label = ((ev.data && ev.data.label) || ev.message || "");
    if (/initiative/i.test(label)) return "Initiative";
    if (/cyber/i.test(label)) return "Cyber";
    if (/intel/i.test(label)) return "Intel";
    return "Roll";
  }

  const PURPOSE_WHY = {
    Initiative: "Higher result wins initiative: intel peek at advantage, and who moves first.",
    Cyber: "Roll to raise cyber rate one step. Rate 4 wins the game immediately.",
    Intel: "The face is how many enemy hand cards you may see. At least one stays hidden.",
    Spot: "Meet or beat the acquisition value to flip that token face-up.",
    "To hit": "Meet the target number to score the hit.",
    Damage: "This face is how many hits you place after the strike connects.",
    Roll: "The face it lands on is the whole result.",
  };

  function whyFor(purpose) {
    return PURPOSE_WHY[purpose] || PURPOSE_WHY.Roll;
  }

  function diceFrom(view) {
    const events = (view && view.event_log) || [];
    if (!events.length) return [];
    const step = Math.max.apply(null, events.map((ev) => ev.step));
    const viewer = view.viewer || "US";
    const dice = [];
    events.forEach((ev) => {
      if (ev.step !== step || ev.type !== "dice") return;
      const rolls = ev.data && ev.data.rolls;
      if (!Array.isArray(rolls) || !rolls.length) return;
      rolls.forEach((roll) => {
        const purpose = purposeOf(ev, roll);
        const side = roll.side || ev.side || viewer;
        (roll.dice || [roll.natural]).forEach((n) => {
          dice.push({
            side: side,
            purpose: purpose,
            kept: n === roll.natural,
            final: n,
          });
        });
      });
    });
    return dice;
  }

  function findToken(view, uid) {
    const bands = (view.board && view.board.bands) || [];
    for (let i = 0; i < bands.length; i++) {
      const list = bands[i].tokens || [];
      for (let j = 0; j < list.length; j++) {
        if (String(list[j].uid) === String(uid)) return list[j];
      }
    }
    return null;
  }

  function otherSide(side) {
    return side === "PRC" ? "US" : "PRC";
  }

  function named(type, uid, down) {
    if (down) return "Unknown #" + uid;
    const art = ART[type];
    return (art ? art[1] : (type || "Aircraft")) + " #" + uid;
  }

  function exchangeFrom(view) {
    const events = (view && view.event_log) || [];
    if (!events.length) return null;
    const step = Math.max.apply(null, events.map((ev) => ev.step));
    const rows = events.filter((ev) => ev.step === step || ev.step === step - 1);
    const destroyed = {};
    const wreck = {};
    rows.forEach((ev) => {
      if (ev.type !== "token_destroyed") return;
      const match = (ev.message || "").match(/#(\d+)/);
      const uid = match ? match[1] : String((ev.data && ev.data.uid) || "");
      if (!uid) return;
      destroyed[uid] = true;
      if (ev.data && ev.data.type) wreck[uid] = ev.data.type;
    });
    function readDuel(pool) {
      let found = null;
      pool.forEach((ev) => {
        const text = ev.message || "";
        const data = ev.data || {};
        let match;
        if ((match = text.match(/Air:\s*#(\d+)\s*->\s*(.*?)\s*#(\d+)/))) {
          found = { kind: "missile", verb: "shoots", from: match[1], to: match[3], toType: match[2], hit: !!destroyed[match[3]] };
        } else if ((match = text.match(/Surface:\s*#(\d+)\s*->\s*(.*?)\s*#(\d+)/))) {
          found = { kind: "missile", verb: "engages", from: match[1], to: match[3], toType: match[2], hit: !!destroyed[match[3]] };
        } else if ((match = text.match(/Base strike:\s*#(\d+)\s*->\s*(US_AIRBASE|PRC_AIRBASE)/))) {
          found = { kind: "base", verb: "strikes", from: match[1], base: match[2], hit: true };
        } else if ((match = text.match(/Acquire \?#(\d+)\(av(\d+)\) with #(\d+)/))) {
          const seen = findToken(view, match[1]);
          const own = seen && seen.side === (view.viewer || "US");
          found = {
            kind: "sensor", verb: "spots", from: match[3], to: match[1], av: match[2],
            faceDown: !own, revealed: !own && seen && !seen.fogged ? seen : null,
            spotted: !!(own && seen && seen.acquired),
          };
        } else if ((match = text.match(/:\s*destroy\b.*?\#(\d+)/i))) {
          found = { kind: "bolt", verb: "strikes", to: match[1], side: ev.side || "US", hit: true, cyber: true };
        } else if (ev.type === "decision" && data.kind === "acquire" && data.actor_uid != null && data.target_uid != null) {
          const to = String(data.target_uid);
          const seen = findToken(view, to);
          const own = seen && seen.side === (view.viewer || "US");
          found = {
            kind: "sensor", verb: "spots", from: String(data.actor_uid), to: to,
            faceDown: !own, revealed: !own && seen && !seen.fogged ? seen : null,
            spotted: !!(own && seen && seen.acquired),
          };
        } else if (ev.type === "decision" && (data.kind === "shoot_air" || data.kind === "shoot_surface") && data.actor_uid != null && data.target_uid != null) {
          const to = String(data.target_uid);
          found = {
            kind: "missile", verb: "shoots", from: String(data.actor_uid), to: to,
            toType: wreck[to] || "", hit: !!destroyed[to],
          };
        } else if (ev.type === "decision" && data.kind === "shoot_surface" && data.actor_uid != null && /AIRBASE/.test(data.band || "")) {
          found = { kind: "base", verb: "strikes", from: String(data.actor_uid), base: data.band, hit: true };
        }
      });
      return found;
    }
    const latest = rows.filter((ev) => ev.step === step);
    const earlier = rows.filter((ev) => ev.step !== step);
    const duel = readDuel(latest) || readDuel(earlier);
    if (!duel) return null;
    rows.forEach((ev) => {
      if (/MD with /i.test(ev.message || "")) duel.shield = true;
    });
    const actor = duel.from ? findToken(view, duel.from) : null;
    const actorSide = actor ? actor.side : (duel.side || "US");
    const actorDown = !actor || !!actor.fogged;
    const from = duel.cyber ? {
      id: "ix-from", side: actorSide, name: actorSide + " cyber", cyber: true,
    } : {
      id: "ix-from",
      uid: duel.from,
      side: actorSide,
      type: actor && !actor.fogged ? actor.type : "",
      name: named(actor && actor.type, duel.from, actorDown),
      faceDown: actorDown,
    };
    let to;
    if (duel.base) {
      const side = duel.base.indexOf("PRC") === 0 ? "PRC" : "US";
      to = { id: "ix-to", side: side, name: side + " airbase", base: true };
    } else {
      const token = findToken(view, duel.to);
      const own = token && token.side === (view.viewer || "US");
      const boardType = token && !token.fogged && token.type ? token.type : "";
      const labeled = (duel.toType || "").trim();
      const known = boardType || (labeled && labeled !== "?" ? labeled : "");
      const down = !!(duel.faceDown && !own) || !known;
      const type = down ? "" : (boardType || known);
      to = {
        id: "ix-to",
        uid: duel.to,
        side: token ? token.side : otherSide(actorSide),
        type: type,
        name: named(type, duel.to, down),
        faceDown: down,
        reveal: duel.revealed || null,
      };
    }
    return {
      kind: duel.kind,
      verb: duel.verb,
      hit: !!duel.hit,
      spotted: !!duel.spotted,
      shield: !!duel.shield,
      fromId: duel.from || "",
      toId: duel.to || duel.base || "",
      from: from,
      to: to,
    };
  }

  function cardFace(spec) {
    const card = document.createElement("article");
    card.className = "ix-card ix-" + String(spec.side || "us").toLowerCase();
    card.id = spec.id;
    const face = document.createElement("div");
    face.className = "ix-face";
    if (spec.faceDown) {
      card.classList.add("ix-down");
      face.textContent = "?";
    } else if (spec.cyber) {
      card.classList.add("ix-cyber");
      face.textContent = "⚡";
    } else if (spec.base) {
      card.classList.add("ix-base");
      face.textContent = spec.side === "PRC" ? "★" : "✚";
    } else {
      const art = ART[spec.type];
      if (art) {
        const img = document.createElement("img");
        img.src = "/art/tokens/" + art[0] + ".jpg";
        img.alt = spec.name;
        face.append(img);
      } else {
        face.textContent = spec.name;
      }
    }
    const name = document.createElement("div");
    name.className = "ix-name";
    name.textContent = spec.name;
    card.append(face, name);
    return card;
  }

  function setActions(mode) {
    // mode: idle | rolling | settled
    rollBtn.hidden = mode !== "idle";
    rollBtn.disabled = mode !== "idle";
    continueBtn.hidden = mode !== "settled";
    continueBtn.disabled = mode !== "settled";
  }

  function hide() {
    clearAuto();
    overlay.hidden = true;
    document.body.classList.remove("afwip-die");
    row.replaceChildren();
    row.classList.remove("die-duel");
    whyList.replaceChildren();
    whyList.hidden = true;
    whyEl.textContent = "";
    whyEl.hidden = false;
    resultEl.textContent = "";
    kicker.textContent = "Roll when ready";
    overlay.classList.remove("settled");
    currentDuel = null;
    activeDice = [];
    setActions("idle");
    phase = "idle";
  }

  function fillWhyList(entries) {
    whyList.replaceChildren();
    const seen = [];
    (entries || []).forEach((entry) => {
      const purpose = entry.purpose || "Roll";
      if (seen.indexOf(purpose) !== -1) return;
      seen.push(purpose);
      const item = document.createElement("div");
      item.className = "die-why-item";
      const name = document.createElement("span");
      name.className = "die-why-name";
      name.textContent = purpose;
      const text = document.createElement("span");
      text.className = "die-why-text";
      text.textContent = whyFor(purpose);
      item.append(name, text);
      whyList.append(item);
    });
    whyList.hidden = seen.length === 0;
    return seen;
  }

  async function load(id) {
    const gameRes = await fetch("/api/games/" + id);
    if (!gameRes.ok) throw new Error("game");
    const game = await gameRes.json();
    let why = "Roll when ready.";
    try {
      const coachRes = await fetch("/api/games/" + id + "/coach");
      if (coachRes.ok) {
        const note = await coachRes.json();
        if (note.why) why = note.why;
      }
    } catch (e) {}
    return {
      dice: diceFrom(game),
      why: why,
      viewer: game.viewer || "US",
      duel: exchangeFrom(game),
      mode: game.mode || "",
      rollPending: !!game.roll_pending,
    };
  }

  function laneName(side, viewer) {
    return side === viewer ? "You · " + side : side;
  }

  function listFaces(nums) {
    if (nums.length === 1) return nums[0];
    if (nums.length === 2) return nums[0] + " and " + nums[1];
    return nums.slice(0, -1).join(", ") + ", and " + nums[nums.length - 1];
  }

  function show(entries, why, viewer, duel, mode) {
    row.replaceChildren();
    currentDuel = duel || null;
    if (currentDuel) {
      window.__afwipDuel = {
        from: String(currentDuel.fromId || ""),
        to: String(currentDuel.toId || ""),
        at: performance.now(),
      };
    }
    const you = viewer || "US";
    const order = [you, you === "US" ? "PRC" : "US"];
    const present = order.filter((side) => entries.some((die) => die.side === side));
    const lanes = present.length ? present : [you];
    const dice = [];
    const board = document.createElement("div");
    board.className = "die-sides" + (lanes.length > 1 ? " die-sides-split" : "");
    lanes.forEach((side, index) => {
      if (index > 0) {
        const vs = document.createElement("div");
        vs.className = "die-vs";
        vs.textContent = "vs";
        board.append(vs);
      }
      const lane = document.createElement("section");
      lane.className = "die-side die-side-" + side.toLowerCase();
      const head = document.createElement("h3");
      head.textContent = laneName(side, you);
      lane.append(head);
      const sub = document.createElement("div");
      sub.className = "die-who";
      sub.textContent = side === you ? "Your dice" : "Opponent";
      lane.append(sub);
      const line = document.createElement("div");
      line.className = "die-line";
      entries.filter((entry) => (entry.side || you) === side).forEach((entry) => {
        const slot = document.createElement("div");
        slot.className = "die-slot";
        const made = cube("?");
        made.kept = entry.kept;
        made.final = entry.final;
        made.side = side;
        made.viewer = you;
        made.cube.classList.add("rock");
        made.btn.classList.add("die-owner-" + side.toLowerCase());
        made.btn.setAttribute("aria-label", laneName(side, you) + " " + entry.purpose + " die");
        slot.append(made.btn);
        const cap = document.createElement("div");
        cap.className = "die-cap";
        cap.textContent = entry.purpose;
        slot.append(cap);
        line.append(slot);
        dice.push(made);
      });
      lane.append(line);
      board.append(lane);
    });
    if (!dice.length) {
      const made = cube("?");
      made.final = null;
      made.kept = true;
      made.side = you;
      made.cube.classList.add("rock");
      board.append(made.btn);
      dice.push(made);
    }
    if (currentDuel) {
      row.classList.add("die-duel");
      const fx = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      fx.setAttribute("class", "ix-fx");
      fx.id = "ix-fx";
      row.append(cardFace(currentDuel.from), board, cardFace(currentDuel.to), fx);
      kicker.textContent = "Roll when ready";
    } else {
      row.classList.remove("die-duel");
      row.append(board);
      kicker.textContent = lanes.length > 1 ? "Roll when ready. Yours are on the left." : "Roll when ready";
    }
    const purposes = fillWhyList(entries);
    // Per-die tutorial copy covers setup rolls (initiative / cyber / intel).
    // Keep the coach one-liner when there is only a single combat purpose.
    if (purposes.length > 1 || purposes.indexOf("Initiative") !== -1 || purposes.indexOf("Cyber") !== -1 || purposes.indexOf("Intel") !== -1) {
      whyEl.textContent = "";
      whyEl.hidden = true;
    } else {
      const sentence = (why || "").match(/.*?[.!?]/);
      whyEl.textContent = sentence ? sentence[0] : (why || "");
      whyEl.hidden = false;
    }
    resultEl.textContent = "";
    const yours = entries.length > 0 && entries.every((die) => die.side === you);
    // Undo only applies to human choices — hide it while spectating agents.
    cancelBtn.hidden = !yours || mode === "agent_v_agent";
    cancelBtn.disabled = false;
    overlay.classList.remove("settled");
    activeDice = dice;
    setActions("idle");
    phase = "idle";
    overlay.hidden = false;
    document.body.classList.add("afwip-die");
    dice.forEach((die) => {
      die.btn.addEventListener("click", (event) => {
        event.stopPropagation();
        clearAuto();
        roll(dice);
      });
    });
    scheduleAutoRoll();
  }

  function finish() {
    if (phase !== "settled") return;
    clearAuto();
    phase = "done";
    continueBtn.disabled = true;
    overlay.hidden = true;
    document.body.classList.remove("afwip-die");
    const btn = document.querySelector(".roll-prompt .roll-btn");
    if (btn && !btn.disabled) {
      btn.click();
      return;
    }
    // Watch Agents / AI turns: reveal even if the React roll prompt is gone.
    const id = gameId();
    if (!id || typeof window.__afwipApply !== "function") return;
    fetch("/api/games/" + id + "/reveal", { method: "POST" })
      .then((res) => (res.ok ? res.json() : null))
      .then((view) => { if (view) window.__afwipApply(view); })
      .catch(() => {});
  }

  async function cancelAction(event) {
    event.stopPropagation();
    event.preventDefault();
    if (phase !== "idle" || canceling) return;
    const id = gameId();
    if (!id || typeof window.__afwipApply !== "function") return;
    canceling = true;
    cancelBtn.disabled = true;
    try {
      const res = await fetch("/api/games/" + id + "/undo", { method: "POST" });
      if (!res.ok) return;
      hide();
      window.__afwipApply(await res.json());
      seenPrompt = document.querySelector(".roll-prompt");
    } catch (e) {
      return;
    } finally {
      canceling = false;
      cancelBtn.disabled = false;
    }
  }

  function roll(dice) {
    if (phase !== "idle") return;
    const pack = dice && dice.length ? dice : activeDice;
    if (!pack.length) return;
    clearAuto();
    phase = "rolling";
    setActions("rolling");
    cancelBtn.hidden = true;
    kicker.textContent = "Rolling…";
    const started = performance.now();
    pack.forEach((die) => die.cube.classList.remove("rock"));
    pack.forEach((die) => die.cube.classList.add("tumble"));
    whyEl.textContent = "Rolling…";
    function frame(now) {
      pack.forEach((die) => paint(die.cube, face()));
      if (now - started < 900) {
        requestAnimationFrame(frame);
        return;
      }
      pack.forEach((die) => {
        die.cube.classList.remove("tumble");
        die.cube.classList.add("rest");
        if (die.final != null) paint(die.cube, die.final);
        die.btn.classList.toggle("kept", !!die.kept);
        die.btn.classList.toggle("dropped", die.final != null && !die.kept);
      });
      const you = (pack[0] && pack[0].viewer) || "US";
      const bits = [];
      [you, you === "US" ? "PRC" : "US"].forEach((side) => {
        const nums = pack.filter((die) => die.side === side && die.kept && die.final != null).map((die) => String(die.final));
        if (!nums.length) return;
        const who = side === you ? "You (" + side + ")" : side;
        bits.push(who + " rolled " + listFaces(nums));
      });
      whyEl.textContent = "";
      resultEl.textContent = bits.length ? bits.join(". ") + "." : "Locked in.";
      if (currentDuel) beginClash();
      else markSettled();
    }
    requestAnimationFrame(frame);
  }

  function markSettled() {
    kicker.textContent = "Continue when ready";
    overlay.classList.add("settled");
    phase = "settled";
    setActions("settled");
    scheduleAutoContinue();
  }

  function svgNode(name, attrs) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.keys(attrs).forEach((key) => node.setAttribute(key, attrs[key]));
    return node;
  }

  function beginClash() {
    phase = "clash";
    kicker.textContent = "Watch the exchange";
    window.setTimeout(() => animateClash(markSettled), 160);
  }

  function animateClash(done) {
    const duel = currentDuel;
    const stage = row;
    const from = document.getElementById("ix-from");
    const to = document.getElementById("ix-to");
    const fx = document.getElementById("ix-fx");
    if (!duel || !from || !to || !fx) {
      done();
      return;
    }
    const sr = stage.getBoundingClientRect();
    fx.setAttribute("viewBox", "0 0 " + sr.width + " " + sr.height);
    fx.setAttribute("width", String(sr.width));
    fx.setAttribute("height", String(sr.height));
    function point(el) {
      const r = el.getBoundingClientRect();
      return { x: r.left + r.width / 2 - sr.left, y: r.top + r.height / 2 - sr.top };
    }
    const a = point(from);
    const b = point(to);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const ms = reduce ? 180 : (duel.kind === "sensor" ? 520 : 640);
    if (duel.shield) to.classList.add("ix-shielded");
    const start = performance.now();
    let head = null;
    let trail = null;
    if (duel.kind === "missile" || duel.kind === "base") {
      trail = svgNode("line", { x1: a.x, y1: a.y, x2: a.x, y2: a.y, class: "ix-trail" });
      head = svgNode("polygon", { points: "-16,-5 14,0 -16,5 -10,0", class: "ix-missile" });
      fx.append(trail, head);
    } else if (duel.kind === "sensor") {
      trail = svgNode("line", { x1: a.x, y1: a.y, x2: a.x, y2: a.y, class: "ix-sensor" });
      fx.append(trail);
    } else {
      trail = svgNode("polyline", { points: a.x + "," + a.y + " " + b.x + "," + b.y, class: "ix-bolt" });
      fx.append(trail);
    }
    function frame(now) {
      const t = Math.min(1, (now - start) / ms);
      const e = t * t * (3 - 2 * t);
      const end = duel.hit || duel.kind === "sensor" || duel.kind === "bolt" || duel.kind === "base" ? 1 : 0.72;
      const x = a.x + (b.x - a.x) * e * end;
      const y = a.y + (b.y - a.y) * e * end;
      if (trail && trail.tagName === "line") {
        trail.setAttribute("x2", String(x));
        trail.setAttribute("y2", String(y));
      }
      if (head) {
        const angle = Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI;
        head.setAttribute("transform", "translate(" + x + " " + y + ") rotate(" + angle + ")");
      }
      if (t < 1) {
        requestAnimationFrame(frame);
        return;
      }
      if (duel.kind === "sensor" && duel.to.reveal) {
        const seen = duel.to.reveal;
        const art = ART[seen.type];
        to.classList.remove("ix-down");
        to.classList.add("ix-open");
        const face = to.querySelector(".ix-face");
        const name = to.querySelector(".ix-name");
        if (face) {
          face.textContent = "";
          if (art) {
            const img = document.createElement("img");
            img.src = "/art/tokens/" + art[0] + ".jpg";
            img.alt = art[1];
            face.append(img);
          }
        }
        if (name) name.textContent = named(seen.type, seen.uid, false);
        resultEl.textContent += " Spot succeeds.";
      } else if (duel.kind === "sensor" && duel.spotted) {
        to.classList.add("ix-open");
        resultEl.textContent += " They spot it.";
      } else if (duel.kind === "sensor") {
        resultEl.textContent += to.classList.contains("ix-down") ? " Still hidden." : " Still hidden from them.";
      } else if (duel.hit && duel.kind === "base") {
        to.classList.add("ix-struck");
        resultEl.textContent += " The strike lands.";
      } else if (duel.hit) {
        to.classList.add("ix-downed");
        resultEl.textContent += " Destroyed.";
      } else {
        to.classList.add("ix-safe");
        resultEl.textContent += " Miss.";
      }
      window.setTimeout(() => {
        if (head) head.remove();
        done();
      }, reduce ? 80 : 420);
    }
    requestAnimationFrame(frame);
  }

  cancelBtn.addEventListener("click", cancelAction);
  rollBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    event.preventDefault();
    clearAuto();
    roll(activeDice);
  });
  continueBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    event.preventDefault();
    clearAuto();
    finish();
  });

  let pollBusy = false;
  let shownKey = "";
  setInterval(() => {
    if (canceling || pollBusy) return;
    const id = gameId();
    if (!id) {
      if (shownKey || !overlay.hidden) hide();
      seenPrompt = null;
      shownKey = "";
      return;
    }
    // Always drive from the server roll_pending flag so Watch Agents shows the
    // same tumble screen even when the React roll-prompt is late or missing.
    pollBusy = true;
    load(id).then((data) => {
      if (!data.rollPending) {
        if (!overlay.hidden && phase !== "rolling" && phase !== "clash") {
          hide();
        }
        seenPrompt = null;
        shownKey = "";
        return;
      }
      const key = id + ":" + (data.dice || []).map((d) => d.side + d.purpose + d.final).join("|");
      if (!overlay.hidden && shownKey === key) return;
      if (phase === "rolling" || phase === "clash" || phase === "settled") return;
      shownKey = key;
      seenPrompt = document.querySelector(".roll-prompt") || key;
      show(data.dice, data.why, data.viewer, data.duel, data.mode);
    }).catch(() => {
      // Never auto-reveal past a failed load.
    }).finally(() => { pollBusy = false; });
  }, 200);
})();
