FROM python:3.12-slim
WORKDIR /app
COPY incidentlab/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY incidentlab ./incidentlab
COPY experiments ./experiments
CMD ["uvicorn","incidentlab.api:app","--host","0.0.0.0","--port","8080"]
