# Security Policy

## Supported Versions

Security fixes target the latest version of the Skill on the default branch.

## Reporting a Vulnerability

Please open a private security advisory on GitHub when possible. If that is not available, open an issue with minimal public detail and ask for a private follow-up channel.

Do not include real credentials, customer data, private exports, or sensitive local paths in public issues.

## Security Model

This Skill is a coordination protocol for logical agents inside one AI tool. It does not grant permissions by itself.

Important boundaries:

- Dashboard is read-only.
- `auto-approve` is not write authorization.
- Worker completion is not final completion.
- Verifier must not auto-fix deliverables.
- Priority cannot bypass authorization, locks, dependencies, or verification.
- Cancellation is not rollback.

## Before Publishing Examples

Sanitize:

- Local absolute paths.
- Usernames and machine names.
- Tokens, API keys, passwords, cookies, and credentials.
- Real customer data or production exports.