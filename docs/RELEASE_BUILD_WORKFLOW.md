# Release Build Workflow

Linear source of truth: FSA-31

Branch: `feature/agent-build-acceleration-release-workflow`

## Purpose

FieldSight Africa now has a GitHub Actions validation pipeline, so future work should move faster through release-sized build branches instead of many small manual micro-phases. The goal is fewer handoffs, fewer repeated Replit checks, and a clearer path from scoped work to validated release.

This is build-process guidance only. It does not change application product behavior.

## Why Move Away From Micro-Phases

Micro-phases were useful while the data foundation, document governance, commercial workflows, and automation layers were being established. They reduced risk while the repository shape was still being discovered.

Now that the validation suite and PR workflow exist, micro-phases create avoidable friction:

- repeated branch setup and PR creation;
- repeated manual Replit validation;
- repeated Linear updates for closely related work;
- slower context transfer between ChatGPT, Codex, GitHub, and Replit;
- more chances for branches to wait on tiny process fixes.

Release-sized builds keep related work together while still preserving GitHub validation, review, and post-merge Replit runtime checks.

## When To Use Release-Sized Builds

Use a release-sized build when:

- the Linear issue has clear scope and boundaries;
- the work touches multiple related files in one feature area;
- existing validation scripts cover the affected surfaces;
- the change does not require payment flow changes unless explicitly scoped;
- the change can be reviewed as one coherent release candidate;
- runtime validation can be done once after merge.

Examples:

- a complete admin workflow with model, route, template, validation, and docs;
- a subscriber workflow plus matching admin visibility;
- a release bundle of related documentation and process automation;
- a full governed feature slice that has explicit validation coverage.

## When Smaller PRs Are Still Justified

Use smaller PRs when:

- the work is high risk or security-sensitive;
- payment, subscription, Stripe, or Paystack behavior is involved;
- data exposure, document access, API safety, or entitlement gates could be affected;
- the requirement is ambiguous and needs review before continuing;
- database changes need isolated scrutiny;
- the PR would become too large to review safely;
- a production incident or urgent bug fix needs a minimal patch.

Release-sized does not mean careless. It means larger coherent batches with the same validation and governance gates.

## Faster Workflow

Use this default workflow:

1. **Linear release issue:** ChatGPT and the user define release-sized scope, acceptance criteria, governance boundaries, and validation expectations in Linear.
2. **Codex large build branch:** Codex creates the feature branch, reads the relevant docs/code, implements the full scoped release slice, and runs local validation.
3. **GitHub Actions validation:** GitHub validates the PR with `scripts/validate_all_phases.py`, compile checks, and whitespace diff checks.
4. **PR review:** The user reviews the PR, confirms boundaries, and requests changes if needed.
5. **Merge:** Merge only after review and validation are acceptable. Do not auto-merge.
6. **Replit one-command validation:** Pull latest `main` in Replit and run `python scripts/post_merge_validate.py`, then perform focused browser/runtime smoke checks.
7. **Linear Done:** Add the post-merge validation note and move Linear to Done only after Replit validation passes. Do not auto-close Linear.

Short form:

```text
Linear release issue -> Codex large build branch -> GitHub Actions validation -> PR review -> merge -> Replit one-command validation -> Linear Done
```

## Roles

### ChatGPT

- Helps shape release-sized Linear issues.
- Keeps scope, boundaries, and acceptance criteria explicit.
- Helps decide whether a release-sized build or smaller PR is safer.

### Codex

- Implements from Linear scope on a GitHub branch.
- Preserves existing app behavior unless explicitly scoped.
- Adds or updates validation and docs with the feature.
- Runs validation before completion.
- Opens a draft PR or pushes the branch if PR creation is blocked.

### GitHub

- Stores the source code and review history.
- Runs PR validation through GitHub Actions.
- Remains the source of truth for code changes.

### Linear

- Stores release scope and delivery state.
- Remains the source of truth for what should be built.
- Moves to Done only after post-merge Replit validation passes.

### Replit

- Hosts and validates runtime behavior after merge.
- Uses shell/browser checks for runtime confidence.
- Is not the routine build agent.

### Replit Agent

- Emergency/debug only because it costs money.
- Use only when normal GitHub/Codex/Replit shell inspection is insufficient.
- Do not use it as routine validation.

## Required Validation

Before completing a Codex build branch:

```bash
python scripts/validate_all_phases.py
python -m compileall app.py models.py routes scripts intelligence_insights.py
git diff --check
```

After merge in Replit:

```bash
python scripts/post_merge_validate.py
```

Then perform focused browser smoke checks for the changed area.

## Governance Rules

- Do not change payments unless explicitly scoped.
- Do not expose secrets, private paths, document files, raw extraction text, contact fields, restricted document fields, API secrets, or key hashes.
- Do not bypass consent, review, redaction, publish-readiness, entitlement, audit, or API safety gates.
- Do not auto-publish.
- Do not add deployment automation unless explicitly scoped.
- Do not auto-merge.
- Do not auto-close Linear.
- Do not weaken existing validators.

## Practical Release Checklist

- Linear issue has release-sized scope and clear boundaries.
- Branch name matches the Linear issue.
- Relevant phase docs and current code are read before edits.
- Validation scripts are updated only when needed and never weakened.
- PR template is completed.
- GitHub Actions passes.
- Replit post-merge validation passes.
- Linear receives a final validation note before Done.
