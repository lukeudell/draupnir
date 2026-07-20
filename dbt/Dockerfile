# ============================================================
#  file:       dbt/Dockerfile
#  purpose:    runtime image for dbt core against postgres
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-04]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# SECURITY: non-root, to limit container breakout blast radius.
# /app is chowned so dbt can write target/ and logs/ at runtime.
RUN useradd -m -u 1000 -s /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

COPY --chown=appuser:appuser . .

# env-var based profile: no secrets baked into the image
RUN cp profiles.docker.yml profiles.yml

# packages are installed at build time; the runtime network is internal-only
RUN dbt deps --profiles-dir .

CMD ["dbt", "build", "--profiles-dir", "."]
