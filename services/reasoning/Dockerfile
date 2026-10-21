FROM python:3.12-slim
WORKDIR /app
COPY services/reasoning/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/reasoning/reasoning_svc ./reasoning_svc
COPY shared /shared
ENV SHARED_SCHEMA_DIR=/shared/schemas
CMD ["uvicorn", "reasoning_svc.main:app", "--host", "0.0.0.0", "--port", "8001"]
