# Template: changelog-release

## Purpose
Auto-generate a changelog from git history since last tag, create a release
tag, push it, open a GitHub Release draft, and notify stakeholders (Slack/Linear).

## Done when
`gh release view [new_tag] --json tagName -q .tagName` outputs "[new_tag]"
AND `gh release view [new_tag] --json isDraft -q .isDraft` outputs "true"
AND Slack notification sent to [channel] (verified via Slack API response)

## Standard constraints
- Only create a DRAFT release — do not publish
- Changelog must follow Keep a Changelog format (Added/Changed/Fixed/Removed)
- Do not force-push or rewrite git history
- Tag must follow semver: vMAJOR.MINOR.PATCH

## Typical MAX_ATTEMPTS: 4
## Escalate if: breaking changes detected in commits (manual semver decision needed)
