# TTB Alcohol Label Verification App — Claude Prompts Playbook

A sequenced set of copy-paste-ready prompts for building an AI-Powered Alcohol Label Verification App (React 18 + Vite + TypeScript frontend; Python/FastAPI backend). Built for a TTB (Alcohol and Tobacco Tax and Trade Bureau) take-home interview project.

### This playbook uses two different Claude tools — read this first

- **Claude Design** builds the **frontend** — the React + Vite interface agents click on. You work in a visual builder with a live preview you can deploy. **Part A (Prompts 0–10)** goes here.
- **Claude Code** builds the **backend** — the API, the AI vision extraction, and the deterministic 27 CFR rules engine that actually decides pass/flag. It runs in a code repo/terminal. **Part B (Prompts B0–B8)** goes here.

Build the frontend first (Part A) against mock data so you have a working, deployable UI immediately. Then build the backend (Part B) to the **same API contract** defined in Part A · Prompt 2. The two halves connect by setting one environment variable (`VITE_API_BASE_URL`) to point the frontend at the real backend — no UI changes. Keep that contract identical on both sides and they snap together.

**Prompt routing — which tool each prompt goes into:**

| Part · Prompt | Paste into | Builds |
|---|---|---|
| **Part A · Prompts 0–10** | **Claude Design** | The full React + Vite frontend: scaffold, components, mock API, upload, result view, Government Warning panel, decisions, batch dashboard, keyboard review, accessibility, deploy |
| **Part B · Prompt B0** | **Claude Code** | Backend scaffold implementing the API contract (mock inference first) |
| **Part B · Prompt B1** | **Claude Code** | Pluggable inference interface + cloud vision-LLM adapter |
| **Part B · Prompt B2** | **Claude Code** | The 27 CFR rules engine — decides pass/flag + cites the reg (+ tests) |
| **Part B · Prompt B3** | **Claude Code** | Image pipeline: evidence crops + legibility/quality score |
| **Part B · Prompt B4** | **Claude Code** | Streaming single-label endpoint (results appear progressively) |
| **Part B · Prompt B5** | **Claude Code** | Batch endpoint — async fan-out for 200–300 labels |
| **Part B · Prompt B6** | **Claude Code** | **On-prem / air-gapped inference adapter — for when cloud is blocked** |
| **Part B · Prompt B7** | **Claude Code** | Security & data handling (ephemeral, no PII storage) |
| **Part B · Prompt B8** | **Claude Code** | Integration tests, connect frontend↔backend, deploy |

---

## How to use this playbook

1. **Paste the prompts in order**, one at a time, into Claude (the AI that generates code / "Claude design"). Each prompt builds on the previous one — don't skip ahead.
2. **After each prompt**, review the generated code and the live preview. If something is off, paste the error or describe the problem and ask Claude to fix it *before* moving to the next prompt.
3. **The backend comes later.** This phase builds a fully working frontend against **mock/stub data** behind a typed, documented API contract. When you later build the real backend (with Claude Code), it implements that same contract and you swap one base URL.
4. **Deploy early and often** to Vercel or Netlify so you always have a shareable link. The final prompt covers deployment.
5. **Keep the API contract stable.** Prompts 2 onward all depend on the types defined in Prompt 2. If you change a field name, tell Claude to update the contract and every consumer.

A few prompts are long. That's intentional — they bake in the exact accessibility numbers, the 3-state status model, and the API contract so the generated app stays consistent. Paste the whole thing.

---

# PART A — Paste these into CLAUDE DESIGN (frontend)

Prompts 0–10 below all go into **Claude Design**. They build the React + Vite frontend against mock data, so you get a working, deployable UI before any backend exists. When you're done here, move to Part B (Claude Code) for the backend.

---

## Prompt 0 — Project setup, ground rules & API contract framing

**Goal:** Scaffold the React + Vite + TS app, lock in the stack, the accessibility bar, the design language, and the API contract as the project's "constitution."

```
You are helping me build the FRONTEND of an "AI-Powered Alcohol Label Verification App" for the U.S. Treasury's TTB (Alcohol and Tobacco Tax and Trade Bureau). I am not a developer — generate complete, runnable code and explain each step briefly.

PHASE: Frontend only. The backend will be built later and will fulfill the API contract we define now. For this phase, everything runs against MOCK data behind a typed API client. Do NOT build a server.

STACK (keep it minimal and deploy-friendly to Vercel/Netlify with zero special build config):
- React 18 + Vite + TypeScript
- React Router for routing
- Plain CSS or CSS Modules with CSS custom properties (design tokens). Do NOT add a CSS framework or component library. We will hand-build a small set of accessible primitives.
- Minimal dependencies. Justify any dependency you add.

ACCESSIBILITY IS A HARD REQUIREMENT (this is a federal app — Section 508 / WCAG 2.1–2.2 AA, following U.S. Web Design System (USWDS) visual conventions). Bake these into the design tokens and base styles now:
- Color contrast >= 4.5:1 for normal text, >= 3:1 for large text and UI components.
- Interactive target size >= 24x24px; primary action buttons >= 44x44px.
- Body text >= 16px; line-height >= 1.5; comfortable line length (~66 characters max for paragraphs).
- NEVER rely on color alone. Every status must combine COLOR + ICON + TEXT label.
- Full keyboard operability with a clearly visible focus ring (a 2px+ outline with offset, high contrast).
- Plain-language, field-specific error messages.
- USWDS look and feel: clean, government-grade, high-contrast, generous whitespace, system-style sans-serif (Source Sans / system-ui stack is fine).

AUDIENCE: compliance agents with a huge range of tech comfort; about half are over 50; the app MUST be usable by a 73-year-old. So: ONE primary action per screen, no hunting for buttons, large legible type, obvious affordances, generous spacing.

THE 3-STATE STATUS MODEL (use this everywhere a field verdict appears):
- 'match'  -> GREEN, check icon, label "Match"
- 'likely' -> AMBER, warning icon, label "Likely match — confirm" (a near-match the agent can one-click Confirm)
- 'flag'   -> RED, alert icon, label "Flag — review"

THE API CONTRACT (the future backend will implement this exactly; for now a mock client returns this shape):
- POST /api/verify  -> input { image: downscaled JPEG blob/dataURL, applicationData } ; output VerificationResult.
- POST /api/verify-batch -> input array of images + optional applicationData ; output array of per-item results (or a jobId + polling).
- VerificationResult = {
    fields: Array<{ fieldName, declaredValue, extractedValue, status: 'match'|'likely'|'flag', confidence: number (0–1), evidenceCropUrl?: string, regulationCite?: string }>,
    governmentWarning: { present: boolean, verbatimMatch: boolean, casingBoldOk: boolean, fontSizeOk: boolean, fontSizeMm?: number | null, fontSizeDpiSource?: 'exif' | 'assumed' | null, contrastOk: boolean, separateAndApart: boolean, detectedText: string, deviations: Array<{ type, message }>, regulation: '27 CFR 16.21/16.22' },
    imageQuality: { score: number (0–1), legible: boolean, note?: string }
  }

LATENCY UX: the real backend will take ~5 seconds. The UI must feel instant: use optimistic UI, skeleton loaders, and STREAM field results in as they arrive (we'll simulate streaming with the mock). NEVER show a blocking full-screen spinner.

TASK FOR THIS STEP ONLY:
1. Scaffold a React 18 + Vite + TypeScript app with React Router.
2. Create a design-token CSS file (:root custom properties) for colors (with the 3 status colors meeting contrast), spacing scale, typography (16px base, 1.5 line-height), radius, and focus-ring styles. Add a documented comment showing the contrast ratio of each status color against its background.
3. Set up a basic app shell: a header with the app name "TTB Label Verification", a skip-to-content link, a main landmark, and routes for: /upload (single), /result, /batch. Stub the pages with placeholder headings for now.
4. Give me the exact terminal commands to run it locally.

Show me the file tree, then the files. Keep it focused on this step — we'll build features in later prompts.
```

