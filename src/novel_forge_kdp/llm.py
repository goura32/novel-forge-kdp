from __future__ import annotations

import json
import re
from copy import deepcopy
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


def build_chat_payload(
    *,
    model: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    temperature: float,
    max_tokens: int | None,
) -> dict[str, Any]:
    schema_hint = "\n\nJSON Schema to satisfy exactly:\n" + json.dumps(schema, ensure_ascii=False)
    request_messages = deepcopy(messages)
    for message in reversed(request_messages):
        if message.get("role") == "user":
            message["content"] = message.get("content", "") + schema_hint
            break
    payload: dict[str, Any] = {
        "model": model,
        "messages": request_messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "think": False,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    return payload


def validate_structured_output(parsed: Any, schema: dict[str, Any], content_preview: str) -> Any:
    errors = sorted(Draft202012Validator(schema).iter_errors(parsed), key=lambda e: list(e.path))
    if errors:
        message = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
        raise LLMClientError(f"JSON schema validation failed: {message}; content preview: {content_preview[:1000]}")
    return parsed


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
        payload = build_chat_payload(model=self.model, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)
        started = datetime.now(UTC).isoformat()
        response = self._post_chat_completion(task, started, payload)
        raw = self._read_response_json(task, started, payload, response)
        self._write_log(task, started, payload, raw)
        return self._parse_and_validate_response(raw, schema)

    def _post_chat_completion(self, task: str, started: str, payload: dict[str, Any]) -> httpx.Response:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.base_url}/v1/chat/completions", json=payload)
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as exc:
            self._write_log(task, started, payload, {"status_code": exc.response.status_code, "text": exc.response.text})
            raise LLMClientError(f"LLM HTTP error {exc.response.status_code}: {exc.response.text[:500]}") from exc
        except httpx.TimeoutException as exc:
            self._write_log(task, started, payload, {"timeout": self.timeout_seconds})
            raise LLMClientError(f"LLM request timed out after {self.timeout_seconds}s") from exc
        except httpx.HTTPError as exc:
            self._write_log(task, started, payload, {"error": repr(exc)})
            raise LLMClientError(f"LLM request failed: {exc}") from exc

    def _read_response_json(self, task: str, started: str, payload: dict[str, Any], response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            self._write_log(task, started, payload, {"status_code": response.status_code, "non_json_text": response.text[:2000]})
            raise LLMClientError(f"LLM response was not JSON: {response.text[:500]}") from exc

    def _parse_and_validate_response(self, raw: Any, schema: dict[str, Any]) -> Any:
        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = parse_json_content(content)
        parsed = self._unwrap_common_container(parsed, schema)
        return validate_structured_output(parsed, schema, content)

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
