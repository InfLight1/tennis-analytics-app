# Design workflow (unique-frontend): status

Round 2 started 2026-11-02 (web app + iPhone app overhaul). Round 1 (Oct 13): references Escape Tab Hell + Northpeak, 6 versions (git 19f1242), frozen into `DESIGN.md`; old references in `design/archive-2026-10-13/`.

## Summary
- Advantage AI web app: film a tennis match on a phone, get each player's top fixes ranked by points lost. Players first, coaches second. Same design will be reused by the iPhone app.
- Screens: player dashboard (`/app`, signed-in home), new analysis (upload / record / court marking), report, sign-in, coach team view (2-3 mockups). The ad/info front page at the main address comes later (signed-in players opening the main address go to their dashboard).
- Works today: court photo hero, calm panels, plain words. Generic today: same rounded green panel everywhere, dashboard is a plain list without visuals, Record match buried.
- Hard rules: real numbers only, no competitor names, no AI technique advice, readable outdoors, phone first.
- **Motion level: None** (Rudra, Nov 2): only interaction feedback.
- Deadline: a couple of days (Rudra, Nov 2).

## Subject brief
- **Subject:** a tennis match filmed on a phone, turned into "what cost you points".
- **Audience / job:** high school + junior players on phones, then coaches on laptops; show your #1 fix at a glance and get the next match filmed.
- **Its world:** chain-link fence, painted court lines, fuzzy yellow ball, match scoreboard, net tape, evening court lights.
- **Most characteristic thing:** your #1 fix as a scoreboard line ("Errors into the net · 6 of 10 points lost") next to a big Record match button.
- **Avoid:** the usual sports-app look (black + neon green, a wall of identical cards).

## Checklist
- [x] 0. Project read, tools checked, subject brief.
- [x] 1. References (Rudra swapped Designs That Work for Human Meet Agent + Forest): Hedging Overview, Summit Widgets, Five Elements, Human Meet Agent, Forest, Apple → 12 versions. `design/references.md`.
- [x] 2. 12 versions (dashboard + report each) in `design/versions/` (local only, gitignored; reference screenshots in `design/references/` stay local too). Compare at `design/versions/index.html` (launch config `design-versions`, port 8780). Known gaps in all: fix #3 "Errors wide" has no tactic/habit/drill in the example data ([TODO]); Player 2 tab is short; video scoreboard score/serve dot are placeholders.
- [x] Rudra picks (Nov 2): **Forest** wins, Apple second, Summit third. Forest taste colours + impeccable visuals; new opening line; start area (Record/Upload) separate from the weekly fix; trends a plain chart players can read; laptop layout uses the wide screen better. Phone view = iPhone app.
- [ ] 3a. Forest v2 (`design/versions/forest-v2/`, shared `forest.css`): built Nov 2. Opening line switcher A "hi, rudra." / B "clear the net." / C "ready to play?" (preview only). Trends = labeled bars ("fewer is better"); Player 2 tab now full from the example data. Rudra (Nov 2): Forest looks good but doesn't stand out, dark theme not readable enough. Superseded by 3b.
- [ ] 3b. Court v3 (`design/versions/court-v3/`, shared `court.css`): dashboard = Summit Widgets layout + Apple taste readability/contrast, solid tiles (no glass); report laptop = Hedging impeccable scoreboard strip + point-by-point chart + Summit photo header + Apple text; report phone = Apple taste, tennis-themed (ball accent, scoreboard numerals, ball pips). Light/dark follows the device, plus a sun/moon toggle in the top bar that remembers the pick (`court.js`). Laptop (1100px+): base text 19px, wider page (1400px), bigger tiles and buttons. Phone viewer: `design/versions/phone.html` (any version in a phone frame, 375/390/430 wide). Dashboard order: one insight + Record first, then latest match, recent matches, and "Your numbers" (data section, always last; contents to be decided later). Rudra (Nov 2): "major improvement", likes the direction; asked for theme toggle, phone viewer, bigger laptop text (done). Next: his phone-view feedback, then freeze.
- [ ] 3. Narrow, quality check (apple-hig, break-ui), freeze into `DESIGN.md`, move into the real pages, coach view mockups.
- [ ] 4. Images (5 slots, Higgsfield).
- [ ] 5. Motion: skipped (None).
- [ ] 6. Tweak bar.
- [ ] 7. 21st.dev review.
- [ ] 8. Final polish (interaction transitions, mobile-native).
