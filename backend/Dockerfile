FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend:/app \
    PORT=8080

WORKDIR /app

RUN addgroup --system qsim && adduser --system --ingroup qsim qsim

COPY requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY . /app/backend

USER qsim

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn backend.api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --workers 2 --timeout-keep-alive 65"]
