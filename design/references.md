# Design references (unique-frontend, Nov 2 2026)

Picked by Rudra on 2026-11-02 for the web app + iPhone app overhaul. Images in `design/references/`. Old set (Oct 13): `design/archive-2026-10-13/references.md`.

Project guardrails added to every style: phone first (375px) and desktop; 44px tap targets; text readable outdoors (strong contrast); real data only (see `design/versions/content/CONTENT.md`); never competitor names; never AI technique advice; one main accent; a "lost points" colour only for points lost.

## 1. Hedging Overview (`hedging-overview.jpg`)
- **Family:** Dashboard UI · dark · product-UI led
- **Aesthetic:** black mobile dashboard + KPI cards with sparklines, one accent area chart with tooltip, pill tabs, dense table with mini charts, condensed numerals, bottom tab bar.
- **Reference:** `design/references/hedging-overview.jpg`. Match the feel, not the content.
- **Intent:** precise and in control, so a match's data is readable at a glance on a phone.
- **Guardrails:** Always one accent colour for all data, KPI cards with a trend line and change, condensed numerals, clear grouping. Never red/green everywhere, decorative imagery, rounded playful shapes, light mode; the AI-look list in `anti-generic.md`, except what this reference clearly shows.

## 2. Summit Widgets (`summit-widgets.jpg`) — "evolve today's look" option
- **Family:** Glassmorphism · dark photo · photo led
- **Aesthetic:** frosted glass widgets over one dramatic landscape (here: our dusk court photo), thin large numerals, progress ring, bar chart with one highlighted bar, quote card, thin light sans.
- **Reference:** `design/references/summit-widgets.jpg`. Match the feel, not the content.
- **Intent:** serene and aspirational, so your match data feels part of the court you play on. Keep today's court-green family (evolve, don't replace).
- **Guardrails:** Always real background blur behind every card, the court photo behind the UI (`content/court-photo.webp`), thin light type, a single warm accent. Never opaque cards, heavy borders, busy multicolour charts, flat solid backgrounds; the AI-look list, except what this reference clearly shows.

## 3. Five Elements (`five-elements.png`) — wildcard
- **Family:** Swiss grid · light · type/data led
- **Aesthetic:** strict two-column split, black and white only, technical diagram as the art (a court diagram), plain grotesk uppercase headline, boxed grey nav tabs, large numeral.
- **Reference:** `design/references/five-elements.png`. Match the feel, not the content.
- **Intent:** thoughtful, precise, calm, so the analysis reads like a measured method, not a gadget. Grid lines echo court lines.
- **Guardrails:** Always a hard-edged grid with clear columns, black/white/grey (one tiny ball-yellow exception allowed for the ball only), diagrams or data as the art, plain uppercase grotesk. Never gradients, rounded corners, colour accents, lifestyle photos; the AI-look list, except what this reference clearly shows.

## 4. Human, Meet Agent (`human-meet-agent.png`) — wildcard
- **Family:** Monochrome luxe · dark · metaphor led
- **Aesthetic:** near-black canvas, serif headline with one word in a pixel font, a swarm of small pixel icons (here: pixel tennis balls / point markers), black-and-white photo detail, monospace body copy, minimal centered nav.
- **Reference:** `design/references/human-meet-agent.png`. Match the feel, not the content.
- **Intent:** clever, confident, a little nostalgic (like an old arcade scoreboard), so a serious AI tool shows personality without shouting.
- **Guardrails:** Always one visual metaphor that tells the story (each point of the match as a pixel), a single word in a contrasting retro font, monospace for long body copy, pure greyscale. Never colour accents (except the "lost points" marker if needed), glowing gradients, stock robot imagery, busy grids in the hero; the AI-look list, except what this reference clearly shows.

## 5. Forest (`forest.jpg`)
- **Family:** Nature editorial · dark green · photo led
- **Aesthetic:** one atmospheric scene filling the top (our dusk court photo with mist / light-beam treatment), huge thin lowercase type, small details to discover, underlined active nav item, round icon badges, framed card on a blurred backdrop.
- **Reference:** `design/references/forest.jpg`. Match the feel, not the content.
- **Intent:** immersive and calming, so opening your match feels like a quiet place to think, not a stats dump.
- **Guardrails:** Always one atmospheric scene, thin geometric type set very large, deep greens throughout, small natural details. Never bright UI colours, busy feature lists, bold heavy type, flat illustrations; the AI-look list, except what this reference clearly shows.

## 6. Apple (no screenshot)
- **Aesthetic:** Apple: restraint, generous whitespace, optical type sizing and tight tracking, translucent materials and depth, soft continuous corners, one accent colour.
- **Reference:** the `apple-design` skill's principles. Not a copy of apple.com.
- **Intent:** calm, precise and physical; content first. Closest to how the iPhone app will feel.
- **Guardrails:** Always the system font stack (`-apple-system, BlinkMacSystemFont, system-ui, ...`; never bundle SF Pro), accessible contrast, 44px tap targets. Never Apple logos, product images or Apple's own copy.
