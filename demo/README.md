# Wallkit interactive demo — embed package

`wallkit-demo.html` is one self-contained file. No build step, no network calls,
no external assets. Open it directly or serve it from any static host.

## Embed in a page

```html
<iframe src="/demos/wallkit-demo.html"
        title="EngTeam Wallkit interactive demo"
        style="width:100%;height:1100px;border:0"
        loading="lazy"></iframe>
```

Give it at least 1100px of height and 1000px of width for the side-by-side
layout. Below roughly 1000px the guided tour wraps under the wall on its own.

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
