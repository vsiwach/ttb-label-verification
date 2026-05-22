# Product Requirements Document
## AI-Powered Alcohol Label Verification App

**Prepared for:** U.S. Department of the Treasury — Alcohol and Tobacco Tax and Trade Bureau (TTB)
**Prepared by:** Vikram Siwach (candidate, IT Specialist)
**Document type:** Take-home prototype PRD
**Version:** 1.0
**Date:** May 21, 2026

---

## 1. Executive Summary

TTB reviews roughly **150,000 label applications per year** with **47 agents** — down from well over 100 in the 1980s — using a review process that has been essentially unchanged since the COLAs Online system went live in 2003. An agent pulls an application, opens the label artwork beside it, and visually confirms that a small set of facts agree: the brand name on the label matches the application, the alcohol content is correct, the mandatory Government Warning is present and properly formatted. A simple application takes five to ten minutes, and as one stakeholder put it, "half their day is essentially data-entry verification."

This document specifies an **AI-Powered Alcohol Label Verification App**: a prototype where a compliance agent uploads a label image (one at a time, or in a batch of hundreds), a vision LLM extracts every TTB-relevant field, and a deterministic rules engine compares those fields against the application data and against federal labeling rules in 27 CFR. The output is a per-field, three-state verdict — **Match / Likely match / Flag** — with the cropped image evidence and the exact regulation citation that supports each call.

The single most important design insight, and the one that should shape every downstream decision, is this: **the bulk of an agent's review time is not judgment — it is mechanical matching and transcription.** Steps that involve genuine legal nuance (does this near-match count? is this evader trying to bury the warning?) are a small fraction of the clock. The app therefore does not try to replace the agent. It **triages**: it does the reading, the normalization, the field-by-field comparison, and the formatting checks in seconds, then presents an evidence-backed recommendation that a human confirms or overrides. **The AI extracts and proposes; the human decides and owns the legal call.** This is not a hedge — it is a hard requirement driven by federal liability, by the adversarial nature of the work, and by the simple fact that skeptical senior agents will only adopt a tool they can see through and overrule.

The headline approach has three load-bearing pieces. First, a **single-pass structured extraction** from a fast multimodal model returns a fixed JSON schema with a confidence score per field, streamed so results appear on screen in under two seconds. Second, a **hand-coded 27 CFR rules engine** — not the LLM — makes every pass/fail determination, so the logic is auditable, testable, and citable. Third, a **Government Warning verification engine** (27 CFR Part 16) performs verbatim text matching plus the formatting checks (ALL CAPS, bold, type-size by container size, contrast) that catch the specific evasion patterns agents see in the field. For the prototype we use a cloud vision LLM in a sandboxed environment that stores nothing sensitive; this PRD documents a concrete production migration path to **Azure OpenAI in Azure Government (FedRAMP High)** that resolves the agency firewall constraint without re-architecting the application.

---

## 2. Critical Review of the Assignment

A senior reviewer should read this take-home as a set of deliberately planted tensions, several of which contradict each other on purpose. Naively "building the feature" fails the assignment; the assignment is testing whether the candidate notices the traps and reasons through them with appropriate scoping. The eight tensions and our resolutions follow.

**(a) The firewall vs. cloud-API contradiction.** Marcus (IT) says the agency network blocks outbound traffic to many domains, and the prior vendor's ML endpoints were firewalled — yet the obvious way to hit the latency and accuracy bar is a cloud vision LLM. This is the central trap. Resolution: we explicitly **separate prototype from production**. The prototype is a standalone POC running in a sandbox with synthetic/public labels and no sensitive data, where a cloud API is the correct, fastest-to-value choice. We then **document a production inference path** — Azure OpenAI in Azure Government (FedRAMP High, IL4/5), which lives inside the Treasury-trusted Azure boundary the agency already uses — plus an air-gapped contingency (Azure AI Document Intelligence disconnected containers + a self-hosted vision model). The firewall is not ignored; it is resolved by moving inference inside the accreditation boundary rather than out to the public internet.

**(b) The five-second hard latency bar.** The prior scanning vendor took 30–40 seconds per label and agents abandoned it: "if we can't get results back in about five seconds, nobody's going to use it." This is a real, falsifiable requirement, not an aspiration. Resolution: a layered latency strategy (Section 11) whose biggest single win is **client-side image downscaling to ~2 MP JPEG** before upload — a 12-megapixel phone photo is the number-one latency killer — combined with single-pass extraction, a fast model (Gemini 2.5 Flash or Claude Haiku 4.5, ~1.5–3 s/call), and **streaming** so fields render in under two seconds of perceived latency. The vendor's 30–40 s was a heavy self-hosted pipeline on full-resolution images; modern fast multimodal is 6–15× faster.

**(c) Accessibility for a 73-year-old and a half-over-50 team.** Sarah's "something my 73-year-old mother could figure out" and "Dave still prints his emails" are not color commentary — they are the acceptance criteria for UX. Resolution: the app is built to **Section 508 / WCAG 2.1–2.2 AA**, on the **U.S. Web Design System (USWDS)**, with concrete targets (≥16px body, ≥4.5:1 contrast, 44×44px primary targets, full keyboard operability, visible focus, plain-language errors). This is also a legal obligation for a federal tool under the 21st Century IDEA Act, not a nicety.

**(d) The "STONE'S THROW" judgment nuance.** Dave's example — `STONE'S THROW` on the label vs. `Stone's Throw` in the application — is "technically a mismatch but obviously the same." A naive string-equality check fails here and "makes his life harder." Resolution: we never emit a boolean. Every field gets a **confidence score** and a **normalized comparison** mapped to three states. The Stone's Throw case lands in **AMBER — "Likely match, confirm,"** showing exactly what differs (case + apostrophe styling) with a one-click confirm. Genuine judgment stays with the human.

