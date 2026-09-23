# Wallkit interactive demo — embed package

`wallkit-demo.html` is one self-contained file. No build step, no network calls,
no external assets. Open it directly or serve it from any static host.

## Embed in a page

```html
<iframe src="/demos/wallkit-demo.html"
        title="EngTeam Wallkit interactive demo"
        style="width:100%;height:850px;border:0"
        loading="lazy"></iframe>
```

Give it at least 850px of height and 1000px of width for the side-by-side
layout. Below roughly 1000px the guided tour wraps under the wall on its own.

**The height figure is measured, not believed.** Rendered in headless Chromium
at four frame sizes, the document floor is **812px** (846px with the tallest
tab open), and at 1920x904 it fits with no scroll at all. It was 1152px until
three things were fixed: the wall pane's frame was a hard 860px over a board
that already scrolls internally, the guided-tour column grew to its content
with no cap, and -- the one that guaranteed a scrollbar on every screen
regardless of content -- the page root combined `min-height:100%` with 68px of
vertical padding under `content-box`, so the document was always viewport
height plus 68px. The root is `border-box` now.

## What it does

A scripted 180-minute wave of agent events folds into the snapshot the wall
renders, exactly the way the courier folds real event shards. Visitors can:

- play, pause and scrub the wave clock
- move between all nine wall tabs
- open item detail rows and EXECUTE an item onto the queue
- answer a parked question and watch the item come off blocked
- switch between the dark and light themes
- reset the demo

Dark is the default theme. Theme tokens are embedded verbatim from
`frontend/theme/theme.css`, so the demo tracks the real design system.

## Source

Built from `newellnarco/EngTeam-Wallkit-BluePrint@main`. See `github.md` in the
project for the screen-to-source map. The editable source is
`Wallkit Demo.dc.html`; re-bundle after any change.

**That source is not in this repository, and this file says so rather than
pretending otherwise.** `Wallkit Demo.dc.html` has never been committed here
(`git log --all --diff-filter=A --name-only --pretty=format: -- '*.dc.html'`
returns nothing -- the pathspec matters, because without it the command lists
every commit that added any file and proves nothing about this one), and no
bundler ships with the kit, so the re-bundle instruction above cannot
currently be followed by anyone working from a clone. Until the source and its bundler are committed,
`wallkit-demo.html` is a **vendored artefact**: the layout fixes recorded under
"Embed in a page" were applied to the bundle directly, by editing the inline
styles the page carries in plain text, and verified by rendering rather than by
rebuilding. A future re-bundle from the real source will silently discard them
unless the same three changes are made there too.
