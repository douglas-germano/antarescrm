FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home antares \
    && mkdir -p /data/project-files \
    && chown -R antares:antares /data
COPY --chown=antares:antares backend/ /app/backend/
COPY --chown=antares:antares scripts/ /app/scripts/
USER antares
EXPOSE 5002
CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "run:app"]
