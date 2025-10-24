@app.route('/save-event-registration', methods=['POST'])
def save_event_registration():
    try:
        # Get form data
        data = request.get_json() if request.is_json else request.form
        
        # Extract fields
        full_name = data.get('fullName', '').strip()
        email = data.get('email', '').strip().lower()
        phone = data.get('phone', '').strip()
        event_name = data.get('eventName', '').strip()
        experience = data.get('experience', '').strip()
        requirements = data.get('requirements', '').strip()
        
        # Validate
        if not all([full_name, email, phone, event_name]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
            
        # Save registration
        reg_id = db.insert_event_registration(
            event_name=event_name,
            full_name=full_name,
            email=email,
            phone=phone,
            experience_level=experience,
            special_requirements=requirements
        )
        
        if reg_id:
            return jsonify({
                'success': True,
                'message': 'Registration successful!',
                'registration_id': reg_id
            })
            
        return jsonify({
            'success': False,
            'message': 'Failed to save registration'
        }), 500
        
    except Exception as e:
        print(f'Registration error: {str(e)}')
        if 'already registered' in str(e).lower():
            return jsonify({
                'success': False,
                'message': str(e)
            }), 409
        return jsonify({
            'success': False,
            'message': 'Registration failed'
        }), 500