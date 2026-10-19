/* When an enabler is played, hold the table on a screen that shows the card
   and a short animation of what it changed. Continue closes the screen. */
(function () {
  const ART = {
    "F-22": "f-22", "F-35A": "f-35a", "F-15C": "f-15c", "F-15E": "f-15e",
    "F-16C": "f-16c", "B-52": "b-52", "EC-130": "ec-130",
    "Attack UAS (US)": "attack-uas-us", "Recon UAS (US)": "recon-uas-us",
    "AEW (US)": "aew-us", "DDG 81": "ddg-81", "DDG 115": "ddg-115", "ADA (US)": "ada-us",
    "J-20B": "j-20b", "JH-7": "jh-7", "J-10": "j-10", "J-15": "j-15", "J-16": "j-16",
    "H-6K": "h-6k", "Attack UAS (PRC)": "attack-uas-prc", "Recon UAS (PRC)": "recon-uas-prc",
    "AEW (PRC)": "aew-prc", "Dalian #105": "dalian-105", "Nanning #162": "nanning-162",
    "Missile Boat Flotilla": "flotilla", "Mid Range ADA (PRC)": "mid-range-ada-prc",
    "Long Range ADA (PRC)": "long-range-ada-prc",
  };
  const FOLLOW = {
    SPAWN_BAND: true, ENABLER_BRANCH: true, ENABLER_PICK: true,
    MD_DECLARE: true, ALLOC_POINT: true,
  };

  const overlay = document.createElement("div");
  overlay.id = "enabler-overlay";
  overlay.hidden = true;
  overlay.innerHTML = [
    '<div class="en-card">',
    '  <p class="en-kicker" id="en-kicker">Enabler</p>',
    '  <div class="en-stage" id="en-stage"></div>',
    '  <p class="en-caption" id="en-caption"></p>',
    '  <button type="button" id="en-continue">Continue</button>',
    '</div>',
  ].join("");
  document.body.appendChild(overlay);
  const stage = overlay.querySelector("#en-stage");
  const kicker = overlay.querySelector("#en-kicker");
  const caption = overlay.querySelector("#en-caption");
  const button = overlay.querySelector("#en-continue");

  let seen = new Set();
  let game = null;
  let openKey = null;
  let pulling = false;
  let watermark = null;
  let held = false;

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

  function asPlay(ev) {
    if (!ev || ev.type !== "decision") return null;
    const msg = ev.message || "";
    const data = ev.data || {};
    const played = msg.match(/Play enabler:\s*(.+)$/);
    const respond = msg.match(/respond:\s*(.+)$/);
    if (!(data.kind === "play_enabler" || played || respond)) return null;
    const name = (played || respond || ["", ""])[1].trim();
    if (!name && !data.card_id) return null;
    return {
      step: ev.step,
      name: name,
      cardId: data.card_id || null,
      side: ev.side || "",
      response: !!respond,
      message: msg,
    };
  }

  function keyOf(play) {
    return play.step + ":" + play.message;
  }

  function followUp(decision) {
    if (!decision) return false;
    if (FOLLOW[decision.node_type]) return true;
    const labels = (decision.choices || []).map(function (choice) { return choice.label || ""; });
    return labels.some(function (label) {
      return /: (acquire|remove|destroy) /i.test(label)
        || /^(Aerial Refueling|Rapid Resupply):/i.test(label)
        || /shoots air-to-air/i.test(label);
    });
  }

  function artFor(view, play) {
    if (play.cardId) return play.cardId;
    const hands = (view && view.hands) || [];
    for (let i = 0; i < hands.length; i++) {
      const cards = (hands[i].spent || []).concat(hands[i].cards || []);
      const hit = cards.find(function (card) { return card.name === play.name; });
      if (hit) return hit.card_id;
    }
    return null;
  }

  function piece(text) {
    const match = (text || "").match(/([A-Za-z0-9][A-Za-z0-9 #()/-]*?)#(\d+)/);
    if (!match) return text || "";
    return match[1].trim() + " #" + match[2];
  }

  function tokenArt(label) {
    const names = Object.keys(ART).sort(function (a, b) { return b.length - a.length; });
    for (let i = 0; i < names.length; i++) {
      if (label.indexOf(names[i]) !== -1) return "/art/tokens/" + ART[names[i]] + ".jpg";
    }
    return "";
  }

  function windowOf(events, play, plays) {
    let end = Infinity;
    for (let i = 0; i < plays.length; i++) {
      if (plays[i].step > play.step) {
        end = plays[i].step;
        break;
      }
    }
    return events.filter(function (ev) {
      return ev.step >= play.step && ev.step < end;
    });
  }

  function scene(events) {
    const destroyed = events.filter(function (ev) {
      return ev.type === "token_destroyed" || ev.type === "squadron_destroyed";
    });
    const entered = events.filter(function (ev) { return ev.type === "token_enters"; });
    const cyber = events.filter(function (ev) { return ev.type === "cyber_change"; });
    const damage = events.filter(function (ev) { return ev.type === "squadron_damage"; });
    const spots = events.filter(function (ev) {
      return ev.type === "decision" && /: acquire /i.test(ev.message || "");
    });
    const dice = events.filter(function (ev) { return ev.type === "dice"; });
    if (destroyed.length) {
      const named = (destroyed[0].message || "").match(/\((.+)\)/);
      const who = named ? named[1] : piece(destroyed[0].message);
      return { kind: "destroy", label: who, note: who + " is destroyed." };
    }
    if (entered.length) {
      const who = piece(entered[0].message).replace(/ enters play$/i, "");
      return { kind: "spawn", label: who || "Token", note: (who || "A token") + " enters play." };
    }
    if (cyber.length) {
      const match = (cyber[0].message || "").match(/(\d+)\s*->\s*(\d+)/);
      const side = cyber[0].side || "";
      const note = match ? side + " cyber rate " + match[1] + " → " + match[2] + "." : "Cyber rate changes.";
      return { kind: "cyber", label: match ? match[2] : "Cyber", from: match ? match[1] : "", note: note };
    }
    if (damage.length) {
      return { kind: "damage", label: "Squadron hit", note: "The squadron takes a hit." };
    }
    if (spots.length) {
      const who = piece(spots[spots.length - 1].message);
      return { kind: "spot", label: who || "Target", note: "Spots " + (who || "a target") + "." };
    }
    if (dice.length) {
      const face = ((dice[0].message || "").match(/D4=(\d+)/) || [])[1];
      return { kind: "effect", label: face ? "Rolled " + face : "Rolled", note: face ? "Rolled " + face + "." : "The card resolves." };
    }
    return { kind: "effect", label: "In effect", note: "The card is in effect." };
  }

  function chip(className, imgSrc, title) {
    const el = document.createElement("div");
    el.className = className;
    if (imgSrc) {
      const img = document.createElement("img");
      img.src = imgSrc;
      img.alt = title;
      img.addEventListener("error", function () { img.remove(); });
      el.appendChild(img);
    }
    if (title && className !== "en-play") {
      const name = document.createElement("div");
      name.className = "en-hit";
      name.textContent = title;
      el.appendChild(name);
    } else if (!imgSrc && title) {
      const name = document.createElement("div");
      name.className = "en-name";
      name.textContent = title;
      el.appendChild(name);
    }
    return el;
  }

  function show(view, play, built) {
    const look = built || scene([]);
    const id = artFor(view, play);
    stage.replaceChildren();
    stage.className = "en-stage en-go " + look.kind;
    kicker.textContent = (play.side ? play.side + " " : "") + (play.response ? "response" : "enabler");
    stage.appendChild(chip("en-play", id ? "/art/cards/" + id + ".jpg" : "", play.name || "Enabler"));
    const link = document.createElement("div");
    link.className = "en-link";
    stage.appendChild(link);
    const target = chip("en-target", look.kind === "cyber" ? "" : tokenArt(look.label), look.kind === "cyber" ? "" : look.label);
    if (look.kind === "cyber") {
      const num = document.createElement("div");
      num.className = "en-num";
      num.textContent = look.label;
      target.insertBefore(num, target.firstChild);
    }
    if (look.kind === "destroy" || look.kind === "damage") {
      const mark = document.createElement("div");
      mark.className = "en-x en-mark";
      target.appendChild(mark);
    }
    stage.appendChild(target);
    caption.textContent = look.note;
    openKey = keyOf(play);
    overlay.hidden = false;
  }

  function hide() {
    overlay.hidden = true;
    openKey = null;
    stage.className = "en-stage";
  }

  button.addEventListener("click", function (event) {
    event.preventDefault();
    event.stopPropagation();
    if (openKey) seen.add(game + ":" + openKey);
    held = false;
    hide();
  });

  function nextPlay(view) {
    // Board fly-to (flycard.js) owns the played-card reveal; keep this modal off.
    if (window.__afwipCardFlyActive) return null;
    if (followUp(view.decision) || dieBusy()) return null;
    const events = view.event_log || [];
    const plays = [];
    events.forEach(function (ev) {
      const play = asPlay(ev);
      if (play) plays.push(play);
    });
    for (let i = 0; i < plays.length; i++) {
      if (plays[i].step <= watermark) continue;
      if (seen.has(game + ":" + keyOf(plays[i]))) continue;
      return { play: plays[i], events: windowOf(events, plays[i], plays) };
    }
    return null;
  }

  async function tick() {
    if (pulling) return;
    const id = gameId();
    if (!id) {
      if (!held) {
        game = null;
        hide();
      }
      return;
    }
    if (id !== game) {
      game = id;
      seen = new Set();
      watermark = null;
      held = false;
      hide();
    }
    if (held || dieBusy()) return;
    pulling = true;
    try {
      const res = await fetch("/api/games/" + id);
      if (!res.ok) return;
      const view = await res.json();
      const events = view.event_log || [];
      const maxStep = events.reduce(function (max, ev) { return Math.max(max, ev.step || 0); }, 0);
      if (watermark == null) {
        watermark = maxStep;
        return;
      }
      if (openKey) {
        const still = events.some(function (ev) {
          const play = asPlay(ev);
          return play && keyOf(play) === openKey;
        });
        if (!still) hide();
        return;
      }
      const found = nextPlay(view);
      if (!found) return;
      show(view, found.play, scene(found.events));
    } catch (e) {
    } finally {
      pulling = false;
    }
  }

  window.__afwipEnablerPreview = function (sample) {
    held = true;
    show({ hands: [] }, {
      step: 0,
      name: sample.name,
      cardId: sample.cardId,
      side: sample.side || "US",
      response: false,
      message: "preview",
    }, {
      kind: sample.kind || "effect",
      label: sample.label || "In effect",
      note: sample.note || "The card is in effect.",
    });
  };

  setInterval(tick, 400);
})();
