"""Native provider contract, secret-safe failures and hybrid retrieval integrity. No paid calls."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from backend.gemini import generate_json
from backend.hybrid import HybridRetriever, normalize
from backend.model import ModelUnavailable
from backend.retrieval import GuideIndex


def adapter():
    return SimpleNamespace(
        provider="gemini",
        model="gemini-3.8-flash",
        key="private-test-key",
        url="https://generativelanguage.googleapis.com/v1beta",
    )


def mock_http(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )


def generate(client):
    return asyncio.run(
        generate_json(
            client,
            [
                {"role": "system", "content": "Support /no_think"},
                {"role": "user", "content": "Hello"},
            ],
            {"type": "object"},
        )
    )


def test_native_gemini_contract_and_usage(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        assert request.headers["x-goog-api-key"] == "private-test-key"
        assert "private-test-key" not in str(request.url)
        config = body["generationConfig"]
        assert (
            not {"temperature", "topP", "topK", "chat_template_kwargs"} & config.keys()
        )
        assert config["thinkingConfig"] == {"thinkingLevel": "LOW"}
        assert body["contents"][0]["role"] == "user"
        assert "/no_think" not in body["systemInstruction"]["parts"][0]["text"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"text": "internal reasoning", "thought": True},
                                {"text": '{"ready":true}'},
                            ]
                        },
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 5,
                    "thoughtsTokenCount": 8,
                },
            },
        )

    mock_http(monkeypatch, handler)
    content, usage = generate(adapter())
    assert json.loads(content) == {"ready": True}
    assert usage == {"input_tokens": 10, "output_tokens": 13, "thinking_tokens": 8}


@pytest.mark.parametrize("status", [403, 429, 500])
def test_provider_errors_never_expose_response_or_key(monkeypatch, status):
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            status,
            json={"error": {"message": "private-test-key sensitive provider body"}},
        ),
    )
    with pytest.raises(ModelUnavailable) as error:
        generate(adapter())
    assert str(status) in str(error.value)
    assert "private-test-key" not in str(error.value) and "sensitive" not in str(
        error.value
    )


@pytest.mark.parametrize("reason", ["MAX_TOKENS", "SAFETY"])
def test_incomplete_generation_is_not_accepted(monkeypatch, reason):
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"candidates": [{"finishReason": reason}]}
        ),
    )
    with pytest.raises(ModelUnavailable, match="incomplete or blocked"):
        generate(adapter())


def test_bad_provider_json_falls_back(monkeypatch):
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "not JSON"}]},
                    }
                ]
            },
        ),
    )
    with pytest.raises(ModelUnavailable):
        generate(adapter())


def index_at(tmp_path):
    source = {
        "version": "v1",
        "documents": [
            {
                "id": "alpha",
                "title": "Delivery",
                "topics": ["delivery"],
                "questions": ["parcel track"],
                "answer": "Check the parcel.",
            },
            {
                "id": "beta",
                "title": "Tags",
                "topics": ["tags"],
                "questions": ["tag garment"],
                "answer": "Garment tags differ from packaging.",
            },
        ],
    }
    path = tmp_path / "guides.json"
    path.write_text(json.dumps(source))
    return GuideIndex(path), source


def test_semantic_retrieval_cache_and_corpus_invalidation(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADLINE_SEMANTIC_RAG", "true")
    index, source = index_at(tmp_path)
    retriever = HybridRetriever(adapter(), tmp_path / "vectors")
    calls = []

    async def embed(texts, task):
        calls.append((texts, task))
        return (
            [[1.0] + [0.0] * 767, [0.0, 1.0] + [0.0] * 766]
            if task == "RETRIEVAL_DOCUMENT"
            else [[0.0, 1.0] + [0.0] * 766]
        )

    monkeypatch.setattr(retriever, "embed", embed)
    query = "unrecognized expression customer@example.com 9000000101"
    docs, meta = asyncio.run(retriever.search(index, query))
    assert docs[0]["id"] == "beta" and meta["document_cache"] == "built"
    assert docs[0]["semantic_score"] == 1
    assert (
        "customer@example.com" not in calls[-1][0][0]
        and "9000000101" not in calls[-1][0][0]
    )
    _, meta = asyncio.run(retriever.search(index, query))
    assert meta["document_cache"] == "hit"
    assert sum(task == "RETRIEVAL_DOCUMENT" for _, task in calls) == 1
    for path in (tmp_path / "vectors").glob("*.json"):
        assert (
            "customer@example.com" not in path.read_text()
            and "unrecognized" not in path.read_text()
        )
    source["version"] = "v2"
    index.path.write_text(json.dumps(source))
    docs, meta = asyncio.run(retriever.search(index, query))
    assert meta["document_cache"] == "built" and docs[0]["version"] == "v2"
    assert sum(task == "RETRIEVAL_DOCUMENT" for _, task in calls) == 2
    docs, _ = asyncio.run(retriever.search(index, query, topics=["delivery"]))
    assert [d["id"] for d in docs] == ["alpha"]


def test_embedding_failure_keeps_approved_lexical_retrieval(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADLINE_SEMANTIC_RAG", "true")
    index, _ = index_at(tmp_path)
    retriever = HybridRetriever(adapter(), tmp_path / "vectors")

    async def fail(*args):
        raise httpx.ReadTimeout("private-test-key must not be exposed")

    monkeypatch.setattr(retriever, "embed", fail)
    docs, meta = asyncio.run(retriever.search(index, "garment tag"))
    assert docs[0]["id"] == "beta" and meta["fallback_reason"]
    assert "private-test-key" not in json.dumps(meta)


def test_corpus_change_during_embedding_does_not_mix_versions(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADLINE_SEMANTIC_RAG", "true")
    index, source = index_at(tmp_path)
    retriever = HybridRetriever(adapter(), tmp_path / "vectors")

    async def embed(texts, task):
        if task == "RETRIEVAL_DOCUMENT":
            return [[1.0] + [0.0] * 767] * 2
        source["version"] = "v2"
        index.path.write_text(json.dumps(source))
        return [[1.0] + [0.0] * 767]

    monkeypatch.setattr(retriever, "embed", embed)
    docs, meta = asyncio.run(retriever.search(index, "garment tag"))
    assert meta["fallback_reason"] and meta["embedding_model"] is None
    assert docs[0]["version"] == "v2" and docs[0]["digest"] == index.digest


@pytest.mark.parametrize("vector", [[], [0, 0], [float("nan"), 1], [float("inf"), 1]])
def test_invalid_embedding_never_enters_index(vector):
    with pytest.raises(ValueError):
        normalize(vector)
