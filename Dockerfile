# Use Python 3.13 slim image
FROM python:3.13-slim

# Install system dependencies + Microsoft SQL ODBC driver
RUN apt-get update && apt-get install -y curl apt-transport-https gnupg2 ca-certificates unixodbc-dev build-essential && \
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc && \
    rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app
COPY . /app

# Install Python dependencies
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Expose port for gunicorn
EXPOSE 8000

# Start Gunicorn (for Django app)
CMD ["gunicorn", "itech_computer_institute.wsgi:application", "-b", "0.0.0.0:8000", "--workers", "2"]
