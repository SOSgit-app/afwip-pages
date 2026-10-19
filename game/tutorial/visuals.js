/* Builds the in-game pictures for each tutorial lesson. */
(function () {
  function h(tag, attrs, kids) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    (kids || []).forEach((kid) => node.append(kid instanceof Node ? kid : document.createTextNode(kid)));
    return node;
  }

  function card(id, caption) {
    return h("figure", { class: "art-card" }, [
      h("img", { src: "/art/cards/" + id + ".jpg", alt: caption }),
      h("figcaption", {}, [caption])
    ]);
  }

  function token(slug, caption) {
    return h("figure", { class: "art-token" }, [
      h("img", { src: "/art/tokens/" + slug + ".jpg", alt: caption }),
      h("figcaption", {}, [caption])
    ]);
  }

  function row(cls, nodes) {
    return h("div", { class: cls }, nodes);
  }

  function felt(cols, border) {
    const board = h("div", { class: "felt" + (border ? " " + border : "") });
    cols.forEach((col) => {
      const klass = "felt-col tone-" + (col.tone || "sea") + (col.reach ? " reach" : "") + (col.hot ? " hot" : "");
      const pcs = h("div", { class: "felt-pcs" });
      (col.tokens || []).forEach((t) => {
        if (t.down) {
          const back = h("div", { class: "token-back " + (t.side || "prc"), title: "Face-down counter" }, ["?"]);
          if (t.av) back.append(h("span", {}, ["AV " + t.av]));
          pcs.append(back);
        } else {
          pcs.append(h("img", { class: "tok", src: "/art/tokens/" + t.slug + ".jpg", alt: t.alt || t.slug }));
        }
      });
      (col.cards || []).forEach((id) => {
        pcs.append(h("img", { class: "mini-sq", src: "/art/cards/" + id + ".jpg", alt: "Card " + id }));
      });
      const cell = h("div", { class: klass }, [h("div", { class: "felt-name" }, [col.name]), pcs]);
      if (col.mark) cell.append(h("div", { class: "felt-mark" }, [col.mark]));
      board.append(cell);
    });
    return board;
  }

  function note(text) {
    return h("p", { class: "visual-note" }, [text]);
  }

  function frame(kicker, kids) {
    return h("figure", { class: "visual" }, [h("p", { class: "visual-kicker" }, [kicker]), ...kids]);
  }

  function cards(list) {
    return row("art-row", list.map(([id, cap]) => card(id, cap)));
  }

  function tokens(list) {
    return row("token-row", list.map(([slug, cap]) => token(slug, cap)));
  }

  const builders = {
    "What this game is": () => frame("On the table", [
      cards([
        [5, "Squadron card. Flip it to create tokens."],
        [22, "Enabler card. An effect from your hand."],
        [49, "Posture. How many cards you draft."],
        [51, "Mission. How you score. Hidden until the end."]
      ]),
      tokens([
        ["f-22", "Token. This is the piece that moves and fights."],
        ["aew-us", "Sensor token. Finds face-down enemies."],
        ["b-52", "Bomber token. Strikes from standoff."]
      ]),
      note("Click any picture to read it at full size. These are the same files the board uses.")
    ]),

    "How a game is built": () => frame("One ATO, in pictures", [
      h("div", { class: "steps" }, [
        [49, "1. Posture"],
        [10, "2. Squadrons"],
        [22, "3. Enablers"],
        [51, "Then score"]
      ].map(([id, label]) => h("div", { class: "step" }, [h("b", {}, [label]), h("img", { src: "/art/cards/" + id + ".jpg", alt: label })]))),
      felt([
        { name: "US standoff", tone: "rear", tokens: [{ slug: "aew-us", alt: "AEW" }] },
        { name: "Band A", tokens: [{ slug: "f-16c", alt: "F-16" }] },
        { name: "Band C", tokens: [{ down: true, side: "prc", av: "4" }] },
        { name: "Band E", tokens: [{ slug: "j-10", alt: "J-10" }] },
        { name: "PRC airbase", tone: "prc", cards: [60] }
      ]),
      note("Step 4 is the turns: tokens on the bands, squadron cards still sitting on a base. Both players pass, then you score.")
    ]),

    "The D4": () => frame("The die is printed on the cards", [
      cards([
        [22, "Cyber Infiltration tells you to roll 1d4 against the access number."],
        [19, "Improved Munitions shows the two-die mark: lo and hi. That is disadvantage and advantage."]
      ]),
      note("Advantage keeps the higher of two dice. Disadvantage keeps the lower. One of each cancels back to a single die. A 4 is the best face.")
    ]),

    "The map and range": () => frame("The same map the app draws", [
      felt([
        { name: "US standoff", tone: "rear", hot: true, tokens: [{ slug: "b-52", alt: "B-52" }], mark: "start" },
        { name: "Band A", mark: "1" },
        { name: "Band B", mark: "2" },
        { name: "Band C", mark: "3" },
        { name: "Band D", mark: "4" },
        { name: "Band E", mark: "5" },
        { name: "PRC airbase", tone: "prc", reach: true, mark: "6" }
      ]),
      note("A B-52 in US standoff reaches the PRC airbase in 6 steps. Its printed surface range is 6, so that bomb run just lands. US airbase, US standoff, and the CL all sit one step off Band A. They are not a single file behind each other.")
    ]),

    "Bases, standoff, and the CL": () => frame("Three homes", [
      felt([
        { name: "US standoff", tone: "rear", tokens: [{ slug: "b-52", alt: "B-52" }, { slug: "aew-us", alt: "AEW" }], mark: "bombers and AEW" },
        { name: "US airbase", tone: "us", cards: [5, 10], mark: "3 VP boxes" },
        { name: "US CL", tone: "us", cards: [8], mark: "launch roll" },
        { name: "PRC airbase", tone: "prc", cards: [62, 60], tokens: [{ slug: "long-range-ada-prc", alt: "ADA" }] },
        { name: "PRC standoff", tone: "rear", tokens: [{ slug: "h-6k", alt: "H-6K" }] }
      ]),
      h("div", { class: "vp-row" }, [
        h("span", {}, ["Airbase VP boxes"]),
        h("i", { class: "vp-box filled" }),
        h("i", { class: "vp-box filled" }),
        h("i", { class: "vp-box" }),
        h("span", { class: "visual-note" }, ["Two filled, one still open. Each filled box is 1 VP and stays filled. The base still launches."])
      ]),
      note("The CL card is an F-35 squadron. Activating it there rolls a D4 for how many of the four jets launch. The airbase cards launch all of theirs.")
    ]),

    "Three kinds of things": () => frame("Card, then the counters it creates", [
      h("div", { class: "compare" }, [
        h("div", {}, [h("h3", {}, ["Squadron card"]), card(5, "90th Fighter Squadron. Two damage squares. Generates 4 F-22 tokens on Band A.")]),
        h("div", {}, [h("h3", {}, ["The tokens"]), tokens([["f-22", "One of the four. Move 2, acquire 2 (+1), air range 1 hitting on 2+."]])])
      ]),
      cards([[22, "An enabler is not a squadron. It never sits on the airbase as a unit. You play it from your hand."]]),
      note("Green squadron cards show DAMAGE and Generate. Enablers show Single Use or Multiple Use, and sometimes a red pin or a yellow bolt.")
    ]),

    "How to read a token": () => frame("Read the counter, left to right", [
      tokens([
        ["f-22", "Wifi is acquire: range 2, triangle +1. The missile is air-to-air: range 1, hit on 2+. No bomb, so it cannot strike a base."],
        ["b-52", "STANDOFF means it may sit in the rear. The bomb is surface range 6. The sunburst on the 2+ is an exploding damage die."],
        ["ada-us", "No move range, so it stays put. The shield is missile defense. The missile is air range 1, hit on 2+."],
        ["ddg-115", "A ship. Long air and surface reach, and it can spend a salvo to defend a shot."]
      ]),
      note("The roundel is the side. The number in the diamond is what the attack roll must meet. Pick a unit below and the same counter stays on screen while you read the words.")
    ]),

    "How the pieces work together": () => frame("One turn's worth of jobs", [
      felt([
        { name: "US standoff", tone: "rear", tokens: [{ slug: "aew-us", alt: "AEW" }], mark: "finds" },
        { name: "Band A", tokens: [{ slug: "f-22", alt: "F-22" }, { slug: "f-16c", alt: "F-16" }], mark: "kills air / bombs" },
        { name: "Band C", tokens: [{ down: true, side: "prc", av: "4" }], mark: "not identified" },
        { name: "Band E", tokens: [{ slug: "j-16", alt: "J-16" }] },
        { name: "PRC standoff", tone: "rear", tokens: [{ slug: "h-6k", alt: "H-6K" }], mark: "threat" },
        { name: "PRC airbase", tone: "prc", tokens: [{ slug: "long-range-ada-prc", alt: "ADA" }], mark: "defends" }
      ]),
      note("The AEW in standoff is the piece that should roll against the face-down AV 4. The F-22 shoots whatever gets flipped if it is in air range. The F-16 can also bomb. The PRC ADA makes that bomb run roll at disadvantage if the shot crosses its zone.")
    ]),

    "What the marks on a card mean": () => frame("Four marks you will see on the card itself", [
      cards([
        [10, "Squadron. Green. Two red DAMAGE squares. Generate tells you the tokens and the band."],
        [22, "Multiple Use. It can come back into a later draft even after you play it."],
        [19, "Red pushpin: enduring. The bias lasts this whole ATO. Also printed Single Use."],
        [12, "Yellow bolt: a response. Play it when its trigger happens, including on the opponent's turn."]
      ])
    ]),

    "Postures": () => frame("The posture cards", [
      h("h3", {}, ["United States"]),
      cards([
        [49, "Standard. 6 enablers, 4 squadrons. The recycle mark means you may take it every cycle."],
        [45, "ACE. Fewer cards. CL squadrons launch in full, and strikes on your airbases are harder."],
        [46, "Surge. The big roster. No contingency location."],
        [47, "Hedgehog. A free ADA token."],
        [48, "Standoff. Both B-52 cards are free on top of the squadron count."]
      ]),
      h("h3", {}, ["People's Republic of China"]),
      cards([
        [103, "Standard. Same 6 and 4, and it can be repeated."],
        [99, "PLAAF. Enablers must be PLAAF cards."],
        [100, "Joint Operations. Many enablers, few squadrons, and those squadrons must fly."],
        [101, "ADA. Both ADA squadrons are free."],
        [102, "Standoff. The H-6K is free, plus an extra PLARF enabler."]
      ])
    ]),

    "Setup and the draft": () => frame("Two decks. Nothing is shared.", [
      h("h3", {}, ["Your US squadrons"]),
      cards([
        [5, "F-22"], [8, "F-35"], [10, "F-16, required in Campaign 1"], [4, "AEW"], [2, "B-52"]
      ]),
      h("h3", {}, ["The PRC deck, which you cannot take from"]),
      cards([
        [62, "J-20"], [60, "J-10, required in Campaign 1"], [58, "AEW"], [61, "H-6K"]
      ]),
      note("You click through your whole roster, then the opponent clicks through theirs. Taking the AEW first does not put your F-22 at risk.")
    ]),

    "Missions": () => frame("The scoring is written on the card", [
      cards([
        [51, "Attrition. The Campaign 1 and 2 mission. Read the three lines of VP."],
        [52, "Interdiction. Bombers, AEW, and squadron cards are worth the most."],
        [50, "Economy of Force. Points for drafted units you did not spend."],
        [53, "N-K Dominance. Points from cyber rate and non-kinetic cards."],
        [54, "Enforce Rule of Law. Points for activating and for generating tokens."]
      ]),
      cards([
        [105, "PRC Attrition. Same idea, other side."],
        [108, "Counter-Intervention. Points for killing air tokens on the ground."]
      ]),
      note("You do not show this card until the game ends. The opponent is always guessing which line you are farming.")
    ]),

    "Initiative and intel": () => frame("What the intel peek looks like", [
      h("div", { class: "hand" }, [
        card(21, "Seen"),
        card(30, "Seen"),
        h("div", { class: "back-card", title: "Still hidden" }, ["HID"])
      ]),
      note("After the D4 bid, each side looks at some of the opponent's hand. At least one card stays hidden, the way the facedown card on the right does. The initiative winner rolls that peek at advantage, chooses who moves first, and gets one cyber raise.")
    ]),

    "Cyber": () => frame("The cards that move the track", [
      cards([
        [22, "Multiple Use. Roll to climb one rate."],
        [15, "SOF cyber. Another raise attempt, single use."],
        [21, "Acquire enemy tokens equal to the rate you already have."],
        [24, "Remove tokens equal to your rate, or force that many discards."],
        [34, "Joint Offensive. Remove twice your rate."],
        [33, "Joint Defensive. Drop the enemy rate by 2."],
        [23, "Cancel their cyber card, or shave 1 off their rate."]
      ]),
      note("You start at rate 1, not 0. The ladder beside this picture is the access roll. Rate 4 ends the game on the spot.")
    ]),

    "Your turn": () => frame("What the app offers on a fresh turn", [
      h("div", { class: "mock" }, [
        felt([
          { name: "US airbase", tone: "us", cards: [5, 4] },
          { name: "Band A", hot: true, tokens: [{ slug: "f-16c", alt: "F-16" }] },
          { name: "Band C", tokens: [{ down: true, side: "prc", av: "2" }] }
        ]),
        h("aside", { class: "mock-side" }, [
          h("div", { class: "mock-prompt" }, ["Your move", h("span", { class: "who" }, ["US"])]),
          h("div", { class: "mock-cat" }, ["Activate Squadron"]),
          h("div", { class: "mock-choice" }, ["Activate 90th Fighter Sq (F-22)"]),
          h("div", { class: "mock-choice" }, ["Activate 960th AEW Sq"]),
          h("div", { class: "mock-cat" }, ["Move"]),
          h("div", { class: "mock-choice" }, ["Move F-16C → Band B"]),
          h("div", { class: "mock-choice" }, ["Move F-16C → Band C"]),
          h("div", { class: "mock-cat" }, ["Acquire Target"]),
          h("div", { class: "mock-choice" }, ["Acquire ? (AV 2) with F-16C"]),
          h("div", { class: "mock-cat" }, ["End / Pass"]),
          h("div", { class: "mock-choice" }, ["Pass / end turn"])
        ])
      ]),
      note("Activate and the move are both listed until you pick one. After you move, the activate lines disappear. You could still acquire with this F-16, because acquire has not been used yet.")
    ]),

    "Activating a squadron": () => frame("The card becomes counters", [
      h("div", { class: "compare" }, [
        h("div", {}, [
          h("h3", {}, ["Fighter card"]),
          card(5, "Generates 4 on your front band."),
          felt([{ name: "Band A", hot: true, tokens: [
            { slug: "f-22", alt: "F-22" }, { slug: "f-22", alt: "F-22" },
            { slug: "f-22", alt: "F-22" }, { slug: "f-22", alt: "F-22" }
          ], mark: "all four" }])
        ]),
        h("div", {}, [
          h("h3", {}, ["Bomber card"]),
          card(2, "Generates 1, on the front band or in standoff."),
          felt([{ name: "US standoff", tone: "rear", tokens: [{ slug: "b-52", alt: "B-52" }], mark: "one token" }])
        ])
      ]),
      note("That activation spent the turn. The new F-22s cannot shoot until a later turn.")
    ]),

    "Movement": () => frame("Move 2 from Band A", [
      felt([
        { name: "Band A", hot: true, tokens: [{ slug: "f-22", alt: "F-22" }], mark: "now" },
        { name: "Band B", reach: true, mark: "1 step" },
        { name: "Band C", reach: true, mark: "2 steps" },
        { name: "Band D", mark: "too far" }
      ]),
      tokens([
        ["f-22", "Move Range 2, printed on the counter."],
        ["b-52", "Move Range 1. Only this and the AEW may move into standoff."],
        ["ada-us", "No move range. It never walks."]
      ]),
      note("Gold outlines are inside this move. One token only. A second fighter stays where it is.")
    ]),

    "Acquire and fog of war": () => frame("Before the roll, and after it", [
      h("div", { class: "compare" }, [
        h("div", {}, [
          h("h3", {}, ["Before"]),
          felt([
            { name: "US standoff", tone: "rear", tokens: [{ slug: "aew-us", alt: "AEW" }], mark: "rolls twice, +2" },
            { name: "Band C", tokens: [{ down: true, side: "prc", av: "4" }], mark: "type hidden" }
          ])
        ]),
        h("div", {}, [
          h("h3", {}, ["After a success"]),
          felt([
            { name: "US standoff", tone: "rear", tokens: [{ slug: "aew-us", alt: "AEW" }] },
            { name: "Band C", reach: true, tokens: [{ slug: "j-20b", alt: "J-20" }], mark: "now a target" }
          ])
        ])
      ]),
      note("Until the roll succeeds you only know the acquisition value, the AV 4 on the back. The app's button reads like Acquire ?#12 (av 4). A grounded fighter on a base never flips. It dies with its squadron card.")
    ]),

    "Shooting": () => frame("Two different shots", [
      h("h3", {}, ["Air-to-air, range 1"]),
      felt([
        { name: "Band C", hot: true, tokens: [{ slug: "f-35a", alt: "F-35" }], mark: "shooter" },
        { name: "Band D", reach: true, tokens: [{ slug: "j-16", alt: "J-16" }], mark: "acquired" }
      ]),
      note("One hit destroys the J-16. There is no second damage die. The F-35's printed air attack is range 1, hit on 2+."),
      h("h3", {}, ["Base strike from standoff"]),
      felt([
        { name: "US standoff", tone: "rear", hot: true, tokens: [{ slug: "b-52", alt: "B-52" }] },
        { name: "Band A" }, { name: "Band B" }, { name: "Band C" }, { name: "Band D" }, { name: "Band E" },
        { name: "PRC airbase", tone: "prc", reach: true, cards: [63], mark: "range 6" }
      ]),
      note("The base itself does not have to be acquired. On a hit the B-52 rolls a D4 and you assign that many hits. The squadron card takes two.")
    ]),

    "Damage": () => frame("Where the hits actually land", [
      cards([
        [10, "A squadron card's two red squares are its hits. One square resets next cycle. Both squares destroy the card and the aircraft still on it."],
        [41, "HIMARS says airbase. Those hits fill VP boxes only. They skip squadron cards."],
        [75, "A PRC ballistic missile says base. Those hits spread across cards and VP boxes."]
      ]),
      h("div", { class: "vp-row" }, [
        h("span", {}, ["VP boxes on the airbase"]),
        h("i", { class: "vp-box filled" }),
        h("i", { class: "vp-box" }),
        h("i", { class: "vp-box" })
      ]),
      note("The damage toy under this picture is that assignment: three exploding hits, spent one at a time onto cards and boxes.")
    ]),

    "Winchester": () => frame("A natural 2 sends it home", [
      felt([
        { name: "Band B", tokens: [{ slug: "f-16c", alt: "F-16" }], mark: "shot on a 2" },
        { name: "Band A" },
        { name: "US airbase", tone: "us", cards: [10], mark: "home next turn" }
      ]),
      tokens([
        ["f-16c", "Winchester unless the attack roll is a 4."],
        ["attack-uas-us", "Keeps ammo on a 3 or a 4."],
        ["aew-us", "Never goes Winchester. No weapon to run dry."]
      ]),
      note("The trip home happens at the start of your turn and does not cost the move. If card 10 were already destroyed, the F-16 would be surrendered instead of landing.")
    ]),

    "Missile defense": () => frame("The shot has to cross this", [
      felt([
        { name: "US standoff", tone: "rear", tokens: [{ slug: "b-52", alt: "B-52" }], mark: "attacker" },
        { name: "Band C", tokens: [{ slug: "ddg-81", alt: "DDG" }], mark: "declare to defend" },
        { name: "PRC airbase", tone: "prc", tokens: [{ slug: "long-range-ada-prc", alt: "Long ADA" }], cards: [63], mark: "ADA is automatic" }
      ]),
      cards([
        [36, "Land-Based Missile Defense places this ADA."],
        [37, "Maritime Missile Defense places a destroyer that can be declared."],
        [29, "Air Launched Decoy can cancel a declared missile-defense attempt."],
        [78, "Hypersonic is unblockable. The ADA does not get a say."]
      ]),
      note("ADA disadvantage happens by itself. The ship spends an air salvo and must be declared before the roll. Both the hit die and the damage die take that disadvantage.")
    ]),

    "Enablers during play": () => frame("The families, as printed cards", [
      cards([
        [31, "Find. Space Reconnaissance acquires without flying a sensor."],
        [24, "Remove. Offensive Cyber deletes tokens or discards."],
        [42, "Strike boxes. Tomahawk fills airbase VP boxes and also places a ship."],
        [30, "Put a unit down. The EC-130 jams PRC attacks from its band."],
        [28, "Bias the cycle. Offensive EW is the red-pin kind."],
        [38, "Answer a hit. Red Horse cancels the damage on your base."],
        [16, "Stretch. Aerial Refueling drafts one squadron past the posture."]
      ]),
      note("The list below is every enabler. The thumbnail is the real card. Click it when you want the printed wording.")
    ]),

    "Keeping score": () => frame("Attrition, counted off the pictures", [
      cards([[51, "The mission you are holding in Campaign 1 and 2."]]),
      h("div", { class: "art-row" }, [
        token("j-10", "+1. Any other token."),
        token("nanning-162", "+3. A ship."),
        card(62, "+2. The squadron card, on top of any tokens you already killed.")
      ]),
      h("div", { class: "vp-row" }, [
        h("span", {}, ["+1 more"]),
        h("i", { class: "vp-box filled" }),
        h("span", { class: "visual-note" }, ["for the airbase box. Those four events are 1 + 3 + 2 + 1 = 7 VP."])
      ])
    ]),

    "How you win": () => frame("Points, unless cyber gets there first", [
      cards([
        [51, "Higher VP after the last ATO wins, once both missions are revealed."],
        [34, "Joint Offensive Cyber is how a high rate deletes a lot of pieces. It is also a step toward rate 4."]
      ]),
      note("Rate 4 does not wait for this card to be scored. The game ends the moment the track hits 4, and the VP lead is ignored.")
    ]),

    "Between ATO cycles": () => frame("What is still on the table", [
      h("div", { class: "compare" }, [
        h("div", {}, [
          h("h3", {}, ["During the ATO"]),
          felt([
            { name: "Band A", tokens: [{ slug: "f-22", alt: "F-22" }] },
            { name: "US airbase", tone: "us", cards: [5] }
          ])
        ]),
        h("div", {}, [
          h("h3", {}, ["After both pass"]),
          felt([
            { name: "Board clear", tone: "rear", mark: "tokens landed" },
            { name: "US airbase", tone: "us", cards: [5], mark: "card remains" }
          ]),
          h("div", { class: "vp-row" }, [h("i", { class: "vp-box filled" }), h("span", { class: "visual-note" }, ["VP box stays filled"])])
        ])
      ]),
      note("A single damage square on a surviving squadron card is erased. A destroyed card does not come back. Cyber rate and the VP total stay. You draft again from what you have left.")
    ]),

    "The five campaigns": () => frame("Campaign 1 is this picture", [
      cards([
        [10, "You must draft the F-16. It is not your only squadron."],
        [49, "Standard only."],
        [51, "Attrition only. No enabler step at all."]
      ]),
      cards([
        [60, "PRC must draft the J-10 in that same campaign."],
        [61, "Campaign 4 removes long-range bombers like the H-6K."],
        [62, "Campaign 5 removes 5th-generation fighters like the J-20."]
      ]),
      note("Tournament Play on the home screen is Campaign 2: this same Attrition and Standard pair, for two ATOs, with the clocks on.")
    ]),

    "Using this app": () => frame("The screen, built from the real pieces", [
      h("div", { class: "mock" }, [
        h("div", {}, [
          felt([
            { name: "US standoff", tone: "rear", tokens: [{ slug: "aew-us", alt: "AEW" }] },
            { name: "Band A", hot: true, tokens: [{ slug: "f-16c", alt: "F-16" }] },
            { name: "Band D", tokens: [{ down: true, side: "prc", av: "2" }] },
            { name: "PRC airbase", tone: "prc", cards: [60] }
          ], ""),
          h("div", { class: "art-row" }, [card(4, "Your AEW, not yet activated"), card(10, "Your F-16, already in the air")])
        ]),
        h("aside", { class: "mock-side" }, [
          h("h3", {}, ["Choices"]),
          h("div", { class: "mock-choice" }, ["Activate 960th AEW Sq"]),
          h("div", { class: "mock-choice" }, ["Move F-16C → Band B"]),
          h("div", { class: "mock-choice" }, ["Acquire ? (AV 2) with AEW"]),
          h("div", { class: "mock-choice" }, ["Pass / end turn"]),
          h("h3", {}, ["Also on the real screen"]),
          h("p", { class: "visual-note" }, ["A Roll button when a die is yours. An event log. Copy state for AI, which pastes only what you are allowed to see."])
        ])
      ]),
      note("Match the token in the button to the counter on the map before you click. A question mark is still face-down.")
    ]),

    "Easy to miss": () => frame("Five pictures that correct a bad plan", [
      tokens([
        ["ddg-115", "Ships move. One band, on the five center bands only."],
        ["ada-us", "Air-to-air does not kill ADA. Acquire it, then use a surface attack."],
        ["j-20b", "AV 4. Your F-16 needs a raw 4. Your AEW rolls twice and adds 2."]
      ]),
      cards([
        [13, "Forward Observers auto-hits. No hit die, so the shooter does not go Winchester."],
        [12, "A recovered aircraft comes back face-down. They acquire it again."]
      ]),
      felt([
        { name: "Band A", hot: true, tokens: [{ slug: "f-35a", alt: "F-35" }], mark: "shoot" },
        { name: "Band B", reach: true, mark: "then move" },
        { name: "US standoff", tone: "rear", tokens: [{ slug: "aew-us", alt: "AEW" }], mark: "and acquire" }
      ]),
      note("Shoot, move, and acquire can share a turn, in any order, on different counters. Launching a squadron cannot share that turn. And both players must pass in a row before the ATO ends.")
    ])
  };

  document.querySelectorAll("article.lesson").forEach((article) => {
    const build = builders[article.dataset.title];
    if (!build || article.querySelector(":scope > .visual")) return;
    const heading = article.querySelector("h2");
    if (heading) heading.insertAdjacentElement("afterend", build());
  });

  const lite = h("div", { id: "lite", hidden: "" }, [h("img", { alt: "" }), h("p", {}, [])]);
  document.body.append(lite);
  function open(src, alt) {
    lite.querySelector("img").src = src;
    lite.querySelector("img").alt = alt || "";
    lite.querySelector("p").textContent = alt || "Click anywhere to close";
    lite.hidden = false;
  }
  function close() { lite.hidden = true; lite.querySelector("img").src = ""; }
  lite.addEventListener("click", close);
  document.addEventListener("click", (event) => {
    const img = event.target.closest("img");
    if (!img || !img.getAttribute("src") || img.closest("#lite")) return;
    if (!img.src.includes("/art/")) return;
    event.preventDefault();
    const cap = img.closest("figure") && img.closest("figure").querySelector("figcaption");
    open(img.getAttribute("src"), (cap && cap.textContent) || img.alt);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !lite.hidden) {
      event.stopPropagation();
      close();
    }
  }, true);
})();
