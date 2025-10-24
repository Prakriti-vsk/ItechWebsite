import os
import re
import time
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
import json
from rapidfuzz import fuzz
import uuid
from datetime import datetime, timedelta
from data.database import Database
from config import Config
import random
from data.courses import courses
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
import sqlite3 

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY if hasattr(Config, 'SECRET_KEY') else 'dev-key-12345'

# database
db = Database()


# Ensure courses table always starts with ID 1 - ROBUST VERSION
try:
    # Try to get courses and handle any database errors
    existing_courses = []
    try:
        existing_courses = db.get_courses() or []
    except Exception as e:
        print(f"⚠️ Error getting courses: {e}")
        existing_courses = []
    
    if not existing_courses:
        # No courses found - reset identity and insert fresh
        print("📋 No courses found, inserting fresh courses...")
        db.reset_courses_identity()
        
        for course in courses:
            try:
                db.insert_course(
                    title=course['title'],
                    description=course['description'],
                    duration=course['duration'],
                    fee=course['fee'],
                    image_url=course.get('image_url')
                )
            except Exception as e:
                print(f"⚠️ Error inserting course {course['title']}: {e}")
        
        print("✅ Courses inserted with IDs starting from 1")
    
    else:
        # Check if we need to reset courses (if they don't start from 1)
        first_course_id = existing_courses[0][0] if existing_courses else None
        if first_course_id and first_course_id != 1:
            print(f"⚠️ Courses start from ID {first_course_id}, not 1. Resetting...")
            # Clear and reset courses to ensure ID starts from 1
            db.clear_and_reset_courses()
            
            # Re-insert all courses
            for course in courses:
                try:
                    db.insert_course(
                        title=course['title'],
                        description=course['description'],
                        duration=course['duration'],
                        fee=course['fee'],
                        image_url=course.get('image_url')
                    )
                except Exception as e:
                    print(f"⚠️ Error inserting course {course['title']}: {e}")
            
            print("✅ Courses reset and inserted with IDs starting from 1")
        else:
            print(f"✅ Courses already exist and start from ID {first_course_id}")

except Exception as e:
    print(f"❌ Error in course initialization: {e}")
    # Fallback - try to insert courses anyway
    for course in courses:
        try:
            db.insert_course(
                title=course['title'],
                description=course['description'],
                duration=course['duration'],
                fee=course['fee'],
                image_url=course.get('image_url')
            )
        except Exception as insert_error:
            print(f"⚠️ Error inserting course {course['title']}: {insert_error}")


with open('data/chatbot_responses.json', 'r') as f:
    chatbot_responses = json.load(f)


def prepare_course_data():
    course_data = []
    for course in courses:
        
        tags = course['title'].lower() + " " + course['description'].lower()
        
        # Add specific tags based on course categories
        if 'programming' in course['title'].lower() or 'development' in course['title'].lower():
            tags += " coding software developer programming "
        if 'design' in course['title'].lower():
            tags += " creative art graphics "
        if 'data' in course['title'].lower():
            tags += " analytics machine learning AI "
        if 'account' in course['title'].lower() or 'tally' in course['title'].lower():
            tags += " finance accounting business "
        if 'typing' in course['title'].lower():
            tags += " office clerical data entry "
            
        course_data.append({
            'id': course['id'],
            'title': course['title'],
            'tags': tags,
            'description': course['description']
        })
    return course_data

course_data = prepare_course_data()

# Create DataFrame for courses
df = pd.DataFrame(course_data)
df['content'] = df['title'] + ' ' + df['description'] + ' ' + df['tags']


tfidf = TfidfVectorizer(stop_words='english')
tfidf_matrix = tfidf.fit_transform(df['content'])


cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)


from chatbot_handler import ChatbotHandler

# Initialize chatbot handler
chatbot_handler = ChatbotHandler()

@app.before_request
def before_request():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    if 'course_recommendation_state' not in session:
        session['course_recommendation_state'] = None

@app.route('/')
def index():
    return render_template('index.html')  

@app.route('/chatbot', methods=['POST'])
def chatbot():
    user_message = request.json.get('message').lower()

    
    if session.get('course_recommendation_state'):
        response = chatbot_handler.handle_course_recommendation_flow(session, user_message)
        return jsonify({'response': response})
    
    # Load chatbot responses
    with open('data/chatbot_responses.json', 'r') as f:
        chatbot_responses = json.load(f)
    
    # Check for normal conversation intents
    intent = chatbot_handler.get_best_intent(user_message, chatbot_responses['intents'])
    
    if intent:
        if intent['tag'] == 'course_recommendation':
            # Start course recommendation flow
            session['course_recommendation_state'] = 'awaiting_interests'
            response = random.choice(intent['responses'])
        else:
            # Handle normal conversation
            response = random.choice(intent['responses'])
            
            # Check if this is a greeting to reset conversation
            if intent['tag'] in ['greeting', 'goodbye']:
                session.pop('course_recommendation_state', None)
                session.pop('user_interests', None)
                session.pop('user_education', None)
                session.pop('user_skills', None)
                session.pop('user_qualifications', None)
    else:
        # Fallback response if no intent matches
        response = "I'm sorry, I didn't understand that. Could you rephrase your question?"

    # Save to database
    chatbot_handler.db.insert_chat_history(session['session_id'], user_message, response)
    return jsonify({'response': response})

