# Design workflow (unique-frontend)

## Step 0 summary (2026-10-13)
- **What:** upload a singles match video, get a per-player report: what is costing points and what to practise. Two screens: Home (`calibration_demo.html`: my reports, filming guide, upload, mark the court, analysing) and Report (`report.html`: player tabs, rings, quick stats, top 3 fixes, keep doing, more stats).
- **For:** tennis players (both players equally); judged for CAC on Design = UX and how intuitive it is.
- **Feel wanted:** minimal; usability and function first, looks second.
- **Hard rules:** keep every feature and flow; real data only; no competitor names; nothing mentions the parent; code freeze Oct 19 (bug fixes only after).
- **Stack:** plain HTML + `web_assets/site.css` (tokens, light/dark) + `site.js`, served by Modal. Restyle = mostly the token file plus small markup changes. No build step.
- **Current look:** dark, green accent, rounded cards, rings. Works and is clear; reads as a generic dark dashboard. Home stacks a lot before the main action.

## Progress
- [x] 0. Understand the project
- Usability changes approved (10-13): all 8 (see design/BRIEF.md). #5 checked: the number mismatch was my local preview mixing an old AI-tip file with newer stats; live app regenerates tips when stats change, so no code change. #6 same cause; cards still get one shape when a fix has no tip.
- [x] 1. Pick references (files in design/references/, prompts in design/references.md). User picked (10-13): Hedging Overview (green highlight, not orange), Escape Tab Hell, Etched Peaks (wildcard). Accent stays tennis green in all three. Light/dark follows the phone's setting. Usability fixes: user wants the list first, before any change.
- [x] 2. Build versions (10-13; all 6 load, no sideways scroll at 375/1280, no console errors). Next: user picks 1-2 favourites at http://localhost:8765/design/versions/index.html (preview `static-site`). Known: "Shots per rally" shows [TODO] in mocks (live data lacks it; the real page shows "Short points" instead), step-2 one-liner wording is new. 3 looks x 2 skills = 6 (deadline), in design/versions/<slug>-<skill>/ (index.html + report.html); comparison page design/versions/index.html. Shared brief design/BRIEF.md, data design/content.json.
- [ ] 3. Narrow and freeze. 10-13: user picked cream (Escape Tab Hell) impeccable + taste. Refined version in design/versions/cream-refined/ = impeccable fonts + bigger rings + bigger #1 fix card + taste's white panels on a darker cream page; "Short points" fallback as in the live report. Waiting on the user's audit. Then into DESIGN.md + tokens
- [ ] 4. Images. 10-13: name Advantage AI + tagline in. User picked hero idea 1 (the filming view). Generated 2 (+1 retry: B came out as sky only, B retry too low/close); A used, as webp 800/1600 in design/versions/cream-refined/assets/ (PNGs local only). Strip under the buttons on phones, beside the copy at >=900px. Other 4 image slots: not planned (minimal).
- [ ] 5. Tweak bar
- [ ] 6. 21st.dev components (optional)
