"""
Test script for Fragment 5.1: Flashcard Generation
Tests the generate_flashcards_from_lecture function
"""

from app import app, db, generate_flashcards_from_lecture, Lecture, Concept, Flashcard
from models import User

def test_flashcard_generation():
    """Test flashcard generation on existing lectures"""
    with app.app_context():
        print("=" * 60)
        print("TESTING FRAGMENT 5.1: FLASHCARD GENERATION")
        print("=" * 60)
        
        # Find a lecture with concepts
        lecture = Lecture.query.join(Concept).first()
        
        if not lecture:
            print("❌ No lectures with concepts found!")
            print("   Upload a lecture first to test flashcard generation.")
            return
        
        print(f"\n📚 Found lecture: {lecture.title}")
        print(f"   Course: {lecture.course.name}")
        
        # Count existing concepts
        concepts = Concept.query.filter_by(lecture_id=lecture.id).all()
        print(f"   Concepts: {len(concepts)}")
        for concept in concepts:
            print(f"      • {concept.name} ({concept.difficulty})")
        
        # Count existing flashcards
        concept_ids = [c.id for c in concepts]
        existing_flashcards = Flashcard.query.filter(Flashcard.concept_id.in_(concept_ids)).count()
        print(f"   Existing flashcards: {existing_flashcards}")
        
        # Generate flashcards
        print(f"\n🎴 Generating flashcards for lecture {lecture.id}...")
        flashcards = generate_flashcards_from_lecture(lecture.id)
        
        if not flashcards:
            print("❌ Flashcard generation failed!")
            return
        
        print(f"\n✅ SUCCESS! Generated {len(flashcards)} flashcards")
        print("\nFlashcards Preview:")
        print("-" * 60)
        
        for i, f in enumerate(flashcards, 1):
            concept = Concept.query.get(f.concept_id)
            print(f"\n{i}. [{f.difficulty}] Concept: {concept.name}")
            print(f"   Front: {f.front}")
            print(f"   Back: {f.back[:100]}{'...' if len(f.back) > 100 else ''}")
        
        print("\n" + "=" * 60)
        print("FRAGMENT 5.1 TEST COMPLETE")
        print("=" * 60)

if __name__ == "__main__":
    test_flashcard_generation()