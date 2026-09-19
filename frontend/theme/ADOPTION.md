# Theme adoption

Three files. `theme.css` is the contract; the rest is optional.

```
theme.css        token layer — palette, type, spacing, motion. Import first.
primitives.css   framework-agnostic component classes built on the tokens.
preview.html     the system applied to app chrome, with a light/dark toggle.
```

## Order

1. Import `theme.css`. **Nothing visibly changes** until components start
   referencing tokens, so it is safe to land on its own.
2. Point existing colour values at semantic tokens, one component at a time.
3. Take `primitives.css` if the classes fit your markup, or map the tokens into
   whatever you already use.

Tailwind: feed the semantic layer into `theme.extend.colors` with `var()`
references and keep existing utility classes.

## Layering rules

Use the **semantic** layer in components — `--surface-panel`, `--text-muted`,
`--accent`, `--status-alert`. Reach for the primitive layer (`--c-blue-850`) only
when defining a new semantic token.

Three rules, all lintable, worth wiring into CI:

- No raw hex anywhere in component CSS.
- Every `var()` resolves to a defined token.
- Every semantic token exists in both light and dark.

## The wall itself

The wall (`tools/wall/render/wall_template.html`) is the one consumer that
cannot follow step 1, because it is a **single self-contained file**: the
courier inlines the snapshot and the page is opened from `file://` as often as
it is served, so there is no stylesheet for it to link. The token layer is
therefore **embedded**, between two markers:

```
/* ==== BEGIN theme.css (embedded verbatim from frontend/theme/theme.css) ==== */
   ... the whole of theme.css, unmodified ...
/* ==== END theme.css ==== */
```

Below the END marker sits the component layer: the `primitives.css` classes the
page actually uses (`.panel`, `table.data`, `.chip`, `.meter`, `.tabs`,
`.notice`, `.empty`) plus the wall-specific pieces — the sweep lamp, the arc
bands, the status chips. It reaches for **tokens only**.

Re-embedding after a theme change is a copy-paste between the markers. Nothing
else in the file moves.

### The sync guard

An embedded copy is a copy that can drift, so `tests/test_wall_design.py` holds
it to the contract:

- every custom-property **name** defined in `theme.css` appears in the
  template's style block — a token added to the theme and not re-embedded fails
  here, not at the next screenshot;
- the embedded block is `theme.css` **verbatim**, not a paraphrase of it;
- **zero hex literals** below the END marker — a raw colour there is a colour
  that will not follow light mode, which is the bug the token layer exists to
  prevent;
- every `var()` in the file resolves to a token the file defines;
- light and dark come from `theme.css`'s own `prefers-color-scheme` rules; the
  component layer never redefines a colour for a mode.

The same file also checks the markup the theme is applied to: the four tab
labels in order, one chip class per status in the closed set
`{planned, in_progress, blocked, review, done, shipped}` plus the neutral
`chip--st-unknown` fallback, the arc grouping, and the error banner that a
malformed `wall.json` raises instead of a blank page.

## Contrast

Every text pair clears WCAG AA (4.5:1) against its intended background in both
modes. Four values from the original wall design failed and were corrected:
`chalk-faint` 2.66, `steel` 3.85, `flag` 4.25, `sage` 4.42. Fine for a 6px dot,
not fine for a chip label.

Brass needs two values. `#c9962f` reads at 6.11:1 on navy but collapses to 2.66:1
on white; light mode uses `#7a5a14` at 6.36:1.

**Verify before changing any colour.** The check is a dozen lines of Python.

## Intent

Blueprint stock and brass. Cool slate ground, warm metal accent, structure
carried by hairline rules rather than cards and shadows.

- Radius stays at 2px so panels read as drawn rules, not floating cards.
- No drop shadows anywhere.
- Tables, not card grids — dense data belongs in aligned columns where values
  compare down a column instead of being hunted across identical boxes.
- Mono is for numerals and identifiers, where alignment or
  character-by-character reading matters. Never as decoration on labels.
- One accent button per view. Brass stops meaning "the primary action" the
  moment there are two.
- Light mode is cool paper, not cream. Deliberate: cream with a warm accent is
  the most common look in generated design work, and the blueprint concept wants
  a cool ground.
