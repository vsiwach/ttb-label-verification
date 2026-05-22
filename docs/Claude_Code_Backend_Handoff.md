# Claude Code Backend — Handoff Guide + One-Shot Prompt

You've finished the frontend in Claude Design. This guide moves everything into Claude Code to build the backend that matches your locked contract.

---

## Step 1 — Get the frontend code onto your machine

Claude Code works inside a real project folder, so the frontend needs to live in one. In order of ease:

- **Best — Publish to GitHub / Export / Download:** In Claude Design, look for a project menu (often a "⋯", a `</>` code view, or a "Publish"/"Export"/"Download" control). If it can push to **GitHub**, do that, then `git clone` the repo locally. If it offers a **download/zip**, save and unzip it.
- **Fallback — let Claude Code rebuild it from the files:** If you can't find an export, open Claude Code in a new empty folder and paste the printed file contents (same way you shared the `src/api` files with me), telling it: *"Create these files at these exact paths."* Claude Code will write them to disk. Do this for every file Claude Design generated.

Either way you should end up with a folder like `ttb-label-verification/` containing `package.json`, `src/`, etc. Confirm it runs: `npm install` then `npm run dev`.

## Step 2 — Drop the context docs into the project

Create a `docs/` folder inside the project and copy these three files into it (they're in your Cowork workspace folder):

- `PRD_TTB_Label_Verification.md` (or the .docx) — product, architecture, the Government Warning engine (§9), Model Strategy (§15), Implementation Plan (§17).
- `TTB_API_Contract_Reference.md` — the EXACT contract + the handoff notes.
- `TTB_Label_Verification_Prompts_Playbook.md` — Part B has the backend build steps.

## Step 3 — (Recommended) Add a CLAUDE.md so Claude Code auto-loads context

Create a file named `CLAUDE.md` in the project root with this:

```
# TTB Label Verification

This repo has a React + Vite + TypeScript frontend (src/) that currently runs on
mock data (USE_MOCK = true in src/api/client.ts). We are now building a Python
FastAPI backend that implements the SAME typed API contract.

Before working on the backend, read:
- docs/TTB_API_Contract_Reference.md  (the exact contract — implement precisely)
- docs/PRD_TTB_Label_Verification.md  (architecture; Government Warning engine §9)
- docs/TTB_Label_Verification_Prompts_Playbook.md  (Part B = backend build steps)

Golden rule: the AI model only extracts + scores what it reads; a deterministic
27 CFR rules engine makes every pass/flag decision and cites the regulation.
```

Claude Code reads `CLAUDE.md` automatically, so it always has the context.

## Step 4 — Open Claude Code and paste the one-shot prompt

Install Claude Code if you haven't, open a terminal, `cd` into the project folder, run `claude`, then paste the **one-shot prompt below**.

## Step 5 — Connect the two halves

When the backend runs, set `USE_MOCK = false` in `src/api/client.ts`, create `.env` with `VITE_API_BASE_URL=http://localhost:8000/api` (or wherever the backend listens), confirm CORS allows the frontend origin, and run both. All your mock scenarios should now flow through the real backend.

---

## THE ONE-SHOT CLAUDE CODE PROMPT

Paste everything in the box below into Claude Code:

```
You are building the BACKEND for an AI-Powered Alcohol Label Verification app for
the U.S. Treasury's TTB. This repo already has a React + Vite + TypeScript frontend
in src/ that calls a typed API and currently runs on mock data (USE_MOCK = true in
src/api/client.ts). Build a Python + FastAPI backend that implements the SAME
contract exactly, so we can flip USE_MOCK to false and point VITE_API_BASE_URL at it.
I'm not a developer — give complete, runnable code, run commands, and explain briefly.

FIRST, read these files in the repo and treat them as the spec:
- docs/TTB_API_Contract_Reference.md  — the EXACT API contract + handoff notes. Implement it precisely.
- docs/PRD_TTB_Label_Verification.md   — architecture; the Government Warning engine (§9); Model Strategy = use a pretrained model, do NOT train (§15).
- docs/TTB_Label_Verification_Prompts_Playbook.md — Part B is the backend build breakdown.
Also read src/api/types.ts, src/api/client.ts, src/api/mockData.ts, src/api/ttbRules.ts — the contract is defined there.

NON-NEGOTIABLE CONTRACT RULES (from the reference doc):
- POST /api/verify — multipart FormData: `image` (file) + `applicationData` (JSON string) -> return the FULL VerificationResult as ONE JSON response. Do NOT use SSE/streaming — the frontend's real path does res.json(). (The field-by-field streaming is a frontend-only illusion.)
- POST /api/verify-batch — multipart FormData: repeated `images` + optional `applicationData` -> return BatchItemResult[] (a JSON array).
- Match the shapes EXACTLY: FieldStatus 'match'|'likely'|'flag'; VerificationField; GovernmentWarningAnalysis (regulation literal '27 CFR 16.21/16.22'); ImageQuality; ApplicationData (beverageType 'spirits'|'wine'|'beer'|'malt'); BatchItemResult with group 'auto-pass'|'needs-confirm'|'needs-review'.
- Replicate the groupFor() bucketing logic from types.ts on the server.
- Keep the VERBATIM_GOVERNMENT_WARNING constant identical to the frontend's.

ARCHITECTURE (the whole point):
- The model ONLY extracts fields + the warning text/style observations + confidence. It makes NO pass/fail decision.
- A DETERMINISTIC 27 CFR rules engine makes every match/likely/flag decision and the Government Warning verdict, and attaches the regulation citation. This module has NO AI and is fully unit-tested.
- Put inference behind a swappable interface selected by env: INFERENCE_MODE = mock | cloud | onprem. Build mock first, then cloud, and stub onprem.

BUILD ORDER (condensed from Part B — do these in sequence, commit after each, show tests passing):
1. Scaffold FastAPI (typed, async), config (.env), CORS for the frontend origin, /health, and a MOCK inference path returning the same fixtures as src/api/mockData.ts so the frontend connects immediately.
2. Inference interface + a CLOUD vision-LLM adapter (provider configurable; single-pass structured JSON; transcribe the Government Warning EXACTLY, preserving case/wording; report whether 'GOVERNMENT WARNING' is caps+bold, approx text height, contrast, separateness). Keep INFERENCE_MODE=mock working with no API key.
3. The 27 CFR RULES ENGINE + thorough unit tests: 3-state field matching with normalization (STONE'S THROW vs Stone's Throw -> 'likely'; 750 mL vs 700 mL -> 'flag'); mandatory fields by beverage type; the Government Warning checks (verbatim vs the constant, ALL-CAPS+bold, font-size-vs-container [<=237mL 1mm / <=3L 2mm / >3L 3mm], contrast, separate-and-apart) with plain-language deviations.
4. Image pipeline (Pillow): legibility/quality score + evidence crops (ephemeral; never persisted).
5. Batch endpoint with async bounded-concurrency fan-out; compute `group` via the same logic.
6. ON-PREM adapter (INFERENCE_MODE=onprem), no outbound calls: local OCR (PaddleOCR/Tesseract) + a self-hosted small VLM (Microsoft Phi-3.5-vision via Ollama/vLLM at a localhost URL), with graceful OCR-only degradation. NO change to the rules engine, endpoints, or frontend.
7. Security/data handling: in-memory only, no PII persistence, no logging of field VALUES, TLS in deploy notes; OFF-by-default production scaffold (audit log, RBAC stub, retention).
8. Integration tests end-to-end in mock mode; then exact steps to connect the frontend (USE_MOCK=false, VITE_API_BASE_URL, CORS); a Dockerfile; deploy notes for (a) Vercel/Render demo and (b) on-prem/Azure Government with INFERENCE_MODE=onprem.

REFINEMENTS vs the mock data (apply these):
- Use CURRENT post-2020 27 CFR citations in the rules engine: spirits §5.63, wine §4.32, malt §7.63, warning §16.21/§16.22. (The mock's 5.32/5.35 etc. are pre-2020 — shape is unchanged, only the values get corrected.)
- Treat both 'beer' and 'malt' as Part 7 malt-beverage rules (ABV optional unless added nonbeverage flavors).

Start with step 1, get the frontend talking to the real server in mock mode, then proceed. Show me run commands (uvicorn) and a curl example returning valid contract JSON.
```
