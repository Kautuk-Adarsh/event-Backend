FROM python:3.10-slim

WORKDIR /code

# 1. Install System Dependencies
# libmagic-dev: Required for file type detection
# libcairo2-dev/libpango1.0-dev: Required for the PDF engine to render fonts
# build-essential/pkg-config: Required to compile Python C-extensions
RUN apt-get update && apt-get install -y \
    build-essential \
    libmagic-dev \
    libjq-dev \
    python3-dev \
    pkg-config \
    libcairo2-dev \
    libpango1.0-dev \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Python Packages
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 3. Copy Application Code
COPY . .

# 4. Networking Settings
# Hugging Face Spaces listens on port 7860
ENV PORT=7860
EXPOSE 7860

# 5. Execution Command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
