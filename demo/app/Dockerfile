FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ENV SERVICE_ROLE=backend
ENV SERVICE_PORT=8080
ENV FAULT_ENABLED=false
ENV FAULT_TYPE=none
ENV SYNTHETIC_TRAFFIC=false

EXPOSE 8080

CMD ["python", "server.py"]