**(e) Batch (200–300) vs. one-at-a-time.** Peak-season importers dump 200–300 applications, processed serially today; batch is a top ask (Janet, Seattle). Resolution: **batch upload with async concurrent fan-out**, a **triage dashboard** that surfaces only the flagged labels, and a keyboard-driven "confirm next" review flow. A 250-label dump completes in well under a minute of wall-clock.

**(f) Imperfect images.** Jenny needs the tool to handle angles, glare, and bad lighting. Resolution: an **image-quality gate** that scores legibility before extraction and, when an image is unreadable, returns a plain-language "request a better image" outcome rather than a confident-but-wrong extraction. This mirrors the agent's existing step-4 behavior.

**(g) "Don't store anything sensitive" / standalone POC scope.** Marcus is explicit: do not integrate with COLA; do not store sensitive data in the prototype. Resolution: **ephemeral, in-memory processing**; images and extracted fields are held only for the life of the request/session and discarded on close; no database of label content; no model training on uploaded data. This is stated as a non-goal (Section 5) and a security posture (Section 8).

**(h) Skeptical-adopter change management (Dave).** A 28-year senior agent who is fast by eye and distrustful of automation is the hardest user to win — and the most important, because his peers follow his lead. Resolution: the AI verdict is always **visible and overridable**, never hidden or forced; the UI is keyboard-driven with big obvious controls and zero learning curve; and the tool is positioned as a **co-pilot that does the data entry**, not a replacement that makes the decision.

**What the assignment is really testing.** It rewards a candidate who recognizes that a "working core application with clean code is preferred over ambitious but incomplete features," who **documents trade-offs** rather than hiding them, and who treats accessibility, latency, and the firewall as first-class engineering constraints rather than afterthoughts. The correct posture is disciplined scoping plus an honest production roadmap — exactly what this PRD delivers.

---

## 3. Current-State Workflow

Today's review is a seven-step manual loop. The clock is dominated by steps 2, 3, and 7 — pulling and visually comparing artwork against the application, then transcribing the outcome.

| Step | Activity | Owner | Typical effort |
|---|---|---|---|
| 1 | **Intake / queue** — application arrives via COLAs Online and lands in a work queue | System / agent | Low |
| 2 | **Pull & display** — agent opens the application record and the label artwork side by side | Agent | Moderate (window juggling) |
| 3 | **Visual comparison** — confirm brand name, class/type, alcohol content, net contents, name/address, origin, and the Government Warning against the application | Agent | **High** (the core of the review) |
| 4 | **Image-quality gate** — if artwork is unreadable, reject and request a better image | Agent | Low–moderate |
| 5 | **Human judgment on near-matches** — resolve "technically different but obviously the same" cases | Agent | Variable |
| 6 | **Decision** — approve, reject, or request a corrected image; on a defect the applicant has 30 days to correct | Agent | Low |
| 7 | **Logging** — record the outcome and any defect codes back in the COLA system | Agent | **High** (data entry) |

A simple application runs five to ten minutes. The defensible characterization from the stakeholder interviews — "half their day is essentially data-entry verification" — is accurate: steps 2, 3, and 7 are mechanical reading, comparing, and typing. Step 5 is where real expertise lives, and it is a minority of the time.

---

## 4. Future-State Workflow & Automation Opportunities

The same seven steps, re-imagined with AI triage and a human-in-the-loop, collapse the mechanical work while leaving every legal determination with the agent.

The agent (or the COLA queue, in production) drops one image or a batch into the app. The client downscales each image and uploads it; the backend runs a single-pass structured extraction, scores image quality, and runs the deterministic rules engine, then streams a per-field, three-state result with cropped evidence. The agent sees a side-by-side view where green fields need no attention, amber fields offer a one-click confirm with the normalized difference shown, and red fields demand review. The agent confirms or overrides, the decision and a draft log entry are assembled automatically, and the agent commits with a single keystroke. In batch mode, the triage dashboard hides everything that passed cleanly and walks the agent only through the flagged labels.

| Step | Today | Future state | Automation level |
|---|---|---|---|
| 1. Intake/queue | Manual queue handling | Auto-ingest, auto-queue | **Automate** |
| 2. Pull & display | Window juggling | App displays artwork + fields together | **Automate** |
| 3. Brand / ABV / warning compare | Visual, by eye | AI extracts + rules engine compares; 3-state verdict with evidence | **AI-assisted, human-in-the-loop** |
| 4. Image-quality gate | Agent judgment | AI legibility score with "request better image" path | **AI-assisted** |
| 5. Near-match judgment | Agent | Stays with agent; AI surfaces the normalized difference | **Human** |
| 6. Decision | Agent | Agent owns approve/reject/request; no dead ends | **Human-owned** |
| 7. Logging | Manual data entry | Auto-drafted log/decision; human confirms | **Auto-draft, human confirms** |

**Before/after.** A clean, simple application that takes roughly seven minutes today should take **under one minute** of agent attention in the future state: a few seconds for the AI to extract and verify, a glance to confirm an all-green result, and one keystroke to commit the auto-drafted log. The savings concentrate exactly where the time is — steps 2, 3, and 7 — without touching step 5, where the agent's expertise matters.

---

## 5. Goals, Non-Goals & Success Metrics

**Goals.** Cut the per-label review time for clean applications by an order of magnitude while keeping the agent in control; extract and verify the **full TTB field set** for distilled spirits, wine, and malt beverages; perform a rigorous, evidence-backed Government Warning check; support both single-label and batch (200–300) workflows; meet a hard ≤5-second latency target; and meet federal accessibility standards out of the box.

**Non-Goals (explicit).**
- **No COLA integration.** This is a standalone POC; it does not read from or write to COLAs Online / myTTB. Per Marcus, a direct integration is out of scope.
- **No data retention.** The prototype stores nothing sensitive — no database of label images or extracted PII, no persistence beyond the request/session.
- **No allergen / nutrition / cancer-warning enforcement.** The Surgeon General's January 2025 advisory urging a cancer warning is **advisory only**; TTB's January 2025 NPRMs proposing mandatory "Alcohol Facts" and major-food-allergen disclosures are **proposed, not final** (comment extended to August 2025; ~5-year compliance window if finalized). The app must **not** reject for missing allergen, nutrition, or cancer content — these are treated as informational/future only.
- **No automated final approval.** The app never auto-approves or auto-rejects a federal application; it recommends and a human commits.

