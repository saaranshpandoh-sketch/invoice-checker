"""Sends an invoice (PDF or image) to Google Gemini and gets back structured data.

Gemini does two jobs here:
  1. Reads the invoice and extracts fields (vendor, dates, line items, totals...).
  2. Flags problems a human reviewer would notice (missing info, odd charges...).

Arithmetic is NOT left to the AI - checks.py re-does the math in plain Python,
because code is 100% reliable at adding numbers.
"""

import asyncio
import base64
import os
from typing import Literal

from google import genai
from google.genai import _interactions_errors as gerr
from pydantic import BaseModel, ValidationError

# Free-tier Gemini models, tried in order. If one is overloaded (Google returns
# "503 Service Unavailable") or too slow, the next one is used.
# Put your preferred model first by setting GEMINI_MODEL in backend/.env.
MODELS = list(dict.fromkeys(filter(None, [
    os.getenv("GEMINI_MODEL"),
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
])))
TIMEOUT_SECONDS = 90  # per model attempt

# ---------------------------------------------------------------------------
# The shape of the answer we want back. Gemini is told to reply with JSON
# that matches these classes (this is called "structured output").
# ---------------------------------------------------------------------------


class LineItem(BaseModel):
    description: str
    quantity: float | None
    unit_price: float | None
    amount: float | None


class Issue(BaseModel):
    severity: Literal["error", "warning", "info"]
    category: str  # e.g. "Missing field", "Suspicious charge", "Date"
    message: str


class InvoiceAnalysis(BaseModel):
    is_invoice: bool
    vendor_name: str | None
    vendor_address: str | None
    customer_name: str | None
    invoice_number: str | None
    invoice_date: str | None  # YYYY-MM-DD
    due_date: str | None  # YYYY-MM-DD
    currency: str | None
    line_items: list[LineItem]
    subtotal: float | None
    tax: float | None
    discount: float | None
    shipping: float | None
    total: float | None
    summary: str
    issues: list[Issue]


SYSTEM_PROMPT = """You are a meticulous accounts-payable reviewer.

You will be given one document. First decide whether it is an invoice (or bill/receipt).
If it is not, set is_invoice to false, explain what it is in the summary, and leave other fields empty/null.

If it is an invoice:
- Extract every field exactly as printed. Use null when a value is not on the document - never guess.
- Dates must be YYYY-MM-DD. Amounts are plain numbers without currency symbols.
- Use a 3-letter currency code (USD, EUR, INR...) when you can tell the currency.
- Write a 2-4 sentence plain-English summary: who billed whom, for what, how much, and when it is due.

Then list issues a careful reviewer would raise. Arithmetic (line totals, subtotal, tax, grand total)
and date order (due date vs invoice date, future or overdue dates) are verified separately by
software, so do NOT report those. Focus on:
- Missing important fields (invoice number, dates, vendor details, customer, payment terms)
- Duplicate or near-duplicate line items
- Vague, unusual or suspicious charges
- Inconsistent information (e.g. different names/addresses, currency mismatch, wrong year)
- Anything illegible or ambiguous
Each issue's category is a short Title Case label such as "Duplicate Line Item" or "Missing Field".
Use "error" for things that should block payment, "warning" for things to double-check,
and "info" for minor notes. Return an empty list if everything looks fine."""


SUPPORTED_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}


class AnalysisError(Exception):
    """A friendly error message we can show to the user."""


_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not os.getenv("GEMINI_API_KEY"):
            raise AnalysisError("GEMINI_API_KEY is not set. Add your key to backend/.env and restart the backend.")
        _client = genai.Client()  # reads GEMINI_API_KEY from the environment
    return _client


def _file_part(data: bytes, media_type: str) -> dict:
    return {
        "type": "document" if media_type == "application/pdf" else "image",
        "data": base64.b64encode(data).decode("utf-8"),
        "mime_type": media_type,
    }


async def _call_model(model: str, data: bytes, media_type: str):
    return await asyncio.wait_for(
        get_client().aio.interactions.create(
            model=model,
            system_instruction=SYSTEM_PROMPT,
            input=[
                _file_part(data, media_type),
                {"type": "text", "text": "Review this invoice."},
            ],
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": InvoiceAnalysis.model_json_schema(),
            },
        ),
        timeout=TIMEOUT_SECONDS,
    )


async def analyze_invoice(data: bytes, media_type: str) -> InvoiceAnalysis:
    get_client()  # fail fast with a friendly message if the key is missing
    try:
        interaction = None
        for model in MODELS:
            try:
                interaction = await _call_model(model, data, media_type)
                break
            except asyncio.TimeoutError:
                continue  # too slow / stuck retrying an overloaded model: try the next one
            except gerr.APIStatusError as e:
                if e.status_code >= 500:
                    continue  # Google-side problem with this model: try the next one
                raise
        if interaction is None:
            raise AnalysisError("All Gemini models are busy right now. Please try again in a few minutes.")
    except gerr.RateLimitError:
        raise AnalysisError("Free-tier limit reached. Wait a minute (or until tomorrow) and try again.")
    except (gerr.AuthenticationError, gerr.PermissionDeniedError):
        raise AnalysisError("Your Gemini API key is invalid or not allowed. Check backend/.env.")
    except gerr.BadRequestError as e:
        if "api key" in str(e).lower():
            raise AnalysisError("Your Gemini API key is invalid. Check backend/.env.")
        raise AnalysisError(f"Gemini couldn't process this file: {e}")
    except gerr.APIStatusError as e:
        raise AnalysisError(f"Gemini API error ({e.status_code}). Try again shortly.")
    except gerr.APIConnectionError:
        raise AnalysisError("Couldn't reach the Gemini API. Check your internet connection.")

    if interaction.status != "completed":
        raise AnalysisError(f"Gemini didn't finish the analysis (status: {interaction.status}).")
    if not interaction.output_text:
        raise AnalysisError("Gemini returned an empty answer. Please try again.")
    try:
        return InvoiceAnalysis.model_validate_json(interaction.output_text)
    except ValidationError:
        raise AnalysisError("Gemini's answer wasn't in the expected format. Please try again.")
