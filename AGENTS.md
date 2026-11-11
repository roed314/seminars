# AGENTS.md (repo scope: seminars)

Repo-specific instructions. The global `~/.config/opencode/AGENTS.md`
(machine setup, `gh`-for-GitHub rule, worktrees, commit identity) still
applies.

## Repo facts

- Flask + Postgres (psycodict, pinned git SHA in `requirements.txt`).
- No `CREATE TABLE` anywhere: schema lives in the DB (psycodict meta
  tables). Local dev normally uses MIT's shared dev DB; for isolated
  work use the embedded-Postgres staging flow (see README + #993).
  Tables the code needs beyond `Schema.md`: `new_topics`, `author_ids`,
  `talk_registrations`, `preendorsed_users`, `subjects`, plus `by_api`
  on seminars/talks.
- Versioned append-only writes (`insert_many`, `DISTINCT ON` reads).
  Reschedules leave negative-`seminar_ctr` tombstones.

## Working rules

- `gh` for all GitHub reads/writes (issues, PRs, comments, checks).
  Never `webfetch`/`curl` `api.github.com`.
- Target branches at `roed314:master`. Never `live`/`stable`.
- One issue per PR; PR body must contain `Closes #N`. Update the PR
  (don't open a second one) when review asks for changes.
- Tests live in `tests/`, stdlib `unittest`, no live DB: extract pure
  functions via `ast`, stub DB access (see `test_api_search_input.py`,
  `test_ics_tombstone.py`). New behavior needs a failing-then-passing test.
- Before pushing: `pytest tests/ -q`, `ruff check seminars tests --select F`,
  YAML parse check. CI runs the same plus a pip-install check.
- Staging server: single instance only — duplicate `start-seminars.py`
  processes will race on the port with stale table metadata. Kill by
  CommandLine match before restarting; restart after any schema change.
- Don't commit `config.ini`, `secrets.ini`, `secret_key`, `*.log`,
  `staging-*` artifacts (all gitignored or out-of-tree).