**Success metrics.**

| Metric | Target |
|---|---|
| Single-label latency (P95, perceived first-field) | **≤ 5 s** end-to-end; first fields streamed < 2 s |
| Per-label review time (clean applications) | ≥ 80% reduction vs. today |
| Batch throughput | 250-label dump fully processed < 60 s wall-clock |
| Agent override rate (proxy for trust/accuracy) | Tracked; high override on green = recalibrate thresholds |
| Government Warning detection recall | No missed-warning false "pass" in test set |
| Accessibility | 100% of screens pass Section 508 / WCAG 2.2 AA automated + manual keyboard audit |

---

## 6. Key Requirements

### 6.1 Functional Requirements

Priorities: **P0** = required for the take-home core; **P1** = strongly expected; **P2** = nice-to-have / roadmap.

| # | Requirement | Priority |
|---|---|---|
| F1 | **Single-label upload** — accept a label image (JPEG/PNG/PDF page), client-side downscale to ~2 MP before upload | P0 |
| F2 | **Full-field extraction by beverage type** — extract brand name, fanciful name, class/type, alcohol content, net contents, name & address, country of origin, and (wine) grape varietal/appellation/vintage; return a fixed JSON schema with a **confidence score per field** | P0 |
| F3 | **Government Warning verification** — verbatim text match against 27 CFR 16.21 plus the 16.22 formatting checks (CAPS + bold on "GOVERNMENT WARNING," type-size by container, contrast, separate-and-apart) | P0 |
| F4 | **Confidence-scored three-state matching** — every field compared to the supplied application data and rendered GREEN / AMBER / RED with the normalized comparison shown | P0 |
| F5 | **Image-quality gate** — score legibility; on unreadable input return a "request a better image" outcome rather than a low-confidence extraction | P0 |
| F6 | **Decision actions with no dead ends** — agent can confirm, override, or request a corrected image on every field and at the application level | P0 |
| F7 | **Auto-drafted log / decision summary** — assemble a structured decision record the agent confirms; export results (JSON/CSV/printable) | P1 |
| F8 | **Batch upload (200–300)** — multi-file upload with async concurrent fan-out | P1 |
| F9 | **Triage dashboard** — batch view that surfaces only flagged labels; sortable by state; "confirm next" keyboard flow | P1 |
| F10 | **Regulation citations** — every pass/flag carries the exact 27 CFR section that justifies it | P1 |
| F11 | **Beverage-type auto-detection** — infer spirits/wine/malt to apply the correct mandatory-field set (with manual override) | P2 |
| F12 | **Evidence cropping** — show the cropped region of the label that supports each extracted field | P1 |

### 6.2 Non-Functional Requirements

| # | Requirement |
|---|---|
| N1 | **Latency** — ≤ 5 s P95 single-label end-to-end; first fields streamed < 2 s; 250-label batch < 60 s |
| N2 | **Accessibility** — Section 508, WCAG 2.1/2.2 AA, USWDS, 21st Century IDEA Act compliance (Section 10) |
| N3 | **Security / data handling** — no PII persistence in the prototype; TLS in transit; ephemeral in-memory processing; no model training on uploaded data |
| N4 | **Reliability** — graceful degradation on model error or timeout (clear message + retry, never a silent wrong answer); per-label failures in a batch do not fail the batch |
| N5 | **Auditability** — the verdict logic is deterministic and testable; the same input always yields the same regulatory determination |
| N6 | **Portability** — inference is behind an interface so the cloud model can be swapped for a FedRAMP/on-prem backend without UI changes |

---

## 7. System Architecture

### 7.1 Prototype Architecture

The prototype is a thin, well-separated three-tier system.

**Client (React + Vite).** A single-page app that handles upload, **client-side image downscaling/compression to ~2 MP JPEG** (the biggest latency lever), the verification result view, the batch dashboard, and all accessibility behavior. Built on USWDS components/tokens.

**API (lightweight backend).** A small service that receives the downscaled image plus the application data, calls the vision LLM with a static cached system prompt requesting a fixed JSON schema, **streams** the extraction back to the client as fields resolve, runs the **deterministic rules engine**, and returns per-field verdicts with citations. For batch, it **fans out concurrent calls** with a bounded worker pool and streams per-label completions to the dashboard.

**Inference (cloud vision LLM).** A fast multimodal model (default **Gemini 2.5 Flash** or **Claude Haiku 4.5**) accepting an image and returning structured JSON. The model only ever **extracts and scores**; it never renders the legal verdict.

**Data flow (single label).** Agent selects an image → client downscales to ~2 MP and uploads with the application fields → API issues one structured-extraction call with prompt caching → model streams a JSON object of fields + per-field confidence + the Government Warning text/format observations → API runs the rules engine: it normalizes each field, compares to the application data, applies the 27 CFR checks, and assigns GREEN/AMBER/RED with a citation → API streams verdicts + evidence crops to the client → agent reviews, confirms/overrides, commits the auto-drafted log. Nothing is persisted after the session.

**The core pattern — LLM extracts, rules engine decides.** This separation is the architectural heart of the system. The LLM is good at reading messy real-world images and proposing structured fields; it is not a reliable, auditable arbiter of federal law and can hallucinate a confident wrong answer. So the LLM's job ends at "here is what I read, and how sure I am." A **hand-coded rules engine** then makes every determination — verbatim warning match, type-size thresholds, mandatory-field presence by beverage type — and attaches the exact 27 CFR citation. This keeps the legal logic deterministic, unit-testable, reviewable by counsel, and stable across model upgrades.

### 7.2 Production Architecture

