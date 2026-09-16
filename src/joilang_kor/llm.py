"""OpenAI 호환 chat/completions 엔드포인트 호출(얇은 HTTP 어댑터).

원본: local_llm_client.py 의 _call_openai_compatible /
_request_json. 원본의 다른 backend(HF worker 서브프로세스, 상주 worker)는 옮기지 않았다.
- endpoint, model, timeout 은 명시적으로 받는다. 실패하면 예외를 그대로 올린다(자동 대체 없음).
- 생성 설정: temperature=0, max_tokens=256 을 기본으로 보낸다. 원고의 do_sample=false 는 서버
  구현(예: vLLM 은 temperature=0 을 탐욕적 디코딩으로 처리)에 따라 표현되며, 이 어댑터는
  API 파라미터만 전달할 뿐 서버의 디코딩 구현을 검증하지 않는다.
- 인증 헤더는 환경변수 JOILANG_KOR_HTTP_AUTH_BEARER 가 있을 때만 보낸다(다른 변수는 읽지 않는다).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_MAX_TOKENS = 256
DEFAULT_TEMPERATURE = 0.0


class LLMCallError(RuntimeError):
    pass


def resolve_endpoint(endpoint: str) -> str:
    """`http://host:port/v1` 또는 전체 경로를 받아 chat/completions URL 로 만든다."""
    url = str(endpoint or "").strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


def _auth_headers() -> dict[str, str]:
    bearer = os.getenv("JOILANG_KOR_HTTP_AUTH_BEARER", "").strip()
    return {"Authorization": f"Bearer {bearer}"} if bearer else {}


def _request_json(url: str, payload: dict[str, Any], timeout_sec: int) -> dict[str, Any]:
    headers = {"Content-Type": "application/json", **_auth_headers()}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as response:
        body = response.read()
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LLMCallError(f"non-JSON response from {url}: {body[:300]!r}") from exc


def call_chat_completion(
    *,
    endpoint: str,
    model: str,
    system: str,
    user: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    """한 번 호출한다. 반환: content, prompt_tokens, completion_tokens, total_tokens, finish_reason."""
    url = resolve_endpoint(endpoint)
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        response = _request_json(url, payload, timeout_sec)
    except urllib.error.HTTPError as exc:
        raise LLMCallError(f"HTTP {exc.code} from {url}: {exc.read()[:300]!r}") from exc
    except urllib.error.URLError as exc:
        raise LLMCallError(f"cannot reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise LLMCallError(f"timeout after {timeout_sec}s: {url}") from exc
    try:
        choice = response["choices"][0]
        content = choice["message"]["content"]
        usage = response.get("usage") or {}
        counts = {k: int(usage.get(k, 0)) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise LLMCallError(f"unexpected payload from {url}: {str(response)[:300]}") from exc
    if not isinstance(content, str):
        raise LLMCallError(f"non-text content from {url}: {content!r}")
    return {"content": content, **counts, "finish_reason": str(choice.get("finish_reason", "") or "")}
