/* Example Standard drafts on the start screen. */
(function () {
  const BUILDS = {
    US: {
      cyber: {
        title: "Cyber",
        idea: "You start at Cyber Rate 1. Cyber Infiltration needs a 3 to reach 2, then a 4 to reach 3, then a 4 to reach 4. Rate 4 ends the game on the spot. Before that, each point of rate is a token you can acquire or remove. The aircraft keep the fight going while those rolls happen.",
        squadrons: [
          [4, "960th AIRBORNE AIR CONTROL SQUADRON", "One AEW. It spots. Your fighters need a face-up target before they can shoot."],
          [3, "99th EXPEDITIONARY RECONNAISSANCE SQUADRON", "Two more spotting aircraft, so the acquire work is not all on the AEW."],
          [5, "90th FIGHTER SQUADRON", "Four F-22s. Stealth, air-to-air only. They hold the sky while you roll."],
          [10, "480th FIGHTER SQUADRON", "Four F-16s. They fight, and they can still bomb the airbase if the cyber rolls miss."]
        ],
        enablers: [
          [22, "CYBER INFILTRATION", "On your turn, roll to raise your Cyber Rate by 1."],
          [15, "SOF CYBER INFILTRATION", "A second climb card, same roll, so one miss does not end the plan."],
          [21, "CYBER RECONNAISSANCE", "Acquire enemy tokens equal to your rate. The rate starts finding targets."],
          [24, "OFFENSIVE CYBER", "Remove enemy tokens equal to your rate, or force that many discards."],
          [34, "JOINT OFFENSIVE CYBER", "Remove enemy tokens equal to twice your rate. This is the payoff before rate 4."],
          [23, "DEFENSIVE CYBER", "Cancel their cyber card, or play it on your turn to drop their rate by 1."]
        ]
      },
      strike: {
        title: "Base strike",
        idea: "A B-52 launches into standoff and still reaches the enemy airbase. Each filled airbase box is 1 victory point, and the box stays filled for the campaign. Forward Observers turns the surface strike you just declared into an automatic hit.",
        squadrons: [
          [2, "69th BOMB SQUADRON", "One B-52. Surface range is long enough to hit the airbase from standoff."],
          [7, "23rd BOMB SQUADRON", "A second B-52, so one lost bomber does not end the strike plan."],
          [1, "124th ATTACK SQUADRON", "Four attack drones. Short-range surface shots once they are close."],
          [10, "480th FIGHTER SQUADRON", "Four F-16s escort the bombers and can bomb on their own."]
        ],
        enablers: [
          [13, "FORWARD OBSERVERS", "Play right after you declare an air-to-surface strike. That strike hits."],
          [41, "HIGH MOBILITY ARTILLERY ROCKET SYSTEM (HIMARS)", "Roll 2 or better, then roll the damage on their airbase."],
          [42, "TOMAHAWK STRIKE", "Puts a destroyer on the board and rolls damage against their airbase."],
          [30, "EC-130 COMPASS CALL", "An EC-130 in a band. Their attacks in that band roll at disadvantage."],
          [36, "LAND-BASED MISSILE DEFENSE", "An ADA token on your airbase or contingency location."],
          [28, "OFFENSIVE ELECTRONIC WARFARE (EW)", "Your attack rolls are at advantage for the rest of the ATO."]
        ]
      },
      air: {
        title: "Air control",
        idea: "Shoot their aircraft after they are spotted. Under Attrition a destroyed squadron card is worth 2. The AEW and Space Reconnaissance do the spotting. Improved Munitions makes your air-to-air rolls advantage for the whole ATO. Spoofing makes their spots harder, so they struggle to shoot back.",
        squadrons: [
          [5, "90th FIGHTER SQUADRON", "Four stealth F-22s. Air-to-air only, and they are hard to spot."],
          [6, "44th FIGHTER SQUADRON", "Four F-15Cs. More air-to-air fighters in the same plan."],
          [8, "34th FIGHTER SQUADRON", "Four stealth F-35s. They shoot aircraft and can also strike the surface."],
          [4, "960th AIRBORNE AIR CONTROL SQUADRON", "The spotter. Fighters cannot shoot a face-down aircraft."]
        ],
        enablers: [
          [19, "IMPROVED MUNITIONS", "All of your air-to-air rolls are at advantage this ATO."],
          [26, "ELECTRONIC WARFARE (EW) SPOOFING", "Their acquisition rolls are at disadvantage for the rest of the ATO."],
          [27, "DEFENSIVE ELECTRONIC WARFARE (EW)", "Their attack rolls are at disadvantage for the rest of the ATO."],
          [29, "AIR LAUNCHED DECOY", "After they roll a hit, or try missile defense, cancel it."],
          [12, "PERSONNEL RECOVERY", "After you lose an aircraft, it returns in your first band and is not a kill."],
          [31, "SPACE RECONNAISSANCE", "Roll a d4 and acquire that many enemy tokens for the fighters."]
        ]
      }
    },
    PRC: {
      cyber: {
        title: "Cyber",
        idea: "You start at Cyber Rate 1. Cyber Infiltration needs a 3 to reach 2, then a 4 to reach 3, then a 4 to reach 4. Rate 4 ends the game. Offensive Cyber spends the rate to remove their tokens or empty their hand. The fighters stay up so the game lasts long enough for the rolls.",
        squadrons: [
          [58, "AEW REGIMENT", "One AEW. It spots US aircraft so your fighters have a legal shot."],
          [57, "UAS AIR BRIGADE", "Two recon drones. More spotting while the cyber cards roll."],
          [62, "5th AIR BRIGADE", "Four stealth J-20s. Air-to-air only. They keep the US fighters off you."],
          [60, "124th AIR BRIGADE", "Four J-10s. They fight, and they can bomb if you also need airbase points."]
        ],
        enablers: [
          [80, "CYBER INFILTRATION", "On your turn, roll to raise your Cyber Rate by 1."],
          [97, "SOF CYBER INFILTRATION", "A second climb card with the same roll."],
          [83, "CYBER RECONNAISSANCE", "Acquire US tokens equal to your rate."],
          [81, "OFFENSIVE CYBER OPERATIONS", "Remove US tokens equal to your rate, or force that many discards."],
          [84, "CYBER COUNTER-UAS", "Destroy US drone tokens equal to your rate."],
          [82, "DEFENSIVE CYBER OPERATIONS", "Cancel a US cyber card, or drop the US rate by 1 on your turn."]
        ]
      },
      strike: {
        title: "Base strike",
        idea: "The H-6K is the bomber, and Badger Surge makes its attacks advantage for the ATO. The JH-7, the J-16, and the attack drones add more surface shots. The missile cards damage the US airbase from the hand. Each filled box is 1 victory point and stays filled.",
        squadrons: [
          [61, "8th BOMBER DIVISION", "One H-6K. Long surface range, so it can reach the US airbase."],
          [55, "UAS AIR REGIMENT", "Four attack drones for short-range surface shots."],
          [64, "126th AIR BRIGADE", "Four JH-7s. Fighters that can also strike the surface."],
          [63, "26th AIR BRIGADE", "Four J-16s. More fighters that can bomb as well as fight."]
        ],
        enablers: [
          [71, "BADGER SURGE", "The H-6K rolls its attacks at advantage for this ATO."],
          [75, "BALLISTIC MISSILE STRIKE", "Roll 2 or better, then roll the damage on the US airbase."],
          [78, "HYPERSONIC MISSILE", "Unblockable. The US airbase takes damage equal to a d4."],
          [76, "LAND ATTACK CRUISE MISSILE", "Another 2-or-better roll, then damage on the US airbase."],
          [95, "SEA DRAGONS STRIKE", "Roll a d4 and inflict that much damage on the US airbase."],
          [90, "SPACE-BASED ELECTRONIC WARFARE (EW)", "US attack rolls, against bases and tokens, are at disadvantage this ATO."]
        ]
      },
      air: {
        title: "Air control",
        idea: "Spot the US aircraft, then shoot them. A destroyed squadron card is worth 2 under Attrition. Elite Pilots and the munitions card make the air-to-air shot stronger. Reserves brings a squadron back after it has lost every aircraft.",
        squadrons: [
          [62, "5th AIR BRIGADE", "Four stealth J-20s. Air-to-air, and hard to spot."],
          [63, "26th AIR BRIGADE", "Four J-16s. Air-to-air, and they can still strike a base."],
          [60, "124th AIR BRIGADE", "Four J-10s. More fighters in the same fight."],
          [58, "AEW REGIMENT", "The spotter. A face-down US aircraft cannot be shot."]
        ],
        enablers: [
          [69, "ELITE PILOTS", "Your next air-to-air attack rolls at advantage."],
          [74, "MUNITIONS UPGRADE", "One fighter squadron shoots air-to-air at range 4 for this ATO."],
          [72, "SPECIAL MISSION AIRCRAFT", "Acquire with a d4, or make the next air-to-air roll advantage."],
          [70, "GROUND-BASED RADAR", "Roll a d4 and acquire that many US tokens."],
          [94, "SPACE RECONNAISSANCE", "Another d4 acquire, from a different card."],
          [67, "RESERVES", "After a squadron loses every aircraft, it comes back full and can launch again."]
        ]
      }
    }
  };

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "tourney builds-card";
  btn.textContent = "Example drafts";
  btn.title = "Standard posture: cyber, base strike, and air control";

  const sheet = document.createElement("div");
  sheet.id = "builds-sheet";
  sheet.hidden = true;
  sheet.innerHTML = '<div class="builds-panel" role="dialog" aria-modal="true" aria-labelledby="builds-title"></div>';
  const panel = sheet.querySelector(".builds-panel");

  let side = "US";
  let style = "cyber";

  function card(entry) {
    const fig = document.createElement("figure");
    fig.className = "builds-card";
    const img = document.createElement("img");
    img.src = "/art/cards/" + entry[0] + ".jpg";
    img.alt = entry[1];
    img.addEventListener("error", function () { img.remove(); });
    const cap = document.createElement("figcaption");
    const name = document.createElement("strong");
    name.textContent = entry[1];
    const why = document.createElement("span");
    why.textContent = entry[2];
    cap.append(name, why);
    fig.append(img, cap);
    return fig;
  }

  function row(title, entries) {
    const block = document.createElement("section");
    block.className = "builds-block";
    const h = document.createElement("h3");
    h.textContent = title;
    const grid = document.createElement("div");
    grid.className = "builds-row";
    entries.forEach(function (entry) { grid.append(card(entry)); });
    block.append(h, grid);
    return block;
  }

  function chip(label, selected, onPick) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.setAttribute("aria-selected", selected ? "true" : "false");
    b.addEventListener("click", onPick);
    return b;
  }

  function render() {
    const build = BUILDS[side][style];
    panel.textContent = "";
    const head = document.createElement("div");
    head.className = "builds-head";
    const titles = document.createElement("div");
    const kicker = document.createElement("p");
    kicker.className = "builds-kicker";
    kicker.textContent = "Standard posture";
    const h = document.createElement("h2");
    h.id = "builds-title";
    h.textContent = build.title;
    titles.append(kicker, h);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "builds-close";
    close.textContent = "Close";
    close.addEventListener("click", hide);
    head.append(titles, close);

    const lead = document.createElement("p");
    lead.className = "builds-lead";
    lead.textContent = "Standard deals 4 squadron cards, and you may stop at 3, plus 6 enabler cards. Campaign 2 uses this posture. These three lists are ways to spend that roster.";

    const sides = document.createElement("div");
    sides.className = "builds-switch";
    sides.append(
      chip("United States", side === "US", function () { side = "US"; render(); }),
      chip("PRC", side === "PRC", function () { side = "PRC"; render(); })
    );
    const styles = document.createElement("div");
    styles.className = "builds-switch";
    styles.append(
      chip("Cyber", style === "cyber", function () { style = "cyber"; render(); }),
      chip("Base strike", style === "strike", function () { style = "strike"; render(); }),
      chip("Air control", style === "air", function () { style = "air"; render(); })
    );

    const idea = document.createElement("p");
    idea.className = "builds-idea";
    idea.textContent = build.idea;

    panel.append(
      head, lead, sides, styles, idea,
      row("Squadrons", build.squadrons),
      row("Enablers", build.enablers)
    );
  }

  function show() {
    render();
    sheet.hidden = false;
    const close = panel.querySelector(".builds-close");
    if (close) close.focus();
  }

  function hide() {
    sheet.hidden = true;
  }

  function mount() {
    const menu = document.querySelector(".menu");
    if (!menu) return;
    const manualBtn = Array.prototype.find.call(menu.querySelectorAll("button"), function (b) {
      return b !== btn && (b.textContent || "").replace(/\s+/g, " ").trim() === "Game Manual";
    });
    if (!manualBtn) return;
    if (btn.previousElementSibling !== manualBtn) manualBtn.insertAdjacentElement("afterend", btn);
  }

  btn.addEventListener("click", function (event) {
    event.stopPropagation();
    if (sheet.hidden) show();
    else hide();
  });
  sheet.addEventListener("click", function (event) {
    if (event.target === sheet) hide();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !sheet.hidden) hide();
  });

  document.body.append(sheet);
  window.__afwipExampleDrafts = function () {
    if (sheet.hidden) show();
    else hide();
  };
  const root = document.getElementById("root");
  if (root) new MutationObserver(mount).observe(root, { childList: true, subtree: true });
  mount();
})();
