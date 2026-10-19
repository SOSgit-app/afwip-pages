/* Credits label on the start panel. Lives outside #root so React cannot wipe it. */
(function () {
  const btn = document.createElement("button");
  btn.id = "menu-credits";
  btn.type = "button";
  btn.textContent = "Credits";
  btn.hidden = true;
  btn.setAttribute("aria-expanded", "false");

  const card = document.createElement("div");
  card.id = "menu-credits-card";
  card.hidden = true;
  card.innerHTML = [
    '<p class="credits-kicker">Credits</p>',
    '<p class="credits-name">Alex Shaffer</p>',
    '<p class="credits-role">Developer</p>',
    '<p class="credits-name">Michael Hernandez</p>',
    '<p class="credits-role">Additional Developer</p>',
  ].join("");

  function place() {
    const menu = document.querySelector(".menu");
    if (!menu) {
      btn.hidden = true;
      card.hidden = true;
      btn.setAttribute("aria-expanded", "false");
      return;
    }
    btn.hidden = false;
    const r = menu.getBoundingClientRect();
    const top = Math.round(r.top + 16);
    const left = Math.round(r.right - 46 - btn.offsetWidth);
    btn.style.top = top + "px";
    btn.style.left = left + "px";
    if (!card.hidden) {
      const b = btn.getBoundingClientRect();
      const sub = menu.querySelector(".subtitle");
      const floor = sub ? sub.getBoundingClientRect().bottom + 10 : b.bottom + 8;
      const width = card.offsetWidth;
      card.style.top = Math.round(floor) + "px";
      card.style.left = Math.round(Math.max(8, b.right - width)) + "px";
    }
  }

  btn.addEventListener("click", (event) => {
    event.stopPropagation();
    card.hidden = !card.hidden;
    btn.setAttribute("aria-expanded", card.hidden ? "false" : "true");
    place();
  });
  document.addEventListener("click", (event) => {
    if (card.hidden) return;
    if (event.target === btn || card.contains(event.target)) return;
    card.hidden = true;
    btn.setAttribute("aria-expanded", "false");
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || card.hidden) return;
    card.hidden = true;
    btn.setAttribute("aria-expanded", "false");
  });

  document.body.append(btn, card);
  window.addEventListener("resize", place);
  window.addEventListener("scroll", place, true);
  const root = document.getElementById("root");
  if (root) {
    new MutationObserver(place).observe(root, { childList: true, subtree: true });
  }
  place();
})();
