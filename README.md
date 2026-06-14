# Daily Knowledge Agent

A small Streamlit app that generates a structured mini-lesson on any topic, then a three-question quiz, with progress stored in SQLite.

Highlights:
- Lesson output stays focused on the exact topic.
- Coding/programming topics include a code snippet and practical coding example.
- History includes prior quiz attempts for each lesson topic/session.

## Prerequisites

- Python 3.10 or newer
- An API key for **Google Gemini** (recommended) or **OpenAI**

### API keys (choose one)

| Provider | Cost | Get a key |
|----------|------|-----------|
| **Google Gemini** | Generous free tier in [Google AI Studio](https://aistudio.google.com/) | [Create API key](https://aistudio.google.com/apikey) |
| **OpenAI** | Paid usage | [OpenAI API keys](https://platform.openai.com/api-keys) |

Copy `.env` and set either `GOOGLE_API_KEY` (with `LLM_PROVIDER=google`) or `OPENAI_API_KEY` (with `LLM_PROVIDER=openai`). If you only set one real key, the app picks that provider automatically unless you override `LLM_PROVIDER`.

## Setup

1. **Clone or copy this project** and open a terminal in the project root.

2. **Create and activate a virtual environment**

   **Windows (PowerShell)**

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   **macOS / Linux**

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure the API key**

   Edit `.env`. Example using **Google** (default in the sample file):

   ```
   LLM_PROVIDER=google
   GOOGLE_API_KEY=your_actual_key
   ```

   Example using **OpenAI**:

   ```
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-...
   ```

## Run

```bash
streamlit run app.py
```

The app creates `knowledge.db` in the project folder on first run and keeps your session history there.

## Project layout

- `app.py` — Streamlit UI
- `agent/lesson.py` — lesson chain (JSON lesson structure)
- `agent/quiz.py` — quiz generation and scoring helpers
- `db/storage.py` — SQLite access
- `prompts/` — prompt templates

## Manual checks

- Try several topics and confirm lessons and quizzes load.
- Restart the app and confirm **History** in the sidebar still lists past sessions and scores.

## Gemini `429` / `RESOURCE_EXHAUSTED`

Free tier is **per model and per day** (see [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)). If you see quota errors for one model, set another in `.env`:

```env
GEMINI_MODEL=gemini-1.5-flash
```

Other values to try: `gemini-2.0-flash-lite`, `gemini-1.5-pro` (stricter limits). Wait for the retry delay or the next day if all free quotas are used. Enable billing in Google AI Studio / Cloud only if you choose a paid plan.
