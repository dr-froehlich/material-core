# Requirements Index

| ID | Title | Status | File | Depends on |
|----|-------|--------|------|------------|
| REQ-001 | Split repository into `material-core` (tooling) and `material` (content) | DONE | [REQ-001](REQ-001.md) | – |
| REQ-002 | Session backlog: tooling ideas to refine post-split | DROPPED | [REQ-002](REQ-002.md) | REQ-001 |
| REQ-003 | Matrix-driven CI with explicit `projects.yml` manifest | DONE | [REQ-003](REQ-003.md) | REQ-001 |
| REQ-004 | `matctl course add` / `matctl course remove` — course lifecycle CLI | DONE | [REQ-004](REQ-004.md) | REQ-001, REQ-003 |
| REQ-005 | Standalone document support — `doc` template and `matctl doc add` / `doc remove` | DONE | [REQ-005](REQ-005.md) | REQ-003, REQ-004 |
| REQ-006 | `matctl token` — token lifecycle CLI (issue / list / revoke / show) | DONE | [REQ-006](REQ-006.md) | REQ-001, REQ-004 |
| REQ-007 | Group scope — shared access scope for co-deployed courses and documents | DONE | [REQ-007](REQ-007.md) | REQ-005, REQ-006 |
| REQ-008 | Group lifecycle, titles, and `modify` commands in matctl | DONE | [REQ-008](REQ-008.md) | REQ-007 |
| REQ-009 | Auto-generated group landing page (`<group>/index.html`) | DONE | [REQ-009](REQ-009.md) | REQ-008 |
| REQ-010 | Correct document language in scaffolded templates (`lang:` not `book.language`) | DONE | [REQ-010](REQ-010.md) | REQ-005 |
| REQ-012 | Fix book chapter numbering and document heading conventions | DONE | [REQ-012](REQ-012.md) | REQ-005 |
| REQ-013 | Orthogonal universal document creation — chapters × slides × brand | OPEN | [REQ-013](REQ-013.md) | REQ-005, REQ-012, REQ-014 |
| REQ-014 | Multi-brand support — visual brand registry in `material-core` | DONE | [REQ-014](REQ-014.md) | REQ-008 |
| REQ-015 | Make Mermaid → PDF (Typst) dependency explicit and self-installing | DONE | [REQ-015](REQ-015.md) | – |
| REQ-016 | Document identity fingerprint — per-project commit hash and template version in rendered output | DONE | [REQ-016](REQ-016.md) | REQ-013, REQ-014 |
| REQ-017 | Wire brand symlinks into `<project>/slides/` so logo, favicon, and theme resolve at slide render time | DONE | [REQ-017](REQ-017.md) | REQ-013, REQ-014 |
| REQ-018 | Multilingual projects — a project may carry the same content in more than one language | OPEN | [REQ-018](REQ-018.md) | REQ-008, REQ-009, REQ-013 |
| REQ-019 | Shareable tokenized links and QR codes for projects and groups | OPEN | [REQ-019](REQ-019.md) | REQ-006, REQ-007, REQ-009 |
| REQ-020 | External project manuals — surface a public project's handbook under the `manuals` group from a single canonical source | DONE (v0.10.0; live deploy pending `material` PR) | [REQ-020](REQ-020.md) | REQ-005, REQ-009, REQ-013 |
| REQ-021 | De-quartizer — export a Quarto `.qmd` source tree to clean, self-contained GFM | OPEN | [REQ-021](REQ-021.md) | – |
| REQ-022 | Rebrand the tooling as DocSteward (repo/package/CLI naming) | DEFERRED | [REQ-022](REQ-022.md) | – |

New requirement template: [REQ-xxx.md](REQ-xxx.md)
