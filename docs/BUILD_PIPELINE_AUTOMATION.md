# Build Pipeline Automation

Linear source of truth: FSA-30

Branch: `feature/build-pipeline-automation-pr-validation`

## Purpose

FieldSight Africa now has a low-cost PR validation layer so future build phases can be checked through GitHub before merge. This is build-process automation only. It does not deploy, auto-merge, close Linear issues, call Replit, or change application behavior.

FSA-31 extends this pipeline with a release-sized build workflow. Future work should normally be grouped into larger coherent release issues rather than many micro-phases, unless risk, ambiguity, payment impact, data exposure, or review size justifies a smaller PR.

See also: `docs/RELEASE_BUILD_WORKFLOW.md`

## Source Of Truth

- **Linear remains the source of truth for scope.** Every build phase should start from the Linear issue requirements and boundaries.
- **GitHub remains the source of truth for code.** Codex implements changes on a feature branch and opens a PR into `main`.
- **GitHub Actions validates PRs.** Pull requests targeting `main` run the phase validation suite, compile checks, and whitespace diff checks.
- **Replit is the runtime validation environment.** After merge, use the Replit shell/browser to pull, restart, and smoke test the live app.
- **Replit Agent is emergency/debug only.** It should not be used as routine validation because it costs money and can drift from the GitHub branch/PR workflow.

## Workflow

Default to the release-sized workflow:

```text
Linear release issue -> Codex large build branch -> GitHub Actions validation -> PR review -> merge -> Replit one-command validation -> Linear Done
```

1. Read the Linear issue and linked phase documentation.
2. Confirm whether the work should be a release-sized PR or a smaller high-risk PR.
3. Create the requested feature branch from current `main`.
4. Implement only the issue scope.
5. Run local validation before pushing:

   ```bash
   python scripts/validate_all_phases.py
   python -m compileall app.py models.py routes scripts intelligence_insights.py
   git diff --check
   ```

6. Push the branch and open a draft PR into `main`.
7. Confirm GitHub Actions PR validation passes.
8. Review the PR template checklist before merge.
9. Merge only after review and validation are acceptable.
10. Pull latest `main` in Replit and run:

   ```bash
   python scripts/post_merge_validate.py
   ```

11. Run focused Replit browser/runtime smoke checks for the changed area.
12. Move the Linear issue to Done only after post-merge Replit validation passes.

## Local Validation Before Completion

For every Codex build branch:

```bash
python scripts/validate_all_phases.py
python -m compileall app.py models.py routes scripts intelligence_insights.py
git diff --check
```

The same commands remain the core GitHub Actions checks.

## Post-Merge Validation

Added by FSA-31:

`scripts/post_merge_validate.py`

Run this in the Replit shell after pulling merged `main`:

```bash
python scripts/post_merge_validate.py
```

The script fails fast and runs:

- `python scripts/validate_all_phases.py`;
- `python -m compileall app.py models.py routes scripts intelligence_insights.py`;
- `git diff --check`.

This is still runtime validation only. It does not deploy, auto-merge, auto-close Linear, call Replit Agent, or change application behavior.

## Earlier Micro-Phase Workflow

The original micro-phase workflow remains valid for high-risk work, but should not be the default:

1. Read the Linear issue and linked phase documentation.
2. Create the requested feature branch from current `main`.
3. Implement only the issue scope.
4. Run local validation before pushing:

   ```bash
   python scripts/validate_all_phases.py
   python -m compileall app.py models.py routes scripts intelligence_insights.py
   git diff --check
   ```

5. Push the branch and open a draft PR into `main`.
6. Confirm GitHub Actions PR validation passes.
7. Review the PR template checklist before merge.
8. Merge only after review and validation are acceptable.
9. Pull/restart/test in Replit after merge.
10. Move the Linear issue to Done only after post-merge Replit validation passes.

## Central Validation Runner

Added:

`scripts/validate_all_phases.py`

The runner executes the existing phase validation scripts in order:

- `scripts/validate_phase_1_data_foundation.py`
- `scripts/validate_phase_2_partner_portal.py`
- `scripts/validate_phase_2_1_reference_quality.py`
- `scripts/validate_phase_3_document_vault.py`
- `scripts/validate_phase_3_0_actor_consent.py`
- `scripts/validate_phase_3_1_document_preview_extraction.py`
- `scripts/validate_phase_3_2_admin_document_review.py`
- `scripts/validate_phase_3_3_redaction_publish_controls.py`
- `scripts/validate_phase_3_4_entitlement_controlled_access.py`
- `scripts/validate_phase_4_0_commercial_packaging.py`
- `scripts/validate_phase_4_1_api_productisation.py`
- `scripts/validate_phase_4_2_commercial_operations.py`
- `scripts/validate_phase_4_3_buyer_due_diligence.py`
- `scripts/validate_phase_4_4_commercial_reporting.py`
- `scripts/validate_phase_5_0_intelligence_automation.py`
- `scripts/validate_phase_5_1_automation_run_processing.py`
- `scripts/validate_phase_5_2_scheduled_processing_alerts.py`
- `scripts/validate_phase_5_3_intelligence_insight_review.py`

The runner fails fast when any script exits non-zero. It streams script output directly, so existing known non-fatal SQLite migration warnings are preserved.

## GitHub Actions PR Validation

Added:

`.github/workflows/pr-validation.yml`

The workflow runs on pull requests targeting `main` and performs:

- repository checkout;
- Python 3.11 setup;
- dependency installation from the existing `pyproject.toml`;
- `python scripts/validate_all_phases.py`;
- `python -m compileall app.py models.py routes scripts intelligence_insights.py`;
- `git diff --check`.

The workflow does not:

- deploy;
- auto-merge;
- call Replit;
- call Replit Agent;
- close Linear issues;
- call paid external services;
- expose secrets.

## Pull Request Template

Added:

`.github/pull_request_template.md`

The template requires:

- Linear issue ID and URL;
- branch name;
- summary;
- validation checklist;
- security and governance boundary confirmation;
- data exposure confirmation;
- Stripe and Paystack flow confirmation;
- manual Replit post-merge checklist.

## Post-Merge Replit Checklist

After a PR merges into `main`:

1. Open the Replit project shell.
2. Pull latest `main`.
3. Restart the Replit app if Python modules, routes, templates, models, scripts, workflow-adjacent config, or dependencies changed.
4. Run focused runtime smoke checks for the changed area.
5. Confirm baseline app surfaces still load, including public pages, auth, subscriber pages, admin pages, exports, partner portal, document workflows, automation dashboards, API-safe metadata, and payment display flows as applicable.
6. Confirm no unexpected data exposure, payment bypass, publish bypass, entitlement bypass, or file access was introduced.
7. Add the post-merge validation note to Linear.
8. Move the Linear issue to Done only after Replit validation passes.

## Boundaries For Future Phases

Build automation should remain cheap and controlled:

- no deployment automation unless a future Linear issue explicitly scopes it;
- no auto-merge;
- no Linear auto-close;
- no Replit Agent routine validation;
- no secrets in workflow logs;
- no payment flow changes for validation convenience;
- no data model changes for build metadata unless explicitly approved;
- no external paid service calls.

If GitHub Actions fails because of an app validation issue, fix the branch and rerun the PR workflow. If GitHub Actions passes but Replit runtime fails after merge, use the Replit shell/browser for inspection and only use Replit Agent for emergency debugging.
