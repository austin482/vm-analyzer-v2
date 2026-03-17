"""
Vercel Python serverless handler for the Lark VM Analyzer.

Design choices for Vercel Hobby (10s limit):
- No Flask: uses the native BaseHTTPRequestHandler format Vercel expects.
- Parallel AI calls: ThreadPoolExecutor with as_completed() so fast records
  don't wait for slow ones.
- Hard 8.5s time guard: guarantees a response before Vercel cuts us off.
- Responds with full JSON result after processing (Lark allows up to ~10s).
"""

import sys
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler

# Make root-level modules importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    LARK_DOC_APP_ID, LARK_DOC_APP_SECRET, LARK_DOC_TOKEN,
    LARK_BASE_APP_ID, LARK_BASE_APP_SECRET, LARK_BASE_TOKEN, LARK_TABLE_ID,
)
from lark_client import LarkClient
from ai_scorer import AIScorer

# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_text(field) -> str:
    """Safely extract a plain string from any Bitable field type."""
    if not field:
        return ""
    if isinstance(field, str):
        return field
    if isinstance(field, list):
        parts = []
        for item in field:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    if isinstance(field, dict):
        if "users" in field:
            return ", ".join(u.get("name", "") for u in field["users"])
        return field.get("text", str(field))
    return str(field)


def run_analyzer() -> dict:
    """
    Core analysis loop.
    Returns a summary dict: {status, processed, skipped, errors[]}.
    """
    start = time.time()
    result = {"status": "success", "processed": 0, "skipped": 0, "errors": []}

    try:
        # ── 1. Init clients ──────────────────────────────────────────────────
        print("init lark clients")
        lark_doc  = LarkClient(LARK_DOC_APP_ID,  LARK_DOC_APP_SECRET)
        lark_base = LarkClient(LARK_BASE_APP_ID, LARK_BASE_APP_SECRET)
        scorer    = AIScorer()

        # ── 2. Load OKR context ──────────────────────────────────────────────
        print("loading okr doc...")
        okr_text = lark_doc.get_wiki_text(LARK_DOC_TOKEN)
        print(f"okr text length: {len(okr_text)} chars")

        # ── 3. Load Bitable records ──────────────────────────────────────────
        print("loading bitable records...")
        records = lark_base.get_all_records(LARK_BASE_TOKEN, LARK_TABLE_ID)
        print(f"total records: {len(records)}")

        # ── 4. Filter: only unscored records ─────────────────────────────────
        # A record needs scoring if Austina Score is None, "", or missing.
        # (We intentionally do NOT re-score 0 — a 0 is a deliberate ❌ Reject.)
        pending = []
        for rec in records:
            fields = rec.get("fields", {})
            vm_pic       = extract_text(fields.get("VM PIC"))
            metric_name  = extract_text(fields.get("Metric Name"))
            austina_score = fields.get("Austina Score")

            if vm_pic and metric_name and (austina_score is None or austina_score == ""):
                pending.append(rec)
            else:
                result["skipped"] += 1

        print(f"pending (unscored): {len(pending)}, skipped: {result['skipped']}")

        if not pending:
            result["message"] = "No unscored records found. Nothing to do."
            return result

        # ── 5. Process in parallel, respect 8.5s time budget ─────────────────
        TIME_LIMIT = 8.5

        def process_one(rec):
            fields       = rec.get("fields", {})
            record_id    = rec["record_id"]
            vm_pic       = extract_text(fields.get("VM PIC"))
            vm_bu        = extract_text(fields.get("PIC BU"))
            metric_name  = extract_text(fields.get("Metric Name"))
            description  = extract_text(fields.get("Description"))

            print(f"  scoring: {vm_pic} | {metric_name}")
            ai_result = scorer.score(okr_text, vm_pic, vm_bu, metric_name, description)

            score      = int(ai_result.get("score", 0))
            suggestion = ai_result.get("suggestion", "")

            ok = lark_base.update_record(
                LARK_BASE_TOKEN, LARK_TABLE_ID, record_id,
                {"Austina Score": score, "AI Suggestion": suggestion},
            )
            print(f"  updated {record_id}: score={score}, ok={ok}")
            return ok, record_id

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(process_one, rec): rec for rec in pending}
            for fut in as_completed(futures):
                elapsed = time.time() - start
                if elapsed > TIME_LIMIT:
                    print(f"time limit {TIME_LIMIT}s reached, stopping early")
                    break
                try:
                    ok, rid = fut.result(timeout=1.0)
                    if ok:
                        result["processed"] += 1
                    else:
                        result["errors"].append(f"update failed for {rid}")
                except Exception as exc:
                    result["errors"].append(str(exc))

    except Exception as exc:
        print(f"fatal: {exc}")
        result["status"] = "error"
        result["errors"].append(str(exc))

    result["elapsed_s"] = round(time.time() - start, 2)
    result["message"] = f"Processed {result['processed']} record(s) in {result['elapsed_s']}s."
    print(result["message"])
    return result


# ── Vercel Python Handler ─────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    """
    Vercel's Python runtime calls handler(request, environ, start_response) — 
    but Vercel also supports the BaseHTTPRequestHandler subclass pattern.
    """

    def _respond(self, body: dict, status: int = 200):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._respond({"status": "ok", "message": "Lark VM Analyzer v2 is running."})

    def do_POST(self):
        # Read (and ignore) any incoming body — we don't need Lark's payload
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length:
            self.rfile.read(content_length)

        result = run_analyzer()
        self._respond(result)

    def log_message(self, fmt, *args):
        # Route handler logs to stdout (visible in Vercel logs)
        print(fmt % args)
