"""LLM client with provider abstraction and a record/replay cache.

The demo never needs a live key: responses are cached under cache/ and
replayed (AGENT_MODE=replay, the default). Recording requires a key once.

Provider is chosen from .env:
  LLM_PROVIDER   openai | gemini          (default: openai)
  LLM_BASE_URL   optional custom endpoint
  LLM_API_KEY    key for the chosen provider (falls back to OPENAI_API_KEY /
                 GEMINI_API_KEY / GOOGLE_API_KEY)
  AGENT_MODEL    model id (default: gpt-4o-mini | gemini-3.5-flash-lite)

Gemini uses the native generateContent API (faster + JSON mode via
responseMimeType); OpenAI uses the standard chat.completions API.

AGENT_MODE:
  replay  - serve from cache only (default; keyless, deterministic)
  record  - call the API for cache misses, store them
  live    - always call the API, no cache
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"

DEFAULT_MODELS = {"openai": "gpt-4o-mini", "gemini": "gemini-3.5-flash-lite"}
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/"


class CacheMiss(Exception):
    pass


class LLMError(RuntimeError):
    pass


def load_env() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()

_client = None


def mode() -> str:
    return os.environ.get("AGENT_MODE", "replay").strip().lower()


def provider() -> str:
    return os.environ.get("LLM_PROVIDER", "openai").strip().lower()


def base_url() -> str | None:
    explicit = os.environ.get("LLM_BASE_URL")
    if explicit:
        return explicit
    if provider() == "gemini":
        return GEMINI_API
    return None


def api_key() -> str | None:
    for n in ("LLM_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        v = os.environ.get(n)
        if v:
            return v
    return None


def model_name() -> str:
    return os.environ.get(
        "AGENT_MODEL", DEFAULT_MODELS.get(provider(), "gpt-4o-mini")
    ).strip()


def _cache_path(system: str, user: str, json_mode: bool, temperature: float) -> Path:
    payload = json.dumps(
        [provider(), base_url(), model_name(), temperature, json_mode, system, user],
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


# ---------------------------------------------------------------- providers

def _call_gemini(system: str, user: str, json_mode: bool, temperature: float) -> str:
    import httpx

    key = api_key()
    if not key:
        raise LLMError("no API key - set LLM_API_KEY in .env or use AGENT_MODE=replay")
    gen: dict = {"temperature": temperature}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen,
    }
    url = f"{base_url() or GEMINI_API}models/{model_name()}:generateContent"

    last = ""
    for attempt in range(5):
        try:
            r = httpx.post(
                url, json=body, headers={"x-goog-api-key": key}, timeout=90
            )
        except httpx.HTTPError as exc:
            last = f"network error: {exc}"
            time.sleep(min(2**attempt, 15))
            continue
        if r.status_code == 200:
            data = r.json()
            try:
                parts = data["candidates"][0]["content"]["parts"]
            except (KeyError, IndexError) as exc:
                raise LLMError(f"malformed response: {json.dumps(data)[:300]}") from exc
            text = "".join(
                p.get("text", "") for p in parts if not p.get("thought", False)
            )
            if not text:
                raise LLMError(f"empty response: {json.dumps(data)[:300]}")
            return text
        if r.status_code in (429, 503):
            last = f"HTTP {r.status_code}: {r.text[:160]}"
            time.sleep(min(2**attempt * 2, 20))
            continue
        raise LLMError(f"HTTP {r.status_code}: {r.text[:400]}")
    raise LLMError(f"LLM unavailable after retries ({last})")


def _openai_client():
    global _client
    if _client is None:
        from openai import OpenAI

        key = api_key()
        if not key:
            raise LLMError(
                "No API key found. Put LLM_API_KEY in .env, or run with "
                "AGENT_MODE=replay to use the recorded cache."
            )
        _client = OpenAI(api_key=key, base_url=os.environ.get("LLM_BASE_URL") or None,
                         timeout=90, max_retries=2)
    return _client


def _call_openai(system: str, user: str, json_mode: bool, temperature: float) -> str:
    kwargs: dict = {
        "model": model_name(),
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    last: Exception | None = None
    for attempt in range(4):
        try:
            resp = _openai_client().chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as exc:
            last = exc
            msg = str(exc).lower()
            if "response_format" in msg:
                kwargs.pop("response_format", None)
                continue
            time.sleep(min(2**attempt, 15))
    raise LLMError(f"LLM call failed: {last}")


def _call(system: str, user: str, json_mode: bool, temperature: float) -> str:
    if provider() == "gemini":
        return _call_gemini(system, user, json_mode, temperature)
    return _call_openai(system, user, json_mode, temperature)


def chat(
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    temperature: float = 0.0,
) -> str:
    CACHE_DIR.mkdir(exist_ok=True)
    path = _cache_path(system, user, json_mode, temperature)

    if mode() in ("replay", "record") and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    if mode() == "replay":
        raise CacheMiss(
            f"no cached response for prompt {path.stem[:12]}... - "
            "run with AGENT_MODE=record (and a key in .env) to record it"
        )

    text = _call(system, user, json_mode, temperature)

    path.write_text(
        json.dumps(
            {
                "provider": provider(),
                "model": model_name(),
                "temperature": temperature,
                "json_mode": json_mode,
                "system": system,
                "user": user,
                "response": text,
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return text