**What you should see / acceptance check:** A running app (`npm run dev`) with a header, a working skip link, and three routable placeholder pages. A tokens CSS file with status colors and documented contrast ratios. Tab through the page — the focus ring is clearly visible. No CSS framework was added.

---

## Prompt 1 — Reusable accessible component primitives

**Goal:** Build the small design-system kit (StatusBadge, Button, Card, FileDropzone, FieldRow, etc.) with accessibility baked in, so every screen stays consistent.

```
Now build a small reusable component library in src/components, following the design tokens and accessibility rules we established. Each component must be keyboard-accessible, have a visible focus ring, and never use color alone.

Build these:

1. StatusBadge — props: status ('match'|'likely'|'flag'), optional size. Renders COLOR + ICON + TEXT:
   - match  -> green, check icon, "Match"
   - likely -> amber, warning icon, "Likely match — confirm"
   - flag   -> red, alert icon, "Flag — review"
   Use inline SVG icons (no icon library). Include an aria-label so screen readers announce the status text. Ensure the badge background/foreground meets >= 4.5:1.

2. Button — variants: primary, secondary, danger, ghost. Primary buttons are >= 44x44px; all interactive targets >= 24x24px. Visible focus ring. Disabled state has a non-color cue (reduced opacity + not-allowed cursor + aria-disabled). Support an optional leading icon.

3. Card — a simple bordered/padded container with an optional title (renders as a heading at a configurable level for correct document outline).

4. FileDropzone — drag-and-drop OR click to upload. Props: accept (e.g. 'image/jpeg,image/png'), multiple (boolean), onFiles(files). Fully keyboard operable (Enter/Space opens the file picker; it's a real <button> or has role/tabindex done correctly). Shows a clear dashed drop area with plain-language instructions and an obvious icon. Announce drag-over state with text, not just color. Validate file type and show a field-specific error if a wrong type is dropped.

5. FieldRow — displays one verification field: the field label, the declared value, the AI-extracted value, and a StatusBadge. Lay it out as a clear row/grid that stacks on narrow screens. Include a slot for an "evidence" thumbnail and, for 'likely' status, a small inline "Confirm" Button.

6. SkeletonLine / SkeletonBlock — shimmer placeholders for loading states (respect prefers-reduced-motion: no shimmer animation if reduced motion is requested).

7. Alert / Callout — variants info, success, warning, error; icon + text; used for plain-language messages.

Create a temporary /styleguide route that renders one of each component with sample data (including all 3 badge states) so I can visually verify them. Make sure tabbing through the styleguide hits every interactive element with a visible focus ring, in a logical order.
```

**What you should see / acceptance check:** A `/styleguide` page showing all three badge states (each with icon + text, not just color), buttons with visible focus rings, a working dropzone (try dragging a file and clicking), and skeleton placeholders. Tab order is logical; reduced-motion users get no shimmer.

---

## Prompt 2 — Mock API client, types & realistic mock data

**Goal:** Define the typed API contract once, with a mock client that simulates ~2–4s latency and streaming, including the STONE'S THROW near-match and a title-case Government Warning violation.

```
Create the typed API contract and a MOCK client that the whole app will use. This is the single source of truth for data shapes — the future real backend will implement the same contract, so keep it clean and documented.

1. src/api/types.ts — export all TypeScript types for the contract:
   - VerificationField { fieldName, declaredValue, extractedValue, status: 'match'|'likely'|'flag', confidence: number, evidenceCropUrl?: string, regulationCite?: string }
   - GovernmentWarningAnalysis { present, verbatimMatch, casingBoldOk, fontSizeOk, contrastOk, separateAndApart, detectedText, deviations: Array<{ type: string, message: string }>, regulation: '27 CFR 16.21/16.22' }
   - ImageQuality { score: number, legible: boolean, note?: string }
   - VerificationResult { fields: VerificationField[], governmentWarning: GovernmentWarningAnalysis, imageQuality: ImageQuality }
   - ApplicationData { brandName, classType, alcoholContent, netContents, bottlerNameAddress, countryOfOrigin?, beverageType: 'spirits'|'wine'|'beer'|'malt' }
   - BatchItemResult { id, fileName, thumbnailUrl, result: VerificationResult, group: 'auto-pass'|'needs-confirm'|'needs-review' }

2. src/api/client.ts — a typed client with two functions and a clear comment block documenting the contract (endpoints, inputs, outputs):
   - verifyLabel(image, applicationData, onField?) : streams fields. Simulate streaming by resolving fields one at a time over ~2–4s total via a callback (onField) or an async iterator, then resolve the governmentWarning and imageQuality at the end. Add a small random per-field delay.
   - verifyBatch(files, applicationData?, onItem?) : fans out, emitting BatchItemResult objects over time so the dashboard can update progressively.
   A single MOCK flag (e.g. const USE_MOCK = true) and a comment showing where to point at the real API base URL later (read from import.meta.env.VITE_API_BASE_URL).

3. src/api/mockData.ts — realistic TTB mock fixtures. Include AT LEAST these scenarios:

   Scenario A (the demo star) — a spirits label "OLD TOM DISTILLERY":
   - brandName declared "OLD TOM DISTILLERY" / extracted "OLD TOM DISTILLERY" -> match
   - classType "Kentucky Straight Bourbon Whiskey" -> match
   - alcoholContent "45% Alc./Vol. (90 Proof)" -> match
   - netContents "750 mL" -> match
   - bottlerNameAddress -> match
   - Government Warning: present, verbatim match TRUE, casing/bold OK, font size OK, contrast OK, separate and apart OK. detectedText = the exact verbatim text below. imageQuality score ~0.92, legible.

   Scenario B (near-match / amber) — brand on the application is "STONE'S THROW" but the label reads "Stone's Throw":
   - brandName declared "STONE'S THROW" / extracted "Stone's Throw" -> status 'likely', confidence ~0.88, with a note that it's a casing difference (one-click confirm).
   - Include one other 'match' field and one 'flag' field (e.g. netContents declared "750 mL" / extracted "700 mL" -> flag).

   Scenario C (Government Warning violation) — a label where the warning is in Title Case and slightly paraphrased:
   - governmentWarning.present TRUE, verbatimMatch FALSE, casingBoldOk FALSE, fontSizeOk FALSE (sub-minimum font), contrastOk TRUE, separateAndApart TRUE.
   - detectedText = a Title Case, paraphrased version (e.g. "Government Warning: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy ...").
   - deviations: [{type:'casing', message:'"GOVERNMENT WARNING" must be all capitals and bold; detected title case.'}, {type:'wording', message:'Statement wording does not match the required verbatim text.'}, {type:'fontSize', message:'Warning text appears below the minimum type size for this container.'}]

   THE EXACT REQUIRED VERBATIM GOVERNMENT WARNING TEXT (store as a constant and use it as the comparison baseline):
   "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems."

   Also include a few mock APPLICATION RECORDS the user can "load" instead of typing (at least the OLD TOM DISTILLERY and STONE'S THROW records).

   For evidenceCropUrl and thumbnails, use placeholder image data URLs or a tiny inline SVG generator so the UI is demonstrable without real images.

4. TTB DOMAIN RULES to encode in a small helper (src/api/ttbRules.ts): mandatory fields differ by beverage type — spirits & wine REQUIRE alcohol content; beer/malt makes ABV optional unless nonbeverage flavors are added. Common required fields for all: brand name, class/type, net contents, name & address of bottler/producer/importer, country of origin (imports only), and the Government Warning (all types). Export a function requiredFields(beverageType) returning the list.

Write the code, then show me a short example of calling verifyLabel and logging the streamed fields so I can confirm streaming works.
```