@app.route('/chat_history')
def get_chat_history():
    history = db.get_chat_history(session['session_id'])
    return jsonify([{
        'user_message': row[0],
        'bot_response': row[1],
        'timestamp': row[2].strftime('%Y-%m-%d %H:%M:%S')
    } for row in history])

@app.route('/courses')
def courses_route():
    query = request.args.get('q', '').lower()
    if query:
        filtered_courses = [c for c in courses if query in c['title'].lower() or query in c['description'].lower()]
    else:
        filtered_courses = courses
    return render_template('courses.html', courses=filtered_courses)

def get_best_intent(user_message, intents, threshold=70):
    user_message = user_message.lower()
    best_score = 0
    best_intent = None
    for intent in intents:
        for pattern in intent["patterns"]:
            score = fuzz.ratio(user_message, pattern.lower())
            if score > best_score:
                best_score = score
                best_intent = intent
    if best_score >= threshold:
        return best_intent
    return None

@app.route('/enroll', methods=['GET', 'POST'])
def enroll():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        course_id = request.form.get('course_id')
        message = request.form.get('message')

        try:
            db.enroll_user(
                name=name,
                email=email,
                phone=phone,
                course_id=int(course_id),
                message=message
            )
            return render_template('enroll.html', success=True)
        except Exception as e:
            print(f"Error saving enrollment: {e}")
            return render_template('enroll.html', success=False, error=str(e))
    return render_template('enroll.html', success=False)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/student-projects', methods=['GET', 'POST'])
def student_projects():
    if request.method == 'POST':
        try:
            # Get form data
            student_name = request.form.get('studentName')
            course = request.form.get('course')
            project_title = request.form.get('projectTitle')
            project_category = request.form.get('projectCategory')
            project_description = request.form.get('projectDescription')
            project_url = request.form.get('projectUrl')
            project_password = request.form.get('projectPassword')
            
            # Handle file uploads
            files = request.files.getlist('projectFiles')
            main_file_url = None
            
            if files and files[0].filename:
                # Create upload directory if it doesn't exist
                upload_dir = os.path.join('static', 'uploads', 'projects')
                os.makedirs(upload_dir, exist_ok=True)
                
                # Create project-specific directory
                timestamp = int(time.time())
                project_dir = os.path.join(upload_dir, f'project_{timestamp}')
                os.makedirs(project_dir, exist_ok=True)
                
                # Save files and find main HTML file
                for file in files:
                    if file.filename and file.filename != '':
                        # Secure the filename
                        filename = secure_filename(file.filename)
                        
                        # Check if it's a ZIP file
                        if filename.lower().endswith('.zip'):
                            # Handle ZIP file
                            main_file_url = handle_zip_upload(file, project_dir, timestamp)
                        else:
                            # Handle individual files
                            file_path = os.path.join(project_dir, filename)
                            file.save(file_path)
                            
                            # Set main file URL (prefer index.html, otherwise first HTML file)
                            if filename.lower() == 'index.html' or (main_file_url is None and filename.lower().endswith('.html')):
                                main_file_url = f'/static/uploads/projects/project_{timestamp}/{filename}'
                        
                        print(f"Saved file: {filename}")
                        print(f"Main file URL: {main_file_url}")
            
            # Use provided URL if no files uploaded
            if not main_file_url and project_url:
                main_file_url = project_url
            
            # Validate required fields
            if not all([student_name, course, project_title, project_category, project_description]):
                return render_template('student-projects.html', 
                                     projects=db.get_all_projects(), 
                                     error="Please fill in all required fields")
            
            # Save to database
            success = db.add_project(
                student_name=student_name,
                course=course,
                project_title=project_title,
                project_category=project_category,
                project_description=project_description,
                project_url=main_file_url,
                password=project_password if project_password else None
            )
            
            if success:
                return redirect(url_for('student_projects', success=True))
            else:
                return render_template('student-projects.html', 
                                     projects=db.get_all_projects(), 
                                     error="Failed to save project")
                
        except Exception as e:
            print(f"Error uploading project: {e}")
            return render_template('student-projects.html', 
                                 projects=db.get_all_projects(), 
                                 error=f"Error uploading project: {str(e)}")
    
    # GET request
    success = request.args.get('success')
    projects = db.get_all_projects()
    return render_template('student-projects.html', projects=projects, success=success)

