# ============================================================
#  file:       data/Dockerfile
#  purpose:    runtime image for the generator and loader
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-04]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# SECURITY: non-root. /app is chowned so the generator can write generated/.
RUN useradd -m -u 1000 -s /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

COPY --chown=appuser:appuser . .
RUN chmod +x seed.sh

CMD ["./seed.sh"]
