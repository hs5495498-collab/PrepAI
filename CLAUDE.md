# CLAUDE.md (repository root)

Permanent instructions for Claude Code when working in this repository.
These apply across the whole repo; `prepai/CLAUDE.md` additionally covers
frontend-specific architecture details.

## Repository layout

- `prepai/` — the Stitch-generated HTML/CSS/JS frontend (see `prepai/CLAUDE.md`).
- `backend/` — the FastAPI backend (see `backend/README.md`).
- GitHub remote: `origin` → `https://github.com/hs5495498-collab/PrepAI`, branch `main`.

## Git workflow — follow every phase, no exceptions

1. Work from the repository root for any Git operation (status, diff, add, commit, push).
2. Preserve the existing frontend and backend architecture. Don't redesign, replace, or migrate either one as a side effect of unrelated work.
3. After each approved development phase:
   - Run `git status` and review the actual diff before touching anything.
   - Run the relevant tests (e.g. `backend/tests` via pytest) and report real pass/fail results — never claim a test passed without running it.
   - Only commit the files that belong to that phase's reviewed, working changes. Don't commit incomplete or unrelated work just because a phase ended.
   - Commit with a clear, descriptive message only after the diff and tests have been reviewed.
   - Push to `origin main` only after verifying the remote state is safe (fetch/inspect first; never push if the remote has diverged without reconciling it explicitly, and never force-push).
4. Never force-push, never run `git reset --hard`, `git clean -fd`, or discard uncommitted user work to make Git operations easier.
5. Never commit or push: `.env` files, secrets/API keys/tokens, virtual environments (`.venv`/`venv`), `__pycache__`, `.pytest_cache`, build artifacts, or other generated files. Keep `.env.example` tracked as a placeholder only.
6. If tests fail, a merge conflict exists, authentication is missing, or the remote has unexpected commits: stop and report the problem. Do not bypass, force through, or guess at a resolution.
7. Keep `README.md`/`backend/README.md` and other relevant docs updated whenever functionality they describe changes.
8. After each completed phase, report: the commit hash, branch, push status, exact files changed, and test results (actually run, not assumed).
