# Invoice Checker

Upload invoices (PDF or image). Google Gemini reads each one, summarizes it, and flags problems.

```
React (frontend/, port 5173)  →  FastAPI (backend/, port 8000)  →  Gemini API
  upload page + results          holds the API key, runs checks     reads the invoice
```

- **AI review** (Gemini): extracts fields and line items, writes a summary, flags missing info, duplicates, suspicious or inconsistent charges.
- **Math check** (plain Python, `backend/checks.py`): line totals, subtotal, tax, grand total, and dates. Code checks the arithmetic so it never "hallucinates" a sum.

## One-time setup

You need **Python 3.10+** (tick "Add python.exe to PATH" when installing) and **Node.js LTS**.

### 1. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Open `backend/.env` and paste your free key from https://aistudio.google.com/apikey after `GEMINI_API_KEY=`.

> If PowerShell says running scripts is disabled, run this once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 2. Frontend

```powershell
cd frontend
npm install
```

## Running the app (two terminals)

**Terminal 1, the backend:**

```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

**Terminal 2, the frontend:**

```powershell
cd frontend
npm run dev
```

Open http://localhost:5173 and drop in some invoices.

## Deploying to Vercel

On Vercel the app runs as a single FastAPI app (`index.py` → `backend/main.py`), which also serves
the built React page from `frontend/dist`. `vercel.json` builds the frontend; Python packages come
from `pyproject.toml`.

1. Create a free account at https://vercel.com.
2. Log in from a terminal in this folder: `npx vercel login`
3. Add your secrets (each command asks for the value; pick **Production**):
   - `npx vercel env add GEMINI_API_KEY`
   - `npx vercel env add APP_PASSWORD`
4. Deploy: `npx vercel --prod`

Limits on Vercel's free plan: max 4 MB per uploaded file, max 300 seconds per analysis.

## Project layout

| File | What it does |
|---|---|
| `backend/main.py` | The FastAPI server: `/api/analyze` receives files and returns results |
| `backend/analyzer.py` | Sends the invoice to Gemini and defines the JSON shape it must return |
| `backend/checks.py` | Re-calculates all the math in Python |
| `frontend/src/App.jsx` | The React page: upload box, result cards |
| `frontend/src/App.css` | Styling (supports light and dark mode) |
| `frontend/vite.config.js` | Forwards `/api` requests from React to the backend |
| `index.py`, `pyproject.toml`, `vercel.json`, `.vercelignore` | Vercel deployment config |

## Cost

The app uses a free-tier Gemini model, so it costs nothing, within Google's free-tier rate limits.
On the free tier, Google may use what you upload to improve its products, so avoid uploading
sensitive real invoices. Change the model with `GEMINI_MODEL` in `backend/.env`.
