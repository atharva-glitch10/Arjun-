"""Light RAG over the elder's own saved stories (CLAUDE.md boundaries 2 and 11).

Stories are embedded locally when they are saved and searched by cosine similarity. No API, no model download, no
text leaves the machine. The embedding is feature-hashed word + character n-grams: it finds stories that share words
and word parts with the question (it works on Devanagari without a tokenizer) but it is NOT a semantic model, so a
paraphrase with no shared words will not match. Swapping `embed()` for a real model changes nothing else.

Only stored story text is ever returned: Arjun may refer to a past story only from these rows, never invent one.
Search is elder-side (private stories included); the family reads shared stories only, via /memory-book.
"""

import hashlib
import math
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import JSON, ForeignKey, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from . import models as m
from .db import Base, get_db
from .deps import require_key

DIM = 512
MIN_SCORE = 0.2  # below this a match is noise: better to remember nothing than something unrelated
_WORD = re.compile(r"[\wऀ-ॿ]+", re.UNICODE)


class StoryEmbedding(Base):
    __tablename__ = "story_embeddings"
    story_id: Mapped[int] = mapped_column(ForeignKey("story_memories.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    vector: Mapped[list[float]] = mapped_column(JSON)


def _bucket(token: str) -> tuple[int, float]:
    h = int.from_bytes(hashlib.blake2b(token.encode("utf8"), digest_size=8).digest(), "big")
    return h % DIM, 1.0 if (h >> 63) & 1 else -1.0


def embed(text: str) -> list[float]:
    """L2-normalised hashed bag of words (weight 2) and in-word character trigrams (weight 1)."""
    vec = [0.0] * DIM
    for word in _WORD.findall(unicodedata.normalize("NFKC", text).casefold()):
        i, sign = _bucket("w:" + word)
        vec[i] += 2.0 * sign
        padded = f"^{word}$"
        for k in range(len(padded) - 2):
            i, sign = _bucket("c:" + padded[k : k + 3])
            vec[i] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def index_story(db: Session, story: m.StoryMemory) -> None:
    """Store (or refresh) the embedding for one story. Call after the story row has an id."""
    row = db.get(StoryEmbedding, story.id)
    vec = embed(story.summary)
    if row is None:
        db.add(StoryEmbedding(story_id=story.id, user_id=story.user_id, vector=vec))
    else:
        row.vector = vec


def drop_story(db: Session, story_id: int) -> None:
    row = db.get(StoryEmbedding, story_id)
    if row is not None:
        db.delete(row)


def search(db: Session, user_id: int, query: str, k: int = 3) -> list[tuple[m.StoryMemory, float]]:
    stories = list(db.scalars(select(m.StoryMemory).where(m.StoryMemory.user_id == user_id)))
    have = {e.story_id: e for e in db.scalars(select(StoryEmbedding).where(StoryEmbedding.user_id == user_id))}
    for st in stories:  # backfill stories saved before the index existed
        if st.id not in have:
            index_story(db, st)
    if len(have) != len(stories):
        db.flush()
        have = {e.story_id: e for e in db.scalars(select(StoryEmbedding).where(StoryEmbedding.user_id == user_id))}
    q = embed(query)
    scored = [(st, _cosine(q, have[st.id].vector)) for st in stories if st.id in have]
    scored = [x for x in scored if x[1] >= MIN_SCORE]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


class StoryHit(BaseModel):
    id: int
    summary: str
    score: float


router = APIRouter(dependencies=[Depends(require_key)])


@router.get("/users/{user_id}/stories/search", response_model=list[StoryHit])
def search_stories(
    user_id: int, q: str = Query(min_length=1, max_length=300), k: int = Query(3, ge=1, le=10), db: Session = Depends(get_db)
) -> list[StoryHit]:
    """Elder-side only (voice session): her own stories most related to `q`, best first. Empty when nothing is related."""
    if db.get(m.User, user_id) is None:
        raise HTTPException(404, "user not found")
    hits = search(db, user_id, q, k)
    db.commit()  # persists any backfilled embeddings
    return [StoryHit(id=st.id, summary=st.summary, score=round(score, 3)) for st, score in hits]
