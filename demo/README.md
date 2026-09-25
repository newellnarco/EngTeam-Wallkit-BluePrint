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

Dark is the default theme. Theme tokens were embedded verbatim from
`frontend/theme/theme.css` when the bundle was made. They are a copy, not a
link: a later change to that stylesheet does not reach the demo (see Source).

## Source -- not in this repository; the demo cannot be regenerated yet

`wallkit-demo.html` is a **vendored build artefact**. Its editable source (a
file named `Wallkit Demo.dc.html`) and the bundler that produced the
self-contained file were never committed here, and no generator for the demo
ships with the kit. It was built against this repository's `main` at the
time; the screen-to-source map it was built with (`github.md`) lived beside
that source and is not here either. This returns nothing:

```
git log --all --diff-filter=A --name-only --pretty=format: -- '*.dc.html'
```

The pathspec matters: without it the command lists every commit that added any
file and proves nothing about this one.

What that means in practice:

- **It cannot be regenerated from a clone.** There is no source to edit and no
  build command to run. Treat the HTML file itself as the source of record.
- **Changes are made to the bundle directly.** The layout fixes recorded under
  "Embed in a page" were applied by editing the inline styles the page carries
  in plain text, and verified by rendering in headless Chromium, not by
  rebuilding.
- **Nothing keeps it in sync.** The event script, the wall tabs and the theme
  tokens are copies taken when the bundle was made; changes to the courier,
  the wall template or `frontend/theme/theme.css` do not reach the demo.
- **If the source is ever committed,** re-apply the three layout fixes there
  too -- a re-bundle from the older source would silently discard them -- and
  replace this section with the real build command.
