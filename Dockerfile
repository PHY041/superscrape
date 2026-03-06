FROM python:3.12-slim

# System deps for Camoufox (headless Firefox) + WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    xauth \
    curl \
    fonts-noto-cjk \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libatspi2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY superscrape/ superscrape/
COPY api/ api/

# Install Python deps (non-editable for Docker)
RUN pip install --no-cache-dir .

# Download Camoufox browser binary (FF135 from daijro/camoufox releases)
# Also install Playwright system deps for the bundled Firefox
RUN python -m camoufox fetch && \
    python -c "import camoufox, glob, os; d=os.path.dirname(camoufox.__file__); print('Binary:', glob.glob(f'{d}/**/firefox*', recursive=True)[:3])"

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# xvfb-run provides virtual display for headless Camoufox
CMD xvfb-run --auto-servernum --server-args="-screen 0 1280x720x24" \
    uvicorn api.main:app --host 0.0.0.0 --port 8001
