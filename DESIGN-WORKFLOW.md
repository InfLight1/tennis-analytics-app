# Design workflow (unique-frontend): status

Done 2026-10-13. Final rules: `DESIGN.md`. Approved static pages: `design/approved/`. References: `design/references.md`.

- [x] 0–1. Project read; references picked (Escape Tab Hell, plus Northpeak for the hero).
- [x] 2. 6 versions built and compared (removed after the pick; in git history, commit 19f1242).
- [x] 3. Narrowed, frozen into `DESIGN.md`, moved into `calibration_demo.html` + `report.html` (+ `web_assets/site.css`, `site.js`).
- [x] 4. Images: 3 of 5 slots (hero court, phone on fence, ball on line), WebP in `web_assets/`.
- [ ] 5. Tweak bar: skipped (close to the Oct 19 freeze). Tokens sit in each page's `:root`.
- [ ] 6. 21st.dev components: not needed.

**Blend pass (2026-10-25, branch `site-blend`, not deployed):** Home seams softened (hero fade + overlapping first panel, photo bands fade in/out, one green ramp to the footer, even 64px gaps, centre court-line thread); Report: More stats + About this data as one panel; fixed a broken phone rule for the closing band. Motion: None. Merge to `main` and deploy only after CAC is submitted. Local look check: launch config `look-preview` (port 8768; real pages, example report data from the live app).