Production keeps the identical client and rules engine and swaps only the inference backend, which is why N6 (portability behind an interface) matters in the prototype.

The recommended production inference target is **Azure OpenAI Service in Azure Government** (FedRAMP High, DoD IL4/5). This is the best fit because TTB/Treasury has been **on Azure since 2019** and already cleared an 18-month FedRAMP path — inference moves **inside** the existing accreditation boundary rather than out to the open internet, which is precisely what resolves the firewall problem that killed the prior vendor. Equivalent alternatives are **Anthropic Claude via Amazon Bedrock GovCloud** (FedRAMP High + IL4/5) and **Google Gemini on Vertex AI Assured Workloads** (FedRAMP High). Government regions typically lag frontier models by about one tier, so we design for "one tier behind" and validate accuracy on that tier.

For the most restrictive environments, an **air-gapped contingency** runs **Azure AI Document Intelligence disconnected containers** for OCR plus a **self-hosted vision model** for field mapping, all inside the agency network. Plain OCR alone (Tesseract, PaddleOCR) cannot do field-mapping and verbatim warning analysis, so OCR is paired with a self-hosted or FedRAMP LLM. This path trades some accuracy and ops overhead for full network isolation and is the fallback if even Azure Government egress is disallowed.

**Model comparison.**

| Model | Price (in/out per 1M tok) | ~Single-call latency | FedRAMP path |
|---|---|---|---|
| **Gemini 2.5 Flash** | $0.30 / $2.50 | 1.5–3 s (OCR-tuned, cheapest) | Vertex AI Assured Workloads (High) |
| **Claude Haiku 4.5** | $1 / $5 | 1.5–3 s | Bedrock GovCloud (High, IL4/5) |
| **GPT-4o** | $2.50 / $10 | 2–4 s | Azure OpenAI in Azure Gov (High, IL4/5) |
| **Claude Sonnet 4.6** | $3 / $15 | 2–4 s | Bedrock GovCloud (High, IL4/5) |
| **Gemini 2.5 Pro** | higher | 3–5 s | Vertex AI Assured Workloads (High) |

Default recommendation: **Gemini 2.5 Flash or Claude Haiku 4.5** for the latency and cost wins, with a heavier model (Sonnet / Gemini Pro) available as an escalation tier for low-confidence or contested labels.

---

## 8. Data Protection & Security

**Prototype posture (explicitly addressing "don't store anything sensitive").** The prototype is a sandboxed POC operating on synthetic and publicly available labels. It performs **ephemeral, in-memory processing**: an uploaded image and its extracted fields exist only for the duration of the request/session and are **discarded on close**. There is **no database** of label content, **no persisted PII**, and **no logging of sensitive field values**. All traffic runs over **TLS**. The cloud inference provider is configured for **no training on submitted data**, using enterprise/zero-retention API terms. In short: nothing sensitive is stored, which is exactly the instruction from IT.

**Production posture.** Production must add what a federal system requires, all inside the FedRAMP boundary: **PII handling** consistent with Treasury rules; a **document retention policy** aligned with TTB records schedules; operation entirely within the **FedRAMP High accreditation boundary** (Azure Government); **audit logging** of who reviewed what and what determination was committed (with the regulation citations preserved for defensibility); and **role-based access control** distinguishing agents, supervisors, and administrators. The prototype's clean separation — UI, rules engine, and inference behind an interface — means these controls are added at the boundary without rewriting the application.

---

## 9. The Government Warning Verification Engine

This is the marquee feature, and the highest-value automated check, because the Government Warning is the most format-sensitive mandatory element and the one evaders most often try to weaken. It is required on **all beverages ≥ 0.5% ABV** (27 CFR Part 16), including the 0.5–7% wines that otherwise fall under FDA.

**The verbatim standard (27 CFR 16.21).** The statement must read **exactly**:

> GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

The engine performs four classes of check, each tied to a regulation and each designed to catch a specific real-world evasion pattern.

**1. Verbatim text match (with paraphrase detection).** The LLM extracts the warning text exactly as it appears on the label. The rules engine normalizes whitespace and OCR artifacts, then compares against the canonical 16.21 string. A normalization step that is too aggressive would let paraphrase slip through, so the engine **does not** normalize away wording differences — it normalizes only true OCR noise (stray spaces, hyphenation at line breaks) and then flags any **substantive deviation**: reworded, abbreviated, or partial text is RED with a diff highlighting what changed. This catches the "paraphrased or abbreviated warning" evasion directly.

**2. ALL-CAPS + bold detection on "GOVERNMENT WARNING" (27 CFR 16.22).** The words "GOVERNMENT WARNING" must be in **capital letters and bold**, and the remainder must **not** be bold. The model reports the rendered case and weight of the heading and body separately; the engine flags lower/mixed-case ("Government Warning"), non-bold headings, or a bolded body. This catches the "mixed/lower case or not bold" evasion.

**3. Type-size vs. container-size check (27 CFR 16.22).** Minimum type size scales with net contents: **≤ 237 mL → 1 mm; > 237 mL to 3 L → 2 mm; > 3 L → 3 mm.** The engine reads the net-contents field (already extracted), selects the applicable threshold, and compares against the measured/estimated warning type size. Sub-minimum font — the classic "shrink it until it's technically there but unreadable" trick — is flagged with the specific threshold cited. Where exact physical measurement from a single image is uncertain, the engine returns AMBER and asks the agent to confirm, rather than guessing.

**4. Legibility, contrast, and "separate and apart" (27 CFR 16.22).** The warning must be **readily legible**, on a **contrasting background**, **not compressed**, and visually **separate and apart** from other text. The engine evaluates contrast, detects compressed/condensed letterforms, and checks whether the warning is crowded into surrounding copy. This catches the "low contrast," "compressed," and "buried/crowded" evasions.