def handle_zip_upload(zip_file, project_dir, timestamp):
    """Handle ZIP file upload and extraction with better path handling"""
    import zipfile
    
    try:
        # Save ZIP file temporarily
        zip_path = os.path.join(project_dir, 'temp.zip')
        zip_file.save(zip_path)
        
        # Extract ZIP file
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Get list of files in ZIP
            file_list = zip_ref.namelist()
            
            # Filter out system files and empty directories
            filtered_files = [f for f in file_list if not f.startswith('__MACOSX/') and not f.startswith('.DS_Store') and not f.endswith('/')]
            
            # Extract all files
            for file_name in filtered_files:
                try:
                    zip_ref.extract(file_name, project_dir)
                    print(f"Extracted: {file_name}")
                except Exception as e:
                    print(f"Error extracting {file_name}: {e}")
            
            # Find main HTML file
            main_html = None
            
            # First, look for index.html in root
            for file_name in filtered_files:
                if file_name.lower() == 'index.html':
                    main_html = file_name
                    break
            
            # If no index.html, look for any HTML file with 'index' in name
            if not main_html:
                for file_name in filtered_files:
                    if 'index' in file_name.lower() and file_name.lower().endswith('.html'):
                        main_html = file_name
                        break
            
            # If still no main file, take the first HTML file
            if not main_html:
                for file_name in filtered_files:
                    if file_name.lower().endswith('.html'):
                        main_html = file_name
                        break
            
            # Clean up temporary ZIP file
            os.remove(zip_path)
            
            if main_html:
                return f'/static/uploads/projects/project_{timestamp}/{main_html}'
            else:
                # If no HTML file found, return None
                print("No HTML file found in ZIP")
                return None
                
    except Exception as e:
        print(f"Error handling ZIP upload: {e}")
        # Clean up on error
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return None

