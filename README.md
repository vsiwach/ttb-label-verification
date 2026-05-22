# TTB Label Verification

A frontend prototype for the U.S. Treasury's **Alcohol and Tobacco Tax and Trade Bureau** (TTB) AI-assisted label compliance review tool.

Compliance agents upload an alcohol label image, the app extracts the text, compares it field-by-field against the COLA application, audits the mandatory federal Government Warning (27 CFR 16.21 / 16.22), and surfaces only the items that need attention.

**The backend is not built yet.** The app runs against a typed mock client that returns realistic fixtures and simulates streaming over ~2–4 s. Pointing it at the real backend later is a one-line config change.

---

## What's here

| Route | Purpose |
|---|---|
| `/upload` | Drag a label image, downscale on-device, enter the application data, kick off verification. |
| `/result` | Side-by-side label + field verdicts streaming in, Government Warning audit, decision actions with auto-drafted log entry. |
| `/batch` | Drop hundreds of labels; triage dashboard groups them into Needs review / Needs confirm / Auto-pass. |
| `/review` | Keyboard-driven "Confirm next" flow (A/R/I/C/N/P/Esc) — step through attention items in seconds. |
| `/system` | Living design system: 3-state status model, tokens with documented contrast ratios, the TypeScript API contract. |
| `/styleguide` | Component library demo — every primitive with sample data. |
| `/api-demo` | Acceptance check for the streaming mock; runs each scenario with a live log. |

### The 3-state status model

Every field verdict combines **color + icon + text** — never color alone.

- **Match** — green check, "Match"
- **Likely** — amber warning, "Likely match — confirm" (one-click resolve)
- **Flag** — red alert, "Flag — review"

### Demo scenarios

| Brand | What it demonstrates |
|---|---|
| `OLD TOM DISTILLERY` | All-match happy path with a compliant Government Warning. |
| `STONE'S THROW` | Casing near-match ("STONE'S THROW" vs "Stone's Throw") plus a net-contents flag (750 mL vs 700 mL). |
| `NORTHWIND BREWING` | Government Warning violation — title case, paraphrased wording, sub-minimum type size. |

---

## Run locally

```bash
# 1. Install
npm install

# 2. (Optional) copy the env template — leave VITE_API_BASE_URL blank for mock mode
cp .env.example .env.local

# 3. Dev server → http://localhost:5173
npm run dev

# 4. Production build → ./dist
npm run build

# 5. Preview the production build → http://localhost:4173
npm run preview
```

Open `http://localhost:5173` and you'll land on `/upload`. The mock returns scenario results based on the brand name field, so loading the **STONE'S THROW** sample application will exercise the casing-near-match + flag path end to end.

---

## Configuration — one variable

The app reads **`VITE_API_BASE_URL`** at build time. That's it.

| Value | Behavior |
|---|---|
| _(empty / unset)_ | **Mock mode.** Fixtures from `src/api/mockData.ts` are served, with a simulated 2–4 s streaming delay. This is the default. |
| `https://api.example.gov` | **Live backend.** `verifyLabel` / `verifyBatch` POST to `${VITE_API_BASE_URL}/verify` and `/verify-batch`. |

The detection lives at the top of `src/api/client.ts`:

```ts
const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? '').trim();
const USE_MOCK = API_BASE_URL.length === 0;
```

**No code change is needed to ship against the real backend.** Set the env var in Vercel/Netlify, redeploy, done.

---

## Deploy

The app is a static SPA. Choose either host below. Both expect the production build output (`dist/`).

### Option A — Vercel

