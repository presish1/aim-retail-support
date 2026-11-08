"""Versioned, approved support-guide retrieval. BM25 runs locally; no customer data is indexed."""

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STOP = set(
    "a an the is are was were i me my we you your it its this that to of for in on at be do does can could would should please and or with have has about just".split()
)
ALIASES = {
    "refunds": "refund",
    "returns": "return",
    "photos": "photo",
    "pictures": "photo",
    "picture": "photo",
    "images": "photo",
    "image": "photo",
    "shipment": "parcel",
    "shipping": "delivery",
    "arrive": "delivery",
    "arrived": "delivery",
    "arriving": "delivery",
    "delayed": "late",
    "overdue": "late",
    "pincode": "pin",
    "tags": "tag",
    "tight": "fit",
    "small": "fit",
    "big": "fit",
    "exchange": "swap",
    "human": "agent",
    "person": "agent",
    "washed": "wash",
    "wore": "worn",
}


def tokens(text):
    return [
        ALIASES.get(t, t)
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if t not in STOP
    ]


class GuideIndex:
    def __init__(self, path=None):
        self.path = Path(path or ROOT / "data/support-guides.json")
        self.signature = None
        self.refresh()

    def refresh(self):
        signature = (self.path.stat().st_mtime_ns, self.path.stat().st_size)
        if signature == self.signature:
            return
        raw = self.path.read_bytes()
        source = json.loads(raw)
        docs = source["documents"]
        if not source.get("version") or len({d["id"] for d in docs}) != len(docs):
            raise ValueError("Support guide requires a version and unique chunk IDs")
        for doc in docs:
            if (
                not re.fullmatch(r"[a-z_]+", doc["id"])
                or not doc.get("answer")
                or not doc.get("topics")
            ):
                raise ValueError("Invalid approved support guide")
        self.version, self.documents = source["version"], docs
        self.by_id = {d["id"]: d for d in docs}
        self.bags = [
            Counter(
                tokens(
                    " ".join([d["title"], *d["questions"], *d["topics"], d["answer"]])
                )
            )
            for d in docs
        ]
        self.lengths = [sum(b.values()) for b in self.bags]
        self.average_length = sum(self.lengths) / max(1, len(docs))
        self.df = Counter(word for bag in self.bags for word in bag)
        self.digest = hashlib.sha256(raw).hexdigest()[:12]
        self.signature = signature

    def search(self, query, topics=(), limit=4):
        self.refresh()
        terms = Counter(tokens(query))
        ranked = []
        topic_set = set(topics)
        filter_by_topic = bool(topic_set) and any(
            topic_set & set(d["topics"]) for d in self.documents
        )
        for doc, bag, length in zip(self.documents, self.bags, self.lengths):
            if filter_by_topic and not topic_set & set(doc["topics"]):
                continue
            score = 0.0
            for word, count in terms.items():
                freq = bag[word]
                if freq:
                    idf = math.log(
                        1
                        + (len(self.documents) - self.df[word] + 0.5)
                        / (self.df[word] + 0.5)
                    )
                    score += (
                        min(count, 2)
                        * idf
                        * freq
                        * 2.2
                        / (freq + 1.2 * (0.25 + 0.75 * length / self.average_length))
                    )
            topic_match = len(topic_set & set(doc["topics"]))
            score += 5 * topic_match
            if score > 0:
                ranked.append(
                    {
                        **doc,
                        "score": round(score, 4),
                        "version": self.version,
                        "source": "data/support-guides.json",
                        "digest": self.digest,
                    }
                )
        return sorted(ranked, key=lambda d: (-d["score"], d["id"]))[:limit]

    @staticmethod
    def evidence(documents):
        return [
            {
                k: d[k]
                for k in (
                    "id",
                    "title",
                    "version",
                    "source",
                    "digest",
                    "score",
                    "semantic_score",
                    "lexical_score",
                )
                if k in d
            }
            for d in documents
        ]


guides = GuideIndex()
