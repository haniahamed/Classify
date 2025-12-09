# models/__init__.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Import all models here for easy access
from .user import User, Upload
from .course import Course
from .lecture import Lecture
from .concept import Concept, ConceptRelationship
from .learning import Quiz, QuizAttempt, Flashcard, FlashcardReview, Progress

__all__ = [
    'db',
    'User',
    'Course',
    'Lecture',
    'Concept',
    'ConceptRelationship',
    'Quiz',
    'QuizAttempt',
    'Flashcard',
    'FlashcardReview',
    'Progress'
]