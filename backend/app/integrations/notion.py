"""Notion adapter (internal-integration token — NOT interactive MCP).

Per the audit, Notion notes are WRITE-ONCE then human-owned: we create the
meeting-note page on dispatch and store its page id, but we do NOT re-push on
drift (so we never clobber a human edit). The verifier only checks the page
still EXISTS, not that its content matches.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import Settings

NOTION_VERSION = "2022-06-28"


@dataclass
class NotionPage:
    id: str
    url: str | None = None


class NotionAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.notion_token)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://api.notion.com/v1",
            headers={
                "Authorization": f"Bearer {self.settings.notion_token}",
                "Notion-Version": NOTION_VERSION,
            },
            timeout=30,
        )

    async def create_meeting_note(self, *, title: str, body: str, dedup_key: str) -> NotionPage:
        if not self.configured:
            return NotionPage(id=f"NOTION-STUB-{dedup_key[:12]}")
        # TODO(M4): create a page in the configured database; store dedup_key in a
        # property so create stays idempotent on retry.
        raise NotImplementedError("real Notion create lands in M4")

    async def page_exists(self, page_id: str) -> bool:
        """Verifier Check 3 for Notion: existence only (not content)."""
        if not self.configured or page_id.startswith("NOTION-STUB-"):
            return True
        async with self._client() as client:
            resp = await client.get(f"/pages/{page_id}")
            return resp.status_code == 200
