"""
Base agent class — wraps Anthropic Claude API calls with
structured JSON output parsing, retry logic, and logging.
"""
import asyncio
import json
import os
import re
from typing import Optional, Type, TypeVar
from datetime import datetime

import anthropic
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
import redis_client as rc
from models import AgentLogEntry

T = TypeVar("T", bound=BaseModel)

_client: Optional[anthropic.Anthropic] = None


def get_anthropic_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        key_preview = (api_key[:8] + "...") if api_key else "NOT SET"
        print(f"[ANTHROPIC] Initializing client — API key: {key_preview}")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


class BaseAgent:
    name: str = "BASE"
    system_prompt: str = ""
    output_model: Type[BaseModel] = BaseModel

    async def _log(self, level: str, message: str, data: Optional[dict] = None):
        entry = AgentLogEntry(
            agent=self.name,
            level=level,
            message=message,
            data=data,
        )
        await rc.log_agent_event(entry)
        return entry

    CLAUDE_TIMEOUT_SECONDS = 30

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def _call_claude(
        self,
        user_message: str,
        tools: Optional[list] = None,
        max_tokens: int = 4096,
    ) -> str:
        """Call Claude via the synchronous client in a thread pool."""
        client = get_anthropic_client()
        model = settings.claude_model
        print(f"[{self.name}] Calling Claude model={model} max_tokens={max_tokens}")

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "system": self.system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(client.messages.create, **kwargs),
                timeout=self.CLAUDE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            print(f"[{self.name}] ERROR: Claude API call timed out after {self.CLAUDE_TIMEOUT_SECONDS}s (model={model})")
            raise

        # Extract text from response
        for block in response.content:
            if hasattr(block, "text"):
                return block.text

        return ""

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from Claude response, stripping all markdown before parsing."""
        text = text.strip()

        # 1. Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Strip all markdown code fences (```json, ```, etc.) and retry
        clean = re.sub(r"```(?:json|JSON)?\s*", "", text)
        clean = re.sub(r"\s*```", "", clean).strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass

        # 3. Extract outermost { } from the original text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        # 4. Extract outermost { } from the stripped text
        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(clean[start : end + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not extract JSON from response: {text[:200]}")

    async def _parse_output(self, text: str) -> BaseModel:
        data = self._extract_json(text)
        return self.output_model.model_validate(data)
