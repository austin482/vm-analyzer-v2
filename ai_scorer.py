import urllib.request
import json
import ssl
from typing import Dict, Any

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class AIScorer:
    """Scores a Value Metric against OKR context using GPT-4o-mini via OpenRouter."""

    def _build_prompt(self, okr_context: str, vm_pic: str, vm_bu: str,
                      metric_name: str, description: str) -> str:
        return f"""You are an expert OKR Alignment Analyzer.
Evaluate whether a Product Manager's submitted "Value Metric" aligns with their assigned OKR for the quarter.

### Full OKR Document Context
{okr_context}

### Value Metric Submission
- VM PIC (submitter): {vm_pic}
- PIC BU (Business Unit): {vm_bu}
- Metric Name: {metric_name}
- Description: {description}

## Evaluation Steps

Step 1 – Verify Ownership:
Does the VM PIC appear anywhere in the OKR document as a responsible person or collaborator?

Step 2 – Evaluate Alignment:
Does the Metric Name + Description drive progress toward a Key Result in the document?

Step 3 – Score & Output (choose ONE of the two formats below):

CASE A – The metric is misaligned, belongs to a different BU/OKR, or the PIC is not in the document:
Output EXACTLY:
{{"score": 0, "suggestion": "❌ Reject"}}

CASE B – The metric aligns (even partially):
Output EXACTLY:
{{"score": <integer 1-100>, "suggestion": "📊 Insights:\\n• <point>\\n• <point>\\n\\n💡 Suggestions:\\n• <point>\\n• <point>"}}

Score guide: 90-100 = perfect, 70-89 = good, 40-69 = weak, 1-39 = very poor.
Output only the raw JSON object, nothing else.
"""

    def score(self, okr_context: str, vm_pic: str, vm_bu: str,
              metric_name: str, description: str) -> Dict[str, Any]:
        """Returns dict with 'score' (int) and 'suggestion' (str)."""
        prompt = self._build_prompt(okr_context, vm_pic, vm_bu, metric_name, description)

        payload = json.dumps({
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": "You are a specialized AI that outputs only valid JSON."},
                {"role": "user",   "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 500,
        }).encode()

        req = urllib.request.Request(
            OPENROUTER_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type":  "application/json",
                "HTTP-Referer":  "https://ajobthing.com",
            },
        )

        try:
            resp = urllib.request.urlopen(req, context=ctx, timeout=8)
            body = json.loads(resp.read())
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:
            # Surface the real error into the Lark suggestion column
            err = str(e)
            if hasattr(e, "read"):
                try:
                    err_body = json.loads(e.read().decode())
                    err = err_body.get("error", {}).get("message", err)
                except Exception:
                    pass
            print(f"[AIScorer] Error: {err}")
            return {
                "score": 0,
                "suggestion": f"📊 Insights:\n• Analysis failed: {err}\n\n💡 Suggestions:\n• Check OPENROUTER_API_KEY in Vercel env vars.",
            }
