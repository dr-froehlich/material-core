# Authoring Manual
# Vorlesungen — Quarto reference

Reference for writing lecture content in this repo. Assumes basic markdown
knowledge and focuses on Quarto-specific extensions in `.qmd` files. The
`_template/` directory shows a rendered example of most features.

Operations and deployment live in [`administration.md`](administration.md).

---

## 1. Front matter

Each `.qmd` starts with a YAML block. Fields currently used:

```yaml
---
title: "Chapter title"
# draft: true             # hide from published site
---
```

Useful additional fields you may want to enable later:

| Field | Effect |
|---|---|
| `subtitle` | Smaller heading under the title (used on slides) |
| `author` | Author name(s); appears in HTML and PDF |
| `date` | Date string; `today` resolves to render date |
| `description` | HTML meta description; shown in link previews |
| `abstract` | Renders an abstract block at the top |
| `keywords` | List, becomes HTML meta keywords |
| `toc: false` | Disables table of contents for this file |
| `number-sections: false` | Disables section numbering for this file |
| `bibliography: refs.bib` | Per-chapter bibliography override |
| `lang: de` / `lang: en` | Language; affects hyphenation, captions |

Project-wide defaults live in `<course>/_quarto.yml`; per-file front matter
overrides them.

---

## 2. Document structure

### Headings and sections

Standard `#`/`##`/`###`. To make a section cross-referenceable, give it an
explicit ID:

```markdown
## Bipolar Transistors {#sec-bjt}

See @sec-bjt for details.
```

Section cross-refs require `crossref` to be configured (already on in the
template via `number-sections: true`).

### Callouts

Five types — `note`, `tip`, `warning`, `important`, `caution`:

```markdown
::: {.callout-note}
## Optional title
Body text.
:::
```

Options: `icon=false`, `collapse=true`, `appearance="simple"|"minimal"`.

### Content visibility

Show in the script (book) but hide on slides:

```markdown
::: {.content-visible unless-format="revealjs"}
Long-form derivation, only in the script.
:::
```

Show on slides only:

```markdown
::: {.content-visible when-format="revealjs"}
:::
```

Show only when rendering with `--profile notes` (teaching notes PDF):

```markdown
::: {.content-visible when-profile="notes"}
::: {.callout-tip}
## Teaching Note
Pacing reminders, demo steps, board sketches.
:::
:::
```

### Speaker notes (slides only)

```markdown
::: notes
Notes for presenter view; never published.
:::
```

---

## 3. Cross-references

Quarto's universal `@`-prefix references. The label prefix tells Quarto what
kind of object you are linking to.

| Prefix | For | Defined by |
|---|---|---|
| `@sec-foo` | Section | `## Heading {#sec-foo}` |
| `@fig-foo` | Figure | `![caption](path){#fig-foo}` |
| `@tbl-foo` | Table | `: caption {#tbl-foo}` after the table |
| `@eq-foo` | Equation | `$$ ... $$ {#eq-foo}` |
| `@thm-foo`, `@def-foo`, … | Theorems/definitions | Theorem-style divs |
| `[@key]` | Bibliography | Entry in `.bib` |

Use `[-@fig-foo]` to suppress the prefix word ("Fig.") in the link text.

---

## 4. Math

Inline: `$E = mc^2$`. Display block:

```markdown
$$
U = U_0 - I \cdot R
$$ {#eq-ohm}

From @eq-ohm we see ...
```

Multi-line aligned equations use the LaTeX `aligned` environment inside `$$`:

```markdown
$$
\begin{aligned}
P &= U \cdot I \\
  &= I^2 \cdot R
\end{aligned}
$$ {#eq-power}
```

Theorem-style blocks (`thm`, `lem`, `cor`, `prp`, `def`, `exm`, `exr`) are
available as fenced divs and produce numbered, cross-referenceable items:

```markdown
::: {#def-ohm}
## Ohm's Law
The voltage across a resistor equals current times resistance.
:::
```

---

## 5. Code blocks

### Non-executable, syntax-highlighted

Use a fence with the language name. Optional attributes in `{}`:

````markdown
```{.python filename="blink.py" code-line-numbers="true"}
from machine import Pin
led = Pin(2, Pin.OUT)
led.value(1)
```
````

Useful attributes: `filename=`, `code-line-numbers=true`, `code-fold=true`,
`code-summary="..."`, line highlighting `code-line-numbers="3,5-7"`.

### Executable Python cells