**What you should see / acceptance check:** A `types.ts` that compiles, a mock client whose example logs fields one-by-one over a couple of seconds (proving streaming), and `mockData.ts` containing the OLD TOM DISTILLERY match scenario, the STONE'S THROW casing near-match, and the Title-Case Government Warning violation with the exact verbatim baseline text stored as a constant.

---

## Prompt 3 — Single-label Upload screen (with client-side downscaling)

**Goal:** Build the upload screen: drag/drop a label image, client-side canvas downscale to ~2MP JPEG, and enter or mock-load the application data to check against.

```
Build the SINGLE-LABEL Upload screen at /upload. ONE primary action: "Verify label". Layout must be clean and obvious for a 73-year-old user — large type, generous spacing, clear labels.

Two sections on the page:

A) UPLOAD THE LABEL IMAGE (use the FileDropzone primitive):
   - Accept image/jpeg and image/png, single file.
   - When a file is selected, show a preview thumbnail and the file name.
   - IMPORTANT — client-side image optimization for latency: before "sending", downscale/compress the image using an HTML canvas to roughly 2 megapixels max (preserve aspect ratio), exported as JPEG at ~0.85 quality. Put this in a reusable util src/utils/downscaleImage.ts (input File -> output { blob, dataUrl, width, height }). Show the user a small note like "Optimized for fast upload (was 4.1 MB, now 0.6 MB)" using real before/after sizes. Handle errors gracefully (e.g., corrupt image) with a plain-language message.
   - Show an inline image-quality hint after optimization is fine; the real legibility score comes from the API later.

B) APPLICATION DATA TO CHECK AGAINST:
   - A form with these fields: Brand name, Class/Type, Alcohol content, Net contents, Name & address of bottler/producer/importer, Country of origin (only relevant for imports), and a Beverage type selector (Spirits / Wine / Beer / Malt).
   - Use the requiredFields(beverageType) helper from ttbRules.ts to mark which fields are required for the chosen beverage type (e.g., alcohol content is required for spirits & wine, optional for beer/malt). Required fields get a visible required indicator (text "(required)", not color alone) and field-specific validation messages.
   - Provide a "Load a sample application" control that populates the form from the mock application records (OLD TOM DISTILLERY, STONE'S THROW) so the user can demo without typing.

VALIDATION & SUBMIT:
   - The primary "Verify label" button is disabled (with a non-color cue) until an image is present and required fields are filled. When disabled, show a plain-language hint about what's missing.
   - On submit: navigate to /result and pass the downscaled image + applicationData (via router state or a lightweight context/store — no heavy state library). Do NOT block the UI; the result screen will handle streaming.

Accessibility: every input has a real <label>, errors are associated via aria-describedby, the form is fully keyboard navigable, and the heading structure is correct. Make the form forgiving — never lose the user's typed data on a validation error.

Show me the screen working with the sample loader.
```

**What you should see / acceptance check:** At `/upload`, you can drag in a JPG/PNG, see a preview, and see a real before/after size note proving the canvas downscale ran. "Load a sample application" fills the form. The beverage-type selector changes which fields are marked required. The "Verify label" button stays disabled with a clear hint until requirements are met, then navigates to `/result`.

---

## Prompt 4 — Single-label Verification Result view (streaming, side-by-side, evidence crops)

**Goal:** Build the result screen with the label image on the left and per-field verdicts streaming in on the right, with skeleton loaders, 3-state badges, evidence crops, and one-click Confirm for amber.

