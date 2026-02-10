# models/user.py
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from . import db


class User(UserMixin, db.Model):
    """User account model"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    courses = db.relationship('Course', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    quiz_attempts = db.relationship('QuizAttempt', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    flashcard_reviews = db.relationship('FlashcardReview', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    progress_records = db.relationship('Progress', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    # Legacy relationship (for v2.5 compatibility during migration)
    uploads = db.relationship('Upload', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def get_study_stats(self):
        """Get user's learning statistics"""
        # Import here to avoid circular imports
        from models.course import Course
        from models.lecture import Lecture
        from models.concept import Concept
        from models.learning import QuizAttempt
        
        # Total courses
        total_courses = Course.query.filter_by(user_id=self.id).count()
        
        # Total lectures across all user's courses
        total_lectures = 0
        courses = Course.query.filter_by(user_id=self.id).all()
        for course in courses:
            total_lectures += course.lectures.count()
        
        # Total concepts across all lectures
        total_concepts = 0
        for course in courses:
            for lecture in course.lectures.all():
                total_concepts += lecture.concepts.count()
        
        # Quiz attempts
        quiz_attempts = QuizAttempt.query.filter_by(user_id=self.id).count()
    
        return {
            'total_courses': total_courses,
            'total_lectures': total_lectures,
            'total_concepts': total_concepts,
            'quiz_attempts': quiz_attempts
        }
    
    def __repr__(self):
        return f'<User {self.email}>'


# Keep old Upload model for backward compatibility during migration
class Upload(db.Model):
    """Legacy upload model (v2.5) - will be migrated to Lecture"""
    __tablename__ = 'upload'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_audio = db.Column(db.String(255), nullable=False)
    is_summary = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_size = db.Column(db.Integer)
    notes_content = db.Column(db.Text)
    transcript_content = db.Column(db.Text)
    
    def __repr__(self):
        return f'<Upload {self.filename}>'