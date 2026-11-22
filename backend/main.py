"""FastAPI backend for the invoice checker.

Local development:  uvicorn main:app --reload   (run inside backend/)
On Vercel:          index.py at the project root imports this `app`.
"""

import hmac
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile

load_dotenv(Path(__file__).parent / ".env")  # local only; on Vercel, env vars come from the dashboard

from analyzer import SUPPORTED_TYPES, AnalysisError, analyze_invoice  # noqa: E402
from checks import run_checks  # noqa: E402

# Vercel rejects request bodies over 4.5 MB, so keep each upload under 4 MB.
MAX_FILE_MB = 4

app = FastAPI(title="Invoice Checker")


# ---------------------------------------------------------------------------
# Password protection. Set APP_PASSWORD (in backend/.env locally, or in Vercel's
# environment variables). If it isn't set, the app is open - handy for local dev.
# ---------------------------------------------------------------------------


def _app_password() -> str:
    return os.getenv("APP_PASSWORD", "")


def require_password(x_app_password: str = Header(default="")) -> None:
    expected = _app_password()
    if expected and not hmac.compare_digest(x_app_password.encode(), expected.encode()):
        raise HTTPException(401, "Wrong password.")


@app.get("/api/health")
async def health():
    return {"status": "ok", "password_required": bool(_app_password())}


@app.post("/api/check-password", dependencies=[Depends(require_password)])
async def check_password():
    return {"ok": True}


@app.post("/api/analyze", dependencies=[Depends(require_password)])
async def analyze(file: UploadFile = File(...)):
    return await _process(file)


async def _process(file: UploadFile) -> dict:
    result = {"filename": file.filename, "ok": False}
    media_type = file.content_type
    if media_type == "image/jpg":
        media_type = "image/jpeg"

    if media_type not in SUPPORTED_TYPES:
        result["error"] = "Unsupported file type. Upload a PDF, PNG, JPG, WEBP or GIF."
        return result

    data = await file.read()
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        result["error"] = f"File is larger than {MAX_FILE_MB} MB."
        return result
    if not data:
        result["error"] = "File is empty."
        return result

    try:
        analysis = await analyze_invoice(data, media_type)
    except AnalysisError as e:
        result["error"] = str(e)
        return result

    ai_issues = [{**issue.model_dump(), "source": "ai"} for issue in analysis.issues]
    issues = run_checks(analysis) + ai_issues
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: order[i["severity"]])

    if any(i["severity"] == "error" for i in issues):
        status = "errors"
    elif any(i["severity"] == "warning" for i in issues):
        status = "warnings"
    else:
        status = "ok"

    result.update(
        ok=True,
        status=status if analysis.is_invoice else "not_invoice",
        invoice=analysis.model_dump(exclude={"issues"}),
        issues=issues,
    )
    return result


# Serve the built React app (frontend/dist) for every non-/api URL.
# Path is relative to the project root, which is where Vercel runs the app.
# check_dir=False lets local development run without a build (Vite serves the page then).
app.frontend("/", directory="frontend/dist", check_dir=False)
