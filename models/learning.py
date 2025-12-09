# models/learning.py
from datetime import datetime, timedelta
from . import db


class Quiz(db.Model):
    """Quiz questions generated from concepts"""
    __tablename__ = 'quizzes'
    
    id = db.Column(db.Integer, primary_key=True)
    concept_id = db.Column(db.Integer, db.ForeignKey('concepts.id'), nullable=False)
    
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(500))
    option_b = db.Column(db.String(500))
    option_c = db.Column(db.String(500))
    option_d = db.Column(db.String(500))
    correct_answer = db.Column(db.String(1), nullable=False)  # 'A', 'B', 'C', or 'D'
    explanation = db.Column(db.Text)
    
    difficulty = db.Column(db.String(20), default='medium')  # 'easy', 'medium', 'hard'
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    attempts = db.relationship('QuizAttempt', backref='quiz', lazy='dynamic',
                              cascade='all, delete-orphan')
    
    def get_options_dict(self):
        """Return options as a dictionary"""
        return {
            'A': self.option_a,
            'B': self.option_b,
            'C': self.option_c,
            'D': self.option_d
        }
    
    def get_success_rate(self):
        """Calculate percentage of correct answers"""
        total = self.attempts.count()
        if total == 0:
            return None
        
        correct = self.attempts.filter_by(is_correct=True).count()
        return (correct / total) * 100
    
    def __repr__(self):
        return f'<Quiz {self.id} for Concept {self.concept_id}>'


class QuizAttempt(db.Model):
    """Record of a user's quiz attempt"""
    __tablename__ = 'quiz_attempts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    
    selected_answer = db.Column(db.String(1), nullable=False)  # 'A', 'B', 'C', or 'D'
    is_correct = db.Column(db.Boolean, nullable=False)
    time_taken = db.Column(db.Integer)  # seconds
    score = db.Column(db.Float, nullable=False)  # 0-100
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<QuizAttempt {self.id} - {"✓" if self.is_correct else "✗"}>'


class Flashcard(db.Model):
    """Flashcards for spaced repetition learning"""
    __tablename__ = 'flashcards'
    
    id = db.Column(db.Integer, primary_key=True)
    concept_id = db.Column(db.Integer, db.ForeignKey('concepts.id'), nullable=False)
    
    front = db.Column(db.Text, nullable=False)  # Question/Prompt
    back = db.Column(db.Text, nullable=False)   # Answer
    
    difficulty = db.Column(db.String(20), default='medium')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    reviews = db.relationship('FlashcardReview', backref='flashcard', lazy='dynamic',
                             cascade='all, delete-orphan')
    
    def get_next_review_date(self, user_id):
        """Get when this card should be reviewed next"""
        review = self.reviews.filter_by(user_id=user_id).order_by(
            FlashcardReview.next_review_date.desc()
        ).first()
        
        if not review:
            return datetime.utcnow()  # Review immediately if never reviewed
        
        return review.next_review_date
    
    def is_due(self, user_id):
        """Check if card is due for review"""
        next_review = self.get_next_review_date(user_id)
        return datetime.utcnow() >= next_review
    
    def __repr__(self):
        return f'<Flashcard {self.id}>'


class FlashcardReview(db.Model):
    """Record of flashcard review with spaced repetition data"""
    __tablename__ = 'flashcard_reviews'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    flashcard_id = db.Column(db.Integer, db.ForeignKey('flashcards.id'), nullable=False)
    
    # Spaced repetition algorithm data (SM-2)
    ease_factor = db.Column(db.Float, default=2.5)  # How "easy" the card is
    interval = db.Column(db.Integer, default=1)     # Days until next review
    repetitions = db.Column(db.Integer, default=0)  # Number of successful reviews
    
    quality = db.Column(db.Integer, nullable=False)  # 0-5 rating
    # 0: Complete blackout
    # 1: Incorrect, but familiar
    # 2: Incorrect, but easy to recall
    # 3: Correct, but difficult
    # 4: Correct, with hesitation
    # 5: Perfect recall
    
    next_review_date = db.Column(db.DateTime, nullable=False)
    reviewed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def calculate_next_review(self):
        """Calculate next review date using SM-2 algorithm"""
        if self.quality < 3:
            # Failed recall - reset
            self.repetitions = 0
            self.interval = 1
        else:
            # Successful recall
            if self.repetitions == 0:
                self.interval = 1
            elif self.repetitions == 1:
                self.interval = 6
            else:
                self.interval = int(self.interval * self.ease_factor)
            
            self.repetitions += 1
        
        # Update ease factor
        self.ease_factor = self.ease_factor + (0.1 - (5 - self.quality) * (0.08 + (5 - self.quality) * 0.02))
        
        # Ease factor should not be less than 1.3
        if self.ease_factor < 1.3:
            self.ease_factor = 1.3
        
        # Calculate next review date
        self.next_review_date = datetime.utcnow() + timedelta(days=self.interval)
    
    def __repr__(self):
        return f'<FlashcardReview {self.id} - Next: {self.next_review_date}>'


class Progress(db.Model):
    """Track user progress on lectures and concepts"""
    __tablename__ = 'progress'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lectures.id'), nullable=True)
    concept_id = db.Column(db.Integer, db.ForeignKey('concepts.id'), nullable=True)
    
    # Progress tracking
    viewed = db.Column(db.Boolean, default=False)
    time_spent = db.Column(db.Integer, default=0)  # seconds
    mastery_level = db.Column(db.Float, default=0.0)  # 0-100
    
    # Timestamps
    first_viewed = db.Column(db.DateTime)
    last_accessed = db.Column(db.DateTime)
    
    # Quiz/flashcard stats
    quiz_attempts = db.Column(db.Integer, default=0)
    quiz_avg_score = db.Column(db.Float, default=0.0)
    flashcard_reviews = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def update_mastery(self):
        """Recalculate mastery level based on quiz and flashcard performance"""
        # Mastery calculation formula:
        # 60% from quiz performance
        # 40% from flashcard performance
        
        quiz_component = self.quiz_avg_score * 0.6 if self.quiz_avg_score else 0
        
        # Flashcard component based on review count and ease
        if self.flashcard_reviews > 0:
            # More reviews and higher success = higher mastery
            flashcard_component = min(self.flashcard_reviews * 5, 40)  # Cap at 40
        else:
            flashcard_component = 0
        
        self.mastery_level = min(quiz_component + flashcard_component, 100)
        self.updated_at = datetime.utcnow()
    
    def mark_viewed(self):
        """Mark as viewed and update timestamps"""
        if not self.viewed:
            self.viewed = True
            self.first_viewed = datetime.utcnow()
        self.last_accessed = datetime.utcnow()
    
    def add_study_time(self, seconds):
        """Add study time and update last accessed"""
        self.time_spent += seconds
        self.last_accessed = datetime.utcnow()
    
    def get_status(self):
        """Get human-readable status"""
        if self.mastery_level >= 80:
            return 'mastered'
        elif self.mastery_level >= 60:
            return 'good'
        elif self.mastery_level >= 40:
            return 'learning'
        else:
            return 'weak'
    
    def __repr__(self):
        return f'<Progress {self.id} - Mastery: {self.mastery_level:.1f}%>'