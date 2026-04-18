# Code conventions (Glas Intelligence)

## File length (soft cap)

- **Target:** keep source files around **750 lines** or fewer (excluding generated assets).
- **Why:** easier review, navigation, and testing; line count is a proxy for single-responsibility.
- **Enforcement:** ESLint `max-lines` is set to **warn** in `frontend/eslint.config.js` (blank lines and block comments skipped in the count). Legacy large files are allowed to warn until refactored.
- **Exceptions:** If a file must stay large temporarily, document why in the PR and prefer extracting composables / child components / Python submodules in follow-ups.

## Refactor pattern

Extract behavior without changing it: move Vue logic to `composables/`, split SFCs into child components under a feature folder, split Python into packages under `services/` or `api/`.
