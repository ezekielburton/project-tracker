# Theming — how light & dark mode work

Read this before writing any front-end CSS for Helix. It explains how the app switches between light and dark, and the few rules that keep new work from breaking in one mode or the other. Most of these rules exist because we already hit the problem the hard way — see "Traps" at the end.

## The short version (follow these 4 rules)

1. **Never hard-code a colour** (`#fff`, `#1a1a1a`, etc.) in CSS. Use a role token instead: `var(--surface)`, `var(--text)`, `var(--border)`, and so on. A test fails the build if you hard-code a hex in a themed stylesheet.
2. **A coloured button, pill, or highlighted state needs its own dark version.** Using a token for the fill (`background: var(--sky)`) is *not* enough — a solid colour that looks right on a light page becomes a glaring block on a dark one. Add a `:root[data-theme="dark"]` override using the tinted values below.
3. **Don't leave text inputs unstyled.** A bare `<input>`/`<textarea>` uses the browser's own white/black, which turns into a glaring white box in dark mode. There's a global fallback that handles this, so just don't override it with a hard-coded colour.
4. When something looks wrong in one mode, check the **Traps** section before anything else — the causes are rarely obvious.

## How the theme is switched and remembered

- The whole thing hangs off one attribute: **`data-theme="dark"` on `<html>`**. Present = dark, absent = light. All the dark styling is written against that attribute.
- A light/dark **toggle** lives in the header (and in Settings → Appearance). Flipping it sets/removes `data-theme`.
- The choice is remembered **two ways**: instantly in the browser (`localStorage`), and saved to the person's account (a `theme_preference` field on the user, saved via `POST /account/theme-prefs`). So it sticks on this device *and* follows them to any other device. Whichever they changed most recently wins on load.
- **No flash on load:** a tiny inline script in `<head>` reads the saved choice and sets `data-theme` *before* any stylesheet loads, so the page never flashes the wrong theme. Don't move or defer that script.

## The colour system

Colours are defined as tokens (CSS variables) in `main.css`, in three layers:

1. **Raw palette** — the actual brand colours by name: `--brand`, `--tangerine`, `--sandstone`, `--sky`, `--coral`, `--clover`, `--white`, `--black`, `--grey-light/mid/dark`, etc.
2. **Semantic aliases** — older helpers already used around the app: `--text-muted`, `--border`, `--border-subtle`, `--surface-hover`.
3. **Role tokens** — the ones you should reach for in new work:
   - `--surface-sunken` — the page background
   - `--surface` — a card or panel
   - `--surface-raised` — a modal or elevated panel
   - `--text`, `--text-muted`, `--text-faint` — text, in order of importance
   - `--border`, `--border-strong` — lines and dividers
   - `--scrim` — the dim backdrop behind a modal

In light mode these point at the light palette. The `:root[data-theme="dark"]` block in `main.css` then redefines the palette *and* the role tokens with dark values, so anything built on role tokens flips automatically.

**Rule of thumb:** build with role tokens (`--surface`, `--text`, `--border`), not raw colour names, and never a raw hex. If you do that, your feature is dark-ready for free — except for coloured fills, which need rule 2.

## Readable text

Text must reach **4.5:1** contrast against what it sits on (WCAG AA) in both themes. The light-theme values were tuned to that:

| Token | Light | Dark | Use |
|---|---|---|---|
| `--tangerine` | `#F27F55` | `#F27F55` | orange text, links, buttons, highlights (the brand colour; below 4.5:1 on cream, so keep it off small body text) |
| `--brand` | `#F27F55` | `#F27F55` | the logo V, sidebar and navigation only |
| `--pine` | `#4F6247` | `#63775B` | green text |
| `--text-muted` | `#5C5C5C` | `#b3a89a` | secondary text |
| `--text-faint` / `--grey-mid` | `#696969` | `#9a8f7e` | the quietest text that is still read |
| `--border-strong` | `#AAAAAA` | `#4a4033` | lines that must be seen, such as input edges |

