# rootcanal-border-shapes

_Root Canal border shapes (2026-11-11) — Box / Scoop (robust ellipsoid) / Snap (convex hull), workflow folders, the 18 shape workflows and their purple counts._

The user asked for non-box borders: "box, snap to point minimum, and something curvy / ice cream scoopy in the middle", each at 5% and 10%. They also asked for workflow folders and for DS, P-spike and Ambiguous to be rerun for every variant.

Their answers (2026-11-11):
- Snap = **convex hull**.
- Scoop = **robust ellipsoid** (MinCovDet).
- Folders **Shape › Grace**.
- Run **without banking**.

Built:
- `rcborder.SHAPES` / `envelope(shape=)`. Levels carry a `shape` dict:
  - ellipsoid: center, M, axes;
  - hull: center, scale, eq, vertices, faces.
- `edges` = the shape's per-axis extent.
- The hull's grace peels hull corners in order of furthest robust Mahalanobis distance.
- Workflow definitions carry `shape` and `folder`. The `rootcanal_workflow_in` pref holds moves made on the page.

The 18 workflows are named "<Shape> <g> · Verified DS / Verified P-spike / Ambiguous"; the ids are in the scratchpad file `shapes_run.json`.
- Purple at 5% / 10%: Box 1334/1225, Scoop 2198/1935, **Snap 671/538**.
- The scoop is worst: an ellipsoid stretched over 37 of the 39 hand-sorted P-spikes swallows most of PTEN.

**The Scoop was retired on 2026-11-12** ("retire and archive all the scoop stuff... like the data and the option in the workflow. Yikes").
- The builder offers Box and Snap only (`RETIRED` in rcworkflow.js).
- The server refuses a new Scoop definition or preview (`WF_RETIRED_SHAPES`). Saved Scoop workflows still run, and the ellipsoid still draws.
- Archived through shared prefs:
  - workflows bc0fbf8e4569, 52d6fcf5f889, 93a828038bba, 6d6737df45ff, 5d52cf9cd610 and 3e1abd34c70c;
  - borders c69c6261e926, 0c3913a5b212, de41d8464e50 and 792915e32eea.
- Don't offer the Scoop again.

**How to apply:** the Meta Workflow (rcmeta) still assumes a box (`rcborder.box_for`). If asked to search with shapes, generalise `evaluate` there. Related: [rootcanal-meta-workflow](rootcanal-meta-workflow.md), [rootcanal-workflow-decisions](rootcanal-workflow-decisions.md).
