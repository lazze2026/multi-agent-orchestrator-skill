# Pull Request

## Summary

## Changed Areas

- [ ] SKILL.md
- [ ] Protocol/reference docs
- [ ] Templates
- [ ] Dashboard
- [ ] Scripts
- [ ] Simulations/tests

## Verification

- [ ] `python scripts/validate_state.py tests/simulations/dashboard-static-html/state.json`
- [ ] `python -m py_compile scripts/generate_dashboard_state.py scripts/validate_state.py`
- [ ] Skill validator passes

## Safety Checklist

- [ ] No secrets, credentials, local absolute paths, or private data are included.
- [ ] Dashboard remains read-only.
- [ ] Authorization and verification rules are not weakened.
- [ ] Checkpoint/resume behavior remains explicit and idempotent.