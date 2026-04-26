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
| REQ-012 | Fix book chapter numbering and document heading conventions | OPEN | [REQ-012](REQ-012.md) | REQ-005 |
| REQ-013 | Orthogonal universal document creation — chapters × slides × brand | OPEN | [REQ-013](REQ-013.md) | REQ-005, REQ-012, REQ-014 |
| REQ-014 | Multi-brand support — visual brand registry in `material-core` | OPEN | [REQ-014](REQ-014.md) | REQ-008 |

New requirement template: [REQ-xxx.md](REQ-xxx.md)