Use `{python}` (curly braces, no leading dot). Quarto runs the cell at render
time and embeds output (text, plots, tables). Requires `jupyter: python3` in
the document or project front matter.

````markdown
```{python}
#| label: fig-uir
#| fig-cap: "Voltage drop across a resistor for varying current."
#| echo: true

import numpy as np
import matplotlib.pyplot as plt

U_0 = 12.0    # V
R   = 4.7     # Ω
I   = np.linspace(0, 2, 200)
U   = U_0 - I * R

fig, ax = plt.subplots()
ax.plot(I, U)
ax.set_xlabel("Current I [A]")
ax.set_ylabel("Voltage U [V]")
ax.grid(True)
plt.show()
```
````

The `#|` lines are cell options. Common ones:

| Option | Effect |
|---|---|
| `label: fig-xxx` | Makes the figure cross-referenceable |
| `fig-cap:` | Figure caption |
| `echo: false` | Hide source, show output |
| `eval: false` | Show source, don't run |
| `output: false` | Run, but suppress output |
| `warning: false` | Hide warnings |
| `fig-width:` / `fig-height:` | Figure size in inches |

Other languages: `{r}`, `{julia}`, `{ojs}`. R cells require `knitr`, others
need their respective Jupyter kernels.

---

## 6. Tables

### Pipe tables (familiar markdown)

```markdown
| Pin | Function | Notes        |
|-----|----------|--------------|
| 0   | GPIO     | Boot strap   |
| 2   | LED      | Active high  |

: GPIO pin assignment {#tbl-gpio}
```

The `: caption {#tbl-...}` line **after** the table makes it numbered and
cross-referenceable via `@tbl-gpio`. Column alignment with `:---`, `---:`,
`:---:`.

### Grid tables

For multi-line cell content, lists inside cells, or block elements (code,
images, math). Borders define the cell grid:

```markdown
+---------------+---------------+--------------------+
| Mode          | Voltage       | Notes              |
+===============+===============+====================+
| Standby       | 3.3 V         | - Wakes on GPIO    |
|               |               | - Slow boot        |
+---------------+---------------+--------------------+
| Active        | 3.3 V         | Full power         |
+---------------+---------------+--------------------+

: Power modes {#tbl-power}
```

`+===+` marks the header row separator (use `+---+` for headerless tables).
Alignment is set by `:` in the separator row, same as pipe tables.

---

## 7. Figures

### File conventions

| Folder | Used for |
|---|---|
| `<course>/assets/diagrams/` | SVGs drawn in Inkscape |
| `<course>/assets/images/` | Screenshots, photos, scans (PNG/JPG) |

### Embedding

```markdown
![Schmitt trigger](../assets/diagrams/schmitt.svg){#fig-schmitt width=70%}

![Oscilloscope screenshot](../assets/images/scope-uart.png){#fig-uart width=80%}
```

Sizing options inside `{}`:

| Option | Example |
|---|---|
| `width=` | `width=60%`, `width=8cm`, `width=300px` |
| `height=` | `height=4cm` |
| `fig-align=` | `left`, `center`, `right` |

The `#fig-...` ID makes the figure cross-referenceable via `@fig-schmitt`.

### Subfigures (briefly)

```markdown
::: {#fig-comparison layout-ncol=2}
![Before](../assets/images/before.png){#fig-before}

![After](../assets/images/after.png){#fig-after}

Before / after comparison.
:::
```

