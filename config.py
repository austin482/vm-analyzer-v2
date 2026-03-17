import os

# ── App 1: OKR Wiki / Doc access ─────────────────────────────────────────────
LARK_DOC_APP_ID     = os.getenv("LARK_DOC_APP_ID",     "cli_a9d1efc6a2381ed4")
LARK_DOC_APP_SECRET = os.getenv("LARK_DOC_APP_SECRET", "wWL8cXBdwk2895DpQFNzBgSgrkT1kujN")
LARK_DOC_TOKEN      = os.getenv("LARK_DOC_TOKEN",      "Pweqw1j8Ci7yGkkIghNlZxmogLf")

# ── App 2: Bitable read/write ────────────────────────────────────────────────
LARK_BASE_APP_ID     = os.getenv("LARK_BASE_APP_ID",     "cli_a9eed0d5dcb89ed3")
LARK_BASE_APP_SECRET = os.getenv("LARK_BASE_APP_SECRET", "uwdb9LnnZbG66aPsP1hvReSGzNOzBZoZ")
LARK_BASE_TOKEN      = os.getenv("LARK_BASE_TOKEN",      "FUBhb3uUaa0h21suULgluANog8f")
LARK_TABLE_ID        = os.getenv("LARK_TABLE_ID",        "tblz3uSEbkQGVXRq")

# ── AI ────────────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL",   "openai/gpt-4o-mini")
