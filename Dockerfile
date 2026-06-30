# Base Python image
FROM python:3.11-slim as base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies & Google Chrome + ChromeDriver (matched versions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg2 \
    curl \
    unzip \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libcups2 \
    libxkbcommon0 \
    fonts-liberation \
    xdg-utils \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver that matches the installed Chrome version
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+\.\d+') \
    && CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$(echo $CHROME_VERSION | cut -d. -f1)" 2>/dev/null || true) \
    && if [ -z "$CHROMEDRIVER_VERSION" ]; then \
         # Fallback: use Chrome for Testing JSON API (Chrome 115+) \
         CHROME_MAJOR=$(echo $CHROME_VERSION | cut -d. -f1) \
         && CHROMEDRIVER_URL=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json" \
            | python3 -c "import json,sys; data=json.load(sys.stdin); versions=[v for v in data['versions'] if v['version'].startswith('${CHROME_MAJOR}.')]; url=versions[-1]['downloads']['chromedriver'][-1]['url'] if versions else ''; print(url)" 2>/dev/null) \
         && if [ -n "$CHROMEDRIVER_URL" ]; then \
              wget -q "$CHROMEDRIVER_URL" -O /tmp/chromedriver.zip \
              && unzip /tmp/chromedriver.zip -d /tmp/chromedriver_dir \
              && find /tmp/chromedriver_dir -name "chromedriver" -exec mv {} /usr/local/bin/chromedriver \; \
              && rm -rf /tmp/chromedriver.zip /tmp/chromedriver_dir; \
            fi; \
       else \
         wget -q "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" -O /tmp/chromedriver.zip \
         && unzip /tmp/chromedriver.zip -d /tmp \
         && mv /tmp/chromedriver /usr/local/bin/chromedriver \
         && rm /tmp/chromedriver.zip; \
       fi \
    && chmod +x /usr/local/bin/chromedriver \
    && chromedriver --version || echo "ChromeDriver install note: manual verification needed"

# Tell the app where ChromeDriver lives
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV CHROME_BIN=/usr/bin/google-chrome

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# Copy application source
COPY . .

# Create volume mounts for database and ensure correct permissions
RUN mkdir -p /app/instance && chown -R 1000:1000 /app/instance

# Expose port
EXPOSE 5000

# Entrypoint: initialise DB then start gunicorn with gevent (non-blocking I/O)
# --worker-class gevent  : greenlet concurrency — won't block on Ollama/Selenium I/O
# --timeout 300          : allow up to 5 min for slow AI responses
# --workers 2            : 2 processes × 4 greenlets = 8 concurrent requests
CMD ["sh", "-c", "flask db upgrade 2>/dev/null || python -c 'from run import app; from app import db; \
app.app_context().__enter__(); db.create_all()' 2>/dev/null; \
exec gunicorn --bind 0.0.0.0:5000 --workers 2 --worker-class gevent --worker-connections 4 --timeout 300 run:app"]