| Evasion pattern (field-observed) | Check that catches it | Citation |
|---|---|---|
| Reworded / paraphrased / abbreviated | Verbatim text match (substantive-diff) | 27 CFR 16.21 |
| "Government Warning" in mixed/lower case | Case detection | 27 CFR 16.22 |
| Heading not bold (or body bolded) | Weight detection | 27 CFR 16.22 |
| Sub-minimum font for container size | Type-size-vs-container check | 27 CFR 16.22 |
| Low-contrast / camouflaged text | Contrast/legibility check | 27 CFR 16.22 |
| Compressed/condensed letterforms | Compression check | 27 CFR 16.22 |
| Buried / not "separate and apart" | Separation check | 27 CFR 16.22 |

Crucially, the engine **flags for human review** rather than auto-failing on the format checks that depend on physical measurement from imperfect images. Jenny gets rigorous, evidence-backed analysis with a drill-in to the cropped warning region; the agent makes the final call.

---

## 10. UX Design Principles & Screen-by-Screen Spec

### 10.1 Design Principles

The user base spans Dave (28 years, prints his emails, fast by eye, skeptical) to Jenny (fresh out of college, detail-obsessed), with half the team over 50 and a stated bar of "something my 73-year-old mother could figure out." These twelve principles govern every screen.

1. **Clean and obvious — no hunting for buttons.** One primary action per screen, visually dominant.
2. **AI is always visible and always overridable.** Never hide the recommendation; never force it.
3. **Never rely on color alone.** Every green/amber/red is paired with an **icon + text label** ("Match" / "Likely match — confirm" / "Flag — review").
4. **Big targets.** ≥24×24 CSS px everywhere; **44×44** for primary actions, given the older user base.
5. **Readable type.** Body ≥16px; line length 45–90 chars (~66); line-height ≥1.5.
6. **High contrast.** ≥4.5:1 normal text, ≥3:1 large text and UI components.
7. **Full keyboard operability** with a clearly **visible focus indicator** — for Dave and for power users in batch mode.
8. **Plain-language errors** that name the field and give a next action ("Couldn't read the alcohol content — upload a clearer image of the front label").
9. **No dead ends.** Every state offers a forward action (confirm, override, request image, skip).
10. **Show the evidence.** Every extracted field links to the **cropped region** it came from.
11. **Triage, don't dump.** In batch, surface only what needs attention.
12. **Built on USWDS** for federal consistency and Section 508 conformance by default.

### 10.2 Screens

**(a) Upload / single-label.** A single large dropzone with one obvious "Upload label" control and a place to enter or paste the application data to verify against. On selection, the client downscales the image, shows a thumbnail, and begins streaming results. Minimal chrome; the dropzone is the screen.

**(b) Verification result view.** A two-column layout: the label artwork on the left, the field-by-field results on the right. Each field row shows the extracted value, the application value, a **three-state badge with icon + text**, and a thumbnail of the **cropped evidence**. Green rows are quiet; amber rows expand inline to show the **normalized comparison** ("Label: STONE'S THROW / Application: Stone's Throw — differs by case + apostrophe styling") with a one-click **Confirm match**; red rows show the mismatch and a **Flag / Request image** action. A dedicated **Government Warning analysis panel** presents the verbatim diff, the CAPS/bold findings, the type-size-vs-container result, and the legibility/contrast/separation checks, each with its 27 CFR citation and a drill-in to the cropped warning region. The bottom of the view holds the **decision actions** — Approve, Reject, Request corrected image — with the **auto-drafted log** ready to confirm. No dead ends, no hidden state.

**(c) Batch upload + triage dashboard.** A multi-file dropzone accepts 200–300 images. As the async fan-out completes, a **triage dashboard** fills in: a sortable, filterable list defaulting to **flagged-first**, with each label showing its overall state badge and a count of flagged fields. Clean all-green labels are collapsed/hidden by default so the agent's attention goes only where it is needed. Janet can see a 250-label dump resolve in under a minute and immediately know how many need her.

**(d) Batch review "confirm next" flow.** From the dashboard, the agent enters a focused review of the flagged set: one label at a time in the same result-view layout, with prominent keyboard shortcuts — **Confirm and next**, **Flag and next**, **Request image and next** — so a skilled agent clears the queue at speed without touching the mouse. A progress indicator ("12 of 38 flagged") keeps orientation.

**Accessibility specifics across all screens:** USWDS components; ≥16px body; ≥4.5:1 contrast; 44×44 primary targets; visible focus rings; ARIA roles and live regions announcing streamed results to screen readers; icon+text state badges; and plain-language, field-named error messages. The app is verified against Section 508 / WCAG 2.2 AA with both automated checks and a manual keyboard pass.

---

## 11. Latency & Cost Strategy

The five-second bar is the requirement the prior vendor failed, and it is non-negotiable: agents abandoned a 30–40 s tool outright. Six techniques, stacked, clear the bar with margin.

1. **Client-side downscale/compress to ~2 MP JPEG** before upload — the single biggest win. A 12-megapixel phone photo is the number-one latency killer; shrinking it cuts both upload and inference time dramatically while preserving legibility for extraction.
2. **Single-pass structured extraction** — one prompt returns the full fixed JSON schema for all fields, instead of multiple round-trips.
3. **Fast model** — Gemini 2.5 Flash or Claude Haiku 4.5 at ~1.5–3 s/call.
4. **Streaming** — fields render as they resolve, so perceived latency is < 2 s even if the full response takes a few seconds. This is what makes the tool *feel* instant.
5. **Async concurrent fan-out for batch** — a 250-label dump runs in parallel and finishes in well under a minute, versus serial processing today.
6. **Prompt caching** of the static system prompt across a batch — the long, fixed instructions are cached once, cutting per-call cost and latency across hundreds of labels.

Realistic wall-clock for one label call is ~2–5 s; with downscaling and streaming, perceived first-field latency lands under two seconds. The prior vendor's 30–40 s was a heavy self-hosted pipeline on full-resolution images; modern fast multimodal is **6–15× faster**.

