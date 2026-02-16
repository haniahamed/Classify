# app.py - Classify v3 Main Application
from flask import Flask, render_template, request, send_file, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
import os
from datetime import datetime
from dotenv import load_dotenv

# Import models from the new models package
from models import db, User, Upload, Course, Lecture, Concept, Quiz, Flashcard, Progress

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///classify.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# OpenAI setup
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise ValueError("❌ OPENAI_API_KEY not found!")
client = OpenAI(api_key=api_key)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def extract_concepts_from_lecture(lecture_id, transcript_text):
    """Extract key concepts from lecture transcript using GPT-4"""
    print(f"🧠 Extracting concepts from lecture {lecture_id}...")
    
    concept_prompt = f"""Analyze this lecture transcript and extract the key concepts.
For each concept, provide:
1. Name (concise, 2-5 words)
2. Definition (1-2 sentences)
3. Difficulty level (beginner/intermediate/advanced)

Return ONLY a JSON array:
[
    {{
        "name": "Concept Name",
        "definition": "Brief definition",
        "difficulty": "beginner"
    }}
]

Extract 3-7 most important concepts.

Transcript:
{transcript_text}
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert at identifying key concepts. Return ONLY valid JSON."},
                {"role": "user", "content": concept_prompt}
            ],
            temperature=0.3
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Remove markdown if present
        if response_text.startswith("```"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        
        import json
        concepts_data = json.loads(response_text)
        
        saved_concepts = []
        for concept_data in concepts_data:
            concept = Concept(
                lecture_id=lecture_id,
                name=concept_data.get('name', 'Untitled'),
                definition=concept_data.get('definition', ''),
                difficulty=concept_data.get('difficulty', 'intermediate')
            )
            db.session.add(concept)
            saved_concepts.append(concept)
        
        db.session.commit()
        
        print(f"✅ Extracted {len(saved_concepts)} concepts")
        return saved_concepts
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return []

def build_concept_relationships(course_id):
    """
    Analyze all concepts in a course and identify relationships between them.
    Creates prerequisite, related, and builds_on relationships.
    """
    from models import ConceptRelationship
    
    print(f"🔗 Building concept relationships for course {course_id}...")
    
    # Get all concepts for this course (through lectures)
    course = Course.query.get(course_id)
    if not course:
        print("❌ Course not found")
        return []
    
    # Get all lectures in the course
    lectures = course.lectures.all()
    if len(lectures) < 2:
        print("⏭️ Need at least 2 lectures to build relationships. Skipping.")
        return []
    
    # Collect all concepts from all lectures
    all_concepts = []
    for lecture in lectures:
        lecture_concepts = Concept.query.filter_by(lecture_id=lecture.id).all()
        all_concepts.extend(lecture_concepts)
    
    if len(all_concepts) < 2:
        print("⏭️ Need at least 2 concepts to build relationships. Skipping.")
        return []
    
    print(f"   Found {len(all_concepts)} concepts across {len(lectures)} lectures")
    
    # Prepare concept data for GPT
    concepts_text = ""
    for i, concept in enumerate(all_concepts, 1):
        concepts_text += f"{i}. {concept.name} (ID: {concept.id})\n"
        concepts_text += f"   Definition: {concept.definition}\n"
        concepts_text += f"   From Lecture: {concept.lecture.title}\n\n"
    
    # GPT prompt for relationship extraction
    relationship_prompt = f"""Analyze these concepts from a course and identify relationships between them.

Concepts:
{concepts_text}

For each meaningful relationship, specify:
1. concept_id: The ID of the first concept
2. related_concept_id: The ID of the second concept
3. relationship_type: One of these:
   - "prerequisite": concept_id must be learned before related_concept_id
   - "related": concepts are connected/similar topics
   - "builds_on": related_concept_id expands/deepens concept_id
   - "part_of": concept_id is a component of related_concept_id

Return ONLY a JSON array:
[
    {{
        "concept_id": 1,
        "related_concept_id": 3,
        "relationship_type": "prerequisite"
    }}
]

Rules:
- Only create relationships where there's a clear, meaningful connection
- Don't relate every concept to every other concept
- Focus on the strongest 3-8 relationships
- If no meaningful relationships exist, return an empty array []

