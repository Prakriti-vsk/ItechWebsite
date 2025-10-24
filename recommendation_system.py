# recommendation_system.py
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from data.courses import courses

class CourseRecommender:
    def __init__(self):
        self.course_data = self.prepare_course_data()
        self.df = pd.DataFrame(self.course_data)
        self.df['content'] = self.df['title'] + ' ' + self.df['description'] + ' ' + self.df['tags']
        self.tfidf = TfidfVectorizer(stop_words='english')
        self.tfidf_matrix = self.tfidf.fit_transform(self.df['content'])
        self.cosine_sim = cosine_similarity(self.tfidf_matrix, self.tfidf_matrix)

    def prepare_course_data(self):
        course_data = []
        for course in courses:
            # Create tags based on course title and description
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
            if 'digital marketing' in course['title'].lower():
                tags += " marketing SEO social media advertising "
            if 'hardware' in course['title'].lower() or 'networking' in course['title'].lower():
                tags += " IT hardware networking troubleshooting "
                
            course_data.append({
                'id': course['id'],
                'title': course['title'],
                'tags': tags,
                'description': course['description']
            })
        return course_data

    def get_recommendations(self, user_input, education_level=None, top_n=5):
        # Transform user input using the same TF-IDF vectorizer
        user_tfidf = self.tfidf.transform([user_input])
        
        # Compute cosine similarity between user input and all courses
        sim_scores = cosine_similarity(user_tfidf, self.tfidf_matrix)
        
        # Get the similarity scores
        sim_scores = sim_scores[0]
        
        # If education level is provided, boost scores for matching courses
        if education_level:
            education_keywords = {
                'high school': ['highschool', '10th', '12th', 'school', 'beginner'],
                'diploma': ['diploma', 'after10th', 'after12th'],
                'bachelor': ['graduate', 'bachelor', 'degree'],
                'master': ['postgraduate', 'master'],
                'phd': ['phd', 'doctorate', 'research']
            }
            
            for level, keywords in education_keywords.items():
                if level in education_level.lower():
                    for idx in range(len(self.df)):
                        course_tags = self.df.iloc[idx]['tags']
                        if any(keyword in course_tags for keyword in keywords):
                            sim_scores[idx] *= 1.5  # Boost score for matching education level
        
        # Get the top N most similar courses
        top_indices = np.argsort(sim_scores)[-top_n:][::-1]
        
        # Return the top N most similar courses with details
        recommendations = []
        for idx in top_indices:
            course = next((c for c in courses if c['id'] == self.df.iloc[idx]['id']), None)
            if course:
                recommendations.append({
                    'id': course['id'],
                    'title': course['title'],
                    'description': course['description'],
                    'duration': course['duration'],
                    'fee': course['fee'],
                    'suitability': "Great fit" if sim_scores[idx] > 0.5 else "Good option"
                })
        return recommendations