**Brand vs text orange.** `--brand` is the main brand colour and stays the bright tangerine everywhere: the logo V, the sidebar, and navigation (active nav items, tabs, the bell badge). Everything else orange uses `--tangerine`, which is the same brand tangerine in both themes. On the light background it is about 2.5:1, so use it for headings, buttons and highlights, not small body text.

**Still below 4.5:1, left for later:** rose, salmon, coral, clover, poppy, oak, ashen, canary and lavender when used as text (they are mainly fills, so changing the token would change the fills too); the single text uses of `#777777` and `#BBBBBB`; pine as text in dark (about 3.5:1); DI canary on sandstone (about 4.3:1). Chart series colours were not part of this pass.

## Exact values to reuse (don't invent new ones)

**Coloured action buttons in dark** — tinted fill + brighter label + translucent border:

- **Blue** (Submit / Save): `background: rgba(143,196,240,0.15)` · `color: #8FC4F0` · `border-color: rgba(143,196,240,0.45)` · hover background `0.24`
- **Green** (Approve / Done): `background: rgba(76,175,90,0.18)` · `color: #6FD07E` · `border-color: rgba(111,208,126,0.45)`
- **Danger**: `background: rgba(255,79,79,0.14)` · `color: #FF7A7A` · `border-color: rgba(255,122,126,0.4)`

**Status pills in dark** — same tinted approach, one per status (In Design, Pre-Production, Handed to Production, On Hold, Cancelled). The full set lives in `shared.css` as the `.status-pill--*` dark rules — copy from there rather than guessing.

## Traps (the expensive lessons — check these first when a mode looks wrong)

1. **A token fill still needs a dark override.** `background: var(--sky)` looks themed but isn't — the token is a solid light-blue that stays bright on dark. Any solid coloured fill (buttons, pills, active/selected states, chat bubbles, wizard steps) needs its own `:root[data-theme="dark"]` rule with the tinted values above. This caused a whole run of "still bright blue" reports.
2. **`color-mix(... , white)` is not theme-safe.** Mixing a colour toward `white` bakes in a light bias regardless of the theme, because `white` never changes. Mix toward `transparent` instead.
3. **Unstyled inputs go white in dark.** A plain `<input>`/`<select>`/`<textarea>` with no `background`/`color` uses the browser default — invisible in light, glaring in dark. There's one global fallback in `main.css` (`input, select, textarea { background: var(--surface); color: var(--text); }`) that covers this; rely on it, don't fight it.
4. **A stray `*/` inside a comment silently kills the next rule.** Any `*/` ends a CSS comment, even mid-sentence — so a comment like `/* .btn-approve-*/danger */` closes early and garbles the rule below it, with no error and no warning. If a fix you *know* is correct and committed simply doesn't apply (after ruling out caching), grep your comments for an early `*/`, and check Chrome DevTools' Styles panel — if the rule isn't listed as matching at all (rather than struck through), the CSS is being dropped as invalid.

## The safety net

`test_dark_mode_css.py` (`test_no_hardcoded_hex_outside_tokens`) scans the themed stylesheets and fails if it finds a hard-coded hex colour outside the token definitions. If it fails, you hard-coded a colour somewhere — replace it with a role token.

## Checklist for a new module that touches the front end

- Build with role tokens (`--surface`, `--text`, `--border`, …); no hard-coded hex.
- Any coloured fill (button, pill, active state) gets a `:root[data-theme="dark"]` tinted override — reuse the values above.
- Don't restyle inputs with fixed colours; let the global fallback handle them.
- Text reaches 4.5:1 in both modes; orange text is `--tangerine`, never `--brand`.
- Open your new UI in **both** modes before calling it done — especially modals, overlays, and anything with a coloured highlight.
- If the hex test fails, or a fix won't apply, check the Traps above.
