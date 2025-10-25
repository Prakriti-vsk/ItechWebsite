FROM python:3.13-slim

# Install system deps and Microsoft ODBC driver
RUN apt-get update && apt-get install -y curl gnupg2 apt-transport-https unixodbc-dev build-essential ca-certificates && rm -rf /var/lib/apt/lists/*

# Install prerequisites and Microsoft ODBC driver (msodbcsql)
RUN set -eux; \
  apt-get update && \
  apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev unixodbc || ( \
  echo "msodbcsql18 failed, trying msodbcsql17" && \
  ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 unixodbc-dev unixodbc \
  ); \
  rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Expose port used by gunicorn
EXPOSE 8000

CMD ["gunicorn", "app:app", "-b", "0.0.0.0:8000", "--workers", "2"]
