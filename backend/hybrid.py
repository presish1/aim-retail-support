"""Small hybrid RAG: approved-guide vectors plus BM25, with an explicit lexical fallback.

Only approved document vectors are persisted. Query strings/vectors and operational
records are never added to the index. No local model download is required.
"""

import hashlib
import json
import math
import os
import re
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def normalize(vector):
    if not vector or any(
        not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector
    ):
        raise ValueError("Invalid embedding")
    length = math.sqrt(sum(v * v for v in vector))
    if not length:
        raise ValueError("Empty embedding")
    return [v / length for v in vector]


def redact_query(text):
    text = re.sub(r"\b[^\s@]+@[^\s@]+\b", "checkout contact", text)
    return re.sub(r"\+?\d[\d ()-]{3,}\d", "reference", text)[:1200]


class HybridRetriever:
    def __init__(self, adapter, cache_dir=None):
        self.adapter = adapter
        self.model = os.getenv("THREADLINE_EMBEDDING_MODEL", "gemini-embedding-001")
        self.dimension = 768
        self.cache_dir = Path(cache_dir or ROOT / "artifacts/local/retrieval")

    async def embed(self, texts, task):
        requests = [
            {
                "model": "models/" + self.model,
                "content": {"parts": [{"text": t}]},
                "taskType": task,
                "outputDimensionality": self.dimension,
            }
            for t in texts
        ]
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            response = await client.post(
                self.adapter.url + "/models/" + self.model + ":batchEmbedContents",
                headers={"x-goog-api-key": self.adapter.key},
                json={"requests": requests},
            )
            response.raise_for_status()
            values = [normalize(e["values"]) for e in response.json()["embeddings"]]
        if len(values) != len(texts) or any(len(v) != self.dimension for v in values):
            raise ValueError("Embedding shape mismatch")
        return values

    async def documents(self, index):
        digest = hashlib.sha256(
            (index.digest + self.model + str(self.dimension)).encode()
        ).hexdigest()
        path = self.cache_dir / (digest + ".json")
        ids = [d["id"] for d in index.documents]
        try:
            cached = json.loads(path.read_text())
            if cached["key"] == digest and cached["ids"] == ids:
                vectors = [normalize(v) for v in cached["vectors"]]
                if len(vectors) == len(ids) and all(
                    len(v) == self.dimension for v in vectors
                ):
                    return vectors, "hit"
        except (OSError, ValueError, KeyError, TypeError):
            pass
        texts = [
            d["title"] + "\n" + "\n".join(d["questions"]) + "\n" + d["answer"]
            for d in index.documents
        ]
        vectors = await self.embed(texts, "RETRIEVAL_DOCUMENT")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_dir / (uuid.uuid4().hex + ".tmp")
        temporary.write_text(
            json.dumps({"key": digest, "ids": ids, "vectors": vectors})
        )
        temporary.replace(path)
        return vectors, "built"

    async def search(self, index, query, topics=(), limit=4):
        lexical = index.search(query, topics, limit=len(index.documents))
        metadata = {
            "method": "BM25 + approved topic filter",
            "embedding_model": None,
            "document_cache": None,
            "fallback_reason": None,
        }
        if getattr(self.adapter, "provider", "") != "gemini" or not getattr(
            self.adapter, "key", ""
        ):
            return lexical[:limit], metadata
        if os.getenv("THREADLINE_SEMANTIC_RAG", "true").lower() != "true":
            metadata["fallback_reason"] = "Semantic retrieval disabled by configuration"
            return lexical[:limit], metadata
        try:
            corpus_digest = index.digest
            vectors, cache = await self.documents(index)
            query_vector = (await self.embed([redact_query(query)], "RETRIEVAL_QUERY"))[
                0
            ]
            index.refresh()
            if index.digest != corpus_digest:
                raise ValueError("Guide changed during semantic retrieval")
            topic_set = set(topics)
            restrict = bool(topic_set) and any(
                topic_set & set(d["topics"]) for d in index.documents
            )
            scored = [
                (d, sum(a * b for a, b in zip(v, query_vector)))
                for d, v in zip(index.documents, vectors)
                if not restrict or topic_set & set(d["topics"])
            ]
            semantic = sorted(scored, key=lambda x: (-x[1], x[0]["id"]))
            ranks = {d["id"]: (r, d["score"]) for r, d in enumerate(lexical, 1)}
            fused = []
            for rank, (doc, similarity) in enumerate(semantic, 1):
                lex_rank, lex_score = ranks.get(doc["id"], (None, 0))
                score = 1 / (60 + rank) + (1 / (60 + lex_rank) if lex_rank else 0)
                fused.append(
                    {
                        **doc,
                        "score": round(score, 6),
                        "semantic_score": round(similarity, 6),
                        "lexical_score": lex_score,
                        "version": index.version,
                        "digest": index.digest,
                        "source": "data/support-guides.json",
                    }
                )
            metadata.update(
                method="Hybrid BM25 + Gemini embeddings + reciprocal-rank fusion",
                embedding_model=self.model,
                dimension=self.dimension,
                document_cache=cache,
            )
            return sorted(fused, key=lambda d: (-d["score"], d["id"]))[:limit], metadata
        except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError):
            metadata["fallback_reason"] = (
                "Semantic retrieval unavailable; approved lexical retrieval used"
            )
            return index.search(query, topics, limit=limit), metadata
