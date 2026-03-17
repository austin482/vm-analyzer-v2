import urllib.request
import json
import ssl
from typing import Dict, List, Any

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

LARK_API = "https://open.larksuite.com/open-apis"


class LarkClient:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token = None

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        if self._token:
            return self._token
        url = f"{LARK_API}/auth/v3/tenant_access_token/internal"
        payload = json.dumps({"app_id": self.app_id, "app_secret": self.app_secret}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, context=ctx)
        data = json.loads(resp.read())
        if data.get("code") != 0:
            raise Exception(f"Lark auth failed: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _get(self, url: str) -> Any:
        req = urllib.request.Request(url, headers=self._headers())
        resp = urllib.request.urlopen(req, context=ctx)
        return json.loads(resp.read())

    def _put(self, url: str, body: dict) -> Any:
        payload = json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload, headers=self._headers(), method="PUT")
        resp = urllib.request.urlopen(req, context=ctx)
        return json.loads(resp.read())

    # ── Document ─────────────────────────────────────────────────────────────

    def get_wiki_text(self, wiki_token: str) -> str:
        """Fetch all text from a Lark Wiki node (resolves wiki token → doc token → blocks)."""
        # Step 1: resolve wiki node to get obj_token
        node_data = self._get(f"{LARK_API}/wiki/v2/spaces/get_node?token={wiki_token}")
        obj_token = node_data.get("data", {}).get("node", {}).get("obj_token")
        if not obj_token:
            raise Exception("Could not resolve wiki node obj_token")

        # Step 2: fetch all document blocks (paginated)
        blocks = []
        page_token = ""
        while True:
            url = f"{LARK_API}/docx/v1/documents/{obj_token}/blocks"
            if page_token:
                url += f"?page_token={page_token}"
            data = self._get(url)
            blocks.extend(data.get("data", {}).get("items", []))
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token", "")

        # Step 3: extract text from all block types
        BLOCK_TEXT_KEYS = [
            "text", "heading1", "heading2", "heading3", "heading4",
            "heading5", "heading6", "bullet", "ordered", "quote", "todo",
        ]
        lines = []
        for block in blocks:
            for key in BLOCK_TEXT_KEYS:
                if key in block:
                    elements = block[key].get("elements", [])
                    line = "".join(e.get("text_run", {}).get("content", "") for e in elements)
                    if line.strip():
                        lines.append(line.strip())
                    break
            # Also handle table cells
            if "table_cell" in block:
                for child in block.get("children", []):
                    pass  # children are their own blocks, already covered

        return "\n".join(lines)

    # ── Bitable ──────────────────────────────────────────────────────────────

    def get_all_records(self, base_token: str, table_id: str) -> List[Dict]:
        """Fetch all records from a Bitable table (handles pagination)."""
        records = []
        page_token = ""
        while True:
            url = f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records"
            if page_token:
                url += f"?page_token={page_token}"
            data = self._get(url)
            resp_data = data.get("data", {})
            records.extend(resp_data.get("items", []))
            if not resp_data.get("has_more"):
                break
            page_token = resp_data.get("page_token", "")
        return records

    def update_record(self, base_token: str, table_id: str, record_id: str, fields: Dict) -> bool:
        """Update specific fields on a single Bitable record. Returns True on success."""
        url = f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}"
        data = self._put(url, {"fields": fields})
        return data.get("code") == 0
