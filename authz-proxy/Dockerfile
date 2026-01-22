FROM python:3.11-slim

LABEL org.opencontainers.image.title="authz-proxy" \
      org.opencontainers.image.description="PEP/PDP Authorization Proxy for Workspace" \
      org.opencontainers.image.authors="INTO-CPS Association"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create non-root user
RUN useradd -m -u 1000 authz && \
    chown -R authz:authz /app

USER authz

EXPOSE 8081

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8081/health')"

CMD ["python", "-m", "app.main"]
