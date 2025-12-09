# models/course.py
from datetime import datetime
from . import db


class Course(db.Model):
    """Course model - groups lectures together"""
    __tablename__ = 'courses'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    lectures = db.relationship('Lecture', backref='course', lazy='dynamic', 
                              cascade='all, delete-orphan', order_by='Lecture.order')
    
    def get_progress_summary(self):
        """Calculate overall course progress"""
        lectures = self.lectures.all()
        if not lectures:
            return {
                'total_lectures': 0,
                'completed_lectures': 0,
                'completion_percentage': 0,
                'total_concepts': 0,
                'mastered_concepts': 0
            }
        
        total_lectures = len(lectures)
        completed_lectures = sum(1 for lec in lectures if lec.is_completed())
        
        # Get all concepts across all lectures
        all_concepts = []
        for lecture in lectures:
            all_concepts.extend(lecture.concepts)
        
        total_concepts = len(all_concepts)
        mastered_concepts = sum(
            1 for concept in all_concepts 
            if concept.get_mastery_level(self.user_id) >= 80
        )
        
        return {
            'total_lectures': total_lectures,
            'completed_lectures': completed_lectures,
            'completion_percentage': (completed_lectures / total_lectures * 100) if total_lectures > 0 else 0,
            'total_concepts': total_concepts,
            'mastered_concepts': mastered_concepts
        }
    
    def get_weak_concepts(self, threshold=60):
        """Get concepts with mastery below threshold"""
        weak_concepts = []
        for lecture in self.lectures:
            for concept in lecture.concepts:
                mastery = concept.get_mastery_level(self.user_id)
                if mastery < threshold:
                    weak_concepts.append({
                        'concept': concept,
                        'mastery': mastery,
                        'lecture': lecture
                    })
        
        # Sort by mastery level (lowest first)
        weak_concepts.sort(key=lambda x: x['mastery'])
        return weak_concepts
    
    def get_strong_concepts(self, threshold=80):
        """Get concepts with mastery above threshold"""
        strong_concepts = []
        for lecture in self.lectures:
            for concept in lecture.concepts:
                mastery = concept.get_mastery_level(self.user_id)
                if mastery >= threshold:
                    strong_concepts.append({
                        'concept': concept,
                        'mastery': mastery,
                        'lecture': lecture
                    })
        
        # Sort by mastery level (highest first)
        strong_concepts.sort(key=lambda x: x['mastery'], reverse=True)
        return strong_concepts
    
    def __repr__(self):
        return f'<Course {self.name}>'