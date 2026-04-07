





## 4. No CI/CD Pipeline

**Severity:** High
**Area:** Repository 

No GitHub Actions or equivalent CI configuration. No automated linting, type checking, or testing on push/PR.

**Recommendation:** Add a GitHub Actions workflow that runs:
- `tsc --noEmit` for the frontend
- `mypy` or `pyright` for Python packages
- Test suites for all packages
- Linting (`ruff` for Python, `eslint` for TypeScript)
