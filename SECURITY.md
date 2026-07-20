# Security

## Dependency baseline

Audited 2026-07-19 with `pip-audit`. Every `requirements.txt` here carries the
note *"check monthly for CVEs, pin exact versions always"*. The pinning had happened;
the checking had not, so findings had accumulated. Most were cleared on that date.

CI runs the audit **blocking**. A new vulnerability fails the build. The handful
below are accepted with a reason, because a `|| true` that makes a green tick
meaningless is worse than an exception someone can read.

## Fixed on 2026-07-19

| Package | Was | Now | Cleared |
|---|---|---|---|
| streamlit | 1.44.0 | 1.54.0 | PYSEC-2026-212, PYSEC-2026-2285. Ten minor versions behind; the app was started and its tests run after the bump |
| pillow | 11.3.0 | 12.3.0 | Six advisories, all transitive via streamlit and cleared by that upgrade |
| python-dotenv | 1.1.0 | 1.2.2 | PYSEC-2026-2270 |


## Accepted, with reasons

| Advisory | Package | Pinned | Needs | Why it stays |
|---|---|---|---|---|
| PYSEC-2026-2440 | dbt-common | 1.27.1 | 1.34.2 | **Blocked upstream.** dbt-core 1.9.4 constrains `protobuf<6.0`, which pins this. Clearing it means moving dbt-core, which is a real migration rather than a bump |
| PYSEC-2026-327 | deepdiff | 7.0.1 | 8.6.1 | Same constraint |
| PYSEC-2026-2445 | deepdiff | 7.0.1 | 8.6.2 | Same constraint |

These three are dbt's own dependencies, reached only by the build tooling and
never by anything serving a request. They are accepted rather than neglected:
each is blocked upstream by dbt-core 1.9.4 constraining protobuf below 6.0, so
clearing them means moving dbt-core.


## How to verify an upgrade

```bash
docker run --rm -v "$PWD/app:/w" -w /w python:3.12-slim \
  sh -c "pip install -q -r requirements.txt pytest && python -m pytest tests -q"
docker compose --profile seed run --rm seed
docker compose --profile seed run --rm dbt
docker compose up -d --build app     # then open http://localhost:8503/
```

Bump the pin, run that, and if it is green remove the matching `--ignore-vuln` from
`.github/workflows/ci.yml` and the row above.

## Reporting

A personal portfolio project with no users to notify. If you find something here
that matters, open an issue.
