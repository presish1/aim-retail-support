"""Native Gemini REST boundary. Keys stay in headers; errors contain no provider payloads."""

import json

import httpx

from .model import ModelUnavailable


async def generate_json(adapter, messages, schema):
    if not adapter.key:
        raise ModelUnavailable("Gemini API key is missing; supported fallback used.")
    systems = [
        m["content"].replace("/no_think", "") for m in messages if m["role"] == "system"
    ]
    contents = [
        {
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [{"text": m["content"]}],
        }
        for m in messages
        if m["role"] != "system"
    ]
    payload = {
        "systemInstruction": {"parts": [{"text": "\n\n".join(systems)}]},
        "contents": contents,
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
            "thinkingConfig": {"thinkingLevel": "LOW"},
            "maxOutputTokens": 2048,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.post(
                adapter.url + "/models/" + adapter.model + ":generateContent",
                headers={"x-goog-api-key": adapter.key},
                json=payload,
            )
            if not response.is_success:
                raise ModelUnavailable(
                    f"Gemini request failed (HTTP {response.status_code}); supported fallback used."
                )
            data = response.json()
        candidate = data.get("candidates", [])[0]
        if candidate.get("finishReason") != "STOP":
            raise ModelUnavailable(
                "Gemini response incomplete or blocked; supported fallback used."
            )
        content = "".join(
            p.get("text", "")
            for p in candidate["content"]["parts"]
            if not p.get("thought")
        )
        json.loads(content)
        usage = data.get("usageMetadata", {})
        return content, {
            "input_tokens": usage.get("promptTokenCount", 0),
            "output_tokens": usage.get("candidatesTokenCount", 0)
            + usage.get("thoughtsTokenCount", 0),
            "thinking_tokens": usage.get("thoughtsTokenCount", 0),
        }
    except ModelUnavailable:
        raise
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise ModelUnavailable(
            "Gemini unavailable or invalid; supported fallback used."
        ) from exc