```
Build the SINGLE-LABEL Verification Result view at /result. It receives the downscaled image + applicationData from the Upload screen and calls the mock verifyLabel client.

LAYOUT — side by side on wide screens, stacked on narrow screens:
- LEFT: the uploaded label image, large and clear. Below it, an IMAGE QUALITY indicator showing the legibility score (e.g., a labeled meter "Image quality: 92% — Legible" with icon + text, not color alone). If the score is low / not legible, show an Alert prompting the agent to request a better image.
- RIGHT: a heading "Field verification" and a list of FieldRow components.

STREAMING / OPTIMISTIC UI (this is important — never a blocking spinner):
- As soon as the screen loads, render the list of EXPECTED fields (from applicationData) as SKELETON rows immediately.
- Call verifyLabel and, as each field result streams in, replace its skeleton with the real FieldRow (declared value, extracted value, StatusBadge). Use a subtle fade/slide-in (respect prefers-reduced-motion).
- Show a small live status like "Verifying… 3 of 6 fields checked" with an aria-live="polite" region so screen-reader users hear progress.

PER-FIELD BEHAVIOR:
- Each FieldRow shows declared vs extracted value and the 3-state StatusBadge (match / likely / flag).
- EVIDENCE: each field has an "Show evidence" affordance that reveals the cropped evidence region (evidenceCropUrl) — e.g., an expandable panel or a small thumbnail that enlarges. Keyboard accessible; the toggle has aria-expanded.
- For 'likely' (amber) fields, show a one-click "Confirm" button inline. Confirming flips that field to 'match' locally and announces the change via aria-live. (This is the STONE'S THROW casing case.)
- Sort or visually prioritize so flags/likely are easy to find, but keep all fields visible.

SUMMARY BAR at the top of the right column: counts like "4 Match · 1 Likely · 1 Flag" using icon + text, and a one-line plain-language summary ("1 field needs review before you can approve").

Leave a clearly marked placeholder slot where the Government Warning panel (next prompt) and the Decision actions (prompt after) will go.

Wire it to the mock so I can run the OLD TOM DISTILLERY (all match) and STONE'S THROW (amber + flag) scenarios end to end from the Upload screen.
```

**What you should see / acceptance check:** Skeleton rows appear instantly, then each field pops in over ~2–4s (real streaming feel, no full-screen spinner). The image is on the left with a legibility meter; fields are on the right with icon+text badges. The STONE'S THROW row shows an amber "Likely match — confirm" with a working Confirm button that flips it to green and announces the change. "Show evidence" reveals a crop and is keyboard-toggleable.

---

## Prompt 5 — Government Warning analysis panel

**Goal:** Build the marquee feature: a panel that verifies the mandatory federal Government Warning for verbatim text, ALL-CAPS + bold title, font-size and contrast minimums, and "separate and apart," with deviations highlighted and the regulation cited.

```
Build the GOVERNMENT WARNING ANALYSIS panel and place it in the reserved slot on the /result screen. This is the most important compliance feature — make it prominent, clear, and authoritative. It reads the governmentWarning object from the VerificationResult.

The panel shows, as a checklist of discrete compliance checks (each is icon + text + pass/fail label, never color alone):
1. Statement present
2. Exact verbatim wording matches the required text (verbatimMatch)
3. "GOVERNMENT WARNING" is ALL CAPS and bold (casingBoldOk)
4. Type size meets the minimum for the container size (fontSizeOk)
5. Legibility / contrast meets the minimum (contrastOk)
6. "Separate and apart" from other label copy (separateAndApart)

Each check uses the 3-state visual language where it makes sense (pass = green check "OK"; fail = red alert "Does not comply"); for borderline items you may use amber "Confirm". 

DETECTED TEXT WITH DEVIATIONS HIGHLIGHTED:
- Show the detectedText from the label.
- Compare it against the required verbatim baseline constant and visually highlight the differences (e.g., title-case "Government Warning" vs required "GOVERNMENT WARNING", paraphrased phrases, missing/changed words). Use a clear, accessible diff style — highlight + an explicit text note for each deviation, not color alone. Render the deviations[] list as plain-language bullet points.
- Show the REQUIRED text alongside or on toggle, clearly labeled "Required text" vs "Detected on label", so the agent can see exactly what's wrong.

REGULATORY CITATION:
- Cite the regulation prominently: "Per 27 CFR 16.21 and 16.22 (Health Warning Statement requirements)." Display the governmentWarning.regulation field.

OVERALL VERDICT:
- A clear top-line: e.g., "Government Warning: COMPLIANT" (green, check) or "Government Warning: 3 issues found — review required" (red, alert), icon + text.

Make it fully keyboard accessible, with an aria-live announcement of the overall verdict when results arrive. Test it with both Scenario A (compliant — OLD TOM DISTILLERY) and Scenario C (title-case + paraphrased + sub-minimum font violation), and show me both.
```

**What you should see / acceptance check:** The compliant scenario shows all six checks passing with a green "COMPLIANT" headline. The violation scenario flags the title-case casing, the paraphrased wording, and the sub-minimum font, with the detected text shown next to the required verbatim text and the specific differences highlighted plus written-out deviation bullets. "27 CFR 16.21 / 16.22" is cited. Verdict is announced to screen readers.

---

## Prompt 6 — Decision actions + auto-drafted log entry

**Goal:** Add the no-dead-ends decision controls: Approve, Reject (with auto-suggested reasons from the flags), or Request better image — each auto-drafting an editable log entry.

```
Add a DECISION ACTIONS section to the /result screen, in the reserved slot below the field list and Government Warning panel. The principle: NO DEAD ENDS — whatever the verification shows, the agent always has a clear next action. ONE primary action emphasized based on context.

THREE actions, as large clear buttons (primary >= 44px):
1. APPROVE — primary/positive. Enabled when there are no unresolved flags (or after the agent overrides). If there are unresolved flags or an amber not yet confirmed, show a plain-language note explaining what should be resolved first, but still allow an explicit override path (don't trap the user).
2. REJECT (with reason) — opens a reason form. AUTO-SUGGEST reasons derived from the current result: every 'flag' field and every failed Government Warning check becomes a checkable suggested reason (e.g., "Net contents mismatch: declared 750 mL, label shows 700 mL", "Government Warning not in required verbatim wording", "Warning text below minimum type size"). The agent can check/uncheck suggestions and add free-text. At least one reason required to reject.
3. REQUEST BETTER IMAGE — for low legibility / unreadable fields; auto-fills a short message referencing the image-quality score.

AUTO-DRAFTED LOG ENTRY:
- When the agent selects an action, auto-draft a structured, editable log entry (a textarea pre-filled) summarizing: the label/brand, the decision, the reasons (from selected suggestions + free text), the Government Warning verdict, the timestamp, and the agent's name placeholder. The agent can edit it, then click "Confirm & save log".
- On confirm, show a success Alert ("Decision recorded. Log saved.") and offer obvious next steps: "Verify another label" and "Back to batch" (if applicable) — again, no dead ends.
- For now, "saving" just stores to local state / localStorage and would later POST to the backend; add a clearly commented TODO for the future endpoint.

Accessibility: the reason form is fully keyboard operable, suggestions are real checkboxes with labels, the auto-drafted textarea is labeled, and action results are announced via aria-live. Make sure the auto-drafted text is genuinely editable and never overwrites the agent's edits unexpectedly.

Demo it on the STONE'S THROW + flag scenario (so Reject shows real auto-suggested reasons) and on the all-match OLD TOM DISTILLERY scenario (so Approve is the obvious primary action).
```