**Cost.** At ~150,000 labels/year and two model calls per label, annual inference cost is trivial:

| Model | Approx. annual cost (150k labels, 2 calls each) |
|---|---|
| Gemini 2.5 Flash | **~$435** |
| Claude Haiku 4.5 | ~$1,050 |
| GPT-4o | ~$2,325 |
| Claude Sonnet 4.6 | ~$3,150 |

The headline point: **cost is not the constraint.** Even the most expensive option is a rounding error against 47 agents' labor. The real constraints are latency, accuracy, and FedRAMP — which is why the architecture optimizes for those and treats model spend as immaterial.

---

## 12. Risks, Trade-offs & Mitigations

| Risk / trade-off | Mitigation |
|---|---|
| **Cloud API vs. agency firewall** | Prototype uses cloud in a sandbox with no sensitive data; production moves inference inside the FedRAMP boundary (Azure OpenAI in Azure Gov), with an air-gapped contingency (Azure DI disconnected containers + self-hosted VLM). Inference behind an interface (N6) makes the swap a backend change. |
| **LLM hallucination / false match** | The LLM never renders the verdict — a deterministic, testable **rules engine** decides and cites 27 CFR. Confidence thresholds drive the three-state UI; **evidence crops** let the agent verify; **human-in-the-loop** owns every decision. |
| **Adoption / change management (Dave)** | Zero learning curve, big obvious keyboard-driven controls, AI verdict always visible **and overridable**, positioned as a co-pilot that does the data entry, not a replacement. Track override rate to recalibrate trust. |
| **Accessibility for an older, mixed-comfort team** | Section 508 / WCAG 2.2 AA on USWDS from day one; icon+text states; 44×44 targets; ≥16px type; full keyboard + visible focus; plain-language errors. Legal obligation under the 21st Century IDEA Act. |
| **Imperfect images (angles, glare, lighting)** | Image-quality gate scores legibility and returns a plain-language "request a better image" path instead of a confident-but-wrong extraction; format checks needing physical measurement degrade to AMBER (confirm) rather than auto-fail. |
| **Regulatory change (allergen / nutrition / cancer)** | App treats these as **informational/future only** and never rejects for them; the rules engine is modular so a finalized rule (with its ~5-year window) can be added as a new, separately-citable check. |
| **Latency regression at scale / on gov-tier models** | Downscaling + streaming + fast model + caching; design for "one tier behind" in gov regions and validate accuracy there; heavier model reserved as an escalation tier only. |
| **Over-trust in green states** | Monitor agent override rate on green; high override signals threshold drift and triggers recalibration. The agent always retains override. |

---

## 13. Phased Roadmap

**Phase 0 — Prototype (this take-home).** Standalone POC: React + Vite client, lightweight API, cloud vision LLM, full-field extraction by beverage type, the Government Warning engine, three-state matching with evidence, single-label **and** batch with a triage dashboard, image-quality gate, auto-drafted decision, export. No COLA integration, no data retention. Deployed working URL + source repo + README + approach docs.

**Phase 1 — Pilot.** Run with a small group of real agents (a skeptic like Dave and a specialist like Jenny) on synthetic and historical labels inside a controlled environment. Tune confidence thresholds against real override behavior, validate the Government Warning checks against known rejection cases, refine the batch flow with Janet's peak-season volumes, and complete a formal Section 508 audit.

**Phase 2 — Production / FedRAMP / COLA integration.** Migrate inference into **Azure OpenAI in Azure Government (FedRAMP High)** (or the air-gapped contingency), add the production security posture (PII handling, retention, audit logging, RBAC), and integrate with COLAs Online / myTTB so intake and logging close the loop. This is where the firewall is fully resolved and the tool becomes part of the agents' daily system of record.

---

## 14. Mapping to Evaluation Criteria

| Stated evaluation criterion | How this design hits it |
|---|---|
| **Correctness / completeness of core requirements** | Full TTB field set by beverage type; the Government Warning engine (16.21/16.22); three-state matching; single + batch; image-quality gate; auto-drafted decision (Sections 6, 9). |
| **Code quality / organization** | Clean three-tier separation; LLM-extracts / rules-engine-decides; inference behind an interface; deterministic, unit-testable regulatory logic (Section 7). |
| **Appropriate technical choices for scope** | Cloud LLM for a sandboxed POC with a documented FedRAMP production path; fast model + downscaling to hit ≤5 s; no over-engineering, no COLA integration in the prototype (Sections 7, 11). |
| **UX & error handling** | USWDS / Section 508 / WCAG AA; icon+text states; evidence crops; no dead ends; plain-language, field-named errors; image-quality "request better image" path (Section 10). |
| **Attention to requirements** | Hard 5-second bar treated as falsifiable; "don't store anything sensitive" honored; firewall constraint resolved; allergen/cancer rules correctly excluded as non-final (Sections 2, 5, 8). |
| **Creative problem-solving** | Confidence-scored three-state triage for the Stone's Throw nuance; evasion-pattern-to-check mapping for the warning; streaming for perceived latency; batch fan-out + triage dashboard (Sections 9, 10, 11). |
| **Documented trade-offs** | Explicit risk/trade-off table and prototype-vs-production split throughout (Sections 2, 12, 13). |

---

## 15. Model Strategy — Build vs. Buy

A core decision for this system is whether to train a custom model or use an existing one. The recommendation is unambiguous: **use pretrained foundation models; do not train a model from scratch, and treat fine-tuning as a measured, optional, later step rather than a default.**

The reasoning is that the task the model performs is narrow and well within the zero-shot capability of modern vision-language models: read the printed text on a label image and report what it sees, with bounding regions and a confidence per field. Contemporary multimodal models do this reliably out of the box, including on imperfect photos. Critically, the *hard* part of this system is not reading the label — it is deciding whether what was read complies with 27 CFR, and that logic is deterministic (the rules engine), not learned. Accuracy therefore comes from prompt design and the rules engine, not from trained weights. Training a custom model would require a large hand-labeled dataset, ML engineering, GPU training infrastructure, and ongoing retraining as models and regulations evolve — none of which is justified when an off-the-shelf model already clears the bar, the annual volume is modest (~150,000 labels), and inference cost is trivial (~$400–$3,200/year, Section 11).

