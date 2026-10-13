# Design brief (shared by all 6 versions)

## The product
Tennis Analytics App: a player uploads a singles match video (filmed from a phone hung on the fence behind one baseline), marks the court, waits for cloud analysis, and gets a per-player report on **what is costing them points and what to practise**. It's for tennis players in general, with both players treated equally. It's judged for the Congressional App Challenge on Concept, **Design (UX, intuitive)** and Technology. The owner wants it **minimal: usability and function come before looks.** It complements a coach and never replaces one. It's honest about data quality.

## Hard rules
- Keep every feature, flow and piece of real copy. Same content in every version; only the design changes.
- Real data only: use `design/content.json` (the real example report) and the real copy in `calibration_demo.html` / `report.html`. Never invent stats, quotes, testimonials, logos or links. Mark anything missing `[TODO]`.
- **The accent/highlight colour is tennis green in every version** (the owner's choice; it replaces any orange/other accent from the reference). Errors/lost points may use one muted red, as today.
- **Light and dark both work and follow the phone's setting** (`prefers-color-scheme`), plus a working toggle in the top bar (`data-theme="light|dark"` on `<html>`), same as today.
- Phone first (375 px wide, 16 px side gutters, no sideways scroll), and it must also look right on a desktop (content column ~760 px). Tap targets ≥ 44 px. Body text ≥ 16 px. Strong contrast (it's used outdoors at a court).
- Never name competitor products. Say "a phone tripod that hooks onto the fence".
- No photos, stock or generated images. Use CSS/SVG only (court diagrams can be inline SVG).
- Fonts: system fonts or at most 2 Google Fonts families. No other external files. One self-contained file per page (inline CSS and JS).
- All design decisions go in CSS custom properties on `:root` (colours, fonts, type scale, spacing, radius, shadow), so the winner can move into `web_assets/site.css`.

## Pages to build (two files per version)
### `index.html`: Home (copy from `calibration_demo.html`)
Top bar: "Tennis Analytics" mark, "New analysis", "My reports", theme toggle.
Order (usability changes 1–3):
1. Hero: "See what's costing you points" + "Upload a match video. Each player gets their top 3 things to fix, with drills to practise."
2. **A clear "See an example report" button** next to the main action (links to `report.html`), not a small text link.
3. **New analysis first** (for a visitor with no reports): step 1 "Choose your match video" (Choose video button, "No video chosen", Upload button, "Up to 60 minutes."). **Add a short note by the button: "Upload over Wi-Fi: a 12-minute 4K video is about 1.5 GB."** Show steps 2 "Mark the court" and 3 "Analysing" as upcoming steps (dimmed), with their real one-line descriptions from the file.
4. "How to film your match": the 5 steps (real copy) with the court diagram(s) as simple inline SVG: phone behind the baseline in the middle, ~8 ft up; all 4 corners and the net in view.
5. "My reports" with its empty state ("No reports yet. Upload a match below and its report will appear here." Reword "below" → "above" since it now sits after the upload), plus the folded "Open a report by its job code" and "Continue an earlier upload".
(Note for the real site: a returning visitor who already has reports sees My reports first. Mock only the new-visitor order.)

### `report.html`: Report (copy and structure from `report.html`, data from `design/content.json`)
- Title "Player 1 vs Player 2", "Points won: 8–11", working Player 1 / Player 2 tabs (small inline JS, data embedded).
- **Usability change 4:** right under the tabs, a compact **"Your #1 fix"** line (the first fix's headline + "−N pts") that jumps to the full Top 3 list.
- Hero: playstyle tags, two rings (Points won %, "8 of 19"; Serves in %, "4 of 13"), quick stats (Aces, Double faults, Shots per rally; use `[TODO]` if a number isn't in the data), one-paragraph AI summary (`ai_summary`).
- "How Player 1 lost points" stacked bar with a working **Lost / Won** switch and a text legend with counts (from `stats.lost_by` / `stats.won_by`).
- **Top 3 things to fix:** rank number, headline (`advice.headline`, else `title`), "−N pts", "Try this:" line (`advice.try_this`, else the first sentence of `advice.match_strategy`). **Usability change 6:** if a fix has no advice, show its `detail` in the same "Why:" slot so every card has the same shape. **Usability change 7:** times shown as plain text labelled **"Find these moments in your video: 0:01 · 5:21"** (not button-looking). Folded "How to practise it" → In matches / Habit to build / Practice drill / Why. Use the first 3 weaknesses with `low_sample: false`.
- "Keep doing" (strengths with +N pts), the line "Tips are written by AI from the tracked patterns. They cover tactics and practice, not stroke technique.", and folded "More stats" and "About this data" (use `coverage.notes`).

## Usability change 8 (all pages)
Bigger tap targets, stronger text contrast, readable in sunlight, clear section grouping. Minimal: no decoration that doesn't help someone read the report.