`@fig-comparison` references the group; `@fig-before` references the panel.
See [Quarto docs › Figure Layout](https://quarto.org/docs/authoring/figures.html#subfigures)
for the full grammar (`layout-nrow`, custom layouts).

---

## 8. Diagrams (Mermaid)

Mermaid is the standard for state charts and flowcharts in this repo. Embed
as a fenced cell; add a label to make it a cross-referenceable figure:

````markdown
```{mermaid}
%%| label: fig-fsm
%%| fig-cap: "FSM of the UART receiver."
stateDiagram-v2
    [*] --> Idle
    Idle --> Start: edge detect
    Start --> Data: sample
    Data --> Stop: 8 bits
    Stop --> Idle
```
````

Mermaid cell options use the `%%|` prefix (Mermaid comments). Mermaid
reference: <https://mermaid.js.org>.

For arbitrary graphs where Mermaid auto-layout falls short, Graphviz is
also built into Quarto via ` ```{dot} ` blocks.

---

## 9. Shared content

### Includes

Pull a fragment into multiple documents (typically: same exercise on both
script and slide):

```markdown
{{< include ../_shared/_exercise-1.qmd >}}
```

The included file **must** start with an underscore so Quarto does not render
it as a standalone page. Convention: keep shared fragments in
`<course>/_shared/`.

### When to use what

| Need | Mechanism |
|---|---|
| Same content on script and slides | `{{< include _shared/_x.qmd >}}` |
| Long prose only in the script | `::: {.content-visible unless-format="revealjs"}` |
| Short summary only on slides | `::: {.content-visible when-format="revealjs"}` |
| Speaker-only prompts | `::: notes` (slides) or `when-profile="notes"` (script) |

---

## 10. Citations and bibliography

### Recommended workflow: Zotero + Better BibTeX

1. Install [Zotero](https://www.zotero.org) and the
   [Better BibTeX](https://retorque.re/zotero-better-bibtex/) extension.
2. Create one Zotero **collection** per course
   (e.g. *Digital- und Mikrocomputertechnik*).
3. In Better BibTeX, set a stable citation key format
   (`auth.lower + year` is a sensible default).
4. Right-click the collection → *Export Collection* → format
   *Better BibLaTeX* → check **Keep updated** → save as
   `<course>/references.bib`.
5. Zotero now rewrites the file whenever the collection changes — commit it
   like any other source file.

### Wiring it into Quarto

In `<course>/_quarto.yml`:

```yaml
bibliography: references.bib
csl: ieee.csl          # optional; otherwise Quarto's default style
```

Per-chapter override (front matter):

```yaml
bibliography: ../references-special.bib
```

### Citing

| Markdown | Renders as |
|---|---|
| `[@knuth1984]` | (Knuth 1984) |
| `@knuth1984` | Knuth (1984) |
| `[-@knuth1984]` | (1984) |
| `[@knuth1984; @lamport1986]` | Multiple |
| `[@knuth1984, p. 23]` | With locator |

The reference list is appended automatically at the end of the document
(or wherever `# References {.unnumbered}` is placed manually).

---

## 11. Slide-specific features (RevealJS)

### Slide structure

Each `##` heading starts a new slide. `#` starts a section divider slide.
Horizontal rule `---` also starts a new slide (within the same section).

### Slide-level attributes

```markdown
## Dense slide {.smaller}
## Scrollable slide {.scrollable}
## Centered title {.center}
```

### Highlight box (custom class from `shared/base.scss`)

```markdown
::: {.highlight-box}
**Definition:** ...
:::
```

### Incremental reveal

```markdown
- First point
- Second point

. . .

Pause, then this paragraph appears.

::: {.fragment}
Appears on next click.
:::

::: {.fragment .fade-up}
With a transition.
:::
```

`. . .` (three dots, spaces between) inserts a pause. The `.fragment` class
gives finer control: `.fade-in`, `.fade-up`, `.highlight-red`, etc.

### Columns

```markdown
:::: {.columns}
::: {.column width="60%"}
Left content.
:::
::: {.column width="40%"}
Right content.
:::
::::
```

### Speaker notes

```markdown
::: notes
Pacing notes, anecdotes, demo steps.
:::
```

Press `S` in the published deck to open the presenter view.

---

## 12. Standalone documents (not part of the book)

Some documents — e.g. the *ESP Survival Guide* — should be published
alongside a course but not appear as a chapter in the script. Pattern:

1. **Place the file outside `chapters/`**, for example
   `<course>/esp-survival-guide.qmd` or under a `reference/` sub-folder.
2. **Do not list it** under `book.chapters` in `<course>/_quarto.yml`. Quarto
   still renders any loose `.qmd` in the project, but it will not appear in
   the book's sidebar/TOC.
3. **Override book defaults in the file's front matter:**

   ```yaml
   ---
   title: "ESP Survival Guide"
   toc: false
   number-sections: false
   format:
     html:
       toc: false
     orange-book-typst:
       toc: false
       number-sections: false
   ---
   ```

4. **Link to it from the book** wherever you want to advertise it:

   ```markdown
   See the [ESP Survival Guide](../esp-survival-guide.html) for hardware setup.
   ```

5. **Build:** `quarto render <course>` renders both the book and the
   standalone document into `<course>/_output/`. The deploy step copies the
   whole tree, so the standalone document ships automatically — no workflow
   change needed.

If a standalone document needs entirely different format settings (e.g. a
different page size or no branding), the next step up is to give it its own
sub-project: a `<course>/reference/_quarto.yml` with `project.type: default`
and an extra `quarto render` line in the workflow.