This holds in both deployments. For the prototype, a commercial cloud vision model (e.g., Claude or Gemini) is used zero-shot. For production inside the Azure Government boundary, a pretrained open-weight small model (e.g., Microsoft Phi-3.5-vision) is self-hosted — still pretrained, simply run on the agency's own hardware. In neither case do we train from scratch.

The one condition under which fine-tuning enters: if the formal evaluation (Section 16) shows the zero-shot model missing a specific, repeatable failure mode — for example, consistently misreading a particular layout or failing to localize a field on busy artwork — then a light fine-tune of the small open-weight model on a few hundred COLA examples is justified to close that measured gap. Even then this is fine-tuning a pretrained model, not training from scratch, and it is a Phase-2+ optimization driven by evidence rather than a starting assumption. **Build-vs-buy verdict: buy (pretrained), with fine-tuning held in reserve.**

---

## 16. Test Data & Evaluation Plan

The system needs evaluation data, not training data (Section 15). The evaluation set must measure two distinct things: **extraction accuracy** (did the model read the label correctly?) and **compliance-decision accuracy** (did the rules engine reach the right verdict, especially on the Government Warning?).

**Inputs under test.** Each test case is a label image plus the declared application data it is checked against: brand name, fanciful name, class/type, alcohol content, net contents, name & address of bottler/producer/importer, country of origin (imports), and beverage type; wine adds varietal/appellation/vintage. Net contents drives the warning type-size check. In the prototype this application data is typed/pasted or loaded from a mock record — there is no live COLA integration.

**A three-part evaluation set.** No single public dataset covers both extraction and compliance, so the set is assembled from three sources:

