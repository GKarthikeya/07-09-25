# Use a slim Python base
FROM python:3.11-slim

# Install Chromium and Chromedriver + minimal deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver fonts-liberation libnss3 libgconf-2-4 libxi6 \
    && rm -rf /var/lib/apt/lists/*

# Create app dir
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . /app

# Env for Flask/Render
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

# Gunicorn start (Render sets $PORT)
CMD ["bash", "-lc", "exec gunicorn -b 0.0.0.0:${PORT} app:app"]
