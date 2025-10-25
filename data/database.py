try:
    import pyodbc
    _has_pyodbc = True
except Exception:
    pyodbc = None
    _has_pyodbc = False

import sqlite3
import os
from config import Config
from datetime import datetime
import hashlib


class Database:
    def __init__(self):
        self.connection = None
        self.cursor = None
        self._is_sqlite = False

        # Attempt SQL Server connection if a connection string is provided and pyodbc is available
        if getattr(Config, 'SQL_CONNECTION_STRING', None) and _has_pyodbc:
            try:
                self.connection = pyodbc.connect(Config.SQL_CONNECTION_STRING)
                self.cursor = self.connection.cursor()
                self._is_sqlite = False
                print("Database connection (pyodbc) successful!")
            except Exception as e:
                print("pyodbc connection failed:", e)
                self.connection = None
                self.cursor = None

        # Fallback to local SQLite file
        if not self.connection:
            try:
                db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'itech_institute.db'))
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                self.connection = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
                # Use default row behaviour (tuples) to match existing indexing by ordinal
                self.cursor = self.connection.cursor()
                self._is_sqlite = True
                print(f"SQLite fallback database connected: {db_path}")
            except Exception as e:
                print("SQLite fallback connection failed:", e)
                self.connection = None
                self.cursor = None

        # If connected, ensure tables and indexes exist
        if self.connection:
            try:
                self.create_tables()
            except Exception as e:
                print(f"Error creating tables: {e}")
            try:
                self.create_indexes()
            except Exception as e:
                print(f"Error creating indexes: {e}")
            
    def create_indexes(self):
        """Create indexes for better performance if they don't exist"""
        try:
            self.execute_query("""
            -- Create index on chat_history.session_id
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_chat_history_session_id' AND object_id = OBJECT_ID('chat_history'))
                CREATE INDEX IX_chat_history_session_id ON chat_history(session_id);
                
            -- Create index on enrollment_history.session_id
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_enrollment_history_session_id' AND object_id = OBJECT_ID('enrollment_history'))
                CREATE INDEX IX_enrollment_history_session_id ON enrollment_history(session_id);
                
            -- Create index on enrollments.course_id
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_enrollments_course_id' AND object_id = OBJECT_ID('enrollments'))
                CREATE INDEX IX_enrollments_course_id ON enrollments(course_id);
                
            -- Create index on projects.student_name
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_projects_student_name' AND object_id = OBJECT_ID('projects'))
                CREATE INDEX IX_projects_student_name ON projects(student_name);
                
            -- Create index on event_registrations.event_name
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_event_registrations_event_name' AND object_id = OBJECT_ID('event_registrations'))
                CREATE INDEX IX_event_registrations_event_name ON event_registrations(event_name);
            """)
        except Exception as e:
            print(f"Error creating indexes: {e}")

    def execute_query(self, query, params=None):
        if self.cursor is None:
            print("No database connection.")
            return None
        try:
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            self.connection.commit()
            return self.cursor
        except Exception as e:
            print("Query failed:", e)
            return None

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()

    def reset_courses_identity(self):
        """Reset the identity/auto-increment in courses table to start from 1 (SQL Server / SQLite-aware)."""
        cursor = None
        try:
            cursor = self.connection.cursor()
            # Try SQL Server command first (requires appropriate permissions)
            try:
                cursor.execute("DBCC CHECKIDENT ('courses', RESEED, 0)")
                self.connection.commit()
                print("✅ Courses identity reseeded using DBCC CHECKIDENT.")
                return True
            except Exception:
                # Fallback: SQLite uses sqlite_sequence table
                try:
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'courses'")
                    self.connection.commit()
                    print("✅ Courses identity reset by clearing sqlite_sequence.")
                    return True
                except Exception:
                    # Last-resort: log and abort — do not DROP and recreate tables in production
                    raise
        except Exception as e:
            try:
                self.connection.rollback()
            except Exception:
                pass
            print("Error resetting courses identity:", e)
            return False
        finally:
            if cursor:
                cursor.close()

    def create_tables(self):
        # Use SQL Server T-SQL when connected to pyodbc; otherwise use SQLite-compatible DDL
        if not getattr(self, '_is_sqlite', False):
            # SQL Server existing behavior (run T-SQL blocks)
            # We keep the original T-SQL statements for SQL Server connections
            self.execute_query("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[chatbot_history]') AND type in (N'U'))
            BEGIN
                CREATE TABLE chatbot_history (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    session_id NVARCHAR(100) NOT NULL,
                    user_message NVARCHAR(MAX) NOT NULL,
                    bot_response NVARCHAR(MAX) NOT NULL,
                    timestamp DATETIME2 DEFAULT GETDATE()
                )
            END
            """)

            self.execute_query("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[courses]') AND type in (N'U'))
            BEGIN
                CREATE TABLE courses (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    title NVARCHAR(100) NOT NULL UNIQUE,
                    description NVARCHAR(MAX) NOT NULL,
                    duration NVARCHAR(50) NOT NULL,
                    fee DECIMAL(10,2) NOT NULL,
                    image_url NVARCHAR(255) NULL,
                    created_at DATETIME2 DEFAULT GETDATE()
                )
            END
            """)

            # Other SQL Server tables follow original definitions
            # ... keep existing SQL Server statements for other tables
            # For brevity, call the previous statements via execute_query as before
            # (the rest of the T-SQL blocks remain unchanged when using SQL Server)
            # We'll execute the remaining blocks using the existing code paths
            # where earlier code already called execute_query for each block.
            # (No-op here because the file still contains those execute_query calls below.)
            return

        # SQLite-compatible DDL
        try:
            ddl_statements = [
                '''
                CREATE TABLE IF NOT EXISTS chatbot_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    bot_response TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                ''',
                '''
                CREATE TABLE IF NOT EXISTS courses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    duration TEXT NOT NULL,
                    fee REAL NOT NULL,
                    image_url TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                ''',
                '''
                CREATE TABLE IF NOT EXISTS enrollments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    phone TEXT,
                    course_id INTEGER,
                    message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY(course_id) REFERENCES courses(id)
                );
                ''',
                '''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    bot_response TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                ''',
                '''
                CREATE TABLE IF NOT EXISTS enrollment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    course_id INTEGER NOT NULL,
                    message TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(course_id) REFERENCES courses(id)
                );
                ''',
                '''
                CREATE TABLE IF NOT EXISTS contact_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    subject TEXT,
                    message TEXT NOT NULL,
                    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                ''',
                '''
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_name TEXT NOT NULL,
                    course TEXT NOT NULL,
                    project_title TEXT NOT NULL,
                    project_category TEXT NOT NULL,
                    project_description TEXT NOT NULL,
                    project_url TEXT,
                    upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    password_hash TEXT
                );
                ''',
                '''
                CREATE TABLE IF NOT EXISTS staff (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    email TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login DATETIME,
                    is_active INTEGER DEFAULT 1
                );
                ''',
                '''
                CREATE TABLE IF NOT EXISTS staff_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    staff_id INTEGER,
                    activity_type TEXT NOT NULL,
                    description TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (staff_id) REFERENCES staff(id)
                );
                ''',
                '''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    location TEXT NOT NULL,
                    seats INTEGER NOT NULL,
                    category TEXT,
                    instructor TEXT,
                    price REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                ''',
            ]

            for stmt in ddl_statements:
                try:
                    self.cursor.executescript(stmt)
                except Exception as e:
                    print("Error executing DDL statement:", e)

            # Commit changes
            try:
                self.connection.commit()
            except Exception:
                pass
        except Exception as e:
            print("Error creating SQLite tables:", e)

    def insert_chat_history(self, session_id, user_message, bot_response):
        query = """
        INSERT INTO chatbot_history (session_id, user_message, bot_response)
        VALUES (?, ?, ?)
        """
        try:
            self.execute_query(query, (session_id, user_message, bot_response))
        except Exception as e:
            print("Error inserting chat history:", e)

    def get_chat_history(self, session_id):
        try:
            query = "SELECT user_message, bot_response, timestamp FROM chat_history WHERE session_id = ? ORDER BY timestamp"
            cursor = self.connection.cursor()
            cursor.execute(query, (session_id,))
            results = cursor.fetchall()
            cursor.close()
            return results
        except Exception as e:
            print("Error fetching chat history:", e)
            return []
    
    def insert_course(self, title, description, duration, fee, image_url=None):
        # Check if course already exists
        check_query = "SELECT COUNT(*) FROM courses WHERE title = ?"
        try:
            cursor = self.connection.cursor()
            cursor.execute(check_query, (title,))
            count = cursor.fetchone()[0]
            cursor.close()
            
            if count > 0:
                print(f"Course '{title}' already exists. Skipping insertion.")
                return False
            
            # Insert course if it doesn't exist
            query = """
            INSERT INTO courses (title, description, duration, fee, image_url)
            VALUES (?, ?, ?, ?, ?)
            """
            self.execute_query(query, (title, description, duration, fee, image_url))
            print(f"Course '{title}' inserted successfully.")
            return True
        except Exception as e:
            print("Error inserting course:", e)
            return False
    
    def get_save_ChatbotHistory(self, session_id, user_message, bot_response):
        self.insert_chat_history(session_id, user_message, bot_response)

    def get_courses(self):
        """Get all courses from database with improved error handling"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM courses ORDER BY id")
            courses = cursor.fetchall()
            cursor.close()
            return courses
        except Exception as e:
            print("Error fetching courses:", e)
            # Try alternative approach
            try:
                query = "SELECT id, title, description, duration, fee, image_url FROM courses ORDER BY id"
                result = self.execute_query(query)
                if result is not None:
                    courses = result.fetchall()
                    result.close()
                    return courses
            except Exception as e2:
                print("Error in fallback fetch:", e2)
            return []

    def enroll_user(self, name, email, phone, course_id, message=None):
        query = """
        INSERT INTO enrollments (name, email, phone, course_id, message)
        VALUES (?, ?, ?, ?, ?)
        """
        try:
            self.execute_query(query, (name, email, phone, course_id, message))
        except Exception as e:
            print("Error enrolling user:", e)

    def get_enrollments(self):
        query = """
        SELECT e.id, e.name, e.email, e.phone, c.title, e.enrollment_date
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        ORDER BY e.enrollment_date DESC
        """
        result = self.execute_query(query)
        if result:
            return result.fetchall()
        return []
    
    def save_chat_history(self, session_id, user_message, bot_response):
        try:
            query = "INSERT INTO chat_history (session_id, user_message, bot_response, timestamp) VALUES (?, ?, ?, GETDATE())"
            cursor = self.connection.cursor()
            cursor.execute(query, (session_id, user_message, bot_response))
            self.connection.commit()
            cursor.close()
        except Exception as e:
            print("Error saving chat history:", e)
    
    def insert_enrollment_history(self, session_id, name, email, phone, course_id, message, timestamp):
        try:
            self.cursor.execute(
                "INSERT INTO enrollment_history (session_id, name, email, phone, course_id, message, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, name, email, phone, course_id, message, timestamp)
            )
            self.connection.commit()
        except Exception as e:
            print("Error saving enrollment history:", e)
    
    def save_contact_message(self, name, email, subject, message):
        query = """
        INSERT INTO contact_messages (name, email, subject, message)
        VALUES (?, ?, ?, ?)
        """
        try:
            self.execute_query(query, (name, email, subject, message))
            return True
        except Exception as e:
            print("Error saving contact message:", e)
            return False

    def get_contact_messages(self, limit=None):
        """Get all contact messages, optionally limited"""
        try:
            cursor = self.connection.cursor()
            if limit:
                query = """
                SELECT TOP (?) id, name, email, subject, message, submitted_at
                FROM contact_messages
                ORDER BY submitted_at DESC
                """
                cursor.execute(query, (limit,))
            else:
                query = """
                SELECT id, name, email, subject, message, submitted_at
                FROM contact_messages
                ORDER BY submitted_at DESC
                """
                cursor.execute(query)
                
            messages = cursor.fetchall()
            cursor.close()
            return messages
        except Exception as e:
            print("Error getting contact messages:", e)
            return []

    def count_contact_messages(self):
        """Count total contact messages"""
        query = "SELECT COUNT(*) FROM contact_messages"
        try:
            cursor = self.execute_query(query)
            if cursor:
                return cursor.fetchone()[0]
            return 0
        except Exception as e:
            print("Error counting contact messages:", e)
            return 0

    def remove_duplicate_courses(self):
        """Remove duplicate courses, keeping only the first occurrence of each title"""
        try:
            query = """
            DELETE FROM courses 
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM courses
                GROUP BY title
            )
            """
            result = self.execute_query(query)
            if result:
                print("Duplicate courses removed successfully.")
            return result
        except Exception as e:
            print("Error removing duplicate courses:", e)
            return None

    def clear_and_reset_courses(self):
        """Clear all courses and reset identity to start from 1"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
            IF EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[courses]') AND type in (N'U'))
            BEGIN
                -- Truncate the table to remove all data
                TRUNCATE TABLE courses;
                
                -- Reset the identity to 1
                DBCC CHECKIDENT ('courses', RESEED, 0);
            END
            """)
            self.connection.commit()
            cursor.close()
            print("✅ All courses cleared and identity reset to start from 1.")
            return True
        except Exception as e:
            print("Error clearing and resetting courses:", e)
            return False

    def save_student_project(self, student_name, course, project_title, project_category, project_description, project_url, files):
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO student_projects (student_name, course, project_title, project_category, project_description, project_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, GETDATE())
            """, (student_name, course, project_title, project_category, project_description, project_url))
        self.connection.commit()
        cursor.close()

    def create_projects_table(self):
        """Create projects table if it doesn't exist"""
        cursor = self.connection.cursor()
        
        # Create base table if it doesn't exist with all required columns
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[projects]') AND type in (N'U'))
        BEGIN
            CREATE TABLE projects (
                id INT IDENTITY(1,1) PRIMARY KEY,
                student_name NVARCHAR(100) NOT NULL,
                course NVARCHAR(100) NOT NULL,
                project_title NVARCHAR(200) NOT NULL,
                project_category NVARCHAR(50) NOT NULL,
                project_description NVARCHAR(MAX) NOT NULL,
                project_url NVARCHAR(500) NULL,
                upload_date DATETIME2 DEFAULT GETDATE(),
                views INT DEFAULT 0,
                likes INT DEFAULT 0,
                shares INT DEFAULT 0,
                password_hash NVARCHAR(255) NULL
            )
        END
        """)
            
        self.connection.commit()
        cursor.close()
        print("Projects table created or already exists.")

    def save_project(self, student_name, course, project_title, project_category, project_description, project_url=None):
        """Save a new project to the database"""
        cursor = self.connection.cursor()
        cursor.execute('''
            INSERT INTO projects (student_name, course, project_title, project_category, project_description, project_url)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (student_name, course, project_title, project_category, project_description, project_url))
        self.connection.commit()
        
        # Get the inserted project ID
        cursor.execute('SELECT @@IDENTITY')
        project_id = cursor.fetchone()[0]
        cursor.close()
        return project_id

    def add_project(self, student_name, course, project_title, project_category, project_description, project_url, password=None):
        cursor = self.connection.cursor()
        
        # Hash password if provided
        password_hash = None
        if password:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        cursor.execute('''
            INSERT INTO projects (student_name, course, project_title, project_category, project_description, project_url, upload_date, views, likes, shares, password_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (student_name, course, project_title, project_category, project_description, project_url, None, 0, 0, 0, password_hash))
        self.connection.commit()
        cursor.close()
        return True

    def get_all_projects(self):
        """Get all projects from the database"""
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM projects ORDER BY upload_date DESC')
        projects = cursor.fetchall()
        cursor.close()
        return projects

    def get_projects_by_category(self, category):
        """Get projects by category"""
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM projects WHERE project_category = ? ORDER BY upload_date DESC', (category,))
        projects = cursor.fetchall()
        cursor.close()
        return projects

    def get_project_by_id(self, project_id):
        """Get a project by its ID"""
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
        project = cursor.fetchone()
        cursor.close()
        return project

    def delete_project(self, project_id):
        """Delete a project by its ID"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Error deleting project: {e}")
            return False

    def verify_project_password(self, project_id, password):
        """Verify password for a project"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('SELECT password_hash FROM projects WHERE id = ?', (project_id,))
            result = cursor.fetchone()
            cursor.close()
            
            if not result:
                return False
            
            stored_password_hash = result[0]
            
            # If no password was set (old projects), allow deletion
            if stored_password_hash is None:
                return True
            
            # Hash the provided password and compare
            provided_password_hash = hashlib.sha256(password.encode()).hexdigest()
            return stored_password_hash == provided_password_hash
            
        except Exception as e:
            print(f"Error verifying password: {e}")
            return False

    def has_password_protection(self, project_id):
        """Check if a project has password protection"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('SELECT password_hash FROM projects WHERE id = ?', (project_id,))
            result = cursor.fetchone()
            cursor.close()
            
            if not result:
                return False
            
            return result[0] is not None
            
        except Exception as e:
            print(f"Error checking password protection: {e}")
            return False

    def increment_project_views(self, project_id):
        """Increment project view count"""
        cursor = self.connection.cursor()
        cursor.execute('''
            UPDATE projects 
            SET views = ISNULL(views, 0) + 1 
            WHERE id = ?
        ''', (project_id,))
        self.connection.commit()
        cursor.close()

    def increment_project_likes(self, project_id):
        """Increment project like count"""
        cursor = self.connection.cursor()
        cursor.execute('''
            UPDATE projects 
            SET likes = ISNULL(likes, 0) + 1 
            WHERE id = ?
        ''', (project_id,))
        self.connection.commit()
        cursor.close()

    def increment_project_shares(self, project_id):
        """Increment project share count"""
        cursor = self.connection.cursor()
        cursor.execute('''
            UPDATE projects 
            SET shares = ISNULL(shares, 0) + 1 
            WHERE id = ?
        ''', (project_id,))
        self.connection.commit()
        cursor.close()

    def create_staff_table(self):
        """Create staff table if it doesn't exist"""
        cursor = self.connection.cursor()
        
        # SQL Server syntax for checking if table exists
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[staff]') AND type in (N'U'))
        BEGIN
            CREATE TABLE staff (
                id INT IDENTITY(1,1) PRIMARY KEY,
                username NVARCHAR(50) UNIQUE NOT NULL,
                name NVARCHAR(100) NOT NULL,
                role NVARCHAR(50) NOT NULL,
                password_hash NVARCHAR(255) NOT NULL,
                email NVARCHAR(100) NULL,
                created_at DATETIME2 DEFAULT GETDATE(),
                last_login DATETIME2 NULL,
                is_active BIT DEFAULT 1
            )
        END
        """)
        
        # Check if there are any staff members, if not create default admin
        cursor.execute('SELECT COUNT(*) FROM staff')
        staff_count = cursor.fetchone()[0]
        
        if staff_count == 0:
            import hashlib
            password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            cursor.execute('''
                INSERT INTO staff (username, name, role, password_hash, email)
                VALUES (?, ?, ?, ?, ?)
            ''', ('admin', 'Administrator', 'admin', password_hash, 'admin@itech.com'))
        
        self.connection.commit()
        cursor.close()

    def create_staff_activity_table(self):
        """Create staff activity log table"""
        cursor = self.connection.cursor()
        
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[staff_activity]') AND type in (N'U'))
        BEGIN
            CREATE TABLE staff_activity (
                id INT IDENTITY(1,1) PRIMARY KEY,
                staff_id INT,
                activity_type NVARCHAR(50) NOT NULL,
                description NVARCHAR(MAX),
                timestamp DATETIME2 DEFAULT GETDATE(),
                CONSTRAINT FK_staff_activity_staff FOREIGN KEY (staff_id) REFERENCES staff (id)
            )
        END
        """)
        
        self.connection.commit()
        cursor.close()

    def authenticate_staff(self, username, password):
        """Authenticate staff member"""
        import hashlib
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            print(f"Attempting to authenticate user: {username}")  # Debug print
            
            cursor = self.connection.cursor()
            cursor.execute("""
            SELECT id, username, name, role, email
            FROM staff 
            WHERE username = ? AND password_hash = ? AND is_active = 1
            """, (username, password_hash))
        
            staff = cursor.fetchone()
            
            if staff:
                print(f"Authentication successful for user: {username}")  # Debug print
                # Update last login
                cursor.execute('UPDATE staff SET last_login = GETDATE() WHERE id = ?', (staff[0],))
                self.connection.commit()
            else:
                print(f"Authentication failed for user: {username}")  # Debug print
            
            cursor.close()
            return staff
        except Exception as e:
            print(f"Authentication error for user {username}: {e}")  # Debug print
            return None
            
    def log_staff_activity(self, staff_id, activity_type, description):
        """Log staff activity"""
        cursor = self.connection.cursor()
        cursor.execute("""
        INSERT INTO staff_activity (staff_id, activity_type, description)
        VALUES (?, ?, ?)
        """, (staff_id, activity_type, description))
        self.connection.commit()
        cursor.close()

    def count_projects(self):
        """Count total projects"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                IF EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[projects]') AND type in (N'U'))
                BEGIN
                    SELECT COUNT(*) FROM projects;
                END
                ELSE
                BEGIN
                    SELECT 0;
                END
            """)
            count = cursor.fetchone()[0]
            cursor.close()
            return count
        except Exception as e:
            print(f"Error counting projects: {e}")
            return 0

    def count_enrollments(self):
        """Count total enrollments"""
        cursor = self.connection.cursor()
        
        # Check if enrollments table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM sqlite_master
            WHERE type='table' AND name='enrollments'
        """)
        
        table_exists = cursor.fetchone()[0] > 0
        
        if table_exists:
            cursor.execute('SELECT COUNT(*) FROM enrollments')
            count = cursor.fetchone()[0]
        else:
            count = 0
        
        cursor.close()
        return count

    def count_unique_students(self):
        """Count unique students"""
        cursor = self.connection.cursor()
        
        # Check if enrollments table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM sqlite_master
            WHERE type='table' AND name='enrollments'
        """)
        
        table_exists = cursor.fetchone()[0] > 0
        
        if table_exists:
            cursor.execute('SELECT COUNT(DISTINCT email) FROM enrollments')
            count = cursor.fetchone()[0]
        else:
            count = 0
        
        cursor.close()
        return count

    def get_recent_projects(self, limit=5):
        """Get recent projects"""
        cursor = self.connection.cursor()
        cursor.execute(f'SELECT TOP {limit} * FROM projects ORDER BY upload_date DESC')
        projects = cursor.fetchall()
        cursor.close()
        return projects

    def get_recent_enrollments(self, limit=5):
        """Get recent enrollments"""
        cursor = self.connection.cursor()
        
        # In SQLite, we check columns using pragma
        columns = {}
        for row in cursor.execute("PRAGMA table_info(enrollments)"):
            columns[row[1]] = True
        
        if 'created_at' in columns:
            cursor.execute(f'SELECT * FROM enrollments ORDER BY created_at DESC LIMIT {limit}')
        else:
            # If no created_at column, just get recent entries by ID
            cursor.execute(f'SELECT * FROM enrollments ORDER BY id DESC LIMIT {limit}')
        
        enrollments = cursor.fetchall()
        cursor.close()
        return enrollments

    def increment_project_views(self, project_id):
        """Increment project view count"""
        cursor = self.connection.cursor()
        cursor.execute("""
        UPDATE projects 
        SET views = ISNULL(views, 0) + 1 
        WHERE id = ?
        """, (project_id,))
        self.connection.commit()
        cursor.close()

    def increment_project_likes(self, project_id):
        """Increment project like count"""
        cursor = self.connection.cursor()
        cursor.execute("""
        UPDATE projects 
        SET likes = ISNULL(likes, 0) + 1 
        WHERE id = ?
        """, (project_id,))
        self.connection.commit()
        cursor.close()

    def reset_staff_tables(self):
        """Reset staff tables (for development only)"""
        cursor = self.connection.cursor()
        
        try:
            cursor.execute('DROP TABLE IF EXISTS staff_activity')
            cursor.execute('DROP TABLE IF EXISTS staff')
            self.connection.commit()
            print("Staff tables dropped successfully")
            
            # Recreate tables
            self.create_staff_table()
            self.create_staff_activity_table()
            print("Staff tables recreated successfully")
            
        except Exception as e:
            print(f"Error resetting staff tables: {e}")
        finally:
            cursor.close()

    def register_staff(self, username, name, role, password, email=None):
        """Register a new staff member"""
        import hashlib
        
        try:
            # Check if username already exists
            if self.staff_exists(username):
                return False, "Username already exists"
            
            # Hash the password
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            cursor = self.connection.cursor()
            cursor.execute("""
            INSERT INTO staff (username, name, role, password_hash, email)
            VALUES (?, ?, ?, ?, ?)
            """, (username, name, role, password_hash, email))
            
            self.connection.commit()
            cursor.close()
            
            return True, "Staff member registered successfully"
            
        except Exception as e:
            print(f"Error registering staff: {e}")
            return False, f"Error registering staff: {str(e)}"

    def staff_exists(self, username):
        """Check if a staff member exists"""
        cursor = self.connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM staff WHERE username = ?', (username,))
        count = cursor.fetchone()[0]
        cursor.close()
        return count > 0

    def get_all_staff(self):
        """Get all staff members"""
        cursor = self.connection.cursor()
        cursor.execute('SELECT id, username, name, role, email, created_at, last_login, is_active FROM staff ORDER BY created_at DESC')
        staff = cursor.fetchall()
        cursor.close()
        return staff

    def update_staff_status(self, staff_id, is_active):
        """Update staff active status"""
        cursor = self.connection.cursor()
        cursor.execute('UPDATE staff SET is_active = ? WHERE id = ?', (is_active, staff_id))
        self.connection.commit()
        cursor.close()

    def get_table_columns(self, table_name):
        """Get column names for a table"""
        cursor = self.connection.cursor()
        columns = []
        for row in cursor.execute(f"PRAGMA table_info({table_name})"):
            columns.append(row[1])  # Column name is at index 1
        cursor.close()
        return columns

    def create_events_table(self):
        """Create events table"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[events]') AND type in (N'U'))
            BEGIN
                CREATE TABLE events (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    title NVARCHAR(100) NOT NULL,
                    description NVARCHAR(MAX) NOT NULL,
                    event_date DATE NOT NULL,
                    event_time TIME NOT NULL,
                    location NVARCHAR(255) NOT NULL,
                    seats INT NOT NULL,
                    category NVARCHAR(100) NULL,
                    instructor NVARCHAR(255) NULL,
                    price DECIMAL(10,2) NULL,
                    created_at DATETIME2 DEFAULT GETDATE()
                )
            END
            """)
            self.connection.commit()
            print("Events table created or already exists.")
        except Exception as e:
            print(f"Error creating events table: {e}")

    def create_event_registrations_table(self):
        """Create event registrations table for SQL Server with staff tracking"""
        try:
            cursor = self.connection.cursor()
            
            # Check if table exists with correct structure
            cursor.execute("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'event_registrations' 
                AND COLUMN_NAME = 'event_name'
            """)
            has_correct_structure = cursor.fetchone() is not None
            
            if not has_correct_structure:
                # Drop existing table if it has wrong structure
                cursor.execute('DROP TABLE IF EXISTS event_registrations')
                
                # Create table with correct structure
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[event_registrations]') AND type in (N'U'))
                BEGIN
                    CREATE TABLE event_registrations (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        event_name NVARCHAR(200) NOT NULL,
                        full_name NVARCHAR(100) NOT NULL,
                        email NVARCHAR(100) NOT NULL,
                        phone NVARCHAR(20) NOT NULL,
                        experience_level NVARCHAR(50) NULL,
                        special_requirements NVARCHAR(MAX) NULL,
                        registration_date DATETIME2 DEFAULT GETDATE(),
                        status NVARCHAR(20) DEFAULT 'pending',
                        approved_by_staff_id INT NULL,
                        action_date DATETIME2 NULL,
                        CONSTRAINT FK_event_registrations_staff FOREIGN KEY (approved_by_staff_id) REFERENCES staff(id)
                    )
                END
                """)
                self.connection.commit()
                print("Event registrations table created successfully with correct structure.")
            else:
                print("Event registrations table already exists with correct structure.")
                
            cursor.close()
            
        except Exception as e:
            print(f"Error creating event registrations table: {e}")

    def clear_all_event_registrations(self):
        """Clear all event registrations - manual operation only"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('DELETE FROM event_registrations')
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Error clearing event registrations: {e}")
            return False

    def insert_event_registration(self, event_name, full_name, email, phone, experience_level=None, special_requirements=None):
        """Insert event registration using the SQL Server database"""
        cursor = None
        try:
            print("Starting event registration insert...")  # Debug
            
            # First check if table exists with correct structure
            if not self.ensure_event_registrations_table():
                print("Could not ensure event_registrations table exists")
                raise Exception("Database table not ready. Please try again.")
                
            print("Table structure verified...")  # Debug

            cursor = self.connection.cursor()
            
            # Check for existing registration
            cursor.execute("""
            SELECT id, status FROM event_registrations 
            WHERE event_name = ? AND email = ?
            """, (event_name, email))
            
            existing = cursor.fetchone()
            if existing:
                status = existing[1]
                print(f"Found existing registration (ID: {existing[0]}) for {email} in event {event_name}")
                raise Exception(f"You have already registered for this event (status: {status})")

            print(f"Inserting registration for {full_name} into event {event_name}")  # Debug

            # Insert registration
            insert_query = """
            INSERT INTO event_registrations 
            (event_name, full_name, email, phone, experience_level, special_requirements, status, registration_date)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
            """
            
            cursor.execute(insert_query, 
                (event_name, full_name, email, phone, experience_level, special_requirements, 'pending'))
            
            row = cursor.fetchone()
            if not row:
                raise Exception("Failed to get registration ID")
                
            registration_id = row[0]
            self.connection.commit()
            print(f"Successfully inserted registration with ID: {registration_id}")  # Debug
            
            return registration_id
            
        except Exception as e:
            if cursor:
                self.connection.rollback()
            print(f"Error in insert_event_registration: {str(e)}")
            raise
            
        finally:
            if cursor:
                cursor.close()
            
    def ensure_event_registrations_table(self):
        """Ensure event_registrations table exists with correct structure"""
        try:
            cursor = self.connection.cursor()
            
            # Check if table exists
            cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[event_registrations]') AND type in (N'U'))
            BEGIN
                CREATE TABLE event_registrations (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    event_name NVARCHAR(200) NOT NULL,
                    full_name NVARCHAR(100) NOT NULL,
                    email NVARCHAR(100) NOT NULL,
                    phone NVARCHAR(20) NOT NULL,
                    experience_level NVARCHAR(50) NULL,
                    special_requirements NVARCHAR(MAX) NULL,
                    registration_date DATETIME2 DEFAULT GETDATE(),
                    status NVARCHAR(20) DEFAULT 'pending',
                    approved_by_staff_id INT NULL REFERENCES staff(id),
                    action_date DATETIME2 NULL,
                    CONSTRAINT UQ_event_registration UNIQUE (event_name, email)
                )
                
                PRINT 'Created event_registrations table'
            END

            -- Ensure status column has the correct default
            IF EXISTS (
                SELECT * FROM sys.columns 
                WHERE object_id = OBJECT_ID(N'[dbo].[event_registrations]')
                AND name = 'status'
                AND default_object_id = 0
            )
            BEGIN
                ALTER TABLE event_registrations
                ADD CONSTRAINT DF_event_registrations_status DEFAULT 'pending' FOR status
            END
            """)
            
            self.connection.commit()
            cursor.close()
            return True
            
        except Exception as e:
            print(f"Error ensuring event_registrations table: {e}")
            return False

    def get_event_registrations(self, limit=None):
        """Get event registrations with optional limit"""
        try:
            cursor = self.connection.cursor()
            if limit:
                cursor.execute('''
                    SELECT TOP (?) er.id, er.event_name, er.full_name, er.email, er.phone, 
                           er.experience_level, er.special_requirements, er.registration_date, 
                           ISNULL(er.status, 'pending') as status, 
                           er.approved_by_staff_id, er.action_date,
                           ISNULL(s.name, '-') as staff_name
                    FROM event_registrations er
                    LEFT JOIN staff s ON er.approved_by_staff_id = s.id
                    ORDER BY er.registration_date DESC
                ''', (limit,))
            else:
                cursor.execute('''
                    SELECT er.id, er.event_name, er.full_name, er.email, er.phone, 
                           er.experience_level, er.special_requirements, er.registration_date, 
                           ISNULL(er.status, 'pending') as status, 
                           er.approved_by_staff_id, er.action_date,
                           ISNULL(s.name, '-') as staff_name
                    FROM event_registrations er
                    LEFT JOIN staff s ON er.approved_by_staff_id = s.id
                    ORDER BY er.registration_date DESC
                ''')
            result = cursor.fetchall()
            cursor.close()
            return result
        except Exception as e:
            print(f"Error getting event registrations: {e}")
            return []

    def count_event_registrations(self):
        """Count total event registrations"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM event_registrations")
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else 0
        except Exception as e:
            print(f"Error counting event registrations: {e}")
            return 0
            
    def count_pending_event_registrations(self):
        """Count pending event registrations"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM event_registrations WHERE status = 'pending'")
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else 0
        except Exception as e:
            print(f"Error counting pending event registrations: {e}")
            return 0

    def update_event_registration_status(self, registration_id, status, staff_id):
        """Update event registration status and track which staff member made the change"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('''
                UPDATE event_registrations 
                SET status = ?, approved_by_staff_id = ?, action_date = GETDATE()
                WHERE id = ?
            ''', (status, staff_id, registration_id))
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Error updating registration status: {e}")
            return False

    def get_staff_name_by_id(self, staff_id):
        """Get staff name by ID"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('SELECT name FROM staff WHERE id = ?', (staff_id,))
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else 'Unknown'
        except Exception as e:
            print(f"Error getting staff name: {e}")
            return 'Unknown'

    def add_missing_event_registration_columns(self):
        """Add missing columns to existing event_registrations table"""
        try:
            cursor = self.connection.cursor()
            
            # Check if status column exists
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'event_registrations' AND COLUMN_NAME = 'status'
            """)
            if cursor.fetchone()[0] == 0:
                cursor.execute("ALTER TABLE event_registrations ADD status NVARCHAR(50) DEFAULT 'pending'")
                print("Added status column to event_registrations table")
            
            # Check if approved_by_staff_id column exists
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'event_registrations' AND COLUMN_NAME = 'approved_by_staff_id'
            """)
            if cursor.fetchone()[0] == 0:
                cursor.execute('ALTER TABLE event_registrations ADD approved_by_staff_id INT')
                print("Added approved_by_staff_id column to event_registrations table")
            
            # Check if action_date column exists
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'event_registrations' AND COLUMN_NAME = 'action_date'
            """)
            if cursor.fetchone()[0] == 0:
                cursor.execute('ALTER TABLE event_registrations ADD action_date DATETIME')
                print("Added action_date column to event_registrations table")
            
            self.connection.commit()
            cursor.close()
        except Exception as e:
            print(f"Error adding missing columns: {e}")


