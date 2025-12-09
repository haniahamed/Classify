# models/concept.py
from datetime import datetime
from . import db


class Concept(db.Model):
    """Concept model - key concepts extracted from lectures"""
    __tablename__ = 'concepts'
    
    id = db.Column(db.Integer, primary_key=True)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lectures.id'), nullable=False)
    
    name = db.Column(db.String(200), nullable=False)
    definition = db.Column(db.Text)
    difficulty = db.Column(db.String(20))  # 'beginner', 'intermediate', 'advanced'
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    quizzes = db.relationship('Quiz', backref='concept', lazy='dynamic', 
                             cascade='all, delete-orphan')
    flashcards = db.relationship('Flashcard', backref='concept', lazy='dynamic',
                                cascade='all, delete-orphan')
    progress_records = db.relationship('Progress', backref='concept', lazy='dynamic',
                                      cascade='all, delete-orphan')
    
    # Relationships to self (prerequisites and related concepts)
    prerequisites = db.relationship(
        'ConceptRelationship',
        foreign_keys='ConceptRelationship.concept_id',
        backref='concept',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    def get_mastery_level(self, user_id):
        """Calculate mastery level for this concept (0-100)"""
        progress = self.progress_records.filter_by(user_id=user_id).first()
        
        if not progress:
            return 0
        
        return progress.mastery_level
    
    def get_quiz_performance(self, user_id):
        """Get average quiz performance for this concept"""
        from .learning import QuizAttempt
        
        attempts = QuizAttempt.query.join(Quiz).filter(
            Quiz.concept_id == self.id,
            QuizAttempt.user_id == user_id
        ).all()
        
        if not attempts:
            return None
        
        avg_score = sum(a.score for a in attempts) / len(attempts)
        return {
            'average_score': avg_score,
            'attempts': len(attempts),
            'best_score': max(a.score for a in attempts),
            'latest_score': attempts[-1].score if attempts else 0
        }
    
    def get_prerequisite_concepts(self):
        """Get all prerequisite concepts"""
        relationships = self.prerequisites.filter_by(
            relationship_type='prerequisite'
        ).all()
        
        return [rel.related_concept for rel in relationships]
    
    def get_related_concepts(self):
        """Get all related concepts"""
        relationships = self.prerequisites.filter_by(
            relationship_type='related'
        ).all()
        
        return [rel.related_concept for rel in relationships]
    
    def __repr__(self):
        return f'<Concept {self.name}>'


class ConceptRelationship(db.Model):
    """Relationships between concepts (prerequisites, related topics)"""
    __tablename__ = 'concept_relationships'
    
    id = db.Column(db.Integer, primary_key=True)
    concept_id = db.Column(db.Integer, db.ForeignKey('concepts.id'), nullable=False)
    related_concept_id = db.Column(db.Integer, db.ForeignKey('concepts.id'), nullable=False)
    relationship_type = db.Column(db.String(50), nullable=False)  # 'prerequisite', 'related', 'builds_on', 'part_of'
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to get the related concept
    related_concept = db.relationship('Concept', foreign_keys=[related_concept_id])
    
    def __repr__(self):
        return f'<ConceptRelationship {self.concept_id} -> {self.related_concept_id}>'