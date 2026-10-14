# Advantage AI design (frozen 2026-10-13)

**Name and tagline:** Advantage AI, "Turn Match Data Into Match Wins".
**Look:** one permanent dark court-green palette (no light/dark switch), photo-led hero, calm panels, tennis-green accent.
**Came from:** references "Escape Tab Hell" (warm editorial, one active item at a time) and "Northpeak" (full-bleed landscape behind the title); see `design/references.md`. The approved design pages (static, sample data) are `design/approved/home.html` and `report.html`; the 6 earlier comparison versions are in git history (commit 19f1242).

## Where the design lives
- `calibration_demo.html` (Home) and `report.html` (Report): each page's `<style>` holds its layout and the colour tokens on `:root`.
- `web_assets/site.css`: shared header bar, footer banner and helpers (loads after the page style).
- `web_assets/site.js`: draws the same header and footer on every page.

## Colours (permanent)
| Token | Hex | Use |
|---|---|---|
| `--bg` | #15261C | page |
| `--surface` | #1C3226 | panels |
| `--surface-2` | #243D2F | tiles, tinted boxes |
| `--line` / `--line-strong` | #31503D / #46684F | borders |
| `--ink` / `--ink-2` / `--muted` | #F1F6EF / #DFEADD / #C3D3C3 | text (all pass strong contrast) |
| `--accent` | #8ED19D | tennis green: active step, links, main buttons |
| `--accent-soft` | #24452F | #1 fix card, chips |
| `--bad` | #E0907F | points lost only |
| green band / footer | #1E4029 / #0D1912 | "How to film" band, footer |
| ball (logo) | #D4EC7E | the ball in the logo |

## Type
- Headings and numbers: **Newsreader** (serif). Body and buttons: **Instrument Sans**. Both from Google Fonts.
- Body 17px (18.4px from "New analysis" down on Home), small text 15–16px, hero headline 40–64px.

## Spacing, shape, motion
- Spacing steps: 4, 8, 12, 16, 24, 32, 48, 64, 96px. Content column 760px, 16px side margins on phones.
- Corners: 8 / 12 / 16px, pills for buttons and tags. Tap targets at least 44–48px.
- Motion: short fades (220ms) only; none when the device asks for reduced motion.

## Layout rules
- Home order (new visitor): photo hero, New analysis (3 steps), How to film (green band with photo), My reports, closing "Every point counts" band, footer. Returning visitors with reports see My reports first.
- The green bar marks the current upload step; finished steps show a check; upcoming steps stay readable.
- Report order: "Your #1 fix" card, overview (big rings, quick stats, AI summary), lost/won bar, top 3 fixes, keep doing, More stats, About this data. Each section is its own panel.
- Same header bar and footer banner on every page. On Home the header floats over the photo.
- Photos (AI-generated, 3 of 5 slots used): hero court from behind the baseline, phone sideways on the fence, ball on the baseline. WebP 800px for phones, 1600px for big screens.

## Always / Never
- **Always:** real data only; one accent (green), red only for lost points; phone first and checked at 375px and at desktop width; text readable outdoors.
- **Never:** competitor names; text inside images; a second colour scheme; decoration that hides a button or a number.
