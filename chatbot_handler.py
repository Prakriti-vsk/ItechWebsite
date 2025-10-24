# chatbot_handler.py
from rapidfuzz import fuzz
import random
from data.database import Database
from recommendation_system import CourseRecommender

class ChatbotHandler:
    def __init__(self):
        self.db = Database()
        self.db.create_tables()
        self.recommender = CourseRecommender()

    def get_best_intent(self, user_message, intents, threshold=70):
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

    def handle_course_recommendation_flow(self, session, user_message):
        """Handle the multi-step course recommendation flow"""
        if session.get('course_recommendation_state') == 'awaiting_interests':
            session['course_recommendation_state'] = 'awaiting_education'
            session['user_interests'] = user_message
            response = "Great! What is your highest education level? (e.g., high school, diploma, bachelor's degree, master's, etc.)"
        
        elif session.get('course_recommendation_state') == 'awaiting_education':
            session['course_recommendation_state'] = 'awaiting_skills'
            session['user_education'] = user_message
            response = f"Thanks! Based on your {user_message}, I can suggest appropriate courses. What skills do you currently have? (e.g., basic computer knowledge, some programming experience)"
        
        elif session.get('course_recommendation_state') == 'awaiting_skills':
            session['course_recommendation_state'] = 'awaiting_qualifications'
            session['user_skills'] = user_message
            response = "Almost done! Do you have any relevant qualifications or certifications? (If none, just say 'none')"
        
        elif session.get('course_recommendation_state') == 'awaiting_qualifications':
            session['user_qualifications'] = user_message
            session['course_recommendation_state'] = None
            
            # Combine all user inputs for recommendation
            user_input = (
                f"{session.get('user_interests', '')} "
                f"{session.get('user_skills', '')} "
                f"{session.get('user_qualifications', '')}"
            )
            
            # Get recommendations with education level consideration
            recommendations = self.recommender.get_recommendations(
                user_input, 
                education_level=session.get('user_education'),
                top_n=3
            )
            
            if recommendations:
                response = f"Based on your {session.get('user_education')} education and profile, I recommend these courses:\n"
                for i, course in enumerate(recommendations, 1):
                    response += (
                        f"\n{i}. {course['title']} ({course['suitability']})\n"
                        f"   - Description: {course['description']}\n"
                        f"   - Duration: {course['duration']}\n"
                        f"   - Fee: ₹{course['fee']:,}\n"
                    )
                response += "\nWould you like more information about any of these courses?"
            else:
                response = "I couldn't find specific recommendations. Please visit our courses page or contact our advisors for more help."
        
        # Save to database
        self.db.insert_chat_history(session['session_id'], user_message, response)
        return response