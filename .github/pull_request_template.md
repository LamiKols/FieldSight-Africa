## Linear

- Linear issue ID:
- Linear issue URL:
- Branch name:

## Summary

- 

## Validation

- [ ] `python scripts/validate_all_phases.py`
- [ ] `python -m compileall app.py models.py routes scripts intelligence_insights.py`
- [ ] `git diff --check`
- [ ] GitHub Actions PR validation passed

Notes:

## Security And Governance Boundaries

- [ ] No application behaviour was changed outside the Linear scope.
- [ ] Consent, review, redaction, publish-readiness, entitlement, and audit gates remain authoritative.
- [ ] No deployment automation, auto-merge, or Linear auto-close was added.
- [ ] No paid external service or Replit Agent dependency was introduced.

## Data Exposure Confirmation

- [ ] No secrets are exposed.
- [ ] No private storage paths, filenames, file hashes, raw extraction text, contact fields, restricted document fields, API secrets, or key hashes are exposed.
- [ ] No new subscriber, API, buyer, public link, file, or download access is created unless explicitly in scope and gated.

## Payment Flow Confirmation

- [ ] Stripe flows are unchanged.
- [ ] Paystack flows are unchanged.
- [ ] No payment bypass or automatic entitlement grant was introduced.

## Manual Replit Post-Merge Checklist

- [ ] Pull latest `main` in Replit after merge.
- [ ] Restart the Replit app if Python modules, routes, templates, models, or configuration changed.
- [ ] Run the relevant smoke checks in Replit shell/browser.
- [ ] Confirm existing public, auth, subscriber, admin, payment, export, partner, document, automation, and API flows still load as applicable.
- [ ] Close the Linear issue only after post-merge Replit validation passes.
