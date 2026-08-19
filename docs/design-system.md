# SentinelOps Command Center design system

This document is the implementation contract for the SentinelOps Command Center
template. The retained template reference remains the visual source of truth;
these tokens and mappings keep the coded dashboard consistent as it grows.

## Typography

- UI family: `Inter`, falling back to `Segoe UI`, system UI, and sans-serif.
- Operational metadata: `IBM Plex Mono`, falling back to `Cascadia Code` and `Consolas`.
- Display hierarchy: 31px page title, 20px panel titles, 27px metric values.
- Labels: compact uppercase text with increased tracking for command-center density.

## Color tokens

| Token | Value | Role |
| --- | --- | --- |
| `--bg` | `#020914` | application canvas |
| `--bg-soft` | `#061322` | secondary surface |
| `--panel` | `#081625` | primary cards and panels |
| `--panel-raised` | `#0b1b2d` | selected/raised navigation |
| `--panel-muted` | `#07121f` | evidence and workflow sections |
| `--line` | `#17314a` | default border |
| `--line-bright` | `#24506b` | hover and emphasis border |
| `--text` | `#f1f7ff` | primary text |
| `--muted` | `#8397ad` | secondary text |
| `--accent` | `#26e4d3` | healthy state and primary action |
| `--accent-blue` | `#4c9dff` | focus and secondary action |
| `--danger` | `#ff526d` | rejection and blocked workflow |
| `--amber` | `#f5c866` | approval/safety gate |

## Asset map

All visible non-standard iconography is provided as a real PNG asset under
`src/web/assets/` and served through `/dashboard-assets/{asset_name}`.

| Asset | Usage |
| --- | --- |
| `sheet/brand-lockup-final.png` | Final transparent SentinelOps logo and command-center subtitle supplied by the user |
| `sheet/button-heartbeat.png` | Ready-made active-incident metric button |
| `sheet/button-flow.png` | Ready-made workflow-stage metric button |
| `sheet/button-shield-check.png` | Ready-made automation-policy metric button |
| `sheet/button-gear.png` | Ready-made settings button |
| `sheet/button-add.png` | Ready-made dispatch action button |
| `sheet/incidents.png` | Incidents navigation |
| `sheet/workflow.png` | Workflow navigation |
| `sheet/safety.png` | Safety policy navigation |
| `sheet/heartbeat.png` | Active-incident metric |
| `sheet/flow.png` | Workflow-stage metric |
| `sheet/shield-check.png` | Automation policy and permission-boundary states |
| `sheet/button-workflow-layers.png` | Ready-made layered button for Demo environment card |
| `sheet/add.png` | Incident dispatch action |
| `sheet/logs.png` | Demo scenario action |
| `sheet/container.png` | Service field |
| `sheet/high.png` | Severity field |
| `sheet/sparkle.png` | Empty-state focal mark |
| `sheet/gear.png` | Settings control |
| `sentinelops-icon-sheet.png` | Original source icon inventory |

## Layout contract

- Desktop: persistent navigation rail with a three-card metric row and a
  split incident workspace.
- Static shell: `html`, `body`, and `.shell` are viewport-bound and do not
  scroll.
- Inner overflow: long sidebar content, form content, result content, and the
  stacked responsive workspace own scrolling where required.
- Responsive breakpoints: two-column workspace collapses at `950px`; the
  navigation rail hides at `650px`.
- Safety: real remediation remains gated behind explicit human approval and
  demo mode never mutates infrastructure.
