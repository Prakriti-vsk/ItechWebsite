FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Install Python dependencies
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Expose port for gunicorn
EXPOSE 8000

# Start Gunicorn (adjust your app entrypoint as needed)
CMD ["gunicorn", "itech_computer_institute.wsgi:application", "-b", "0.0.0.0:8000", "--workers", "2"]
