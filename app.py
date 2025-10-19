from flask import Flask, render_template, request, send_file
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Get API key from environment variable
api_key = os.environ.get("OPENAI_API_KEY")

# Validate API key exists
if not api_key:
    raise ValueError("❌ OPENAI_API_KEY not found! Please set it in your .env file or environment variables.")

client = OpenAI(api_key=api_key)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_audio():
    try:
        # Check if file exists in request
        if "audio" not in request.files:
            return "No audio file in request", 400
        
        file = request.files["audio"]
        
        if file.filename == "":
            return "No file selected", 400

        # Get summarize preference (checkbox sends "on" when checked)
        summarize = request.form.get("summarize") == "on"
        print(f"Summarize mode: {summarize}")

        # Save uploaded file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        print(f"File saved: {filepath}")

        # Step 1: Transcribe using Whisper
        print("Transcribing audio...")
        with open(filepath, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )

        # Handle transcription response
        if isinstance(transcription, str):
            transcript_text = transcription
        else:
            transcript_text = transcription.text if hasattr(transcription, 'text') else str(transcription)

        print(f"Transcription complete: {len(transcript_text)} characters")

        # Step 2: Generate notes (summarized or raw)
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
            print("Summary generated successfully")
            pdf_prefix = "Classify_Summary"
        else:
            print("Using raw transcript...")
            notes = transcript_text
            pdf_prefix = "Classify_Transcript"

        # Step 3: Generate PDF with proper text wrapping and page handling
        pdf_filename = f"{pdf_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = os.path.join(UPLOAD_FOLDER, pdf_filename)

        c = canvas.Canvas(pdf_path, pagesize=letter)
        width, height = letter
        
        # Set up margins and starting position
        left_margin = 40
        right_margin = width - 40
        max_width = right_margin - left_margin
        top_margin = height - 50
        bottom_margin = 50
        line_height = 14
        
        y_position = top_margin
        c.setFont("Helvetica", 12)

        # Process each line with wrapping
        for line in notes.split("\n"):
            if not line.strip():
                # Empty line - add spacing
                y_position -= line_height
                if y_position < bottom_margin:
                    c.showPage()
                    c.setFont("Helvetica", 12)
                    y_position = top_margin
                continue
            
            # Wrap long lines to fit within margins
            wrapped_lines = simpleSplit(line, "Helvetica", 12, max_width)
            
            for wrapped_line in wrapped_lines:
                # Check if we need a new page
                if y_position < bottom_margin:
                    c.showPage()
                    c.setFont("Helvetica", 12)
                    y_position = top_margin
                
                # Draw the text
                c.drawString(left_margin, y_position, wrapped_line)
                y_position -= line_height

        c.save()
        print(f"PDF created: {pdf_filename}")

        # Clean up uploaded audio file
        try:
            os.remove(filepath)
            print(f"Cleaned up: {filepath}")
        except Exception as cleanup_error:
            print(f"Warning: Could not remove {filepath}: {cleanup_error}")

        # Return the PDF file
        return send_file(
            pdf_path, 
            as_attachment=True, 
            download_name=pdf_filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error occurred: {error_msg}")
        
        # Return user-friendly error page
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error - Classify</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    padding: 20px;
                }}
                .error-container {{
                    background: white;
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                    max-width: 600px;
                    text-align: center;
                }}
                h2 {{ color: #e74c3c; margin-bottom: 20px; }}
                p {{ color: #555; margin: 20px 0; line-height: 1.6; }}
                .error-details {{
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 20px 0;
                    font-family: monospace;
                    font-size: 14px;
                    color: #e74c3c;
                    word-wrap: break-word;
                }}
                a {{
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 12px 30px;
                    border-radius: 25px;
                    text-decoration: none;
                    margin-top: 20px;
                    transition: transform 0.2s;
                }}
                a:hover {{ transform: translateY(-2px); }}
            </style>
        </head>
        <body>
            <div class="error-container">
                <h2>❌ Error Processing Audio</h2>
                <p>We encountered an error while processing your audio file.</p>
                <div class="error-details">{error_msg}</div>
                <p><strong>Common solutions:</strong></p>
                <ul style="text-align: left; color: #555;">
                    <li>Check if your API key is valid</li>
                    <li>Ensure the audio file is not corrupted</li>
                    <li>Try a smaller audio file (under 25 MB)</li>
                    <li>Check your internet connection</li>
                </ul>
                <a href="/">← Try Again</a>
            </div>
        </body>
        </html>
        """, 500


if __name__ == "__main__":
    print("🚀 Starting Classify V1...")
    print(f"📁 Upload folder: {UPLOAD_FOLDER}")
    print(f"🔑 API Key loaded: {'✅' if api_key else '❌'}")
    app.run(debug=True, host="127.0.0.1", port=5000)