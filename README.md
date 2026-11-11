# researchseminars.org

Codebase behind [researchseminars.org](https://researchseminars.org) — a
listing of online (and offline) mathematics seminars and conferences.
Flask + Postgres (via [psycodict](https://github.com/roed314/psycodict)).

Upstream: [`roed314/seminars`](https://github.com/roed314/seminars)
(`master` → `live` → `stable` releases).
This fork (`winstoncheong/seminars:master`) integrates pending fixes with
green CI; see [Outstanding PRs](#outstanding-prs-to-upstream).

## Quickstart (local dev)

```bash
git clone git@github.com:roed314/seminars.git
cd seminars
git submodule init && git submodule update
pip install -r requirements.txt   # pinned; validated on staging (see #993)
python start-seminars.py --debug  # writes config.ini, serves on :37778
```

You need Postgres. The dev database password comes from
`researchseminars@mit.edu` (see `GettingStarted.md`), or bring up the
local staging DB below. Schema reference: `Schema.md` (note: it omits
`new_topics`, `author_ids`, `talk_registrations`, `preendorsed_users`,
`subjects`, and the `by_api` column — staging reverse-engineered them;
see `staging-setup.py` notes in #993).

## Staging (local Postgres, no Docker)

```bash
python -m venv staging-env && staging-env/Scripts/python -m pip install pgserver
# start embedded postgres, create role/db, create schema + seed, boot app
```

Details in [#993](https://github.com/roed314/seminars/pull/993).
Smoke suite: `GET /health`, `GET /`, `POST /api/0/search/*`,
`GET /api/0/search/series?name={"$like":"..."}`, seminar ICS,
`GET /user/info`.

## Layout

| Path | What |
|------|------|
| `seminars/homepage/` | Browse/search/ICS routes + templates |
| `seminars/create/` | Organizer edit flows (series/talk/schedule) |
| `seminars/users/` | Auth, favorites, personal ICS feed |
| `seminars/api/` | Machine API (`/api/0/...`) |
| `seminars/templates/`, `seminars/static/` | Jinja + JS |
| `seminars/knowls.yaml` | Help texts (loaded at import) |
| `tests/` | Isolated `unittest` harness — no live DB (see `CONTRIBUTING.md`) |
| `configfiles/` | Apache/gunicorn/supervisord deploy |
| `docs/` | Architecture notes (`docs/architecture.html`) |

## Testing & CI

```bash
python -m pytest tests/ -q
python -m pyflakes seminars tests
python -c "import yaml; yaml.safe_load(open('seminars/knowls.yaml'))"
```

GitHub Actions runs the same on push/PR (see `.github/workflows/ci.yml`).
Every PR must link an issue (`Closes #N`) and state verification limits.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Target PRs at `master`.
For AI-agent conventions in this repo, see [`AGENTS.md`](AGENTS.md).

## Outstanding PRs to upstream

| PR | What |
|----|------|
| #987 | Weekday-array fix, closes #984 |
| #989 | ICS tombstone filter, closes #931 |
| #991 | Sync-limit docs, closes #990 |
| #992 | CI, templates, CONTRIBUTING |
| #993 | Pinned deps (staging-validated) |
| #994 | API save hardening: reject deleted keys, closes #670 |
| #995 | Tz-aware now for edited_at/ongoing display, closes #742 |
| #996 | Livestream filter requires online, closes #921 |
| #988 | Meta: fixed-but-never-closed issues |

## License

GNU AGPLv3 — see `LICENSE`.
