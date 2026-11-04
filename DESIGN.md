# Advantage AI design: "Court" (frozen 2026-11-02, landing added 2026-11-04)

**Name and tagline:** Advantage AI, "Turn Match Data Into Match Wins". Slogan: "Built by a player, for players" (footer on every page).
**Look:** clean, high-contrast, solid tiles on a plain page (no see-through glass); a sharp court photo across the top of each page; ball-yellow for the main action; scoreboard-style numbers. **The website has one fixed look (the Light column); light and dark are for the iPhone app only (Rudra, Nov 4).**
**Came from (round 2, Nov 2):** dashboard = Summit Widgets layout + Apple readability; report on laptops = Hedging Overview scoreboard strip + point-by-point chart; report on phones = Apple, made more tennis. References in `design/references.md`. Approved static pages: `design/versions/court-v3/` (`index.html` dashboard, `report.html` report, `court.css`, `court.js`; local only). Round 1 (Oct 13, dark green + serif) is in git history.
**Same screens on the iPhone app:** the phone layout is the app layout.

## Where the design lives
- `web_assets/tokens.css`: every colour, font, size and radius (website look; dark values for the app are in the table below). Pages use these tokens only.
- `web_assets/court.css`: shared tiles, buttons, fixes list, ball pips (dashboard and report). `web_assets/site.css`: header, footer, phone tab bar. `web_assets/site.js`: draws those.
- Pages: `app.html` (dashboard, `/app`), `report.html`, `account.html` (sign-in + coach view), `landing.html` (front page, `/`), `calibration_demo.html` (new analysis, `/new`).
- Each page's own `<style>`: layout only.

## Colours
| Token | Light | Dark | Use |
|---|---|---|---|
| `--page` | #EDF0F2 | #0E1113 | page |
| `--tile` | #FFFFFF | #1A1E21 | tiles |
| `--tile-2` | #F4F6F7 | #23282C | inner boxes, chips |
| `--line` | #DCE1E4 | #2E3438 | borders |
| `--ink` / `--ink-2` / `--ink-3` | #0F1A14 / #47534D / #5F6A64 | #EEF2EF / #B3BDB8 / #8F9A95 | text |
| `--ball` | #C6DA2C | same | main action (Record, start), "ahead", won pips, ball dot. Text on it is always #0F1A14 |
| `--ball-soft` | #EFF5C8 | #2A3214 | "Try this" boxes |
| `--lost` / `--lost-soft` | #C2412F / #FBE5E1 | #F2836F / #3A221E | points lost only |
| `--night` | #0F1A14 | #000000 | the dark "New match" tile, #1 FIX tag |

## Type
- System font stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, Roboto`); never bundle SF Pro.
- **Landing page exception (Rudra, Nov 2):** the landing page at the main address keeps the round-1 fonts, **Newsreader** (serif headings) + **Instrument Sans** (body), for a premium feel. The app screens use the system stack.
- Scoreboard numbers: **Barlow Condensed 700** (Google Fonts), numbers only.
- Headings 700 with tight tracking: XL clamp(2.4rem, 5.4vw, 3.6rem), L clamp(1.6rem, 2.6vw, 2.1rem), M 1.3rem, S 1.05rem. Body 1.0625rem.
- Laptops (1100px+): base size 118.75% (body about 20px), page width 1400px, bigger tiles/buttons/pips.

## Shape, spacing, motion
- Radius 20px tiles (24px on laptops), 12px inner boxes, pills for buttons/tabs. Tap targets 44px+ (main button 58px, 66px on laptops).
- Gutter clamp(16px, 4vw, 48px); sections 56px apart (40px on phones).
- Motion level **None**: only tap feedback (press scale .97, 120-200ms colour changes). Nothing moves on scroll. Reduced motion respected.

## Layout rules
- **Dashboard (signed-in home, `/app`):** order is fixed. 1) Court photo + "Hi, name". 2) Two tiles: **This week's fix** (white: one insight, one big number, Try this, Watch the points) and **New match** (dark: Record match in ball-yellow, Upload a video, filming tip). 3) Your latest match: top 3 fixes + what you did well. 4) Recent matches (scoreboard scores, Win/Loss tags). 5) **Your numbers** (data for keen players), always last, latest match first in every chart. Never open with data.
- **Report:** photo header with title, Save as PDF, Share with your coach, Player tabs. Then the **#1 FIX scoreboard strip** (fix, line, ball pips, big count), watch the points (video + moment times + Try this) beside the top fixes, what went well (big numbers + ball pips), serve and return (each with a plain line), point by point (yellow ahead, red behind), how sure the app is.
- **Phone:** one column, same order, solid bottom tab bar (Home, Matches, Record as a ball, Account).
- Charts: plain labels, say "fewer is better" / "more is better", a one-line verdict, latest first; built for players and coaches, not analysts.
- Kept from round 1 (behaviour, restyled): New analysis steps (Upload | Record switch, camera preview, mark the court with the 7 draggable dots, full-screen recording view); Save as PDF print layout; My reports cards with delete (asks first); passcode + sign-in.

## Landing page (`/`, Nov 4)
- Fonts: Newsreader titles (regular weight, italic for the key words), Instrument Sans body. Serif titles are for this page only.
- Colours added: `--court-deep` #0A1410 (page dark), `--court-out` #154734, `--court-in` #1E7A52, `--court-line` #EEF2EF, `--lost-glow` #F2836F.
- **Wow moment:** a drawn court, seen from the back fence where the phone films, with a rally that ends in the net. Scrolling raises the camera overhead, the 11 lost points of the example match land on the court, then the net errors light up and the #1 fix card appears. Real counts; spots labelled as illustration.
- Order: court story, how it works (3 steps), the report, 17 of 20 band, for coaches (sample team view, labelled), for parents and schools, Every point counts. No price shown yet. Motion is this one moment only; reduced motion or no scripts shows everything stacked.
- Signed-in players go to `/app` (`/?stay=1` keeps them on the page).

## The one bold thing
The **#1 fix as a scoreboard** (big condensed count + one ball per lost point) next to a bright ball-yellow Record button. Everything else stays quiet.

## Always / Never
- **Always:** real data only (sample data labelled); solid tiles; ball-yellow only for the main action and "good" (landing: also the 17 of 20 band); red only for points lost; check at 375px and laptop width.
- **Never:** see-through/glossy glass cards; low-contrast text on photos (darken behind text); competitor names; text inside images; AI technique advice; new colours/fonts outside `tokens.css`; generic AI looks (purple gradients, neon on black, walls of identical cards).