**What you should see / acceptance check:** On a clean scenario, Approve is the emphasized action and recording it produces an editable, pre-filled log entry. On the flag scenario, Reject opens with real auto-suggested reasons pulled from the mismatched field and the Government Warning failures as checkboxes. Request better image references the legibility score. After confirming, you get a success message and clear next-step links — never a dead end.

---

## Prompt 7 — Batch upload + triage dashboard

**Goal:** Build the bulk flow: drag a folder / multi-select 200–300 images, simulate async fan-out, and show a triage dashboard grouping results into auto-pass / needs-confirm / needs-review.

```
Build the BATCH flow at /batch. Goal: an agent can upload 200–300 label images at once and quickly see only the ones that need attention.

UPLOAD:
- Use FileDropzone in multiple mode; allow selecting many files (multi-select) and dragging a folder of images. Show the count selected and total size, and run the same canvas downscale util on each image before "sending".
- Optionally let the agent attach one shared applicationData set or run without it (image-only checks like Government Warning still apply). Keep it simple.

PROCESSING (simulate async fan-out with the mock verifyBatch):
- Show overall progress: a labeled progress bar ("Processing 312 labels — 148 done") with icon + text and an aria-live polite count. Never a blocking spinner — results stream in and the dashboard fills progressively.
- Each item resolves to a BatchItemResult with a group: 'auto-pass' (all fields match AND warning compliant), 'needs-confirm' (has amber/likely but no flags), 'needs-review' (has any flag or warning failure).

TRIAGE DASHBOARD:
- Three clear group cards/columns with counts and icon + text: "Auto-pass", "Needs confirm" (amber), "Needs review" (red). SURFACE ATTENTION FIRST: order them review → confirm → pass, or visually emphasize the ones needing attention. Auto-pass can be collapsed by default ("289 passed automatically — expand to see").
- Each item row shows a thumbnail, file name, brand (if extracted), the group badge, and a quick summary ("Net contents mismatch", "Warning: title case"). Clicking an item (or pressing Enter) opens its full result (reuse the /result view, or a detail panel) — and keep a "Back to dashboard" path.
- A prominent primary button: "Start review" / "Confirm next" that launches the keyboard review flow (next prompt) over the items needing attention.
- Provide filters/tabs (All / Needs review / Needs confirm / Auto-pass) and a count of how many still need action.

Performance: 200–300 rows must scroll smoothly — render efficiently (virtualize if needed, or keep rows lightweight) but keep dependencies minimal. Generate enough mock batch items (mix of pass/confirm/review, including some STONE'S THROW-style amber and some warning violations) to make the dashboard realistic.

Show me the dashboard processing a few hundred mock items with the three groups populating live.
```

**What you should see / acceptance check:** At `/batch`, multi-selecting/dropping many images kicks off a progressive fill — a labeled progress bar and counts update live (no blocking spinner). Results land in three groups (review/confirm/pass) with icon+text badges; auto-pass is collapsed by default so attention items are surfaced first. Clicking an item opens its detail; a prominent "Start review" / "Confirm next" button is present. A few hundred mock rows scroll smoothly.

---

## Prompt 8 — Batch keyboard "Confirm Next" review flow

**Goal:** A fast, keyboard-driven flow to step through flagged labels one at a time with minimal clicks.

```
Build the keyboard-driven "CONFIRM NEXT" review flow, launched from the batch dashboard. It steps the agent through ONLY the items needing attention (needs-review then needs-confirm), one at a time, with minimal clicks and strong keyboard support.

LAYOUT (one item at a time, full focus):
- Show the current item's label image (left) and its field verdicts + Government Warning panel (right) — reuse the components from the single-label result view.
- A clear progress indicator: "Item 4 of 23 needing attention".
- The decision actions from Prompt 6 (Approve / Reject-with-reason / Request better image) with auto-drafted log entry.

KEYBOARD SHORTCUTS (display a small, visible legend; also expose via a "?" help toggle):
- A = Approve (and advance to next)
- R = Reject (open reason form; pre-checked suggested reasons; Enter to confirm and advance)
- I = Request better image (and advance)
- C = Confirm all amber/likely fields on this item at once
- N / → = Next item, P / ← = Previous item
- Esc = back to dashboard
Make shortcuts safe: don't fire while the agent is typing in a textarea/input; show which keys are active. Each shortcut also has a visible clickable button (don't force keyboard-only).

FLOW BEHAVIOR:
- After a decision, auto-advance to the next attention item and move focus to a sensible landmark (announce "Item 5 of 23" via aria-live). Maintain a running tally ("18 approved, 3 rejected, 2 pending").
- When finished, show a completion summary screen with counts and a "Back to dashboard" button. No dead ends.
- Decisions update the dashboard groups when the agent returns.

Accessibility: focus management between items is critical — move focus to the item heading on advance, keep a visible focus ring, ensure shortcuts have accessible equivalents, and announce transitions politely. Test stepping through ~5 mock attention items end to end using only the keyboard.

Show me the full keyboard flow working over the mock batch.
```

**What you should see / acceptance check:** From the dashboard, "Start review" / "Confirm next" opens a single-item view stepping only through attention items. Pressing A/R/I records a decision and auto-advances; C confirms all amber fields; N/P navigate; Esc returns. Shortcuts don't fire while typing in a field, each has a visible button equivalent, focus moves to the item heading on advance, and transitions are announced. A completion summary appears at the end.

---

## Prompt 9 — Accessibility & polish pass

**Goal:** A dedicated hardening pass: keyboard nav, focus management, ARIA, contrast audit, plain-language errors, responsive layout, and complete empty/error/loading states.

```
Do a full ACCESSIBILITY AND POLISH PASS across the whole app. Treat this as a Section 508 / WCAG 2.1–2.2 AA audit and fix everything you find. Go screen by screen (upload, result, government warning, decisions, batch dashboard, confirm-next flow) and report what you changed.

CHECK AND FIX:
1. Color contrast: verify every text/background and UI-component pair meets >= 4.5:1 (normal text) / >= 3:1 (large text and UI). List the actual ratios for the status colors and any borderline pairs; adjust tokens if any fail.
2. Color independence: confirm NO status is conveyed by color alone anywhere — every one pairs color + icon + text. Fix any violations.
3. Keyboard: every interactive element reachable and operable by keyboard, logical tab order, visible focus ring everywhere (>= 2px, sufficient contrast), no keyboard traps. Skip-to-content link works.
4. Focus management: on route changes and after streaming/dialog actions, move focus sensibly and announce changes via aria-live. Modals/dialogs (reason form) trap focus and restore it on close.
5. ARIA & semantics: correct landmarks (header/main/nav), heading hierarchy (single h1 per page, no skipped levels), real labels for all inputs, aria-describedby for errors/hints, aria-expanded for disclosures, role/labels on custom widgets. Don't over-ARIA — prefer native elements.
6. Target sizes: interactive targets >= 24x24px; primary actions >= 44x44px. Fix any too-small controls.
7. Typography & readability: body >= 16px, line-height >= 1.5, paragraph line length ~66 chars. Plain language throughout.
8. Plain-language, field-specific errors: review every error/validation message — make them specific and actionable ("Enter the net contents, e.g., 750 mL", not "Invalid input"). No raw technical errors shown to users.
9. Responsive: verify layouts work and stay usable from ~360px mobile up to wide desktop; side-by-side becomes stacked gracefully; text reflows; no horizontal scroll; supports 200% browser zoom.
10. State coverage: every screen has clear EMPTY, LOADING (skeletons, not blocking spinners), ERROR (plain-language with a retry/next action — no dead ends), and SUCCESS states. Handle the mock failing gracefully.
11. Reduced motion: respect prefers-reduced-motion (no shimmer/slide animations).

After fixing, give me a short ACCESSIBILITY SELF-CHECK REPORT: a checklist of each item above marked pass/fixed, the status-color contrast ratios, and any known limitations. Keep dependencies minimal — don't add an a11y framework, just correct the code.
```

