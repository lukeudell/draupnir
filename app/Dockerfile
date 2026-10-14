# ============================================================
#  file:       app/Dockerfile
#  purpose:    runtime image for the streamlit campaign pacing monitor
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-01]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# SECURITY: Run as non-root to limit container breakout blast radius
RUN useradd -m -u 1000 -s /bin/bash appuser
USER appuser

COPY . .

EXPOSE 8503

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
  CMD python -c "import os,urllib.request; b=os.getenv('STREAMLIT_SERVER_BASE_URL_PATH','').strip('/'); p='/'+b if b else ''; urllib.request.urlopen('http://localhost:8503'+p+'/_stcore/health')" || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8503", "--server.address=0.0.0.0"]
