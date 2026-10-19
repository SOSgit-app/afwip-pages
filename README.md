# AFWI — GitHub Pages build (browser engine)

This is a **separate copy** of AFWIP for static hosting. The original
`afwip-game-main` Python/FastAPI desktop game is unchanged and remains the
full-featured product (LAN, GPT proxy, ONNX via onnxruntime, PyInstaller).

## What this build does

- Runs the **same Python rules** in the browser via [Pyodide](https://pyodide.org/)
- Keeps the existing React UI (`game/`)
- Supports **Practice vs Agent** (random AI), **Watch Agents**, and **Hotseat**
- Hides network join / GPT for now (desktop build still has them)

## What it does not do yet

- Two-device LAN play
- GPT opponent
- Trained ONNX difficulties in-browser (models are copied under `models/` for a later onnxruntime-web pass)

## Local preview

From this folder (needs network once to fetch the Pyodide CDN):

```bash
python -m http.server 5500
```

Open <http://127.0.0.1:5500/>. First load downloads the Python runtime and can
take a minute; later loads are faster (browser cache).

## Deploy to GitHub Pages

1. Create a new repo under your SOS org (do **not** overwrite the desktop repo).
2. Push this `afwip-pages` folder as that repo’s root on `main`.
3. In GitHub → **Settings → Pages → Source**: **GitHub Actions**.
4. The workflow [`.github/workflows/pages.yml`](.github/workflows/pages.yml) publishes the site.

If the site is at `https://ORG.github.io/REPO/`, asset paths are prefixed
automatically by `js/boot.js`.

## Layout

| Path | Role |
|------|------|
| `index.html` | Boot screen + loads UI after the engine is ready |
| `js/boot.js` | Pyodide + `/api` fetch shim + path prefixing |
| `python/afwip/` | Rules / session (copied from desktop) |
| `python/stubs/` | Tiny pettingzoo/gymnasium stand-ins |
| `python/session_api.py` | In-browser stand-in for FastAPI routes |
| `game/` | Static UI copied from `web/dist` |
| `art/` | Junction/copy of card & token art |
| `models/` | ONNX files reserved for a future browser AI pass |

## Keeping the desktop game safe

Develop and ship classroom/LAN builds from **`afwip-game-main`**. Treat
**`afwip-pages`** as the static demo track. When rules change in desktop,
re-copy `afwip/` (and `web/dist` → `game/`) into this tree and regenerate
`python/manifest.json`.
