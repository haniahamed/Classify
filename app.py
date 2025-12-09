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
    """View a specific course with all its lectures"""
    course = Course.query.get_or_404(course_id)
    
    # Check ownership
    if course.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))
    
    # Get progress summary
    progress_summary = course.get_progress_summary()
    weak_concepts = course.get_weak_concepts(threshold=60)
    strong_concepts = course.get_strong_concepts(threshold=80)
    
    return render_template("view_course.html", 
                          course=course,
                          progress=progress_summary,
                          weak_concepts=weak_concepts[:5],  # Top 5 weak
                          strong_concepts=strong_concepts[:5])  # Top 5 strong


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