Return ONLY valid JSON, no explanations.
"""
    
    try:
        # Call GPT-4o-mini
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are an expert at identifying relationships between educational concepts. Return ONLY valid JSON."
                },
                {"role": "user", "content": relationship_prompt}
            ],
            temperature=0.3
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Remove markdown if present
        if response_text.startswith("```"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        
        # Parse JSON
        import json
        relationships_data = json.loads(response_text)
        
        if not isinstance(relationships_data, list):
            print(f"⚠️ Expected list, got {type(relationships_data)}")
            return []
        
        # Delete existing relationships for this course (to avoid duplicates)
        # Get concept IDs for this course
        concept_ids = [c.id for c in all_concepts]
        ConceptRelationship.query.filter(
            ConceptRelationship.concept_id.in_(concept_ids)
        ).delete(synchronize_session=False)
        
        # Save relationships to database
        saved_relationships = []
        for rel_data in relationships_data:
            # Validate concept IDs exist
            concept_id = rel_data.get('concept_id')
            related_id = rel_data.get('related_concept_id')
            
            if not concept_id or not related_id:
                continue
            
            # Check both concepts exist and belong to this course
            if concept_id not in concept_ids or related_id not in concept_ids:
                print(f"⚠️ Skipping invalid relationship: {concept_id} -> {related_id}")
                continue
            
            relationship = ConceptRelationship(
                concept_id=concept_id,
                related_concept_id=related_id,
                relationship_type=rel_data.get('relationship_type', 'related')
            )
            db.session.add(relationship)
            saved_relationships.append(relationship)
        
        db.session.commit()
        
        print(f"✅ Created {len(saved_relationships)} concept relationships:")
        for rel in saved_relationships:
            concept = Concept.query.get(rel.concept_id)
            related = Concept.query.get(rel.related_concept_id)
            print(f"   {concept.name} --[{rel.relationship_type}]--> {related.name}")
        
        return saved_relationships
    
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error: {e}")
        print(f"Response was: {response_text[:300]}")
        return []
    except Exception as e:
        print(f"❌ Error building relationships: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def generate_quiz_from_lecture(lecture_id):
    """
    Generate quiz questions from lecture concepts using GPT-4.
    Creates 5-7 multiple choice questions linked to concepts.
    """
    print(f"📝 Generating quiz for lecture {lecture_id}...")
    
    # Get the lecture
    lecture = Lecture.query.get(lecture_id)
    if not lecture:
        print("❌ Lecture not found")
        return []
    
    # Get all concepts for this lecture
    concepts = Concept.query.filter_by(lecture_id=lecture_id).all()
    
    if not concepts:
        print("⚠️ No concepts found. Cannot generate quiz without concepts.")
        return []
    
    print(f"   Found {len(concepts)} concepts to generate questions from")
    
    # Prepare concept data for GPT
    concepts_text = ""
    for i, concept in enumerate(concepts, 1):
        concepts_text += f"{i}. {concept.name} (ID: {concept.id})\n"
        concepts_text += f"   Definition: {concept.definition}\n"
        concepts_text += f"   Difficulty: {concept.difficulty}\n\n"
    
    # Also include lecture content for context (OPTIMIZED: reduced from 2000 to 1000 chars)
    lecture_context = lecture.summary if lecture.summary else lecture.transcript
    if len(lecture_context) > 1000:
        lecture_context = lecture_context[:1000] + "..."
    
    # GPT prompt for quiz generation (OPTIMIZED: shorter, more direct)
    quiz_prompt = f"""Generate {len(concepts)} MCQ questions from these concepts.

Concepts:
{concepts_text}

Context: {lecture_context}

