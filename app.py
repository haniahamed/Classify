from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///classify.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
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


# ==================== DATABASE MODELS ====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploads = db.relationship('Upload', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_audio = db.Column(db.String(255), nullable=False)
    is_summary = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_size = db.Column(db.Integer)  # in bytes
    notes_content = db.Column(db.Text)  # Store actual notes text
    transcript_content = db.Column(db.Text)  # Store full transcript


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
    # Get user's uploads
    uploads = Upload.query.filter_by(user_id=current_user.id).order_by(Upload.created_at.desc()).all()
    return render_template("dashboard.html", uploads=uploads)


@app.route("/upload", methods=["POST"])
@login_required
def upload_audio():
    try:
        if "audio" not in request.files:
            return "No audio file in request", 400
        
        file = request.files["audio"]
        
        if file.filename == "":
            return "No file selected", 400

        summarize = request.form.get("summarize") == "on"
        print(f"User: {current_user.email} | Summarize: {summarize}")

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

        # Save to database
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

        # Clean up audio file
        try:
            os.remove(filepath)
        except:
            pass

        # Return JSON for AJAX request
        return {
            "success": True,
            "upload_id": upload.id,
            "filename": file.filename,
            "is_summary": summarize,
            "created_at": upload.created_at.strftime('%b %d, %Y')
        }

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error - Classify</title>
            <style>
                body {{
                    font-family: Arial; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh; display: flex; justify-content: center; align-items: center;
                }}
                .error {{ background: white; padding: 40px; border-radius: 20px; text-align: center; }}
                h2 {{ color: #e74c3c; }}
                a {{ color: #667eea; text-decoration: none; }}
            </style>
        </head>
        <body>
            <div class="error">
                <h2>❌ Error Processing Audio</h2>
                <p>{str(e)}</p>
                <a href="/dashboard">← Back to Dashboard</a>
            </div>
        </body>
        </html>
        """, 500


@app.route("/api/notes/<int:upload_id>")
@login_required
def get_notes(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    
    if upload.user_id != current_user.id:
        return {"error": "Access denied"}, 403
    
    return {"content": upload.notes_content or "No content available"}


@app.route("/view/<int:upload_id>")
@login_required
def view_notes(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    
    # Check if user owns this upload
    if upload.user_id != current_user.id:
        flash("Access denied!", "error")
        return redirect(url_for('dashboard'))
    
    return render_template("view_notes.html", upload=upload)


@app.route("/enhance/<int:upload_id>", methods=["POST"])
@login_required
def enhance_notes(upload_id):
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


if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Create database tables
    print("🚀 Starting Classify V2...")
    print(f"🔑 API Key loaded: {'✅' if api_key else '❌'}")
    app.run(debug=True, host="127.0.0.1", port=5000)