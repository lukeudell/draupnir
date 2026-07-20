# Security

## Threat model

This project is published as source and also runs as a live, embedded demo on a
public site. Two things follow from that, and they shape everything below.

An untrusted visitor can interact with the dashboard. So the app takes no input
that reaches SQL, renders nothing from the database without escaping it, holds a
database role that can only SELECT, and carries a server-side statement timeout.

Anyone can read the source. So there is nothing secret in it: no credential has
a working default, and every secret arrives from the environment.

The demo is meant to sit behind the host site's reverse proxy. Both published
ports therefore bind loopback only. Exposing the app directly would make TLS,
rate limiting and access control at the proxy optional rather than mandatory,
which is the difference between a demo and an open port on a server you care
about.

## What the database role can actually do

The app connects as `portfolio_reader`, which holds `USAGE` and `SELECT` and
nothing else. Verified against a live database rather than assumed: `CREATE
TABLE`, `DROP TABLE`, `UPDATE`, `DELETE`, `CREATE ROLE`, `ALTER ROLE ...
SUPERUSER` and `COPY ... TO PROGRAM` are all refused. That last one is the
usual route from SQL execution to shell on Postgres, and it needs a privilege
this role does not have.

Migrations, loading and dbt run as the owner role, which is a separate
credential the app never receives.

## Secrets: the deploy contract

Secrets are delivered as environment variables and nothing else. This repo holds
no secret, no encrypted secrets file, and no key: encryption and decryption are
the operator's concern, on the operator's workstation. The app never learns that
SOPS exists.

```bash
sops exec-env <secrets-file> 'docker compose up -d'
```

There is deliberately no `sops`, no `age`, no key file and no decryption step in
this repo, in any image, in CI, or on the server.

**Secret. Two credentials, and only these:**

| Variable | What it is | Class |
|---|---|---|
| `DB_PASSWORD` | Postgres owner password. Runs migrations, the loader and dbt | service credential |
| `READER_DB_PASSWORD` | Password for the SELECT-only role the app connects as | service credential |

Both are service credentials: regenerable, no data loss if rotated, swap the
value and redeploy. **This project holds no data-encrypting key.** It encrypts
nothing at rest, so there is nothing here that is irreplaceable if lost, and
nothing that needs a vault entry alongside its secrets file.

Generate them URL-safe, because they end up in connection strings:
`openssl rand -hex 32`.

**Not secret. Configuration, safe in plain sight:**

`DB_USER`, `DB_NAME`, `READER_DB_USER`, `POSTGRES_EXPOSE_PORT`,
`APP_EXPOSE_PORT`, `APP_BASE_PATH`.

**Derived inside compose,** never set by the operator: the containers read
`PORTFOLIO_DB_*` and dbt reads `DBT_*`. Compose maps the two credentials above
onto them, which is why the app never sees the owner password: it is given
`READER_DB_PASSWORD` and nothing more.

**How the rules are kept:**

- Nothing starts unconfigured. Compose uses `${DB_PASSWORD:?...}`, and the app
  refuses to start on a missing credential with a configuration error that is
  explicitly distinct from the offline state, so a deploy that was never
  configured cannot masquerade as a database outage.
- No secret has a working default anywhere.
- No secret is logged. Failures surface as an exception type, never a value.
- No secret is baked into an image. Each build context has a `.dockerignore`
  excluding `.env*`, `dbt/profiles.yml` and `.streamlit/secrets.toml`. That last
  pair matters: both are gitignored *because* they hold plaintext credentials
  for local use, and `COPY . .` would otherwise put them in a layer. A later
  `RUN` that overwrites the file does not undo this, because the earlier layer
  keeps the original and `docker save` recovers it. Verified by building with a
  marker credential in place and searching every layer blob for it.
- CI holds nothing sensitive: its Postgres password is invented in-job and
  named `ci_only_not_a_secret`.

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

## Staying current

Pinned dependencies and a pinned base image mean this repo can drift from safe to
vulnerable with no commit to trigger a scan. Three things cover that:

- **CI runs on a weekly schedule** as well as on push, so `pip-audit`, `bandit`,
  `gitleaks` and the Trivy image scans run against a quiet repo.
- **Trivy scans every image in the deployed stack**, which means the app image
  and `postgres:16`, not just the one this repo builds. A pinned base image is a
  frozen set of system packages and the database half holds the data.
- **Dependabot** proposes weekly upgrades for all three pip manifests, all three
  Dockerfiles and the GitHub Actions, grouped per ecosystem.

Three repository settings do the rest, and they are settings rather than files,
so they need enabling once on GitHub: Dependabot alerts, Dependabot security
updates, and secret scanning with push protection. Private vulnerability
reporting is worth turning on at the same time.

## Reporting

A personal portfolio project with no users to notify. If you find something here
that matters, open an issue.
