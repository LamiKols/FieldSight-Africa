# FieldSight Africa Agent Instructions

These instructions apply to the entire repository for Codex, Copilot-style coding agents, and other automated contributors.

## Sources Of Truth

- Linear is the source of truth for scope, acceptance criteria, and boundaries.
- GitHub is the source of truth for code, review, pull requests, and validation history.
- Replit is runtime validation only after merge or when explicitly requested for inspection.
- Replit Agent is emergency/debug only because it costs money and can drift from the GitHub branch workflow.

## Build Workflow

- Prefer release-sized PRs over micro-phases unless the work is high risk, ambiguous, security-sensitive, payment-sensitive, or likely to need isolated review.
- Use the workflow: Linear release issue -> Codex large build branch -> GitHub Actions validation -> PR review -> merge -> Replit one-command validation -> Linear Done.
- Implement on feature branches and preserve the existing Flask/Replit application structure.
- Do not auto-merge pull requests.
- Do not auto-close Linear issues.
- Always run validation before completion.

## Required Validation

Run the relevant validation commands before completing work. For release-sized builds, use:

```bash
python scripts/validate_all_phases.py
python -m compileall app.py models.py routes scripts intelligence_insights.py
git diff --check
```

After merge in Replit, use:

```bash
python scripts/post_merge_validate.py
```

## Product And Governance Boundaries

- Do not change payments unless explicitly scoped by Linear.
- Do not change Stripe or Paystack flows unless explicitly scoped.
- Do not expose secrets, private paths, document files, raw extraction text, contact fields, restricted document fields, API secrets, or key hashes.
- Do not bypass consent, review, redaction, publish-readiness, entitlement, audit, or API safety gates.
- Do not auto-publish data, metadata, insights, documents, API output, buyer access, or subscriber access.
- Do not add deployment automation unless explicitly scoped.
- Do not weaken existing validation scripts or GitHub Actions checks.

## Change Discipline

- Read the relevant phase docs before modifying related behavior.
- Keep changes scoped to the Linear issue.
- Avoid unrelated refactors.
- Preserve existing public routes, auth, subscriber flows, admin flows, payment flows, export behavior, partner workflows, document governance, automation governance, and Replit configuration unless the issue explicitly changes them.
- Prefer adding documentation or validation around build-process work instead of touching runtime application code.