@app.route('/view-uploaded-project/<int:project_id>')
def view_uploaded_project(project_id):
    try:
        project = db.get_project_by_id(project_id)
        if not project:
            return render_template('404.html', message="Project not found"), 404
        
        project_url = project[6]  # Assuming project URL is at index 6
        
        # Check if it's an uploaded file
        if project_url and project_url.startswith('/static/uploads/projects/'):
            # Increment view count
            db.increment_project_views(project_id)
            
            # Serve the HTML file directly
            file_path = project_url[1:]  # Remove leading slash
            if os.path.exists(file_path):
                # Read and serve HTML content
                with open(file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Update relative paths to work with Flask static serving
                project_dir = os.path.dirname(project_url)
                html_content = update_relative_paths(html_content, project_dir)
                
                return html_content
            else:
                return render_template('404.html', message="Project file not found"), 404
        else:
            # If it's an external URL, redirect to it
            return redirect(project_url)
            
    except Exception as e:
        print(f"Error viewing uploaded project: {e}")
        return render_template('404.html', message="Error loading project"), 500

def update_relative_paths(html_content, project_dir):
    """Update relative paths in HTML to work with Flask static serving"""
    import re
    
    
    html_content = re.sub(
        r'href="([^"]*\.css)"',
        f'href="{project_dir}/\\1"',
        html_content
    )
    
    
    html_content = re.sub(
        r'src="([^"]*\.js)"',
        f'src="{project_dir}/\\1"',
        html_content
    )
    
    # Update image sources
    html_content = re.sub(
        r'src="([^"]*\.(png|jpg|jpeg|gif|svg|webp))"',
        f'src="{project_dir}/\\1"',
        html_content
    )
    
    # Update background images in CSS
    html_content = re.sub(
        r'url\(["\']?([^"\']*\.(png|jpg|jpeg|gif|svg|webp))["\']?\)',
        f'url("{project_dir}/\\1")',
        html_content
    )
    
    return html_content

@app.route('/project/<int:project_id>')
def view_project(project_id):
    try:
        project = db.get_project_by_id(project_id)
        
        if not project:
            return render_template('404.html', message="Project not found"), 404
        
        # Increment view count
        db.increment_project_views(project_id)
        
        return render_template('project-detail.html', project=project)
    except Exception as e:
        print(f"Error viewing project: {e}")
        return render_template('404.html', message="Error loading project"), 500

@app.route('/delete-project/<int:project_id>', methods=['POST'])
def delete_project(project_id):
    try:
        # Get project details before deletion
        project = db.get_project_by_id(project_id)
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'})
        
        # Check if password verification is required
        try:
            if request.is_json:
                request_data = request.get_json()
            else:
                request_data = {}
        except Exception as e:
            request_data = {}
        
        provided_password = request_data.get('password') if request_data else None
        
        # Check if project has password protection
        has_protection = db.has_password_protection(project_id)
        
        if has_protection:
            if not provided_password:
                return jsonify({
                    'success': False, 
                    'error': 'This project is password protected. Please enter the correct password.'
                })
            
            # Verify password
            if not db.verify_project_password(project_id, provided_password):
                return jsonify({
                    'success': False, 
                    'error': 'Incorrect password. Unable to delete project.'
                })
        
        # Delete associated files if they exist
        project_url = project[6]
        if project_url and project_url.startswith('/static/uploads/projects/'):
            file_path = project_url[1:]  # Remove leading slash
            if os.path.exists(file_path):
                try:
                    # Delete entire project directory
                    project_dir = os.path.dirname(file_path)
                    import shutil
                    if os.path.exists(project_dir):
                        shutil.rmtree(project_dir)
                        print(f"Deleted project directory: {project_dir}")
                except Exception as e:
                    print(f"Error deleting project files: {e}")
        
        # Delete from database
        success = db.delete_project(project_id)
        if success:
            return jsonify({'success': True, 'message': 'Project deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to delete project from database'})
            
    except Exception as e:
        print(f"Error in delete_project: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/like-project/<int:project_id>', methods=['POST'])
def like_project(project_id):
    try:
        # Only increment likes, not views
        db.increment_project_likes(project_id)
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error liking project: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/share-project/<int:project_id>', methods=['POST'])
def share_project(project_id):
    try:
        # Increment share count
        db.increment_project_shares(project_id)
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error tracking share: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/events')
def events():
    return render_template('events.html')

@app.route('/branches')
def branches():
    return render_template('branches.html')

@app.route('/staff-login', methods=['GET', 'POST'])
def staff_login():
    # If user is already logged in, redirect to dashboard
    if session.get('is_staff'):
        return redirect(url_for('staff_dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember_me = request.form.get('remember_me')
        
        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('staff-login.html')
            
        # Check if staff exists and password is correct
        staff = db.authenticate_staff(username, password)
        
        if staff:
            # Create session
            session.clear()  # Clear any existing session data
            session.permanent = True  # Make session last longer
            app.permanent_session_lifetime = timedelta(days=5)  # Set session lifetime to 5 days
            
            session['staff_id'] = staff[0]
            session['staff_username'] = staff[1]
            session['staff_name'] = staff[2]
            session['staff_role'] = staff[3]
            session['is_staff'] = True
            
            print("Login successful. Session data:", dict(session))  # Debug print
            
            # Set remember me cookie if checked
            if remember_me:
                session.permanent = True
                app.permanent_session_lifetime = timedelta(days=30)
            
            # Log login activity
            db.log_staff_activity(staff[0], 'login', f'User {username} logged in')
            
            flash('Login successful! Welcome back.', 'success')
            return redirect(url_for('staff_dashboard'))
        else:
            # Check if user exists
            if not db.staff_exists(username):
                flash('User not found. Please register first.', 'error')
                return redirect(url_for('staff_register'))
            else:
                flash('Invalid username or password. Please try again.', 'error')
    
    return render_template('staff-login.html')

@app.route('/admin-settings')
def admin_settings():
    # Only allow super admin or existing staff with admin role
    if not session.get('is_staff') or session.get('staff_role') != 'admin':
        flash('Access denied. Administrator privileges required.', 'error')
        return redirect(url_for('staff_login'))
    
    # Get dashboard data similar to staff dashboard
    try:
        dashboard_data = {
            'all_staff': db.get_all_staff(),
            'staff_info': {
                'name': session.get('staff_name'),
                'role': session.get('staff_role'),
                'username': session.get('staff_username')
            }
        }
    except Exception as e:
        print(f"Admin settings error: {e}")
        dashboard_data = {
            'all_staff': [],
            'staff_info': {
                'name': session.get('staff_name'),
                'role': session.get('staff_role'),
                'username': session.get('staff_username')
            }
        }
    
    return render_template('admin-settings.html', 
                         current_admin_password=Config.ADMIN_REGISTRATION_PASSWORD,
                         data=dashboard_data)

@app.route('/change-admin-password', methods=['POST'])
def change_admin_password():
    # Only allow admin users
    if not session.get('is_staff') or session.get('staff_role') != 'admin':
        flash('Access denied. Administrator privileges required.', 'error')
        return redirect(url_for('staff_login'))
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    # Validation
    if not all([current_password, new_password, confirm_password]):
        flash('All fields are required.', 'error')
        return redirect(url_for('admin_settings'))
    
    # Check current password
    if current_password != Config.ADMIN_REGISTRATION_PASSWORD:
        flash('Current password is incorrect.', 'error')
        return redirect(url_for('admin_settings'))
    
    # Check password match
    if new_password != confirm_password:
        flash('New passwords do not match.', 'error')
        return redirect(url_for('admin_settings'))
    
    # Check password strength
    if len(new_password) < 8:
        flash('New password must be at least 8 characters long.', 'error')
        return redirect(url_for('admin_settings'))
    
    try:
        # Update config file
        config_path = 'config.py'
        with open(config_path, 'r') as file:
            content = file.read()
        
        # Replace the password in config
        old_line = f'ADMIN_REGISTRATION_PASSWORD = "{Config.ADMIN_REGISTRATION_PASSWORD}"'
        new_line = f'ADMIN_REGISTRATION_PASSWORD = "{new_password}"'
        content = content.replace(old_line, new_line)
        
        with open(config_path, 'w') as file:
            file.write(content)
        
        # Update the config in memory (requires app restart for full effect)
        Config.ADMIN_REGISTRATION_PASSWORD = new_password
        
        # Log the activity
        db.log_staff_activity(
            session['staff_id'], 
            'admin_password_change', 
            f'Admin password changed by {session.get("staff_username")}'
        )
        
        flash('Admin password updated successfully! Please note that the application may need to be restarted for all changes to take effect.', 'success')
        
    except Exception as e:
        print(f"Error updating admin password: {e}")
        flash('Error updating password. Please try again.', 'error')
    
    return redirect(url_for('admin_settings'))

@app.route('/staff-register', methods=['GET', 'POST'])
def staff_register():
    if request.method == 'POST':
        username = request.form.get('username')
        name = request.form.get('name')
        role = request.form.get('role')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        email = request.form.get('email')
        admin_password = request.form.get('admin_password')
        
        # Validation
        if not all([username, name, role, password, confirm_password, admin_password]):
            flash('All fields are required including admin password.', 'error')
            return render_template('staff-register.html')
        
        # Check admin password first
        if admin_password != Config.ADMIN_REGISTRATION_PASSWORD:
            flash('Invalid admin password! Only authorized administrators can create staff accounts.', 'error')
            return render_template('staff-register.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('staff-register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('staff-register.html')
        
        # Register staff
        success, message = db.register_staff(username, name, role, password, email)
        
        if success:
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('staff_login'))
        else:
            flash(message, 'error')
    
    return render_template('staff-register.html')

@app.route('/staff-dashboard')
def staff_dashboard():
    print("\n=== Starting Dashboard Access ===")
    print("Session data:", dict(session))
    print("Database connection status:", bool(db.connection))  # Debug print
    
    # Check if user is logged in
    if not session.get('is_staff'):
        flash('Please login first to access the dashboard', 'warning')
        return redirect(url_for('staff_login'))
        
    # Verify staff_id exists
    if not session.get('staff_id'):
        session.clear()
        flash('Session is invalid. Please login again.', 'error')
        return redirect(url_for('staff_login'))
    
    # Ensure we have a valid database connection first
    if not hasattr(db, 'connection') or db.connection is None:
        flash('Database connection error. Please try again later.', 'error')
        return redirect(url_for('staff_login'))
        
    # Initialize dashboard data with defaults and basic staff info first
    dashboard_data = {
        'staff_info': {
            'name': session.get('staff_name', 'Unknown'),
            'role': session.get('staff_role', 'Staff'),
            'username': session.get('staff_username', '')
        },
        'total_projects': 0,
        'total_enrollments': 0,
        'total_students': 0,
        'total_contact_messages': 0,
        'total_event_registrations': 0,
        'recent_projects': [],
        'recent_enrollments': [],
        'recent_contact_messages': [],
        'recent_event_registrations': [],
        'all_staff': []
    }

    try:
        # Get each piece of data individually with debug logging
        print("\nLoading dashboard statistics...")
        
        try:
            dashboard_data['total_projects'] = db.count_projects()
            print("Projects count loaded:", dashboard_data['total_projects'])
        except Exception as e:
            print("Error loading projects count:", e)
            
        try:
            dashboard_data['total_enrollments'] = db.count_enrollments()
            print("Enrollments count loaded:", dashboard_data['total_enrollments'])
        except Exception as e:
            print("Error loading enrollments count:", e)
            
        try:
            dashboard_data['total_students'] = db.count_unique_students()
            print("Students count loaded:", dashboard_data['total_students'])
        except Exception as e:
            print("Error loading students count:", e)
            
        try:
            dashboard_data['total_contact_messages'] = db.count_contact_messages()
            print("Contact messages count loaded:", dashboard_data['total_contact_messages'])
        except Exception as e:
            print("Error loading contact messages count:", e)
            
        try:
            dashboard_data['total_event_registrations'] = db.count_event_registrations()
            print("Event registrations count loaded:", dashboard_data['total_event_registrations'])
        except Exception as e:
            print("Error loading event registrations count:", e)
        
        # Get recent data
        try:
            dashboard_data['recent_projects'] = db.get_recent_projects(5)
        except Exception as e:
            print(f"Error getting recent projects: {e}")
            
        try:
            dashboard_data['recent_enrollments'] = db.get_recent_enrollments(5)
        except Exception as e:
            print(f"Error getting recent enrollments: {e}")
            
        try:
            dashboard_data['recent_contact_messages'] = db.get_contact_messages(5)
        except Exception as e:
            print(f"Error getting contact messages: {e}")
            
        try:
            dashboard_data['recent_event_registrations'] = db.get_event_registrations(5)
        except Exception as e:
            print(f"Error getting event registrations: {e}")
            
        try:
            dashboard_data['all_staff'] = db.get_all_staff()
        except Exception as e:
            print(f"Error getting staff list: {e}")
            
    except Exception as e:
        print(f"Error loading dashboard data: {e}")
        flash('Some dashboard data could not be loaded.', 'warning')
        # Don't redirect, just continue with what we have
    
    # Get pending event registration count
    try:
        pending_registrations = db.count_pending_event_registrations()
    except Exception as e:
        print(f"Error getting pending registrations: {e}")
        pending_registrations = 0
        
    print("Dashboard data loaded successfully")  # Debug print
    
    return render_template('staff-dashboard.html', 
                         data=dashboard_data,
                         pending_registrations=pending_registrations)

@app.route('/staff-dashboard-safe')
def staff_dashboard_safe():
    if not session.get('is_staff'):
        return redirect(url_for('staff_login'))
    
    # Get dashboard data with error handling
    try:
        total_projects = db.count_projects()
    except:
        total_projects = 0
    
    try:
        total_enrollments = db.count_enrollments()
    except:
        total_enrollments = 0
    
    try:
        total_students = db.count_unique_students()
    except:
        total_students = 0
    
    try:
        recent_projects = db.get_recent_projects(5)
    except:
        recent_projects = []
    
    try:
        recent_enrollments = db.get_recent_enrollments(5)
    except:
        recent_enrollments = []
    
    try:
        all_staff = db.get_all_staff()
    except:
        all_staff = []
    
    dashboard_data = {
        'total_projects': total_projects,
        'total_enrollments': total_enrollments,
        'total_students': total_students,
        'recent_projects': recent_projects,
        'recent_enrollments': recent_enrollments,
        'all_staff': all_staff,
        'staff_info': {
            'name': session.get('staff_name'),
            'role': session.get('staff_role'),
            'username': session.get('staff_username')
        }
    }
    
    return render_template('staff-dashboard.html', data=dashboard_data)

@app.route('/staff-logout')
def staff_logout():
    if session.get('staff_id'):
        # Log logout activity
        db.log_staff_activity(session['staff_id'], 'logout', f'User {session.get("staff_username")} logged out')
    
    # Clear session
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('staff_login'))

# Clean registration route:
@app.route('/save-event-registration', methods=['POST'])
def save_event_registration():
    try:
        data = request.get_json() if request.is_json else request.form
        if not data:
            return jsonify({'success': False, 'message': 'No form data received'}), 400

        # Extract and clean fields
        full_name = str(data.get('fullName', '')).strip()
        email = str(data.get('email', '')).strip().lower()
        phone = str(data.get('phone', '')).strip()
        event_name = str(data.get('eventName', '')).strip()
        experience = str(data.get('experience', '')).strip()
        requirements = str(data.get('requirements', '')).strip()

        # Validate required fields
        if not all([full_name, email, phone, event_name]):
            missing = []
            if not full_name: missing.append('fullName')
            if not email: missing.append('email')
            if not phone: missing.append('phone')
            if not event_name: missing.append('eventName')
            return jsonify({
                'success': False,
                'message': f'Missing required fields: {", ".join(missing)}'
            }), 400

        # Add registration to database
        reg_id = db.insert_event_registration(
            event_name=event_name,
            full_name=full_name,
            email=email,
            phone=phone,
            experience_level=experience if experience else None,
            special_requirements=requirements if requirements else None
        )

        return jsonify({
            'success': True,
            'message': 'Registration successful!',
            'registration_id': reg_id
        })

    except Exception as e:
        error_msg = str(e)
        print(f'Registration error: {error_msg}')

        if 'already registered' in error_msg.lower():
            return jsonify({
                'success': False,
                'message': error_msg
            }), 409

        return jsonify({
            'success': False,
            'message': 'An error occurred during registration. Please try again later.'
        }), 500

# Route to view all event registrations (for staff)
@app.route('/event-registrations')
def view_event_registrations():
    if not session.get('is_staff'):
        return redirect(url_for('staff_login'))
    
    try:
        registrations = db.get_event_registrations()
        print(f"Found {len(registrations)} event registrations")
        return render_template('event-registrations.html', registrations=registrations)
        
    except Exception as e:
        print(f"Error in view_event_registrations: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/update-registration-status', methods=['POST'])
def update_registration_status():
    if not session.get('is_staff'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        registration_id = data.get('id')
        new_status = data.get('status')
        staff_id = session.get('staff_id')
        
        print(f"Updating registration {registration_id} to {new_status} by staff {staff_id}")
        
        if not registration_id or not new_status:
            return jsonify({'success': False, 'message': 'Missing ID or status'}), 400
        
        success = db.update_event_registration_status(registration_id, new_status, staff_id)
        
        if success:
            db.log_staff_activity(
                staff_id, 
                'registration_status_change', 
                f'Changed registration {registration_id} status to {new_status}'
            )
            
            return jsonify({'success': True, 'message': 'Status updated successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to update status'}), 500
        
    except Exception as e:
        print(f"Error updating status: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/clear-all-registrations', methods=['POST'])
def clear_all_registrations():
    if not session.get('is_staff'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        staff_id = session.get('staff_id')
        staff_name = session.get('staff_name', 'Unknown')
        
        # Get count before clearing for logging
        cursor = db.connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM event_registrations')
        count_before = cursor.fetchone()[0]
        cursor.close()
        
        # Clear all registrations
        success = db.clear_all_event_registrations()
        
        if success:
            # Log the activity with details
            db.log_staff_activity(
                staff_id, 
                'clear_all_registrations', 
                f'Cleared {count_before} event registrations'
            )
            
            return jsonify({
                'success': True, 
                'message': f'Successfully cleared {count_before} registrations',
                'count': count_before
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to clear registrations'}), 500
        
    except Exception as e:
        print(f"Error clearing registrations: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/get-registration-stats', methods=['GET'])
def get_registration_stats():
    """Get current registration statistics"""
    if not session.get('is_staff'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        registrations = db.get_event_registrations()
        
        total = len(registrations)
        pending = sum(1 for reg in registrations if reg[8] == 'pending')
        approved = sum(1 for reg in registrations if reg[8] == 'approved')
        rejected = sum(1 for reg in registrations if reg[8] == 'rejected')
        
        return jsonify({
            'success': True,
            'stats': {
                'total': total,
                'pending': pending,
                'approved': approved,
                'rejected': rejected
            }
        })
        
    except Exception as e:
        print(f"Error getting stats: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/debug-courses')
def debug_courses():
    """Debug route to check course IDs"""
    try:
        courses_from_db = db.get_courses()
        if courses_from_db:
            course_info = []
            for course in courses_from_db:
                course_info.append({
                    'id': course[0],
                    'title': course[1],
                    'description': course[2][:50] + '...' if len(course[2]) > 50 else course[2]
                })
            
            return jsonify({
                'success': True,
                'total_courses': len(course_info),
                'first_course_id': courses_from_db[0][0],
                'last_course_id': courses_from_db[-1][0],
                'starts_from_1': courses_from_db[0][0] == 1,
                'courses': course_info
            })
        else:
            return jsonify({
                'success': True,
                'message': 'No courses found in database',
                'total_courses': 0
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

# Debug routes
@app.route('/debug/projects')
def debug_projects():
    projects = db.get_all_projects()
    debug_info = []
    for project in projects:
        debug_info.append({
            'id': project[0],
            'name': project[1],
            'title': project[3],
            'url': project[6],
            'url_type': 'uploaded' if project[6] and project[6].startswith('/static/uploads/projects/') else 'external'
        })
    return jsonify({'projects': debug_info})

@app.route('/debug-upload')
def debug_upload():
    upload_dir = 'static/uploads/projects'
    if os.path.exists(upload_dir):
        files = os.listdir(upload_dir)
        return jsonify({'files': files, 'directory': upload_dir})
    else:
        return jsonify({'error': 'Upload directory does not exist', 'directory': upload_dir})

@app.route('/debug-files')
def debug_files():
    upload_dir = 'static/uploads/projects'
    if os.path.exists(upload_dir):
        files = os.listdir(upload_dir)
        return jsonify({'files': files, 'directory': upload_dir})
    else:
        return jsonify({'error': 'Upload directory does not exist', 'directory': upload_dir})

@app.route('/debug/project-stats/<int:project_id>')
def debug_project_stats(project_id):
    project = db.get_project_by_id(project_id)
    if project:
        return jsonify({
            'id': project[0],
            'title': project[3],
            'views': project[8] or 0,
            'likes': project[9] or 0,
            'shares': project[10] or 0
        })
    return jsonify({'error': 'Project not found'})

@app.route('/debug/project-structure/<int:project_id>')
def debug_project_structure(project_id):
    try:
        project = db.get_project_by_id(project_id)
        if not project:
            return jsonify({'error': 'Project not found'})
        
        project_url = project[6]
        if not project_url or not project_url.startswith('/static/uploads/projects/'):
            return jsonify({'error': 'Not an uploaded project'})
        
        # Get project directory
        if project_url.endswith('.html'):
            project_dir = os.path.dirname(project_url[1:])  # Remove leading slash
        else:
            project_dir = project_url[1:]  # Remove leading slash
        
        # List all files in project directory
        if os.path.exists(project_dir):
            files = []
            for root, dirs, file_names in os.walk(project_dir):
                for file_name in file_names:
                    file_path = os.path.join(root, file_name)
                    relative_path = os.path.relpath(file_path, project_dir)
                    files.append({
                        'name': file_name,
                        'path': relative_path,
                        'size': os.path.getsize(file_path),
                        'exists': os.path.exists(file_path)
                    })
            
            return jsonify({
                'project_id': project_id,
                'project_title': project[3],
                'project_url': project_url,
                'project_dir': project_dir,
                'files': files,
                'total_files': len(files)
            })
        else:
            return jsonify({'error': 'Project directory not found', 'path': project_dir})
            
    except Exception as e:
        return jsonify({'error': str(e)})

# Create upload directory on startup
os.makedirs('static/uploads/projects', exist_ok=True)

@app.route('/download-project-zip/<int:project_id>')
def download_project_zip(project_id):
    try:
        project = db.get_project_by_id(project_id)
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'})
        
        project_url = project[6]
        if not project_url or not project_url.startswith('/static/uploads/projects/'):
            return jsonify({'success': False, 'error': 'No downloadable files'})
        
        # Get project directory
        if project_url.endswith('.html'):
            project_dir = os.path.dirname(project_url[1:])  # Remove leading slash
        else:
            project_dir = project_url[1:]  # Remove leading slash
        
        # Create ZIP file
        import zipfile
        from io import BytesIO
        
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            if os.path.isdir(project_dir):
                for root, dirs, files in os.walk(project_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, project_dir)
                        zip_file.write(file_path, arcname)
            else:
                # Single file
                zip_file.write(project_dir, os.path.basename(project_dir))
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            as_attachment=True,
            download_name=f'project_{project_id}_{project[3].replace(" ", "_")}.zip',
            mimetype='application/zip'
        )
        
    except Exception as e:
        print(f"Error downloading project: {e}")
        return jsonify({'success': False, 'error': str(e)})

def validate_zip_project(zip_file):
    """Validate ZIP file for project upload"""
    import zipfile
    
    try:
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            
            # Check if there's at least one HTML file
            has_html = any(f.lower().endswith('.html') for f in file_list)
            if not has_html:
                return False, "ZIP file must contain at least one HTML file"
            
            # Check file sizes
            total_size = sum(zip_ref.getinfo(name).file_size for name in file_list)
            if total_size > 100 * 1024 * 1024:  # 100MB limit
                return False, "ZIP file too large (max 100MB)"
            
            # Check for dangerous files
            dangerous_extensions = ['.exe', '.bat', '.cmd', '.com', '.pif', '.scr']
            for file_name in file_list:
                if any(file_name.lower().endswith(ext) for ext in dangerous_extensions):
                    return False, f"Dangerous file type found: {file_name}"
            
            return True, "Valid ZIP file"
            
    except zipfile.BadZipFile:
        return False, "Invalid ZIP file"
    except Exception as e:
        return False, f"Error validating ZIP: {str(e)}"

@app.route('/check-staff-exists', methods=['POST'])
def check_staff_exists():
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({'error': 'Username is required'}), 400
    
    exists = db.staff_exists(username)
    return jsonify({'exists': exists})

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')
        
        # Validate required fields
        if not all([name, email, message]):
            flash('Name, email, and message are required.', 'error')
            return render_template('contact.html')
        
        # Save contact message to database
        try:
            success = db.save_contact_message(name, email, subject, message)
            if success:
                flash('Thank you for your message! We will get back to you soon.', 'success')
                return redirect(url_for('contact'))
            else:
                flash('Sorry, there was an error sending your message. Please try again.', 'error')
        except Exception as e:
            print(f"Error saving contact message: {e}")
            flash('Sorry, there was an error sending your message. Please try again.', 'error')
    
    return render_template('contact.html')

@app.route('/register-event', methods=['POST'])
def register_event():
    try:
        data = request.get_json()
        
        # Extract form data
        event_name = data.get('event_name')
        full_name = data.get('full_name')
        email = data.get('email')
        phone = data.get('phone')
        experience_level = data.get('experience_level')
        special_requirements = data.get('special_requirements')
        
        #  required fields
        if not all([event_name, full_name, email, phone]):
            return jsonify({
                'success': False, 
                'message': 'Please fill in all required fields.'
            }), 400
        
        # Save to database
        registration_id = db.insert_event_registration(
            event_name=event_name,
            full_name=full_name,
            email=email,
            phone=phone,
            experience_level=experience_level,
            special_requirements=special_requirements
        )
        
        if registration_id:
            return jsonify({
                'success': True,
                'message': 'Registration successful! You will receive a confirmation email shortly.',
                'registration_id': registration_id
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Registration failed. Please try again.'
            }), 500
            
    except Exception as e:
        print(f"Error saving event registration: {e}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while processing your registration.'
        }), 500

@app.route('/debug-db')
def debug_db():
    try:
        cursor = db.connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM event_registrations')
        count = cursor.fetchone()[0]
        cursor.close()
        return f"Database connection OK. Event registrations count: {count}"
    except Exception as e:
        return f"Database error: {str(e)}"

@app.route('/debug-db-connection')
def debug_db_connection():
    try:
        # Test SQL Server connection
        cursor = db.connection.cursor()
        cursor.execute('SELECT @@VERSION')
        version = cursor.fetchone()[0]
        cursor.close()
        
        # Test event_registrations table
        cursor = db.connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM event_registrations')
        count = cursor.fetchone()[0]
        cursor.close()
        
        return f"✅ Database OK<br>Version: {version}<br>Event registrations: {count}"
    except Exception as e:
        return f"❌ Database Error: {str(e)}"

@app.route('/debug-table-structure')
def debug_table_structure():
    try:
        cursor = db.connection.cursor()
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'event_registrations'
            ORDER BY ORDINAL_POSITION
        """)
        columns = cursor.fetchall()
        cursor.close()
        
        result = "<h3>Event Registrations Table Structure:</h3><ul>"
        for col in columns:
            result += f"<li><strong>{col[0]}</strong> - {col[1]} (Nullable: {col[2]}, Default: {col[3]})</li>"
        result += "</ul>"
        
        return result
    except Exception as e:
        return f"❌ Error checking table structure: {str(e)}"

if __name__ == '__main__':
    # Initialize database
    db.create_tables()
    db.create_projects_table()
    db.create_staff_table()
    db.create_staff_activity_table()
    db.create_event_registrations_table()  
    db.remove_duplicate_courses()
    
    app.run(debug=True)