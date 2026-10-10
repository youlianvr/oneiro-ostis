# Oneiro — design direction, tokens and states (W0)

Companion to `docs/MASTER-PLAN.md` § 3 (the shape of the product) and § 4 (the
settings catalog). This file records the direction and the token vocabulary; the
tokens themselves live in `python/oneiro/static/console.css` and are measured by
`tests/test_console_tokens.py`. The five screens arrive in W6 — this is the ground
they are built on.

## 1. Direction

One window, one loopback origin, five screens: Conversation, Tasks, Tools, Settings,
Memory. The interface exists to answer three questions — *what is happening now*,
*what is needed from me*, *what changed* — and a panel that answers none of them is not
in v1.

CowAgent is the design source, not the shell: its conversation rendering, composer and
state handling are studied and reworked, while navigation, layout and every panel are
ours (`docs/DECISIONS-v1.md` § 1.3). What is kept from it is the working mechanic, not
the twelve-screen host console.

Rules that hold on every screen:

- **No JSON on screen.** Structured data is shown as fields, lists and cards; the raw
  value is available where it is genuinely the content (the settings catalog), never as
  the interface.
- **No lying panel.** A capability that is not wired yet is either hidden or shown as
  declared-not-in-force; nothing is faked (`pending` in the settings catalog is the
  same rule).
- **Every failure is a sentence.** A refusal carries its reason in plain words, with the
  exact arguments it refused.
- **Keyboard first.** One visible focus treatment, reachable in every theme,
  `prefers-reduced-motion` honoured.

## 2. Token vocabulary

A theme re-declares the same custom properties; nothing below the token blocks names a
colour. The vocabulary, per theme:

| Group | Tokens | Use |
| --- | --- | --- |
| Surfaces | `--oi-bg`, `--oi-bg-alt`, `--oi-surface`, `--oi-surface-2` | page, page stripe, cards, nested cards |
| Text | `--oi-fg`, `--oi-muted` | body text, metadata |
| Lines | `--oi-border` | separators, card outlines |
| Interaction | `--oi-accent`, `--oi-accent-fg`, `--oi-accent-soft`, `--oi-focus` | primary action, its label, tinted background, focus ring |
| Meaning | `--oi-success`, `--oi-warning`, `--oi-danger` | state of a task, an approval, a failure |

Shared, theme-independent: the spacing scale (`--oi-space-1..6`), radii, the type scale
(`--oi-text-xs..2xl`), motion durations, and the two shadow levels.

Motion is short and purposeful only: `--oi-motion-fast` 120 ms, `--oi-motion-base`
180 ms, one easing. Transitions carry state change, never decoration; the reduced-motion
media query collapses them all.

## 3. The five themes and where they come from

The library is `tools/ux-ui-agent-skills/design-systems/library/` (138 systems, each
with a `DESIGN.md`); the match was verified on 2026-10-09.

| `ui.theme` | Library system | Character | Notable deviation |
| --- | --- | --- | --- |
| `night` (default) | none — derived | dark and warm; terracotta accent, warm greys | built from `warm-editorial`'s palette plus a dark neutral base, since the library has no dark theme of this character. Recorded as a derivation, not as a library system. |
| `paper` | `paper` | light, print-inspired, near-black ink | accent darkened to true ink; the library's `#8B5CF6` secondary is not used as text |
| `editorial` | `editorial` | serif headings (Gelasio), ink on white | the library's neutral secondary becomes `--oi-surface-2` |
| `cosmic` | `cosmic` | cool light, wide display face | accent `#1D4ED8` instead of the library's `#3B82F6`, which reads 3.7:1 with white text (below AA) |
| `agentic` | `agentic` | warm off-white, orange accent | accent `#B83F00` instead of `#FF5701`, which reads 3.0:1 with white text |

No web fonts are fetched: the product is local-only and one window must render with what
the machine has. Library families are named first with real fallbacks.

## 4. What is measured, not asserted

`tests/test_console_tokens.py` reads the stylesheet and checks, per theme:

- the theme names equal `ui.theme`'s declared choices, so the setting and the CSS cannot
  drift apart;
- every theme declares every token;
- **contrast**: `fg`/`bg`, `fg`/`surface`, `muted`/`bg` and `accent-fg`/`accent` reach
  WCAG 2.2 AA (4.5:1); `success`, `warning`, `danger` and `accent` reach 3:1 against the
  background, which is what a state colour needs;
- reduced motion and `:focus-visible` are present;
- nothing paints a literal colour below the token blocks — the failure mode that makes a
  theme switch half-work.

W7 repeats this for the finished screens, adds the RU/EN catalogs and takes the contrast
measurement into the built pages.

## 5. States every element and panel must have (W6 checklist)

Per element: rest, hover, active, focus-visible, disabled, loading.
Per panel: empty (with a sentence, not a blank), loading, error (with the reason), and
the declared-not-in-force state for anything the build does not do yet.

A conversation turn is a card sequence, not a log line: the message, each tool call, its
result, a refusal with its reason, an approval request with its exact arguments, a
question, and an unknown outcome — each with a badge on the composer so the owner can see
that something is waiting.
