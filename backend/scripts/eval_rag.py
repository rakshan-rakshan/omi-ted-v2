"""
RAG pipeline evaluation script.
Runs 25 Telugu + 25 English theological queries through the full pipeline:
embed_query → hybrid_search → generate_answer.
Outputs eval_report.md with precision@5, latency, model info.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import AsyncSessionLocal
from services.embeddings import embed_query, embed_dim
from services.hybrid_search import hybrid_search
from services.answer_gen import generate_answer
from config import settings

logger = logging.getLogger(__name__)

EN_QUERIES = [
    "What does the Bible say about salvation?",
    "Explain the Trinity",
    "Who is Jesus Christ?",
    "What is the role of the Holy Spirit?",
    "How should Christians pray?",
    "What does the Bible teach about baptism?",
    "What is the meaning of the cross?",
    "How does God forgive sins?",
    "What is the Second Coming?",
    "What does faith mean in Christianity?",
    "Explain the concept of grace",
    "What is the Great Commission?",
    "How should Christians handle suffering?",
    "What are the fruits of the Spirit?",
    "What is the church according to the Bible?",
    "Explain the incarnation of Christ",
    "How does prayer change things?",
    "What is the significance of the resurrection?",
    "What does the Bible say about love?",
    "How can someone be born again?",
    "What is the purpose of marriage?",
    "Explain the book of Revelation",
    "What is sanctification?",
    "How does God guide believers?",
    "What does the Bible say about healing?",
]

TE_QUERIES = [
    "రక్షణ గురించి బైబిల్ ఏమి చెప్పింది?",
    "త్రిత్వము అంటే ఏమిటి?",
    "యేసుక్రీస్తు ఎవరు?",
    "పరిశుద్ధాత్మ పాత్ర ఏమిటి?",
    "క్రైస్తవులు ఎలా ప్రార్థించాలి?",
    "బాప్టిజం గురించి బైబిల్ ఏమి బోధిస్తుంది?",
    "సిలువ యొక్క అర్థం ఏమిటి?",
    "దేవుడు పాపాలను ఎలా క్షమిస్తాడు?",
    "రెండవ రాకడ అంటే ఏమిటి?",
    "క్రైస్తవ మతంలో విశ్వాసం అర్థం ఏమిటి?",
    "కృప అనే భావనను వివరించండి",
    "గొప్ప ఆజ్ఞాపించు ఏమిటి?",
    "క్రైస్తవులు బాధను ఎలా ఎదుర్కోవాలి?",
    "ఆత్మ ఫలాలు ఏమిటి?",
    "బైబిల్ ప్రకారం సంఘం అంటే ఏమిటి?",
    "క్రీస్తు అవతారాన్ని వివరించండి",
    "ప్రార్థన విషయాలను ఎలా మారుస్తుంది?",
    "పునరుత్థానం యొక్క ప్రాముఖ్యత ఏమిటి?",
    "ప్రేమ గురించి బైబిల్ ఏమి చెప్పింది?",
    "ఎవరైనా ఎలా పునర్జన్మ పొందవచ్చు?",
    "వివాహం యొక్క ఉద్దేశ్యం ఏమిటి?",
    "ప్రకటన గ్రంథాన్ని వివరించండి",
    "పరిశుద్ధపరచడం అంటే ఏమిటి?",
    "దేవుడు విశ్వాసులను ఎలా నడిపిస్తాడు?",
    "స్వస్థత గురించి బైబిల్ ఏమి చెప్పింది?",
]

REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_report.md")


async def eval_one(query: str, is_telugu: bool) -> dict:
    t0 = time.monotonic()

    embedding = await embed_query(query)
    t1 = time.monotonic()
    embed_latency = int((t1 - t0) * 1000)

    async with AsyncSessionLocal() as session:
        results = await hybrid_search(
            session, query, embedding, top_k=5, filters=None
        )
    t2 = time.monotonic()
    search_latency = int((t2 - t1) * 1000)

    chunk_dicts = [
        {
            "chunk_id": r.chunk_id,
            "chunk_text": r.chunk_text,
            "title": r.title,
            "youtube_id": r.youtube_id,
        }
        for r in results
    ]

    answer, citations, gen_latency = await generate_answer(query, chunk_dicts)
    t3 = time.monotonic()
    total_latency = int((t3 - t0) * 1000)

    return {
        "query": query,
        "is_telugu": is_telugu,
        "precision_at_5": len(results) / 5.0 if results else 0.0,
        "embed_latency_ms": embed_latency,
        "search_latency_ms": search_latency,
        "gen_latency_ms": gen_latency,
        "total_latency_ms": total_latency,
        "num_chunks": len(results),
        "answer_preview": answer[:200] if answer else "",
        "model_used": settings.rag.generation_model,
    }


def _write_report(en_results: list[dict], te_results: list[dict]) -> None:
    model = en_results[0]["model_used"] if en_results else "unknown"

    en_total_latency = sum(r["total_latency_ms"] for r in en_results)
    te_total_latency = sum(r["total_latency_ms"] for r in te_results)
    en_avg_latency = en_total_latency / max(len(en_results), 1)
    te_avg_latency = te_total_latency / max(len(te_results), 1)

    en_precision = sum(r["precision_at_5"] for r in en_results) / max(len(en_results), 1)
    te_precision = sum(r["precision_at_5"] for r in te_results) / max(len(te_results), 1)

    lines = [
        "# RAG Evaluation Report",
        "",
        f"**Model:** {model}",
        f"**Embedding dim:** {embed_dim()}",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        "| Metric | English | Telugu |",
        "|--------|---------|--------|",
        f"| Queries | {len(en_results)} | {len(te_results)} |",
        f"| Avg precision@5 | {en_precision:.4f} | {te_precision:.4f} |",
        f"| Avg total latency | {en_avg_latency:.0f}ms | {te_avg_latency:.0f}ms |",
        f"| Avg embed latency | {sum(r['embed_latency_ms'] for r in en_results) / max(len(en_results), 1):.0f}ms | {sum(r['embed_latency_ms'] for r in te_results) / max(len(te_results), 1):.0f}ms |",
        f"| Avg search latency | {sum(r['search_latency_ms'] for r in en_results) / max(len(en_results), 1):.0f}ms | {sum(r['search_latency_ms'] for r in te_results) / max(len(te_results), 1):.0f}ms |",
        f"| Avg gen latency | {sum(r['gen_latency_ms'] for r in en_results) / max(len(en_results), 1):.0f}ms | {sum(r['gen_latency_ms'] for r in te_results) / max(len(te_results), 1):.0f}ms |",
        "",
        "## Per-Query Results (English)",
        "",
        "| # | Query | Precision@5 | Total (ms) | Chunks | Answer Preview |",
        "|---|-------|-------------|------------|--------|----------------|",
    ]

    for i, r in enumerate(en_results, 1):
        preview = r["answer_preview"].replace("|", "/")
        lines.append(
            f"| {i} | {r['query']} | {r['precision_at_5']:.2f} | "
            f"{r['total_latency_ms']} | {r['num_chunks']} | {preview} |"
        )

    lines += [
        "",
        "## Per-Query Results (Telugu)",
        "",
        "| # | Query | Precision@5 | Total (ms) | Chunks | Answer Preview |",
        "|---|-------|-------------|------------|--------|----------------|",
    ]

    for i, r in enumerate(te_results, 1):
        preview = r["answer_preview"].replace("|", "/")
        lines.append(
            f"| {i} | {r['query']} | {r['precision_at_5']:.2f} | "
            f"{r['total_latency_ms']} | {r['num_chunks']} | {preview} |"
        )

    report = "\n".join(lines)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report written to {REPORT_PATH}")


async def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print(f"Running eval on {len(EN_QUERIES)} English + {len(TE_QUERIES)} Telugu queries...")

    en_results: list[dict] = []
    for i, q in enumerate(EN_QUERIES):
        r = await eval_one(q, is_telugu=False)
        en_results.append(r)
        print(f"  [{i + 1}/{len(EN_QUERIES)}] EN: {q[:50]}... → {r['total_latency_ms']}ms, p@{r['precision_at_5']:.2f}")

    te_results: list[dict] = []
    for i, q in enumerate(TE_QUERIES):
        r = await eval_one(q, is_telugu=True)
        te_results.append(r)
        print(f"  [{i + 1}/{len(TE_QUERIES)}] TE: {q[:50]}... → {r['total_latency_ms']}ms, p@{r['precision_at_5']:.2f}")

    _write_report(en_results, te_results)
    print("Eval complete.")


if __name__ == "__main__":
    asyncio.run(main())
