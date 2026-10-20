/* Save / Load next to New game: download the decision tape, re-upload to resume. */
(function () {
  const saveBtn = document.createElement("button");
  saveBtn.id = "afwip-save-game";
  saveBtn.type = "button";
  saveBtn.textContent = "Save";
  saveBtn.title = "Download a file you can Load later to continue this game";
  saveBtn.hidden = true;

  const loadBtn = document.createElement("button");
  loadBtn.id = "afwip-load-game";
  loadBtn.type = "button";
  loadBtn.textContent = "Load";
  loadBtn.title = "Open a saved game file and continue where you left off";

  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = "application/json,.json";
  fileInput.hidden = true;

  document.body.append(saveBtn, loadBtn, fileInput);

  function newGameButton() {
    return [...document.querySelectorAll(".topbar button")].find(
      (b) => (b.textContent || "").trim() === "New game"
    );
  }

  function readGame() {
    const el = document.querySelector(".topbar");
    if (!el) return null;
    const m = el.textContent.match(/game\s+([0-9a-f]+)\s+·\s+rev\s+(\d+)/i);
    return m ? { id: m[1], rev: Number(m[2]) } : null;
  }

  function place() {
    const btn = newGameButton();
    if (!btn) {
      saveBtn.hidden = true;
      loadBtn.hidden = true;
      return;
    }
    const bar = btn.closest(".topbar") || btn.parentElement;
    const game = readGame();
    saveBtn.hidden = !game;
    loadBtn.hidden = false;
    // Right of New game: New game → Save → Load
    if (saveBtn.parentElement !== bar || btn.nextSibling !== saveBtn) {
      if (btn.nextSibling) bar.insertBefore(saveBtn, btn.nextSibling);
      else bar.append(saveBtn);
    }
    if (loadBtn.parentElement !== bar || saveBtn.nextSibling !== loadBtn) {
      if (saveBtn.nextSibling) bar.insertBefore(loadBtn, saveBtn.nextSibling);
      else bar.append(loadBtn);
    }
  }

  async function downloadSave() {
    const game = readGame();
    if (!game) return;
    saveBtn.disabled = true;
    try {
      const res = await fetch("/api/games/" + game.id + "/save");
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        window.alert(err.detail || "Could not save this game.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "afwip-save-" + game.id + ".json";
      document.body.append(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      window.alert("Could not save this game.");
    } finally {
      saveBtn.disabled = false;
    }
  }

  async function uploadSave(file) {
    if (!file) return;
    loadBtn.disabled = true;
    try {
      const text = await file.text();
      const save = JSON.parse(text);
      const res = await fetch("/api/games/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ save: save }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        window.alert(err.detail || "Could not load that save file.");
        return;
      }
      const view = await res.json();
      if (typeof window.__afwipApply === "function") {
        window.__afwipApply(view);
      }
      if (view.mode === "human_v_agent" && save.paced !== false) {
        try {
          await fetch("/api/games/" + view.game_id + "/pace", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ on: true }),
          });
          try { localStorage.setItem("afwip_live", "1"); } catch (e) {}
        } catch (e) { /* coach will retry */ }
      }
    } catch (e) {
      window.alert("That file is not a valid AFWIP save.");
    } finally {
      loadBtn.disabled = false;
      fileInput.value = "";
    }
  }

  saveBtn.addEventListener("click", downloadSave);
  loadBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    uploadSave(file);
  });

  setInterval(place, 400);
  place();
})();