Return JSON array only:
[{{"concept_id": 1, "question": "...", "option_a": "...", "option_b": "...", "option_c": "...", "option_d": "...", "correct_answer": "B", "explanation": "...", "difficulty": "intermediate"}}]"""
    
    try:
        # Call GPT-4o-mini (OPTIMIZED: lower temperature, max_tokens limit)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Expert educator. Return ONLY valid JSON array."
                },
                {"role": "user", "content": quiz_prompt}
            ],
            temperature=0.3,  # OPTIMIZED: Lower for faster, more consistent responses
            max_tokens=2000,  # OPTIMIZED: Limit response length
            timeout=30  # OPTIMIZED: 30 second timeout
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Remove markdown if present
        if response_text.startswith("```"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        
        # Parse JSON
        import json
        questions_data = json.loads(response_text)
        
        if not isinstance(questions_data, list):
            print(f"⚠️ Expected list, got {type(questions_data)}")
            return []
        
        # Delete existing quiz questions for this lecture's concepts (to avoid duplicates)
        concept_ids = [c.id for c in concepts]
        Quiz.query.filter(Quiz.concept_id.in_(concept_ids)).delete(synchronize_session=False)
        
        # Save questions to database
        saved_questions = []
        for q_data in questions_data:
            # Validate concept_id exists
            concept_id = q_data.get('concept_id')
            if not concept_id or concept_id not in concept_ids:
                print(f"⚠️ Skipping question with invalid concept_id: {concept_id}")
                continue
            
            quiz = Quiz(
                concept_id=concept_id,
                question=q_data.get('question', 'Question not provided'),
                option_a=q_data.get('option_a', ''),
                option_b=q_data.get('option_b', ''),
                option_c=q_data.get('option_c', ''),
                option_d=q_data.get('option_d', ''),
                correct_answer=q_data.get('correct_answer', 'A').upper(),
                explanation=q_data.get('explanation', ''),
                difficulty=q_data.get('difficulty', 'medium')
            )
            db.session.add(quiz)
            saved_questions.append(quiz)
        
        db.session.commit()
        
        print(f"✅ Generated {len(saved_questions)} quiz questions")
        for i, q in enumerate(saved_questions, 1):
            concept_name = next((c.name for c in concepts if c.id == q.concept_id), 'Unknown')
            print(f"   {i}. [{q.difficulty}] {concept_name}: {q.question[:60]}...")
        
        return saved_questions
    
    except Exception as e:
        print(f"❌ Error generating quiz: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def generate_course_quiz(course_id, questions_per_lecture=2):
    """
    Generate a comprehensive quiz for entire course.
    Pulls questions from all lectures in the course.
    
    Args:
        course_id: The course ID
        questions_per_lecture: Number of questions per lecture (default: 2)
    
    Returns:
        List of Quiz objects
    """
    print(f"📝 Generating course-wide quiz for course {course_id}...")
    
    # Get the course
    course = Course.query.get(course_id)
    if not course:
        print("❌ Course not found")
        return []
    
    # Get all lectures in the course
    lectures = course.lectures.all()
    
    if not lectures:
        print("⚠️ No lectures found in course")
        return []
    
    print(f"   Found {len(lectures)} lectures")
    
    # Collect all concepts from all lectures
    all_concepts = []
    for lecture in lectures:
        lecture_concepts = Concept.query.filter_by(lecture_id=lecture.id).all()
        all_concepts.extend(lecture_concepts)
    
    if not all_concepts:
        print("⚠️ No concepts found in course lectures")
        return []
    
    print(f"   Found {len(all_concepts)} total concepts across all lectures")
    
    # Smart selection: Pick top concepts per lecture based on difficulty
    # Priority: intermediate > advanced > beginner (for better assessment)
    difficulty_priority = {'intermediate': 1, 'advanced': 2, 'beginner': 3}
    
    selected_concepts = []
    for lecture in lectures:
        lecture_concepts = [c for c in all_concepts if c.lecture_id == lecture.id]
        
        if not lecture_concepts:
            continue
        
        # Sort by difficulty priority and take top N
        sorted_concepts = sorted(
            lecture_concepts, 
            key=lambda c: difficulty_priority.get(c.difficulty, 99)
        )
        
        selected_concepts.extend(sorted_concepts[:questions_per_lecture])
    
    if not selected_concepts:
        print("⚠️ No concepts selected for quiz")
        return []
    
    print(f"   Selected {len(selected_concepts)} concepts for course quiz")
    
    # Check if quiz already exists for these concepts
    concept_ids = [c.id for c in selected_concepts]
    existing_quiz = Quiz.query.filter(Quiz.concept_id.in_(concept_ids)).first()
    
    if existing_quiz:
        print(f"   ✅ Course quiz already exists with {len(concept_ids)} questions")
        # Return all existing questions
        return Quiz.query.filter(Quiz.concept_id.in_(concept_ids)).all()
    
    # Generate quiz questions for selected concepts
    # Prepare concept data
    concepts_text = ""
    for i, concept in enumerate(selected_concepts, 1):
        lecture = Lecture.query.get(concept.lecture_id)
        concepts_text += f"{i}. {concept.name} (ID: {concept.id}, Lecture: {lecture.title})\n"
        concepts_text += f"   Definition: {concept.definition}\n"
        concepts_text += f"   Difficulty: {concept.difficulty}\n\n"
    
    # GPT prompt for course quiz
    quiz_prompt = f"""Generate {len(selected_concepts)} MCQ questions for a course assessment.

Course: {course.name}
Concepts from multiple lectures:
{concepts_text}