1. Push this repo to GitHub / GitLab / Bitbucket.
2. Go to **[vercel.com/new](https://vercel.com/new)** → **Import Project** → pick the repo.
3. Vercel should auto-detect Vite. Confirm:
   - **Framework Preset**: `Vite`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. **(Now or later)** Under **Environment Variables**, leave `VITE_API_BASE_URL` blank for the mock deploy. When the backend ships, paste its URL here and redeploy — that's the only change.
5. Click **Deploy**. ~30 s later you get a `https://<project>.vercel.app` URL.

SPA routing is handled by `vercel.json` (in this repo) — every path rewrites to `index.html`, so refreshing `/result` or `/batch` survives.

### Option B — Netlify

**The drag-and-drop path (no Git needed):**

1. Run `npm run build` locally.
2. Go to **[app.netlify.com/drop](https://app.netlify.com/drop)**.
3. Drag the entire `dist/` folder onto the page.
4. Netlify gives you a `https://<random>.netlify.app` URL within a minute.

The `public/_redirects` file gets copied into `dist/` during build and serves as the SPA fallback — deep links survive refresh.

**The Git-connected path (for continuous deploys):**

1. Push the repo to GitHub / GitLab.
2. Go to **[app.netlify.com](https://app.netlify.com)** → **Add new site** → **Import an existing project**.
3. Netlify reads `netlify.toml` (in this repo) and pre-fills:
   - **Build command**: `npm run build`
   - **Publish directory**: `dist`
4. **(Now or later)** Under **Site settings → Environment variables**, set `VITE_API_BASE_URL` when the backend exists; redeploy via the Netlify UI.
5. Click **Deploy site**.

---

## Sanity checklist before sharing the URL

Tab through each of these on the deployed link:

- [ ] App loads at `/` (or `/upload`) with the government banner, header, skip-to-content link, and no console errors.
- [ ] **Tab from the very top** — focus lands on **Skip to main content** first, with a visible gold ring.
- [ ] `/upload` → load **OLD TOM DISTILLERY** → drop any JPG/PNG → "Optimized for fast upload" appears with real before/after sizes → submit reaches `/result`.
- [ ] `/result` streams field rows in over ~2–4 s; Government Warning panel renders "Compliant"; decision panel's Approve card is **Recommended**.
- [ ] Repeat with **STONE'S THROW** → brand row shows amber **Likely**, net-contents shows red **Flag**, Reject card is **Recommended**, suggested-reason checkbox is pre-checked.
- [ ] Repeat with **NORTHWIND BREWING** → Government Warning shows red "3 issues found" with diff highlighting + plain-language deviation bullets.
- [ ] `/batch` → "+ Add 75 mock labels" → "Process 75 labels" → progress bar advances; needs-review / needs-confirm sections surface; auto-pass collapsed.
- [ ] `/batch` → **Start review** → keyboard `A` / `R` / `I` / `C` / `N` / `P` / `Esc` all work; typing in a textarea suppresses them.
- [ ] **Refresh on `/result`** (or any deep link) — it should NOT 404. The SPA-fallback config takes care of this.
- [ ] Shrink the window to ~360 px or open DevTools mobile emulation — every page reflows with no horizontal scroll.
- [ ] Run a Lighthouse a11y audit on `/upload` — expect ≥ 95.

---

## Switching to the real backend (later)

When the backend exists at, say, `https://api.ttb-label-verification.example.gov`:

**Vercel:**
1. Project → **Settings → Environment Variables** → add `VITE_API_BASE_URL` = the URL.
2. **Deployments → Redeploy** the most recent build.

**Netlify:**
1. Site → **Site configuration → Environment variables** → add `VITE_API_BASE_URL`.
2. **Deploys → Trigger deploy → Deploy site**.

No code change. The client picks it up at build time and `USE_MOCK` flips to `false`.

---

## File layout

```
.
├── src/
│   ├── api/
│   │   ├── types.ts        # The TTB API contract (single source of truth)
│   │   ├── ttbRules.ts     # Required fields per beverage type
│   │   ├── mockData.ts     # Three demo scenarios + saved application records
│   │   └── client.ts       # verifyLabel / verifyBatch (mock + real)
│   ├── components/         # StatusBadge, Button, Card, FileDropzone, FieldRow…
│   ├── pages/              # Upload, Result, Batch, Review, Styleguide, System, ApiDemo
│   └── utils/
│       └── downscaleImage.ts
├── public/
│   └── _redirects          # SPA fallback for Netlify drag-and-drop
├── .env.example            # Environment variable template
├── vercel.json             # Vercel SPA rewrite + security headers
├── netlify.toml            # Netlify build config + SPA fallback + headers
└── README.md
```

---

## Accessibility commitment

This is a federal application, so the bar is **Section 508 / WCAG 2.1–2.2 AA** at minimum. Specific commitments baked into the codebase:

- Color contrast ≥ 4.5 : 1 for body text, ≥ 3 : 1 for large text and UI components.
- Every status combines color + icon + text — never color alone.
- Visible 3 px gold focus ring on every interactive element (≥ 6.9 : 1 contrast).
- Skip-to-content link is the first focusable element.
- All inputs have real `<label>`s; errors associate via `aria-describedby` and use plain-language messages.
- Primary actions are ≥ 44 × 44 px; incidental controls ≥ 24 × 24 px.
- Body text 16 px / 1.5 line height; paragraph measure capped at ~66 ch.
- Streaming results respect `prefers-reduced-motion`.
- Keyboard-only operation is fully supported, including the "Confirm next" review flow.

See `/system` in the app for the full design system and `/styleguide` for the component library.

---

## Evaluation harness

End-to-end accuracy harness against real COLA labels lives in `test/eval/`.

### Two gates

```
make eval-synth   # MUST be 100% — deterministic CI gate (no API key)
make eval-real    # accuracy report on real COLA labels (cloud mode; not a gate)
```

`make eval-synth` boots the backend in mock mode, drives the 9 synthetic
fixtures in `test/synthetic/` through `/api/verify`, and asserts every
group + per-field + warning verdict is correct. Runs in plain `pytest` too:
```
cd backend && pytest tests/test_eval_synthetic.py
```

`make eval-real` runs the same harness against the COLA Cloud free-sample
labels in `test/eval/data/`. End-to-end accuracy here is AI-bounded; see
`test/eval/ANALYSIS.md` for the most recent run, the targets that apply, and
the engine refinements that landed during eval iteration.

### Building the real dataset

```
make build-eval-data
```
Pulls the COLA Cloud CC0 sample (~1,000 records), filters to images where the
Government Warning is visible in OCR text, drops keg-size ambiguity, stratifies
across 23 categories, and emits `test/eval/data/cola_sample.csv` + downloaded
WebP images. Adds 8 mutation rows (declared net contents / brand / ABV
mutations on real labels) so the harness can score rejection-detection.

### Running real labels through the system

```
echo "ANTHROPIC_API_KEY=sk-ant-..." > backend/.env
echo "INFERENCE_MODE=cloud"        >> backend/.env
make serve-cloud      # in one terminal
make eval-real        # in another; report → test/eval/report.md
```

---

## Coverage: what's handled vs flagged for human review

The rules engine has two responsibilities: **decide** what it has high
confidence about (with an auditable citation), and **route the rest to
human review** with an explicit reason. Nothing is silently auto-passed.

See **[docs/COVERAGE.md](docs/COVERAGE.md)** for the complete matrix:
- A. Field matching — every rule that can produce `match` / `likely` / `flag`
- B. Mandatory fields per beverage type (with 27 CFR citations)
- C. Government Warning checks (16.21 verbatim + 16.22 format)
- D. Cases explicitly out of prototype scope
- E. Image-quality routing
- F. Inference layer — what the engine trusts vs verifies
- G. Test surface — where the 100% guarantee lives

### Quick summary

**Deterministic 100% gates (rules engine, no AI):**
- 62 unit tests covering every field-matching and warning rule
- 9 synthetic-fixture cases run through the live FastAPI in mock mode
- Both run in plain `pytest` and in CI

**Conservative-by-design behaviour on real labels:**
- Low-confidence extractions are downgraded — a confident-but-wrong AI
  read can never auto-pass
- Multi-image realities (warning on a back panel, ABV on a front panel)
  route missing fields to "needs-confirm" with a clear note, not "flag"
- Unmeasurable font size routes to "please confirm manually" with the
  16.22 threshold cited
