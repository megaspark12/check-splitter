# Check Splitter

A web application for splitting restaurant bills among friends. Upload a receipt photo, and the AI will extract items automatically. Each person can select what they ordered, and the app calculates everyone's share including tax and tip.

## Features

- 📷 **Receipt Scanning** - Upload or take a photo of your receipt
- 🤖 **AI-Powered OCR** - Automatically extracts items and prices using Google Gemini
- 👥 **Multi-User Sessions** - Share a code or QR for friends to join
- ✅ **Item Selection** - Each person selects what they ordered
- 💰 **Smart Splitting** - Handles shared items, tax distribution, and custom tips
- 📱 **Mobile-Friendly** - Works great on phones

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy, SQLite
- **Frontend**: Vanilla HTML/CSS/JavaScript
- **AI**: Google Gemini 2.5 Flash for receipt OCR

## Quick Start

1. Clone the repository
2. Create a virtual environment: `python -m venv .venv`
3. Activate it: `source .venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and add your Gemini API key
6. Run the server: `uvicorn app.main:app --reload`
7. Open http://localhost:8000

## License

MIT
