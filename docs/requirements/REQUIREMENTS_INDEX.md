# Requirements Index

| ID | Title | Status | File | Depends on |
|----|-------|--------|------|------------|
| REQ-001 | Split repository into `material-core` (tooling) and `material` (content) | DONE | [REQ-001](REQ-001.md) | – |
| REQ-002 | Session backlog: tooling ideas to refine post-split | DROPPED | [REQ-002](REQ-002.md) | REQ-001 |
| REQ-003 | Matrix-driven CI with explicit `projects.yml` manifest | DONE | [REQ-003](REQ-003.md) | REQ-001 |
| REQ-004 | `matctl course add` / `matctl course remove` — course lifecycle CLI | DONE | [REQ-004](REQ-004.md) | REQ-001, REQ-003 |
| REQ-005 | Standalone document support — `doc` template and `matctl doc add` / `doc remove` | DONE | [REQ-005](REQ-005.md) | REQ-003, REQ-004 |
| REQ-006 | `matctl token` — token lifecycle CLI (issue / list / revoke / show) | DONE | [REQ-006](REQ-006.md) | REQ-001, REQ-004 |
| REQ-007 | Prefix grouping — shared access scope for co-deployed courses and documents | OPEN | [REQ-007](REQ-007.md) | REQ-005, REQ-006 |

New requirement template: [REQ-xxx.md](REQ-xxx.md)
