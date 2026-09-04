---
name: planetscale
description: Index of PlanetScale operating skills — read-only inventory, Vitess and Postgres safety reviews, Insights and query tags, Traffic Control, webhooks, schema recommendations, approval gates, and the full best-practices assessment. Use to pick the right workflow skill before inspecting or changing a PlanetScale organization, database, branch, or schema.
---

# PlanetScale operating skills

These skills drive PlanetScale itself: they gather evidence through the PlanetScale MCP server, review it, and turn it into recommendations.

## Where to start

- Full best-practices assessment across every area, ending in one report: `safe-orchestrator`.
- Anything narrower: run `readonly-inventory` first so later steps work from real organization, database, and branch data instead of assumptions.
- Engine-specific schema, indexing, and query guidance: use the `database` skill index instead.

## Rules that apply to all of them

- Gather read-only evidence before recommending anything.
- Never create, modify, or delete a PlanetScale resource without explicit approval; `change-gates-and-approval-contract` defines the approval contract, and `autonomous-execution-mode` defines the only conditions under which approval can be granted up front.
- State what you verified separately from what you inferred.

## Skills

<!-- BEGIN GENERATED INDEX -->
<!-- END GENERATED INDEX -->
