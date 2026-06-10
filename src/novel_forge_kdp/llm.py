from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator


class LLMClientError(RuntimeError):
    pass


def parse_json_content(content: str) -> Any:
    text = content.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMClientError(f"LLM did not return valid JSON: {exc}") from exc


class OllamaOpenAIClient:
    def __init__(
        self,
        base_url: str = "http://ws1.local:11434",
        model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
        timeout_seconds: float = 3600,
        log_dir: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.log_dir = log_dir

    def complete_json(
        self,
        *,
        task: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        temperature: float = 0.4,
        max_tokens: int | None = 24576,
    ) -> Any:
        schema_hint = "\n\nJSON Schema to satisfy exactly:\n" + json.dumps(schema, ensure_ascii=False)
        request_messages = [dict(m) for m in messages]
        for message in reversed(request_messages):
            if message.get("role") == "user":
                message["content"] = message.get("content", "") + schema_hint
                break
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": request_messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        started = datetime.now(UTC).isoformat()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.base_url}/v1/chat/completions", json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._write_log(task, started, payload, {"status_code": exc.response.status_code, "text": exc.response.text})
            raise LLMClientError(f"LLM HTTP error {exc.response.status_code}: {exc.response.text[:500]}") from exc
        except httpx.TimeoutException as exc:
            self._write_log(task, started, payload, {"timeout": self.timeout_seconds})
            raise LLMClientError(f"LLM request timed out after {self.timeout_seconds}s") from exc
        except httpx.HTTPError as exc:
            self._write_log(task, started, payload, {"error": repr(exc)})
            raise LLMClientError(f"LLM request failed: {exc}") from exc

        raw = response.json()
        self._write_log(task, started, payload, raw)
        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = parse_json_content(content)
        parsed = self._unwrap_common_container(parsed, schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(parsed), key=lambda e: list(e.path))
        if errors:
            message = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
            raise LLMClientError(f"JSON schema validation failed: {message}; content preview: {content[:1000]}")
        return parsed

    @staticmethod
    def _unwrap_common_container(parsed: Any, schema: dict[str, Any]) -> Any:
        if not isinstance(parsed, dict):
            return parsed
        validator = Draft202012Validator(schema)
        if not list(validator.iter_errors(parsed)):
            return parsed
        for key in ("result", "data", "series", "series_plan", "volume", "outline", "scene", "review"):
            value = parsed.get(key)
            if isinstance(value, dict) and not list(validator.iter_errors(value)):
                return value
        return parsed

    def _write_log(self, task: str, started: str, request: dict[str, Any], response: Any) -> None:
        if self.log_dir is None:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        path = self.log_dir / f"{stamp}_{task}.json"
        path.write_text(json.dumps({"started_at": started, "task": task, "request": request, "response": response}, ensure_ascii=False, indent=2), encoding="utf-8")
