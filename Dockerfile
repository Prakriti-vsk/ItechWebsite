FROM python:3.13-slim

# Install system deps and Microsoft ODBC driver
RUN apt-get update && apt-get install -y curl gnupg2 apt-transport-https unixodbc-dev build-essential ca-certificates && rm -rf /var/lib/apt/lists/*

# Add Microsoft package repository and install ODBC driver (msodbcsql17)
RUN set -eux; \
  # fetch Microsoft signing key and add in a GPG-trusted way (apt-key is deprecated)
  curl -fsSL https://packages.microsoft.com/keys/microsoft.asc -o /tmp/microsoft.asc; \
  gpg --batch --dearmor /tmp/microsoft.asc; \
  install -o root -g root -m 644 /tmp/microsoft.asc.gpg /etc/apt/trusted.gpg.d/microsoft.gpg || true; \
  rm -f /tmp/microsoft.asc /tmp/microsoft.asc.gpg; \
  # add repository list
  curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list -o /etc/apt/sources.list.d/mssql-release.list; \
  apt-get update; \
  ACCEPT_EULA=Y apt-get install -y msodbcsql17; \
  rm -rf /var/lib/apt/lists/*;

WORKDIR /app
COPY . /app

RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Expose port used by gunicorn
EXPOSE 8000

CMD ["gunicorn", "app:app", "-b", "0.0.0.0:8000", "--workers", "2"]