**What you should see / acceptance check:** Claude returns a self-check report listing each item as pass/fixed with the actual status-color contrast ratios. Spot-check: tab the whole app keyboard-only with no traps and visible focus everywhere; shrink to ~360px and zoom to 200% with no horizontal scroll; trigger a validation error and confirm the message is specific and plain; enable reduced motion and confirm animations stop. Every screen has empty/loading/error/success states.

---

## Prompt 10 — Deployment to Vercel / Netlify

**Goal:** Make the app deployable to Vercel or Netlify with environment-variable placeholders for the future real API base URL.

```
Prepare the app for deployment to Vercel or Netlify (static SPA, no backend yet). I am not a developer — give me exact, click-by-click steps.

1. Confirm the production build works: provide the build command and verify the output (Vite default: npm run build -> dist). Add SPA routing fallback config so deep links like /result and /batch don't 404 on refresh:
   - Netlify: a public/_redirects (or netlify.toml) rule routing /* to /index.html (200).
   - Vercel: a vercel.json rewrite to /index.html, or note that Vercel handles Vite SPA routing.
2. Environment variables for the FUTURE real API: ensure the mock client reads import.meta.env.VITE_API_BASE_URL and falls back to mock mode when it's empty (USE_MOCK). Add a .env.example documenting VITE_API_BASE_URL. Explain that today we leave it empty (mock mode) and later set it to the real backend URL — no code changes needed to switch.
3. Give me two deployment paths with exact steps:
   a) Vercel: push to a Git repo, import in Vercel, framework preset = Vite, build = npm run build, output = dist, deploy. Where to set VITE_API_BASE_URL later.
   b) Netlify: drag-and-drop the dist folder OR connect the Git repo (build = npm run build, publish = dist). Where to set VITE_API_BASE_URL later.
4. Add a short README section: what the app is, that it currently runs on mock data, how to run locally, how to deploy, and how to point it at the real backend later by setting one env var.
5. Sanity checklist before sharing the link: app loads, all routes work on refresh, mock scenarios (OLD TOM DISTILLERY, STONE'S THROW, warning violation, batch) all demo correctly, no console errors.

Give me everything I need to get a live shareable URL.
```

**What you should see / acceptance check:** A successful `npm run build`, a `dist` folder, and SPA-fallback config so `/result` and `/batch` survive a refresh. A `.env.example` documenting `VITE_API_BASE_URL`, with the app defaulting to mock mode when it's unset. Following the Vercel or Netlify steps yields a live URL where all mock scenarios demo correctly with no console errors.

---

# PART B — Paste these into CLAUDE CODE (backend)

Part B builds the backend the frontend calls. **The golden rule: implement the exact same API contract you defined in Part A · Prompt 2** (`/api/verify`, `/api/verify-batch`, and the `VerificationResult` / `GovernmentWarningAnalysis` shapes). Match the contract and you connect the two halves by setting one environment variable (`VITE_API_BASE_URL`) in the frontend — no UI changes.

Architecture reminder, because it's the whole point: **the AI model only extracts and scores what it sees; a deterministic 27 CFR rules engine makes every pass/flag decision and cites the regulation.** That keeps the legal logic auditable and lets you swap the AI model — **cloud → on-prem (Prompt B6)** — without touching the rules or the UI.

Run these in a new repo/folder with Claude Code. Suggested stack: **Python + FastAPI** (excellent for AI/image work and streaming); Node + Express works equally well — pick one and tell Claude.

---

## Prompt B0 — Backend scaffold + API contract (mock inference first)

**Goal:** Stand up the server implementing the contract so the existing frontend can talk to a real backend immediately.

```
You are building the BACKEND for an AI-Powered Alcohol Label Verification App for the U.S. Treasury's TTB. A React frontend already exists and calls this API. Build it in Python + FastAPI (typed, async). I'm not a developer — give complete runnable code and exact run commands.

Implement EXACTLY this API contract (it MUST match the frontend's types):
- POST /api/verify — input: multipart with an image file (already downscaled client-side) + a JSON applicationData { brandName, classType, alcoholContent, netContents, bottlerNameAddress, countryOfOrigin?, beverageType: 'spirits'|'wine'|'beer'|'malt' }. Output: VerificationResult.
- POST /api/verify-batch — input: many images (+ optional shared applicationData). Output: array of per-item results { id, fileName, result, group }.
- VerificationResult = { fields: Array<{ fieldName, declaredValue, extractedValue, status:'match'|'likely'|'flag', confidence:number, evidenceCropUrl?, regulationCite? }>, governmentWarning: { present, verbatimMatch, casingBoldOk, fontSizeOk, contrastOk, separateAndApart, detectedText, deviations:[{type,message}], regulation:'27 CFR 16.21/16.22' }, imageQuality: { score, legible, note? } }

For THIS step: build the project skeleton, config (pydantic-settings, .env), CORS allowing the frontend origin, structured logging, a /health route, and a MOCK inference path that returns the same fixtures the frontend used (OLD TOM DISTILLERY all-match, STONE'S THROW amber near-match, a Title-Case Government Warning violation) so the frontend can hit a real server right away. Define clear typed Pydantic models for the contract. Give me run commands (uvicorn) and a curl example.
```

**What you should see / acceptance check:** `uvicorn` starts the server; pointing the frontend's `VITE_API_BASE_URL` at it shows the same mock scenarios; `curl` to `/api/verify` returns valid `VerificationResult` JSON.

---

## Prompt B1 — Inference interface + cloud vision-LLM adapter

**Goal:** Put inference behind one swappable interface; first adapter is a cloud vision LLM doing single-pass structured extraction.

