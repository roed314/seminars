# Contributing to seminars

This repo powers `researchseminars.org`. It is maintained by volunteers; small,
well-tested PRs get reviewed fastest.

## Branch flow

- `master` — development. **Target all PRs here.**
- `live` / `stable` — production releases, updated by maintainers via
  `master -> live -> stable` merges. Do not target them.

## Local setup

```bash
git clone git@github.com:roed314/seminars.git
cd seminars
git submodule init && git submodule update
pip install -r requirements.txt
python start-seminars.py --debug   # generates config.ini, serves locally
```

You need Postgres. See `GettingStarted.md` and `Schema.md`.

## Before opening a PR

1. **Link an issue.** Every PR body must contain `Closes #N` (or `Related to #N`
   for follow-ups). PRs with empty bodies will not be reviewed.
2. **Keep it small.** One issue per PR. Refactors and behavior changes go in
   separate PRs.
3. **Add or update regression tests** under `tests/` (stdlib `unittest` style,
   no live DB required — see `tests/test_api_search_input.py` for the
   isolated-harness pattern: extract pure functions via `ast`, stub the DB).
4. **Run checks locally:**
   ```bash
   python -m pytest tests/ -q
   python -m ruff check seminars tests --select F
   python -c "import yaml; yaml.safe_load(open('seminars/knowls.yaml'))"
   ```
   CI runs the same three commands on every push/PR.
5. **State verification limits** in the PR body: what you ran, what you did
   not (e.g. "no live-DB end-to-end test").

## Commit messages

- Imperative subject line, `Closes #N` trailer where applicable.
- Use your `users.noreply.github.com` address if you keep your email private
  (pushes exposing private emails are rejected, `GH007`).

## What gets merged fastest

- Fixes with a failing-then-passing isolated test.
- Docs that state provider behavior with sources (Google/Apple/Outlook poll
  windows, feed size caps), not folklore.
- Anything that reduces full-table scans (`all_seminars()`) or unbatched
  per-row commits.
