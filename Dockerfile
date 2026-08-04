# Use official Python 3.11 image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Install system dependencies (including PostgreSQL & WeasyPrint C-libraries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    libgobject-2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    gobject-introspection \
    libharfbuzz0b \
    pango1.0-tools \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN python manage.py collectstatic --no-input || true

EXPOSE 8080

CMD exec gunicorn --bind 0.0.0.0:${PORT} --workers 3 --threads 8 --timeout 120 ssepl_backend.wsgi:application