```
Refactor inference behind a single interface so the model is swappable. Define an abstract LabelExtractor with one async method: extract(image_bytes, beverage_type) -> ExtractedLabel { fields: {name -> {value, confidence, bbox?}}, warningText, warningStyle {casingAllCaps, bold, approxFontMm?, contrastOk?, separateAndApart?}, imageQuality {score, legible} }. The extractor ONLY reads the image and reports what it sees plus confidence — it makes NO pass/fail decision.

Implement a CloudExtractor adapter that calls a vision LLM (provider configurable via env — Anthropic Claude, OpenAI, or Google Gemini; default to one and document the others). Requirements:
- Single pass: ONE call returns a fixed JSON schema for ALL fields plus the detected Government Warning text and style observations. Use the provider's structured/JSON output mode.
- Prompt the model to transcribe the Government Warning EXACTLY as printed — preserve case and any wording errors, do NOT auto-correct — and to report whether 'GOVERNMENT WARNING' is in capitals and bold, the approximate text height, and whether the warning is visually separate from other text.
- Downscale defensively server-side if the image is large; set a timeout; on error raise a typed InferenceError.
Keep the MOCK extractor too, selected by an env flag (INFERENCE_MODE=mock), so the system runs with no API key. Show me how to switch providers with env vars.
```

**What you should see / acceptance check:** With a real API key, the cloud adapter extracts fields from a real label image in a few seconds; with `INFERENCE_MODE=mock` it still runs fully offline.

---

## Prompt B2 — The 27 CFR rules engine (the heart) + tests

**Goal:** Deterministic, auditable pass/flag decisions with regulation citations. No AI in this module.

```
Build the DETERMINISTIC RULES ENGINE that turns an ExtractedLabel + applicationData into the VerificationResult. NO AI here — pure, unit-tested functions. This is the legal core; it must be auditable and citable.

1. Field matching -> 3 states. For each field, normalize (trim, collapse whitespace, case-fold, normalize apostrophes/quotes/accents) then compare declared vs extracted: 'match' (normalized-equal), 'likely' (close — case/punctuation/styling differences or small edit distance, e.g. "STONE'S THROW" vs "Stone's Throw"), or 'flag' (substantive difference, e.g. "750 mL" vs "700 mL"). Expose thresholds as config. Include the normalized-comparison detail so the UI can explain a 'likely'.

2. Mandatory fields by beverage type (cite sections): spirits (27 CFR 5.63) & wine (4.32) REQUIRE alcohol content; malt/beer (7.63) makes ABV OPTIONAL unless alcohol comes from added nonbeverage flavors. All types require brand name, class/type, net contents, name & address, country of origin (imports), and the Government Warning. A missing mandatory field is a 'flag' with its citation.

3. Government Warning engine (27 CFR 16.21 / 16.22):
   - verbatimMatch: compare extracted warning text to this EXACT baseline, after normalizing ONLY true OCR noise (stray spaces, line-break hyphenation) — do NOT normalize away wording or case. Any reworded/abbreviated/partial text => verbatimMatch=false with a diff of what changed.
     BASELINE: "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems."
   - casingBoldOk: 'GOVERNMENT WARNING' must be ALL CAPS and bold; the rest must NOT be bold.
   - fontSizeOk: minimum type size by container (read netContents): <=237 mL -> 1 mm; >237 mL to 3 L -> 2 mm; >3 L -> 3 mm. If size can't be measured confidently from one image, return null/borderline so the UI shows AMBER 'confirm' rather than a hard fail.
   - contrastOk and separateAndApart from the style observations.
   - Build deviations[] as plain-language messages, each with a 'type' and the citation.

4. Image quality: pass the score through; if not legible, steer the result toward 'request a better image'.
5. Every field and check carries the exact 27 CFR citation.

Write thorough UNIT TESTS: STONE'S THROW -> 'likely'; net-contents mismatch -> 'flag'; the exact baseline warning -> compliant; a Title-Case + paraphrased + sub-minimum-font warning -> the three correct deviations; beer with no ABV -> not flagged; spirits with no ABV -> flagged. Run the tests and show them passing.
```

**What you should see / acceptance check:** Tests pass; fed the mock extracted data, the engine reproduces the exact verdicts the frontend mock showed.

---

## Prompt B3 — Image pipeline: evidence crops + quality score

**Goal:** Server-side image handling that produces the legibility score and the cropped evidence the UI displays.

```
Add the image pipeline using Pillow/OpenCV. Validate and read the uploaded image. Compute an image-quality/legibility score (blur via variance-of-Laplacian, resolution, and—if the extractor returns bounding boxes—average field confidence) -> imageQuality {score, legible, note}. If the extractor returns field bounding boxes, generate cropped evidence images for each field and for the Government Warning, store them in a short-lived temp store, and return them as evidenceCropUrl (served from a /crops/{id} route, or as data URLs). Crops MUST be ephemeral — purge on session end / after a short TTL; never persist label content. Handle corrupt/unsupported images with a typed error and a plain-language message. If the extractor gives no boxes, degrade gracefully (no crop; field still verified).
```

**What you should see / acceptance check:** The result includes a real legibility score and, where boxes exist, viewable crops; a corrupt image returns a clean, plain-language error.

---

## Prompt B4 — Streaming single-label endpoint

**Goal:** Stream field verdicts as they resolve, so the frontend's progressive UI feels instant (<2 s perceived).

```
Make /api/verify stream results so the frontend renders fields as they arrive (the UI already expects progressive results). Implement Server-Sent Events (SSE) or chunked streaming: emit each field verdict as it's computed, then the Government Warning analysis, then imageQuality, then a 'done' event. Keep a non-streaming JSON fallback for simple clients. The flow: extract once, then emit per-field decisions from the rules engine incrementally. Make sure the streamed event shapes match the frontend's contract notes from Part A · Prompt 2/4. Show a curl example consuming the stream.
```

**What you should see / acceptance check:** `curl` shows events arriving over time; against the real backend, the frontend result view fills in field by field.

---

## Prompt B5 — Batch endpoint (async fan-out)

**Goal:** Process 200–300 labels concurrently and group them for triage.

```
Implement /api/verify-batch for 200–300 images. Use an async worker pool with bounded concurrency (configurable, e.g. 8–16 in flight) to fan out extraction calls, run the rules engine per item, and assign group: 'auto-pass' (all match + warning compliant), 'needs-confirm' (amber, no flags), 'needs-review' (any flag or warning failure). Stream per-item completions via SSE so the dashboard fills live (match the frontend's batch flow). A single item failing must NOT fail the batch — return an error status for that item and continue. Add backpressure / rate-limit handling for the cloud provider. Test with ~50 mock images and show the three groups populating.
```

