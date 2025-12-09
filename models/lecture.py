# models/lecture.py
from datetime import datetime
from . import db


class Lecture(db.Model):
    """Lecture model - individual lecture within a course"""
    __tablename__ = 'lectures'
    
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    # Audio file info
    audio_path = db.Column(db.String(500))
    original_filename = db.Column(db.String(255))
    file_size = db.Column(db.Integer)  # in bytes
    
    # Content
    transcript = db.Column(db.Text)  # Raw Whisper transcription
    summary = db.Column(db.Text)     # AI-generated summary/notes
    
    # Source tracking: 'upload' or 'recording'
    source = db.Column(db.String(20), default='upload')
    
    # Metadata
    order = db.Column(db.Integer, default=0)  # Order in course
    duration = db.Column(db.Integer)  # Audio duration in seconds
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    concepts = db.relationship('Concept', backref='lecture', lazy='dynamic', 
                              cascade='all, delete-orphan')
    progress_records = db.relationship('Progress', backref='lecture', lazy='dynamic',
                                      cascade='all, delete-orphan')
    
    def is_completed(self):
        """Check if lecture has been fully studied"""
        # A lecture is considered completed if:
        # 1. User has viewed it
        # 2. At least one quiz attempt
        # 3. Average concept mastery > 70%
        
        progress = self.progress_records.filter_by(
            user_id=self.course.user_id
        ).first()
        
        if not progress or not progress.viewed:
            return False
        
        concepts = self.concepts.all()
        if not concepts:
            return progress.viewed  # If no concepts, just check if viewed
        
        avg_mastery = sum(
            c.get_mastery_level(self.course.user_id) for c in concepts
        ) / len(concepts)
        
        return avg_mastery >= 70
    
    def get_study_time(self, user_id):
        """Get total time spent studying this lecture"""
        progress = self.progress_records.filter_by(user_id=user_id).first()
        return progress.time_spent if progress else 0
    
    def __repr__(self):
        return f'<Lecture {self.title}>'