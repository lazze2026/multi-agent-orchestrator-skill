# Contributing

Contributions are welcome. This repository is a Skill and protocol package, so changes should preserve clarity, safety boundaries, and testability.

## Good Contributions

- Improve the protocol wording or examples.
- Add realistic simulations under `tests/simulations/`.
- Improve dashboard state generation or validation.
- Add install notes for more AI tools.
- Fix unclear safety rules or edge cases.

## Before Opening a Pull Request

1. Run the Skill validator if available:

```bash
python <path-to-skill-creator>/scripts/quick_validate.py .
```

2. Validate dashboard demo data:

```bash
python scripts/validate_state.py tests/simulations/dashboard-static-html/state.json
```

3. Run Python syntax checks:

```bash
python -m py_compile scripts/generate_dashboard_state.py scripts/validate_state.py
```

4. Do not commit secrets, local absolute paths, private customer data, or real API exports.

## Pull Request Checklist

- [ ] The change keeps Dashboard read-only.
- [ ] The change does not weaken authorization, locks, verification, or checkpoint rules.
- [ ] Tests or simulation artifacts were updated when behavior changed.
- [ ] Documentation was updated for user-visible changes.
- [ ] No generated cache files are included.