**What you should see / acceptance check:** A batch of dozens processes concurrently, streams completions, groups correctly, and survives an individual item error without aborting.

---

## Prompt B6 — On-prem / air-gapped inference (FOR WHEN CLOUD IS BLOCKED)

**Goal:** A drop-in extractor that needs ZERO outbound internet — for the firewalled/air-gapped government network. This is the answer to "what if cloud isn't allowed."

```
Add an ON-PREM extractor implementing the SAME LabelExtractor interface but making NO outbound internet calls, for deployment inside a firewalled/air-gapped government network. Architecture:

1. OCR layer (local, always available): use PaddleOCR (preferred) or Tesseract to extract text + per-word bounding boxes + font-style hints, fully offline. (Document that Azure AI Document Intelligence 'disconnected containers' is a drop-in enterprise alternative that also runs air-gapped.)
2. Vision-language layer (local, recommended): call a SELF-HOSTED small open-weight vision model — Microsoft Phi-3.5-vision is a strong fit for an Azure shop and small enough to run on a modest GPU; Qwen2.5-VL or Llama 3.2 Vision also work — served locally via Ollama or vLLM at an in-network URL (configurable via env; default http://localhost:11434). Use it to detect and characterize the label image: map OCR text into the structured fields and transcribe the Government Warning exactly, especially for skewed/glare images. Same single-pass JSON output as the cloud adapter.
3. Graceful degradation: if the local VLM is unavailable, fall back to OCR-only + the rules engine. The deterministic checks — verbatim warning match, ALL-CAPS/bold, font-size-vs-container, exact field matches — need NO model at all; they run on OCR output. With no VLM, route ambiguous/low-confidence cases to AMBER (human confirm) instead of failing them.

Make the active extractor selectable by env: INFERENCE_MODE=cloud|onprem|mock, with NO change to the rules engine, the endpoints, or the frontend. Add a README section explaining: (a) why this resolves the firewall problem — ALL inference stays inside the network, e.g. a hardened sandbox VM / VNet inside the agency's Azure Government tenant, which is inside the accreditation boundary rather than an outbound public ML endpoint the firewall would block; (b) rough hardware — one modern GPU comfortably handles TTB's ~600 labels/workday at ~1–3 s/label; (c) accuracy/latency trade-offs vs cloud. Show it running in onprem mode against a sample label with Ollama.
```

**What you should see / acceptance check:** With `INFERENCE_MODE=onprem` and a local Ollama/vLLM model, a label is verified with no external network calls. Stop the model and OCR-only mode still verifies, routing uncertainty to amber. The rules engine, endpoints, and frontend are untouched.

---

## Prompt B7 — Security & data handling

**Goal:** Honor "store nothing sensitive" for the prototype; scaffold the production controls.

```
Harden data handling to match the PRD's posture. PROTOTYPE: process images and extracted fields in memory only; do NOT persist label content or PII; purge temp crops on session end / short TTL; log events and metrics only — never field VALUES; require TLS in the deployment notes; configure the cloud provider for zero data retention / no training on submitted data. Add an OFF-by-default, clearly-commented PRODUCTION scaffold: structured audit logging (who verified what, the decision, and the regulation citations — NOT the PII), a role-based access-control stub (agent / supervisor / admin), and a configurable retention policy. Add input limits (max file size and count) and basic abuse protection. Document all of this in a SECURITY.md with a prototype-vs-production table.
```

**What you should see / acceptance check:** No PII is written to disk or logs; crops expire; `SECURITY.md` clearly separates prototype posture from production controls.

---

## Prompt B8 — Integration tests, connect frontend↔backend, deploy

**Goal:** Wire the two halves together and ship.

```
Finish and connect everything. 1) Add integration tests hitting /api/verify and /api/verify-batch end-to-end in mock mode (fast, no API key) covering the OLD TOM DISTILLERY, STONE'S THROW, warning-violation, and batch scenarios. 2) Give exact steps to connect the frontend: set VITE_API_BASE_URL to the backend URL, confirm CORS, and verify the real (non-mock) flow works for every scenario. 3) Provide deployment notes for THREE targets: (a) PROTOTYPE DEMO — frontend on Vercel; backend either as Vercel Python serverless functions (keep deps light — Pillow only, NO OpenCV/torch/PaddleOCR; set maxDuration ~60s; use SSE for streaming) OR, if you need heavier image libraries, a small always-on host (Render / Railway / Fly.io) with the frontend still on Vercel; use INFERENCE_MODE=cloud here. (b) A Dockerfile for container hosts. (c) PRODUCTION / air-gapped — an on-prem or Azure Government sandbox VM/VNet with INFERENCE_MODE=onprem; note explicitly that this path does NOT use Vercel or any public host, because all inference must stay inside the agency boundary. 4) Update the README: an architecture diagram (frontend ↔ API ↔ pluggable inference + rules engine), how to run each INFERENCE_MODE, and the prototype→production path. 5) A pre-demo sanity checklist. Keep dependencies lean.
```

**What you should see / acceptance check:** Integration tests pass in mock mode; pointing the frontend at the backend, all scenarios work end-to-end; `docker build` succeeds; the README explains the three run modes and the production path.

---

## Tips for working with Claude on this build

- **Iterate one screen at a time.** Finish and visually verify each prompt before moving on. If you paste prompts 0–10 all at once, the output gets shallow. Slow is fast here.
- **Paste error messages back verbatim.** If the preview breaks or the terminal shows a red error, copy the whole message into Claude and say "fix this." Don't paraphrase it.
- **Ask for a diff, not a rewrite.** When you want a small change, say "show me only the changes (a diff) to file X" so you don't lose working code or get an accidental rewrite of the whole app.
- **Keep the API contract stable.** Prompts 2 onward all depend on the types from Prompt 2. If you ever change a field name or shape, tell Claude: "update the contract in types.ts AND every component that uses it." Stability here is what lets the real backend drop in later.
- **Request an accessibility self-check after meaningful changes.** Say "do a quick a11y self-check on what you just changed: contrast, keyboard, color-independence, labels." Catch regressions early — it's a federal app and accessibility is the headline requirement.
- **Always demo with the mock scenarios.** When you ask Claude to verify a feature, name the scenario: "test this on the STONE'S THROW amber case and the Title-Case Government Warning violation." Concrete data exposes bugs that abstract testing misses.
- **Hold the line on simplicity.** If Claude reaches for a heavy dependency or a complex state library, push back: "keep it minimal and deploy-friendly — can we do this with built-in React + the existing primitives?" One primary action per screen, large legible type, no hunting for buttons.
- **Save your work.** Commit to Git (or download the project) after each successful prompt, so you can always roll back to the last working version.
```
