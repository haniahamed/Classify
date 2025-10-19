# 🎓 Classify V1 - Intelligent Classroom App

**Version:** 1.0.0  
**Date:** October 2025

Convert lecture audio recordings into organized notes with AI-powered transcription and summarization.

---

## ✨ Features

- 🎤 **Audio Transcription** - Converts audio to text using OpenAI Whisper
- 🤖 **AI Summarization** - Generates structured notes with GPT-4o-mini
- 📄 **Raw Transcript Mode** - Toggle between summary and full transcript
- 📑 **PDF Export** - Automatically generates downloadable PDF notes
- 🎨 **Material Design UI** - Clean, modern interface with smooth animations
- 📱 **Responsive Design** - Works on desktop and mobile devices

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))

### Installation

1. **Clone or download this project**

2. **Install dependencies:**

   ```bash
   py -m pip install -r requirements.txt
   ```

3. **Set up your API key:**

   ```bash
   # Windows Command Prompt
   set OPENAI_API_KEY=your-api-key-here

   # Windows PowerShell
   $env:OPENAI_API_KEY="your-api-key-here"

   # Linux/Mac
   export OPENAI_API_KEY=your-api-key-here
   ```

4. **Run the app:**

   ```bash
   py app.py
   ```

5. **Open your browser:**
   ```
   http://127.0.0.1:5000
   ```

---

## 📖 How to Use

1. **Upload Audio** - Select an audio file (MP3, WAV, M4A, OGG, FLAC)
2. **Choose Mode** - Toggle between:
   - ✨ **Summarized Notes** (AI-powered structured summary)
   - 📄 **Raw Transcript** (Full transcription without summarization)
3. **Convert** - Click "Convert to Notes"
4. **Download** - PDF automatically downloads when ready

---

## 🎯 Supported Audio Formats

- MP3
- WAV
- M4A
- OGG
- FLAC

**Maximum file size:** 25 MB

---

## 🛠️ Technical Stack

- **Backend:** Flask (Python)
- **AI Models:**
  - OpenAI Whisper (transcription)
  - GPT-4o-mini (summarization)
- **PDF Generation:** ReportLab
- **Frontend:** HTML5, CSS3, Vanilla JavaScript

---

## 📂 Project Structure

```
Classify_V1/
├── app.py                 # Flask backend
├── templates/
│   └── index.html        # Frontend UI
├── uploads/              # Temporary storage for audio/PDF files
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

---

## 💡 Features Breakdown

### Transcription

- Uses OpenAI's Whisper model for accurate speech-to-text
- Supports multiple languages
- Handles various audio qualities

### Summarization (Optional)

- Extracts key points from lectures
- Organizes content with headings and bullet points
- Preserves important details

### PDF Generation

- Automatic text wrapping
- Multi-page support
- Clean, readable formatting
- Timestamped filenames

---

## 🔒 Security Notes

- ⚠️ **Never commit API keys to version control**
- Use environment variables for sensitive data
- Consider using `.env` files with `python-dotenv` for production

---

## 🐛 Troubleshooting

### "pip is not recognized"

```bash
py -m pip install -r requirements.txt
```

### "No module named 'flask'"

```bash
py -m pip install flask openai reportlab
```

### API Key Issues

Make sure your API key is set in the environment before running:

```bash
set OPENAI_API_KEY=your-key-here
py app.py
```

---

## 📊 API Usage & Costs

- **Whisper API:** ~$0.006 per minute of audio
- **GPT-4o-mini:** ~$0.15 per 1M input tokens, ~$0.60 per 1M output tokens
- Raw transcript mode uses only Whisper (cheaper!)

---

## 🚦 Roadmap (Future Versions)

Ideas for V2 and beyond:

- [ ] User authentication
- [ ] Save notes history
- [ ] Multiple language support
- [ ] Custom summarization styles
- [ ] Batch processing
- [ ] Export to multiple formats (DOCX, TXT, MD)
- [ ] Cloud storage integration

---

## 📝 License

This project is for educational purposes.

---

## 🙏 Acknowledgments

- OpenAI for Whisper and GPT models
- Flask framework
- ReportLab PDF library
- Material Design inspiration

---

## 📧 Support

For issues or questions, please check:

- OpenAI API documentation: https://platform.openai.com/docs
- Flask documentation: https://flask.palletsprojects.com/

---

**Classify V1** - Built with ❤️ for better learning
