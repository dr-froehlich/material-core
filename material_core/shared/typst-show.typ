#import "orange-book/lib.typ": book, part, chapter, appendices

// Quarto's typst output stamps Mermaid PNGs (and other raster images) with a
// pixel-derived absolute width/height (e.g. 7in × 10in) that overflows the A4
// text region. There are two emission shapes to cover:
//   * captioned diagrams become `#figure(...)` — handled by the figure rule;
//   * uncaptioned diagrams become a bare `#box(image(...))` — handled by the
//     image rule, which is what most Mermaid blocks actually hit.
// Both scale the offending content down to fit the available space; neither
// upscales, so already-small images keep their authored size. The image rule
// also runs while the figure rule measures its body, so a captioned diagram is
// fitted once (by the image rule) and the figure rule then no-ops — no double
// scaling.
#show figure: it => layout(size => context {
  let m = measure(it.body)
  if m.width > size.width {
    let f = size.width / m.width
    align(center)[
      #scale(x: f * 100%, y: f * 100%, origin: top + left, reflow: true, it.body)
      #v(it.gap, weak: true)
      #it.caption
    ]
  } else { it }
})

#show image: it => layout(size => context {
  let m = measure(it)
  // Limiting factor across width and height; `calc.min(1, …)` never upscales.
  let f = calc.min(1, size.width / m.width, size.height / m.height)
  if f < 1 {
    scale(x: f * 100%, y: f * 100%, origin: top + left, reflow: true, it)
  } else { it }
})

#show: book.with(
$if(title)$
  title: [$title$],
$endif$
$if(subtitle)$
  subtitle: [$subtitle$],
$endif$
$if(by-author)$
  author: "$for(by-author)$$it.name.literal$$sep$, $endfor$".replace("~", "\u{00A0}"),
$endif$
$if(date)$
  date: "$date$",
$endif$
$if(lang)$
  lang: "$lang$",
$endif$
  main-color: brand-color.at("primary", default: blue),
  logo: {
    let logo-info = brand-logo.at("medium", default: none)
    if logo-info != none { image(logo-info.path, alt: logo-info.at("alt", default: none)) }
  },
$if(toc-depth)$
  outline-depth: $toc-depth$,
$endif$
$if(lof)$
  list-of-figure-title: "$if(crossref.lof-title)$$crossref.lof-title$$else$$crossref-lof-title$$endif$",
$endif$
$if(lot)$
  list-of-table-title: "$if(crossref.lot-title)$$crossref.lot-title$$else$$crossref-lot-title$$endif$",
$endif$
$if(margin-geometry)$
  padded-heading-number: false,
$endif$
  heading-style: 1,
)

$if(margin-geometry)$
// Configure marginalia page geometry for book context
#import "@preview/marginalia:0.3.1" as marginalia

#show: marginalia.setup.with(
  inner: (
    far: $margin-geometry.inner.far$,
    width: $margin-geometry.inner.width$,
    sep: $margin-geometry.inner.separation$,
  ),
  outer: (
    far: $margin-geometry.outer.far$,
    width: $margin-geometry.outer.width$,
    sep: $margin-geometry.outer.separation$,
  ),
  top: $if(margin.top)$$margin.top$$else$1.25in$endif$,
  bottom: $if(margin.bottom)$$margin.bottom$$else$1.25in$endif$,
  book: true,
  clearance: $margin-geometry.clearance$,
)
$endif$
