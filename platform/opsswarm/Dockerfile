FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY platform/opsswarm/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY platform/opsswarm/opsswarm /app/opsswarm
COPY platform/opsswarm/config /app/config

RUN mkdir -p /app/runtime-data

EXPOSE 8088

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health', timeout=2)"

CMD ["uvicorn","opsswarm.api:app","--host","0.0.0.0","--port","8088"]
