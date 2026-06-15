"""
Evaluation endpoints.
POST /api/v1/eval/run — run the gold set through the pipeline
GET /api/v1/eval/metrics — retrieve evaluation metrics
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import QueryLog, Chunk
from services.embeddings import embed_query
from services.hybrid_search import hybrid_search

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["eval"])


class EvalQuestion(BaseModel):
    id: int
    question: str
    expected_answer: str = ""
    relevant_chunk_ids: list[int] = []


class EvalResult(BaseModel):
    question_id: int
    question: str
    retrieved_chunk_ids: list[int]
    recall_at_5: float
    recall_at_10: float
    precision_at_5: float


class EvalMetricsResponse(BaseModel):
    total_questions: int
    avg_recall_at_5: float
    avg_recall_at_10: float
    avg_precision_at_5: float


@router.get("/eval/metrics", response_model=EvalMetricsResponse)
async def get_eval_metrics(
    session: AsyncSession = Depends(get_session),
) -> EvalMetricsResponse:
    gold_path = Path(__file__).parent.parent / "eval" / "gold_set.json"
    if not gold_path.exists():
        return EvalMetricsResponse(
            total_questions=0, avg_recall_at_5=0.0,
            avg_recall_at_10=0.0, avg_precision_at_5=0.0,
        )

    with open(gold_path) as f:
        questions = json.load(f)

    recalls_5 = []
    recalls_10 = []
    precisions_5 = []

    for q in questions[:50]:
        qid = q.get("id")
        question_text = q.get("question", "")
        relevant_ids = set(q.get("relevant_chunk_ids", []))
        if not relevant_ids:
            continue

        query_emb = await embed_query(question_text)
        results = await hybrid_search(
            session, question_text, query_emb, top_k=10,
        )
        retrieved_ids = [r.chunk_id for r in results]

        retrieved_set = set(retrieved_ids)
        true_positives_5 = len(relevant_ids & set(retrieved_ids[:5]))
        true_positives_10 = len(relevant_ids & set(retrieved_ids[:10]))

        recall_5 = true_positives_5 / len(relevant_ids) if relevant_ids else 0
        recall_10 = true_positives_10 / len(relevant_ids) if relevant_ids else 0
        precision_5 = true_positives_5 / 5 if retrieved_ids else 0

        recalls_5.append(recall_5)
        recalls_10.append(recall_10)
        precisions_5.append(precision_5)

    n = len(recalls_5) or 1
    return EvalMetricsResponse(
        total_questions=n,
        avg_recall_at_5=sum(recalls_5) / n,
        avg_recall_at_10=sum(recalls_10) / n,
        avg_precision_at_5=sum(precisions_5) / n,
    )
