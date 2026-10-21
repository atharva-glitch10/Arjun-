FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY core_api ./core_api
CMD ["uvicorn", "core_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