Return JSON array only:
[{{"concept_id": 1, "question": "...", "option_a": "...", "option_b": "...", "option_c": "...", "option_d": "...", "correct_answer": "B", "explanation": "...", "difficulty": "intermediate"}}]"""
    
    try:
        # Call GPT-4o-mini
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Expert educator. Return ONLY valid JSON array."
                },
                {"role": "user", "content": quiz_prompt}
            ],
            temperature=0.3,
            max_tokens=3000,  # More tokens for course quiz
            timeout=45  # Longer timeout for course quiz
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Remove markdown if present
        if response_text.startswith("```"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        
        # Parse JSON
        import json
        questions_data = json.loads(response_text)
        
        if not isinstance(questions_data, list):
            print(f"⚠️ Expected list, got {type(questions_data)}")
            return []
        
        # Save questions to database
        saved_questions = []
        for q_data in questions_data:
            # Validate concept_id exists
            concept_id = q_data.get('concept_id')
            if not concept_id or concept_id not in concept_ids:
                print(f"⚠️ Skipping question with invalid concept_id: {concept_id}")
                continue
            
            quiz = Quiz(
                concept_id=concept_id,
                question=q_data.get('question', 'Question not provided'),
                option_a=q_data.get('option_a', ''),
                option_b=q_data.get('option_b', ''),
                option_c=q_data.get('option_c', ''),
                option_d=q_data.get('option_d', ''),
                correct_answer=q_data.get('correct_answer', 'A').upper(),
                explanation=q_data.get('explanation', ''),
                difficulty=q_data.get('difficulty', 'medium')
            )
            db.session.add(quiz)
            saved_questions.append(quiz)
        
        db.session.commit()
        
        print(f"✅ Generated {len(saved_questions)} course quiz questions")
        for i, q in enumerate(saved_questions, 1):
            concept = Concept.query.get(q.concept_id)
            lecture = Lecture.query.get(concept.lecture_id)
            print(f"   {i}. [{q.difficulty}] {lecture.title}: {q.question[:60]}...")
        
        return saved_questions
    
    except Exception as e:
        print(f"❌ Error generating course quiz: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


# ==================== USER LOADER ====================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==================== ROUTES ====================

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template("landing.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == "POST":
        email = request.form.get("email")
        name = request.form.get("name")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        # Validation
        if not email or not name or not password:
            flash("All fields are required!", "error")
            return render_template("signup.html")

        if password != confirm_password:
            flash("Passwords do not match!", "error")
            return render_template("signup.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters!", "error")
            return render_template("signup.html")

        # Check if user already exists
        if User.query.filter_by(email=email).first():
            flash("Email already registered!", "error")
            return render_template("signup.html")

        # Create new user
        user = User(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for('login'))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f"Welcome back, {user.name}!", "success")

            # Redirect to next page or dashboard
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash("Invalid email or password!", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))


@app.route("/dashboard")
@login_required
def dashboard():
    """Main dashboard - shows courses and study stats"""
    # Get user's courses
    courses = Course.query.filter_by(user_id=current_user.id).order_by(Course.created_at.desc()).all()
    
    # Get legacy uploads (v2.5 compatibility)
    uploads = Upload.query.filter_by(user_id=current_user.id).order_by(Upload.created_at.desc()).all()
    
    # Get study stats
    stats = current_user.get_study_stats()
    
    return render_template("dashboard.html", 
                          courses=courses, 
                          uploads=uploads,
                          stats=stats)


# ==================== COURSE ROUTES (NEW FOR V3) ====================

@app.route("/courses/create", methods=["GET", "POST"])
@login_required
def create_course():
    """Create a new course"""
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description", "")
        
        if not name:
            flash("Course name is required!", "error")
            return redirect(url_for('create_course'))
        
        course = Course(
            user_id=current_user.id,
            name=name,
            description=description
        )
        db.session.add(course)
        db.session.commit()
        
        flash(f"Course '{name}' created successfully!", "success")
        return redirect(url_for('view_course', course_id=course.id))
    
    return render_template("create_course.html")


@app.route("/courses/<int:course_id>")
@login_required
def view_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    if course.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))
    
    # Get progress summary
    progress_summary = course.get_progress_summary()
    weak_concepts = course.get_weak_concepts(threshold=60)
    strong_concepts = course.get_strong_concepts(threshold=80)
    
    # Get all concepts for this course
    from models import ConceptRelationship
    all_concepts = []
    for lecture in course.lectures.all():
        lecture_concepts = Concept.query.filter_by(lecture_id=lecture.id).all()
        all_concepts.extend(lecture_concepts)
    
    # Get concept relationships
    concept_ids = [c.id for c in all_concepts]
    relationships = ConceptRelationship.query.filter(
        ConceptRelationship.concept_id.in_(concept_ids)
    ).all() if concept_ids else []
    
    # Convert to JSON-serializable format
    concepts_json = []
    for c in all_concepts:
        concepts_json.append({
            'id': c.id,
            'name': c.name,
            'definition': c.definition,
            'difficulty': c.difficulty,
            'lecture': {
                'id': c.lecture.id,
                'title': c.lecture.title
            }
        })
    
    relationships_json = []
    for r in relationships:
        relationships_json.append({
            'concept_id': r.concept_id,
            'related_concept_id': r.related_concept_id,
            'relationship_type': r.relationship_type
        })
    
    return render_template("view_course.html", 
                          course=course,
                          progress=progress_summary,
                          weak_concepts=weak_concepts[:5],
                          strong_concepts=strong_concepts[:5],
                          all_concepts=all_concepts,
                          concepts_json=concepts_json,
                          relationships_json=relationships_json)


@app.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@login_required
def edit_course(course_id):
    """Edit course details"""
    course = Course.query.get_or_404(course_id)
    
    # Check ownership
    if course.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        course.name = request.form.get("name")
        course.description = request.form.get("description", "")
        db.session.commit()
        
        flash("Course updated successfully!", "success")
        return redirect(url_for('view_course', course_id=course.id))
    
    return render_template("edit_course.html", course=course)


@app.route("/courses/<int:course_id>/delete", methods=["POST"])
@login_required
def delete_course(course_id):
    """Delete a course and all its lectures"""
    course = Course.query.get_or_404(course_id)
    
    # Check ownership
    if course.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))
    
    course_name = course.name
    db.session.delete(course)
    db.session.commit()
    
    flash(f"Course '{course_name}' deleted successfully!", "success")
    return redirect(url_for('dashboard'))

@app.route("/courses/<int:course_id>/upload-lecture", methods=["GET", "POST"])
@login_required
def upload_lecture(course_id):
    """Upload a new lecture to a specific course"""
    course = Course.query.get_or_404(course_id)
    
    # Check ownership
    if course.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        try:
            # Check if audio file exists
            if "audio" not in request.files:
                return {"error": "No audio file in request"}, 400

            file = request.files["audio"]
            if file.filename == "":
                return {"error": "No file selected"}, 400

            # Get form data
            lecture_title = request.form.get("title", file.filename)
            summarize = request.form.get("summarize") == "on"
            
            print(f"📤 Uploading lecture to course {course.name}")
            print(f"   Title: {lecture_title}")
            print(f"   Summarize: {summarize}")

            # Save uploaded file
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)
            file_size = os.path.getsize(filepath)

            # Step 1: Transcribe audio
            print("🎙️ Transcribing audio...")
            with open(filepath, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )

            transcript_text = transcription if isinstance(transcription, str) else transcription.text
            print(f"✅ Transcription complete: {len(transcript_text)} characters")

            # Step 2: Generate summary or use raw transcript
            if summarize:
                print("🤖 Generating AI summary...")
                summary_prompt = (
                    "Summarize the following lecture into clear, structured notes. "
                    "Use headings, bullet points, and organize the content logically:\n\n"
                    f"{transcript_text}"
                )
                chat_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": summary_prompt}]
                )
                summary = chat_response.choices[0].message.content
                print("✅ Summary generated")
            else:
                summary = transcript_text
                print("📄 Using raw transcript")

            # Step 3: Create Lecture in database
            lecture = Lecture(
                course_id=course_id,
                title=lecture_title,
                audio_path=filepath,
                original_filename=file.filename,
                file_size=file_size,
                transcript=transcript_text,
                summary=summary,
                source='upload'
            )
            db.session.add(lecture)
            db.session.commit()
            
            print(f"✅ Lecture created: ID {lecture.id}")

            # Step 4: Create initial progress record
            progress = Progress(
                user_id=current_user.id,
                lecture_id=lecture.id,
                viewed=False
            )
            db.session.add(progress)
            db.session.commit()

            # Step 4.5: Extract concepts from transcript
            extract_concepts_from_lecture(lecture.id, transcript_text)

            # Step 4.6: Build concept relationships
            build_concept_relationships(course_id)
            
            # Step 4.7: Generate quiz questions from concepts
            # OPTIMIZATION: Skip quiz generation during upload
            # Quiz will auto-generate when user clicks "Take Quiz" button
            # This makes upload 2-3 seconds faster!
            # Uncomment line below to generate quiz during upload:
            # generate_quiz_from_lecture(lecture.id)

            # Step 5: Clean up audio file
            try:
                os.remove(filepath)
                print("🗑️ Temporary audio file removed")
            except:
                pass

            # Return JSON response for AJAX
            return {
                "success": True,
                "lecture_id": lecture.id,
                "course_id": course_id,
                "title": lecture_title,
                "created_at": lecture.created_at.strftime('%b %d, %Y')
            }

        except Exception as e:
            print(f"❌ Error uploading lecture: {str(e)}")
            return {"error": str(e)}, 500
    
    # GET request - show upload form
    return render_template("upload_lecture.html", course=course)



# ==================== LECTURE ROUTES (UPDATED FOR V3) ====================

@app.route("/upload", methods=["POST"])
@login_required
def upload_audio():
    """Upload audio and create lecture (v3) or upload (v2.5 compatibility)"""
    try:
        if "audio" not in request.files:
            return {"error": "No audio file in request"}, 400

        file = request.files["audio"]
        if file.filename == "":
            return {"error": "No file selected"}, 400

        # Get form data
        summarize = request.form.get("summarize") == "on"
        course_id = request.form.get("course_id")  # NEW: Optional course assignment
        lecture_title = request.form.get("title", file.filename)  # NEW: Lecture title
        
        print(f"User: {current_user.email} | Summarize: {summarize} | Course: {course_id}")

        # Save uploaded file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        file_size = os.path.getsize(filepath)

        # Step 1: Transcribe
        print("Transcribing audio...")
        with open(filepath, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )

        transcript_text = transcription if isinstance(transcription, str) else transcription.text
        print(f"Transcription complete: {len(transcript_text)} characters")

        # Step 2: Summarize or use raw
        if summarize:
            print("Generating AI summary...")
            summary_prompt = (
                "Summarize the following lecture into clear, structured notes. "
                "Use headings, bullet points, and organize the content logically:\n\n"
                f"{transcript_text}"
            )
            chat_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": summary_prompt}]
            )
            notes = chat_response.choices[0].message.content
            pdf_prefix = "Classify_Summary"
        else:
            notes = transcript_text
            pdf_prefix = "Classify_Transcript"

        # Step 3: Generate PDF
        pdf_filename = f"{pdf_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = os.path.join(UPLOAD_FOLDER, pdf_filename)

        c = canvas.Canvas(pdf_path, pagesize=letter)
        width, height = letter
        left_margin = 40
        right_margin = width - 40
        max_width = right_margin - left_margin
        top_margin = height - 50
        bottom_margin = 50
        line_height = 14
        y_position = top_margin
        c.setFont("Helvetica", 12)

        for line in notes.split("\n"):
            if not line.strip():
                y_position -= line_height
                if y_position < bottom_margin:
                    c.showPage()
                    c.setFont("Helvetica", 12)
                    y_position = top_margin
                continue

            wrapped_lines = simpleSplit(line, "Helvetica", 12, max_width)
            for wrapped_line in wrapped_lines:
                if y_position < bottom_margin:
                    c.showPage()
                    c.setFont("Helvetica", 12)
                    y_position = top_margin
                c.drawString(left_margin, y_position, wrapped_line)
                y_position -= line_height

        c.save()
        print(f"PDF created: {pdf_filename}")

        # Step 4: Save to database (v3 if course_id, v2.5 if not)
        if course_id:
            # NEW V3: Create Lecture
            lecture = Lecture(
                course_id=course_id,
                title=lecture_title,
                audio_path=filepath,
                original_filename=file.filename,
                file_size=file_size,
                transcript=transcript_text,
                summary=notes,
                source='upload'
            )
            db.session.add(lecture)
            db.session.commit()
            
            # Create initial progress record
            progress = Progress(
                user_id=current_user.id,
                lecture_id=lecture.id,
                viewed=False
            )
            db.session.add(progress)
            db.session.commit()
            
            record_type = "lecture"
            record_id = lecture.id
        else:
            # OLD V2.5: Create Upload (backward compatibility)
            upload = Upload(
                user_id=current_user.id,
                filename=pdf_filename,
                original_audio=file.filename,
                is_summary=summarize,
                file_size=file_size,
                notes_content=notes,
                transcript_content=transcript_text
            )
            db.session.add(upload)
            db.session.commit()
            
            record_type = "upload"
            record_id = upload.id

        # Clean up audio file
        try:
            os.remove(filepath)
        except:
            pass

        # Return JSON response
        return {
            "success": True,
            "type": record_type,
            "id": record_id,
            "filename": file.filename,
            "is_summary": summarize,
            "created_at": datetime.utcnow().strftime('%b %d, %Y')
        }

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return {"error": str(e)}, 500


@app.route("/lectures/<int:lecture_id>")
@login_required
def view_lecture(lecture_id):
    """View lecture notes and progress"""
    lecture = Lecture.query.get_or_404(lecture_id)
    
    # Check ownership
    if lecture.course.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))
    
    # Get or create progress record
    progress = Progress.query.filter_by(
        user_id=current_user.id,
        lecture_id=lecture.id
    ).first()
    
    if not progress:
        progress = Progress(
            user_id=current_user.id,
            lecture_id=lecture.id,
            viewed=False
        )
        db.session.add(progress)
        db.session.commit()
    
    # Mark as viewed
    progress.mark_viewed()
    db.session.commit()
    
    return render_template("view_lecture.html", lecture=lecture, progress=progress)


@app.route("/lectures/<int:lecture_id>/generate-quiz", methods=["POST"])
@login_required
def generate_lecture_quiz(lecture_id):
    """Manually generate or regenerate quiz for a lecture"""
    lecture = Lecture.query.get_or_404(lecture_id)
    
    # Check ownership
    if lecture.course.user_id != current_user.id:
        return {"error": "Access denied"}, 403
    
    # Generate quiz
    questions = generate_quiz_from_lecture(lecture_id)
    
    if questions:
        flash(f"✅ Successfully generated {len(questions)} quiz questions!", "success")
        return {"success": True, "count": len(questions)}
    else:
        flash("⚠️ Could not generate quiz. Make sure the lecture has concepts.", "error")
        return {"error": "Quiz generation failed"}, 500


@app.route("/lectures/<int:lecture_id>/quiz")
@login_required
def take_quiz(lecture_id):
    """Display quiz questions for a lecture"""
    lecture = Lecture.query.get_or_404(lecture_id)
    
    # Check ownership
    if lecture.course.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))
    
    # Get all concepts for this lecture
    concepts = Concept.query.filter_by(lecture_id=lecture_id).all()
    
    if not concepts:
        flash("No concepts found for this lecture. Upload a lecture with content first.", "error")
        return redirect(url_for('view_lecture', lecture_id=lecture_id))
    
    # Get all quiz questions for these concepts
    concept_ids = [c.id for c in concepts]
    questions = Quiz.query.filter(Quiz.concept_id.in_(concept_ids)).all()
    
    if not questions:
        flash("No quiz questions available. Generating quiz now...", "info")
        generate_quiz_from_lecture(lecture_id)
        # Reload questions
        questions = Quiz.query.filter(Quiz.concept_id.in_(concept_ids)).all()
    
    if not questions:
        flash("Could not generate quiz questions. Please try again.", "error")
        return redirect(url_for('view_lecture', lecture_id=lecture_id))
    
    # Shuffle questions for variety
    import random
    questions_list = list(questions)
    random.shuffle(questions_list)
    
    return render_template("take_quiz.html", lecture=lecture, questions=questions_list)


@app.route("/lectures/<int:lecture_id>/quiz/submit", methods=["POST"])
@login_required
def submit_quiz(lecture_id):
    """Grade quiz and save attempt"""
    from models import QuizAttempt
    
    lecture = Lecture.query.get_or_404(lecture_id)
    
    # Check ownership
    if lecture.course.user_id != current_user.id:
        return {"error": "Access denied"}, 403
    
    # Get form data
    answers = request.form.to_dict()
    time_taken = int(request.form.get('time_taken', 0))
    
    # Get all questions
    concept_ids = [c.id for c in Concept.query.filter_by(lecture_id=lecture_id).all()]
    questions = Quiz.query.filter(Quiz.concept_id.in_(concept_ids)).all()
    
    # Grade each question
    results = []
    correct_count = 0
    
    for question in questions:
        question_key = f"question_{question.id}"
        selected_answer = answers.get(question_key, '').upper()
        is_correct = (selected_answer == question.correct_answer)
        
        if is_correct:
            correct_count += 1
        
        # Save attempt
        attempt = QuizAttempt(
            user_id=current_user.id,
            quiz_id=question.id,
            selected_answer=selected_answer if selected_answer else 'X',
            is_correct=is_correct,
            time_taken=time_taken // len(questions) if len(questions) > 0 else 0,
            score=100 if is_correct else 0
        )
        db.session.add(attempt)
        
        results.append({
            'question': question,
            'selected': selected_answer,
            'correct': question.correct_answer,
            'is_correct': is_correct,
            'explanation': question.explanation
        })
    
    db.session.commit()
    
    # Calculate overall score
    score = (correct_count / len(questions) * 100) if len(questions) > 0 else 0
    
    # Update progress
    progress = Progress.query.filter_by(
        user_id=current_user.id,
        lecture_id=lecture_id
    ).first()
    
    if progress:
        progress.quiz_attempts += 1
        # Update average score
        if progress.quiz_avg_score == 0:
            progress.quiz_avg_score = score
        else:
            progress.quiz_avg_score = (progress.quiz_avg_score + score) / 2
        progress.update_mastery()
        db.session.commit()
    
    return render_template("quiz_results.html", 
                         lecture=lecture,
                         results=results,
                         score=score,
                         correct_count=correct_count,
                         total_questions=len(questions),
                         time_taken=time_taken)


@app.route("/courses/<int:course_id>/quiz")
@login_required
def take_course_quiz(course_id):
    """Display quiz questions for entire course (all lectures)"""
    course = Course.query.get_or_404(course_id)
    
    # Check ownership
    if course.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))
    
    # Get all lectures in this course
    lectures = course.lectures.all()
    
    if not lectures:
        flash("No lectures found in this course.", "error")
        return redirect(url_for('view_course', course_id=course_id))
    
    # Get all concepts from all lectures
    all_concepts = []
    for lecture in lectures:
        lecture_concepts = Concept.query.filter_by(lecture_id=lecture.id).all()
        all_concepts.extend(lecture_concepts)
    
    if not all_concepts:
        flash("No concepts found in this course. Upload lectures with content first.", "error")
        return redirect(url_for('view_course', course_id=course_id))
    
    # Get all quiz questions for these concepts
    concept_ids = [c.id for c in all_concepts]
    all_questions = Quiz.query.filter(Quiz.concept_id.in_(concept_ids)).all()
    
    # If no questions exist, generate for all lectures
    if not all_questions:
        flash("Generating quiz for all lectures... This may take a moment.", "info")
        for lecture in lectures:
            lecture_concepts = Concept.query.filter_by(lecture_id=lecture.id).all()
            if lecture_concepts:
                generate_quiz_from_lecture(lecture.id)
        
        # Reload questions
        all_questions = Quiz.query.filter(Quiz.concept_id.in_(concept_ids)).all()
    
    if not all_questions:
        flash("Could not generate quiz questions. Please try again.", "error")
        return redirect(url_for('view_course', course_id=course_id))
    
    # Select 10-15 questions (or 2-3 per lecture, whichever is less)
    import random
    questions_per_lecture = max(2, min(3, len(all_questions) // len(lectures)))
    
    selected_questions = []
    for lecture in lectures:
        lecture_concept_ids = [c.id for c in Concept.query.filter_by(lecture_id=lecture.id).all()]
        lecture_questions = [q for q in all_questions if q.concept_id in lecture_concept_ids]
        
        if lecture_questions:
            # Take 2-3 questions per lecture
            sample_size = min(questions_per_lecture, len(lecture_questions))
            selected_questions.extend(random.sample(lecture_questions, sample_size))
    
    # Shuffle final question set
    random.shuffle(selected_questions)
    
    return render_template("take_quiz.html", 
                         course=course,
                         lecture=None,  # Signal this is a course quiz
                         questions=selected_questions,
                         is_course_quiz=True)


@app.route("/courses/<int:course_id>/quiz/submit", methods=["POST"])
@login_required
def submit_course_quiz(course_id):
    """Grade course quiz and save attempts"""
    from models import QuizAttempt
    
    course = Course.query.get_or_404(course_id)
    
    # Check ownership
    if course.user_id != current_user.id:
        return {"error": "Access denied"}, 403
    
    # Get form data
    answers = request.form.to_dict()
    time_taken = int(request.form.get('time_taken', 0))
    
    # Get question IDs from form
    question_ids = [int(key.split('_')[1]) for key in answers.keys() if key.startswith('question_')]
    questions = Quiz.query.filter(Quiz.id.in_(question_ids)).all()
    
    # Grade each question and track by lecture
    results = []
    correct_count = 0
    lecture_stats = {}  # {lecture_id: {'correct': 0, 'total': 0}}
    
    for question in questions:
        question_key = f"question_{question.id}"
        selected_answer = answers.get(question_key, '').upper()
        is_correct = (selected_answer == question.correct_answer)
        
        if is_correct:
            correct_count += 1
        
        # Save attempt
        attempt = QuizAttempt(
            user_id=current_user.id,
            quiz_id=question.id,
            selected_answer=selected_answer if selected_answer else 'X',
            is_correct=is_correct,
            time_taken=time_taken // len(questions) if len(questions) > 0 else 0,
            score=100 if is_correct else 0
        )
        db.session.add(attempt)
        
        # Track by lecture
        concept = Concept.query.get(question.concept_id)
        lecture_id = concept.lecture_id
        
        if lecture_id not in lecture_stats:
            lecture_stats[lecture_id] = {'correct': 0, 'total': 0, 'lecture': concept.lecture}
        
        lecture_stats[lecture_id]['total'] += 1
        if is_correct:
            lecture_stats[lecture_id]['correct'] += 1
        
        results.append({
            'question': question,
            'selected': selected_answer,
            'correct': question.correct_answer,
            'is_correct': is_correct,
            'explanation': question.explanation,
            'lecture': concept.lecture
        })
    
    db.session.commit()
    
    # Calculate overall score
    score = (correct_count / len(questions) * 100) if len(questions) > 0 else 0
    
    # Update progress for each lecture
    for lecture_id, stats in lecture_stats.items():
        progress = Progress.query.filter_by(
            user_id=current_user.id,
            lecture_id=lecture_id
        ).first()
        
        if progress:
            progress.quiz_attempts += 1
            lecture_score = (stats['correct'] / stats['total'] * 100)
            
            if progress.quiz_avg_score == 0:
                progress.quiz_avg_score = lecture_score
            else:
                progress.quiz_avg_score = (progress.quiz_avg_score + lecture_score) / 2
            
            progress.update_mastery()
    
    db.session.commit()
    
    return render_template("quiz_results.html", 
                         course=course,
                         lecture=None,  # Signal this is a course quiz
                         results=results,
                         score=score,
                         correct_count=correct_count,
                         total_questions=len(questions),
                         time_taken=time_taken,
                         lecture_stats=lecture_stats,
                         is_course_quiz=True)


# ==================== LEGACY ROUTES (V2.5 COMPATIBILITY) ====================

@app.route("/api/notes/<int:upload_id>")
@login_required
def get_notes(upload_id):
    """Legacy endpoint for v2.5 uploads"""
    upload = Upload.query.get_or_404(upload_id)

    if upload.user_id != current_user.id:
        return {"error": "Access denied"}, 403

    return {"content": upload.notes_content or "No content available"}


@app.route("/view/<int:upload_id>")
@login_required
def view_notes(upload_id):
    """Legacy view for v2.5 uploads"""
    upload = Upload.query.get_or_404(upload_id)

    # Check if user owns this upload
    if upload.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))

    return render_template("view_notes.html", upload=upload)


@app.route("/enhance/<int:upload_id>", methods=["POST"])
@login_required
def enhance_notes(upload_id):
    """Legacy enhancement for v2.5 uploads"""
    upload = Upload.query.get_or_404(upload_id)

    # Check if user owns this upload
    if upload.user_id != current_user.id:
        return {"error": "Access denied"}, 403

    enhancement_type = request.json.get("type")
    section_text = request.json.get("text", upload.notes_content)

    # Enhancement prompts
    prompts = {
        "explain": f"Explain the following topic in more depth with examples:\n\n{section_text}",
        "simplify": f"Explain the following in simple terms (ELI5 - Explain Like I'm 5):\n\n{section_text}",
        "keypoints": f"Extract the key points from the following text as a bullet list:\n\n{section_text}",
        "quiz": f"Generate 5 multiple choice questions based on this content:\n\n{section_text}"
    }

    if enhancement_type not in prompts:
        return {"error": "Invalid enhancement type"}, 400

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompts[enhancement_type]}]
        )

        enhanced_content = response.choices[0].message.content
        return {"content": enhanced_content}

    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/download/<int:upload_id>")
@login_required
def download(upload_id):
    """Legacy download for v2.5 uploads"""
    upload = Upload.query.get_or_404(upload_id)

    # Check if user owns this upload
    if upload.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))

    pdf_path = os.path.join(UPLOAD_FOLDER, upload.filename)

    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=True, download_name=upload.filename)
    else:
        flash("File not found!", "error")
        return redirect(url_for('dashboard'))


# ==================== DATABASE INITIALIZATION ====================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Create all tables
        print("✅ Database tables created!")
    
    print("🚀 Starting Classify V3...")
    print(f"🔑 API Key loaded: {'✅' if api_key else '❌'}")
    print("📊 Available models: User, Course, Lecture, Concept, Quiz, Flashcard, Progress")
    app.run(debug=True, host="127.0.0.1", port=5000)