# GitHub Copilot Instructions For FieldSight Africa

Follow these repository rules when proposing or editing code.

- Linear is the source of truth for scope.
- GitHub is the source of truth for code.
- Replit is runtime validation only, not the routine build agent.
- Replit Agent is emergency/debug only because it costs money.
- Prefer release-sized PRs over micro-phases unless risk justifies smaller PRs.
- Do not change application product behavior for build-process issues.
- Do not change models, routes, templates, payment flows, access controls, exports, or Replit configuration unless the Linear issue explicitly requires it.
- Do not change Stripe or Paystack unless explicitly scoped.
- Do not expose secrets, private paths, document files, raw extraction text, contact fields, restricted document fields, API secrets, or key hashes.
- Do not bypass consent, review, redaction, publish-readiness, entitlement, audit, or API safety gates.
- Do not auto-publish.
- Do not add deployment automation, auto-merge, or Linear auto-close behavior.
- Keep validation intact and do not weaken existing validators.

Before completing a change, run or preserve the expected validation path:

```bash
python scripts/validate_all_phases.py
python -m compileall app.py models.py routes scripts intelligence_insights.py
git diff --check
```

After a merge, use Replit shell/browser for runtime validation and prefer:

```bash
python scripts/post_merge_validate.py
```
