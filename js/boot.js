/* Boot the Pyodide rules engine, then hand control to the React UI. */
(function () {
  const statusEl = () => document.getElementById("afwip-boot-status");
  const setStatus = (msg) => {
    const el = statusEl();
    if (el) el.textContent = msg;
  };

  function detectBase() {
    // Project Pages: /repo/…  — User/org site or local server: /
    const path = location.pathname || "/";
    if (location.hostname.endsWith("github.io")) {
      const parts = path.split("/").filter(Boolean);
      if (parts.length >= 1) return "/" + parts[0] + "/";
    }
    if (path.includes("/game/")) {
      const i = path.indexOf("/game/");
      return path.slice(0, i + 1);
    }
    const dir = path.endsWith("/") ? path : path.replace(/\/[^/]*$/, "/");
    return dir || "/";
  }

  const BASE = detectBase();
  window.AFWIP_BASE = BASE;

  function withBase(url) {
    if (typeof url !== "string") return url;
    if (!url.startsWith("/") || url.startsWith("//")) return url;
    return BASE.replace(/\/$/, "") + url;
  }

  /** Pyodide may pass string | Request | URL | RequestInfo. */
  function requestUrl(input) {
    if (typeof input === "string") return input;
    if (!input) return "";
    if (typeof input.url === "string") return input.url;
    if (typeof input.href === "string") return input.href;
    try {
      return String(input);
    } catch (e) {
      return "";
    }
  }

  // Rewrite absolute root URLs so art/assets work under /repo/ on Pages.
  const origSetAttribute = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (name, value) {
    if (
      (name === "src" || name === "href") &&
      typeof value === "string" &&
      value.startsWith("/") &&
      !value.startsWith("//")
    ) {
      value = withBase(value);
    }
    return origSetAttribute.call(this, name, value);
  };
  const imgDesc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, "src");
  if (imgDesc && imgDesc.set) {
    Object.defineProperty(HTMLImageElement.prototype, "src", {
      configurable: true,
      enumerable: imgDesc.enumerable,
      get: imgDesc.get,
      set: function (value) {
        if (typeof value === "string" && value.startsWith("/") && !value.startsWith("//")) {
          value = withBase(value);
        }
        return imgDesc.set.call(this, value);
      },
    });
  }

  let pyodide = null;
  let readyResolve;
  const ready = new Promise((r) => {
    readyResolve = r;
  });
  window.AFWIP_ENGINE_READY = ready;

  async function apiCall(url, init) {
    await ready;
    const method = (init && init.method) || "GET";
    const body = (init && init.body) || "";
    const full = requestUrl(url);
    const resultJson = await pyodide.runPythonAsync(
      `session_api.handle(${JSON.stringify(method)}, ${JSON.stringify(full)}, ${JSON.stringify(String(body))})`
    );
    const result = JSON.parse(resultJson);
    return new Response(JSON.stringify(result.body), {
      status: result.status,
      headers: { "Content-Type": "application/json" },
    });
  }
  window.__afwipApi = apiCall;

  const origFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    let url = requestUrl(input);
    const original = url;
    if (url.startsWith("/") && !url.startsWith("//")) {
      url = withBase(url);
    }
    if (url.indexOf("/api/") !== -1) {
      return apiCall(url, init || {});
    }
    // Rebased site-relative path → fetch the string URL.
    if (url && url !== original) {
      return origFetch(url, init);
    }
    return origFetch(input, init);
  };

  // Bump when Python sources change so GitHub Pages / browser caches cannot
  // keep serving a stale stub or env.py.
  const PYTHON_CACHE = "watch-copy-tight";

  async function writeTree(pyodideInst, manifest, rootUrl) {
    for (const rel of manifest) {
      const res = await origFetch(rootUrl + rel + "?v=" + PYTHON_CACHE, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error("Failed to load " + rel + " (" + res.status + ")");
      const text = await res.text();
      const virt = "/pages/" + rel;
      const parts = virt.split("/");
      let dir = "";
      for (let i = 1; i < parts.length - 1; i++) {
        dir += "/" + parts[i];
        try {
          pyodideInst.FS.mkdir(dir);
        } catch (e) {
          /* exists */
        }
      }
      pyodideInst.FS.writeFile(virt, text);
    }
  }

  async function boot() {
    setStatus("Loading Python runtime (first visit can take a minute)…");
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js";
    document.head.appendChild(script);
    await new Promise((resolve, reject) => {
      script.onload = resolve;
      script.onerror = () => reject(new Error("Could not load Pyodide from CDN"));
    });

    setStatus("Starting engine…");
    pyodide = await loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.27.5/full/" });

    setStatus("Installing numpy + pydantic…");
    await pyodide.loadPackage(["micropip", "numpy"]);
    const micropip = pyodide.pyimport("micropip");
    await micropip.install("pydantic");

    setStatus("Loading AFWIP rules…");
    const manRes = await origFetch(
      withBase("/python/manifest.json") + "?v=" + PYTHON_CACHE,
      { cache: "no-store" }
    );
    if (!manRes.ok) throw new Error("missing python/manifest.json");
    const manifest = await manRes.json();
    if (!Array.isArray(manifest)) {
      throw new Error("python/manifest.json must be a JSON array of file paths");
    }
    await writeTree(pyodide, manifest, withBase("/python/"));

    await pyodide.runPythonAsync(`
import sys
sys.path.insert(0, "/pages/stubs")
sys.path.insert(0, "/pages")
import session_api
from afwip.env import AFWIPEnv
if not hasattr(AFWIPEnv, "_clear_rewards"):
    raise RuntimeError("AFWIPEnv missing _clear_rewards after Pages load")
`);
    setStatus("Starting game UI…");
    readyResolve();
    const overlay = document.getElementById("afwip-boot");
    if (overlay) overlay.hidden = true;
    window.dispatchEvent(new Event("afwip-engine-ready"));
  }

  window.AFWIP_BOOT = boot;
})();
