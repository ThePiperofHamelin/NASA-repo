FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .
ENV CACHE_DIR=/cache
EXPOSE 8000
CMD ["gunicorn", "--workers", "1", "--threads", "16", "--timeout", "600", "--bind", "0.0.0.0:8000", "main:app"]
