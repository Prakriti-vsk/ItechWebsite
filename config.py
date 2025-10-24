import pyodbc

class Config:
    SECRET_KEY = 'your-strong-secret-key-here-12345'  # Change this in production
    
    SQL_CONNECTION_STRING = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=DESKTOP-HUD5G4G;"  # Your SQL Server instance name
        "DATABASE=ITechDB;"  # Your database name
        "Trusted_Connection=yes;"  # Windows Authentication
    )
    
    # Add the database name here to create it if it doesn't exist
    DATABASE_NAME = "ITechDB"
    
    # Admin password for staff registration protection
    # Change this to a secure password that only admin knows
    ADMIN_REGISTRATION_PASSWORD = "Itech@2025"

try:
    # First connect to master database
    conn = pyodbc.connect(Config.SQL_CONNECTION_STRING)
    cursor = conn.cursor()
    
    # Create database if it doesn't exist
    cursor.execute(f"""
    IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = '{Config.DATABASE_NAME}')
    BEGIN
        CREATE DATABASE {Config.DATABASE_NAME}
    END
    """)
    conn.commit()
    conn.close()
    
    # Now update connection string to use the created database
    Config.SQL_CONNECTION_STRING = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=.;"
        f"DATABASE={Config.DATABASE_NAME};"
        "Trusted_Connection=yes;"
    )
    
    # Test connection to the new database
    conn = pyodbc.connect(Config.SQL_CONNECTION_STRING)
    print("Connection successful!")
    conn.close()
except Exception as e:
    import os

    # Lightweight config that reads from environment variables.
    # This avoids committing secrets and prevents side-effects at import time
    # (import-time side-effects can break deployments where the DB or drivers
    # are not available during module import).

    class Config:
        # Secret key for Flask sessions. Set this in the Render dashboard as an env var.
        SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')

        # SQL connection string. Example for SQL Server (use SQL auth / full host on Render):
        # 'DRIVER={ODBC Driver 17 for SQL Server};SERVER=<host>,<port>;DATABASE=<db>;UID=<user>;PWD=<pass>'
        SQL_CONNECTION_STRING = os.environ.get('SQL_CONNECTION_STRING', '')

        # Database name (used by local scripts if needed)
        DATABASE_NAME = os.environ.get('DATABASE_NAME', 'ITechDB')

        # Admin password for staff registration protection (override in env)
        ADMIN_REGISTRATION_PASSWORD = os.environ.get('ADMIN_REGISTRATION_PASSWORD', 'change-me')


    def ensure_required_env_vars():
        """Optional helper: call this at startup to assert required vars are present in prod."""
        required = []
        # For production you may want to require SQL_CONNECTION_STRING and SECRET_KEY
        if os.environ.get('FLASK_ENV') == 'production':
            required = ['SECRET_KEY', 'SQL_CONNECTION_STRING']

        missing = [v for v in required if not os.environ.get(v)]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


    # Note: Do not perform database creation or pyodbc connections at import time here.
    # If you need to create the DB on first-run, call a startup function from your
    # application entrypoint after the environment is fully initialized.