1. **Real labels with real application data** — from the [TTB Public COLA Registry](https://www.ttb.gov/regulated-commodities/labeling/cola-public-registry) (official; approved label images with declared fields and genuine Government Warnings, 1999–present, free, no signup) and its cleaned, programmatically-accessible mirror [COLA Cloud](https://colacloud.us/) (2.9M+ applications, 5M+ images, with CC0-licensed CSV subsets). Roughly 20–50 cases across spirits, wine, and malt beverages provide realistic positives with ground-truth fields.
2. **Varied real-world bottle photography** — to stress image-reading robustness on diverse designs, angles, and lighting: the Hugging Face wine-image datasets [carolinembithe/wine-images-126k](https://huggingface.co/datasets/carolinembithe/wine-images-126k), [Francesco/wine-labels](https://huggingface.co/datasets/Francesco/wine-labels), and [christopher/winesensed](https://huggingface.co/datasets/christopher/winesensed), plus an academic [beer-bottle image set](https://arxiv.org/pdf/2201.03791).
3. **Hand-crafted compliance violations (~10)** — the part no public dataset provides, and the part that proves the rules engine. Generated (AI image generation works well, as the brief itself suggests) to include: a title-case "Government Warning," a paraphrased/abbreviated warning, a sub-minimum-font warning, a missing warning, a STONE'S THROW-style fuzzy brand near-match, a net-contents mismatch, and distilled spirits missing the mandatory ABV.

**How it is used.** Parts 1 and 2 validate extraction; Part 3 validates the deterministic checks and the three-state matching. The rules-engine unit tests (Claude Code, Prompt B2) encode the Part-3 expectations as assertions, and the integration tests (Prompt B8) run the full set end-to-end. Targets: no missed-warning false "pass" on the violation set; high field-extraction accuracy on the real set; correct three-state classification of the near-match cases.

**Licensing note.** COLA Cloud's CC0 subsets are clean for any use; raw COLA Registry images are applicants' artwork (fine for private prototyping and evaluation — verify before redistribution); Hugging Face dataset licenses vary and should be checked per dataset.

---

## 17. Implementation Plan — Claude Design → Claude Code → Production

The build proceeds in three stages, deliberately sequenced so a demonstrable, deployable artifact exists as early as possible, and so the two halves are joined by a single stable seam: the typed API contract.

**Stage 1 — Frontend, in Claude Design.** Build the entire React + Vite interface against mock data and the typed API contract (playbook Part A, Prompts 0–10): the upload screen with client-side downscaling, the streaming result view with per-field three-state badges and evidence crops, the Government Warning analysis panel, the no-dead-ends decision actions, the batch upload + triage dashboard, the keyboard "confirm next" flow, an accessibility pass to Section 508 / WCAG AA, and deployment to Vercel. The output is a working, shareable UI that demonstrates the whole experience before any backend exists. The handoff artifact is the API contract defined in Prompt 2.

**Stage 2 — Backend, in Claude Code.** Implement that exact contract (playbook Part B, Prompts B0–B8): a FastAPI service, the inference-provider interface with a commercial cloud-vision adapter, the deterministic 27 CFR rules engine and its unit tests, the image pipeline (evidence crops + legibility scoring), the streaming endpoint, the batch fan-out, the on-prem adapter (built here but run in cloud mode for the demo), the security/data-handling posture, and integration tests. The two halves are connected by pointing the frontend's `VITE_API_BASE_URL` at the backend. The output is a complete end-to-end prototype on real (commercial) inference, deployed — frontend on Vercel, backend as a Vercel Python function or a small always-on host.

This Stage-1 / Stage-2 split *is* the take-home deliverable: a deployed working prototype plus clean, well-organized code.

**Stage 3 — Production (documented, not built in the take-home).** What remains to make this a real agency system: move inference inside the Azure Government boundary — either Azure OpenAI (managed, FedRAMP High) or a self-hosted Phi-3.5-vision on a sandboxed GPU VM/VNet (`INFERENCE_MODE=onprem`), which resolves the firewall; add the production security posture (PII handling, document retention, audit logging, RBAC) inside the FedRAMP boundary; integrate with COLAs Online / myTTB so intake and decision write-back close the loop; run a formal Section 508 audit and a pilot with real agents (a skeptic like Dave, a specialist like Jenny) to tune confidence thresholds against real override behavior; and, only if the evaluation reveals a measured accuracy gap, fine-tune the small open-weight model. Because inference sits behind an interface and the rules engine is deterministic, none of this requires changing the frontend or the verdict logic — production is a swap at the boundary, not a rewrite.

| Stage | Tool | Builds | Output |
|---|---|---|---|
| **1** | **Claude Design** | React + Vite UI on mock data + the API contract (Part A, Prompts 0–10) | Deployable frontend; the contract is the handoff |
| **2** | **Claude Code** | API, cloud-vision adapter, 27 CFR rules engine, image/streaming/batch, on-prem adapter, tests (Part B, B0–B8) | End-to-end prototype on commercial inference, deployed |
| **3** | **Production (documented)** | Azure Government inference, FedRAMP security posture, COLA integration, 508 audit, agent pilot, optional fine-tune | Agency-ready system inside the accreditation boundary |

---

## 18. Appendix

### A. Verbatim Government Warning Text (27 CFR 16.21)

> GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

Formatting requirements (27 CFR 16.22): "GOVERNMENT WARNING" in **capital letters and bold**; remainder **not** bold; readily legible; on a contrasting background; not compressed; separate and apart from other information. Minimum type size by container: **≤ 237 mL → 1 mm; > 237 mL to 3 L → 2 mm; > 3 L → 3 mm.** Required on all beverages **≥ 0.5% ABV**.

### B. Mandatory Label Elements by Beverage Type

| Element | Distilled spirits (Part 5, §5.63) | Wine (Part 4, §4.32) | Malt beverages (Part 7, §7.63) |
|---|---|---|---|
| Brand name | Required | Required | Required |
| Class / type | Required | Required | Required |
| **Alcohol content** | **Required** | **Required** | **Optional**\* |
| Net contents | Required (same field of vision as name/address) | Required | Required (most common malt error when wrong) |
| Name & address (bottler/distiller/importer) | Required (same field of vision as net contents) | Required | Required |
| Country of origin (imports) | Required | Required | Required |
| Sulfite declaration ("CONTAINS SULFITES") | Conditional (≥10 ppm) | Conditional (where applicable) | — |
| FD&C Yellow No. 5 / aspartame | Conditional (aspartame → verbatim "PHENYLKETONURICS: CONTAINS PHENYLALANINE") | Conditional | — |
| Grape varietal / appellation / vintage | — | Conditional (wine) | — |
| Government Warning (Part 16) | Required (≥0.5% ABV) | Required (≥0.5% ABV) | Required (≥0.5% ABV) |

\*Malt beverage alcohol content becomes **mandatory** if the product contains alcohol derived from added nonbeverage flavors/ingredients. Part 4 governs wine ≥7% ABV; wine at 0.5–7% ABV falls under FDA labeling but **still** requires the Part 16 warning.

### C. Key 27 CFR Citations

- **27 CFR Part 16** — Health warning statement (the Government Warning); §16.21 verbatim text; §16.22 formatting, type-size, contrast, and "separate and apart" requirements.
- **27 CFR Part 5, §5.63** — Mandatory label information, distilled spirits.
- **27 CFR Part 4, §4.32** — Mandatory label information, wine.
- **27 CFR Part 7, §7.63** — Mandatory label information, malt beverages.
- TTB Form **5100.31** — Certificate of Label Approval (COLA).

### D. Sources & Links

- TTB — Labeling resources and COLAs Online / myTTB: https://www.ttb.gov/labeling and https://www.ttb.gov/online-services
- TTB COLA public registry: https://www.ttb.gov/labeling/cola-registry
- eCFR — Title 27 (Alcohol, Tobacco Products and Firearms): https://www.ecfr.gov/current/title-27
- eCFR — 27 CFR Part 16 (Health Warning Statement): https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16
- Section508.gov (federal accessibility): https://www.section508.gov
- WCAG 2.2 (W3C): https://www.w3.org/TR/WCAG22/
- U.S. Web Design System (USWDS): https://designsystem.digital.gov
- 21st Century IDEA Act guidance: https://digital.gov/resources/21st-century-integrated-digital-experience-act/
- FedRAMP Marketplace: https://marketplace.fedramp.gov
- Azure OpenAI in Azure Government: https://learn.microsoft.com/azure/ai-services/openai/azure-government
- Amazon Bedrock (AWS GovCloud) — FedRAMP/IL: https://aws.amazon.com/govcloud-us/
- Google Cloud Vertex AI Assured Workloads: https://cloud.google.com/assured-workloads
- Azure AI Document Intelligence (disconnected containers): https://learn.microsoft.com/azure/ai-services/document-intelligence/containers/disconnected
- COLAClear (automated TTB label pre-screen, public beta May 2026): https://www.colaclear.com

**Test-data sources (Section 16):**

- TTB Public COLA Registry (official, free): https://www.ttb.gov/regulated-commodities/labeling/cola-public-registry — search/view: https://www.ttbonline.gov/colasonline/publicSearchColasBasic.do
- COLA Cloud (cleaned/enriched COLA registry, CC0 subsets): https://colacloud.us
- Hugging Face — carolinembithe/wine-images-126k: https://huggingface.co/datasets/carolinembithe/wine-images-126k
- Hugging Face — Francesco/wine-labels: https://huggingface.co/datasets/Francesco/wine-labels
- Hugging Face — christopher/winesensed: https://huggingface.co/datasets/christopher/winesensed
- Beer-bottle image set (academic): https://arxiv.org/pdf/2201.03791

*Note: the "C — TTB COLA on a .NET/Azure stack" detail is a stakeholder claim and is treated as an assumption, not a publicly confirmed fact.*
