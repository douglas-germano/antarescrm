FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && HF_HUB_DISABLE_XET=1 python -c 'from huggingface_hub import snapshot_download; snapshot_download("Systran/faster-whisper-base", revision="ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66", local_dir="/opt/atlas-whisper", allow_patterns=["config.json","model.bin","tokenizer.json","vocabulary.txt"])' \
    && useradd --uid 10001 --create-home antares \
    && mkdir -p /data/project-files \
    && chown -R antares:antares /data
COPY --chown=antares:antares backend/ /app/backend/
COPY --chown=antares:antares scripts/ /app/scripts/
USER antares
EXPOSE 5002
CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "--access-logformat", "%(h)s %(m)s %(U)s %(s)s", "run:app"]
