# Use an official Python image
FROM python:3.10-slim

# Set the working directory
WORKDIR /code

# Install system dependencies for document processing
RUN apt-get update && apt-get install -y \
    build-essential \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the rest of your app code
COPY . .

# Set the environment variable for the port (Hugging Face uses 7860)
ENV PORT=7860

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]