"""
Glossary endpoints.

GET    /api/v1/glossary                    — list all terms (filterable by category)
POST   /api/v1/glossary                    — create a new term (one term, many meanings)
POST   /api/v1/glossary/bulk               — upsert many terms (one-click save)
PATCH  /api/v1/glossary/{id}              — update a term
DELETE /api/v1/glossary/{id}              — delete a term
GET    /api/v1/glossary/lookup?te={word}  — quick lookup for editor hints

A term can have MANY English meanings (stored as a JSON list in `meanings`).
`en_term` is kept as the PRIMARY meaning (= meanings[0]) so GlossaryApplier's
single-replacement and any pre-meanings rows keep working unchanged.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import GlossaryTerm

router = APIRouter(tags=["glossary"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GlossaryResponse(BaseModel):
    id: int
    te_term: str
    en_term: str            # primary meaning (meanings[0])
    meanings: list[str]     # all English meanings, primary first
    category: str
    notes: str | None


class GlossaryCreate(BaseModel):
    te_term: str
    en_term: str | None = None          # back-compat: single meaning
    meanings: list[str] | None = None   # preferred: one-or-many meanings
    category: str = "general"
    notes: str | None = None


class GlossaryPatch(BaseModel):
    te_term: str | None = None
    en_term: str | None = None
    meanings: list[str] | None = None
    category: str | None = None
    notes: str | None = None


class GlossaryBulkItem(BaseModel):
    te_term: str
    meanings: list[str]
    category: str = "general"
    notes: str | None = None


class GlossaryBulkRequest(BaseModel):
    terms: list[GlossaryBulkItem]


class GlossaryBulkResponse(BaseModel):
    created: int
    updated: int
    skipped: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {"theology", "name", "place", "general"}


def _meanings_of(term: GlossaryTerm) -> list[str]:
    """Parse the JSON meanings list, falling back to [en_term] for old rows."""
    if term.meanings:
        try:
            parsed = json.loads(term.meanings)
            if isinstance(parsed, list):
                cleaned = [str(m).strip() for m in parsed if str(m).strip()]
                if cleaned:
                    return cleaned
        except (json.JSONDecodeError, TypeError):
            pass
    return [term.en_term] if term.en_term else []


def _to_response(term: GlossaryTerm) -> GlossaryResponse:
    return GlossaryResponse(
        id=term.id,
        te_term=term.te_term,
        en_term=term.en_term,
        meanings=_meanings_of(term),
        category=term.category,
        notes=term.notes,
    )


def _clean_meanings(raw: list[str] | None) -> list[str]:
    seen: list[str] = []
    for m in raw or []:
        s = (m or "").strip()
        if s and s not in seen:
            seen.append(s)
    return seen


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/glossary", response_model=list[GlossaryResponse])
async def list_glossary(
    category: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> list[GlossaryResponse]:
    """Return all glossary terms, optionally filtered by category."""
    q = select(GlossaryTerm).order_by(GlossaryTerm.te_term)
    if category:
        q = q.where(GlossaryTerm.category == category)
    result = await session.execute(q)
    return [_to_response(t) for t in result.scalars().all()]


@router.get("/glossary/lookup", response_model=list[GlossaryResponse])
async def lookup_glossary(
    te: str = Query(..., description="Telugu word or phrase to look up"),
    session: AsyncSession = Depends(get_session),
) -> list[GlossaryResponse]:
    """Quick lookup for the editor — returns terms where te_term contains `te`."""
    result = await session.execute(
        select(GlossaryTerm)
        .where(GlossaryTerm.te_term.contains(te))
        .order_by(GlossaryTerm.te_term)
        .limit(10)
    )
    return [_to_response(t) for t in result.scalars().all()]


@router.post("/glossary", response_model=GlossaryResponse, status_code=201)
async def create_term(
    body: GlossaryCreate,
    session: AsyncSession = Depends(get_session),
) -> GlossaryResponse:
    """Create a new glossary term with one or many meanings."""
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(422, detail=f"category must be one of {sorted(VALID_CATEGORIES)}")

    meanings = _clean_meanings(body.meanings)
    if not meanings and body.en_term:
        meanings = _clean_meanings([body.en_term])
    if not meanings:
        raise HTTPException(422, detail="Provide en_term or at least one meaning.")

    te_term = body.te_term.strip()
    if not te_term:
        raise HTTPException(422, detail="te_term is required.")

    existing = await session.execute(
        select(GlossaryTerm).where(GlossaryTerm.te_term == te_term)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail=f"Term '{te_term}' already exists in the glossary.")

    term = GlossaryTerm(
        te_term=te_term,
        en_term=meanings[0],
        meanings=json.dumps(meanings, ensure_ascii=False),
        category=body.category,
        notes=body.notes,
    )
    session.add(term)
    await session.commit()
    await session.refresh(term)
    return _to_response(term)


@router.post("/glossary/bulk", response_model=GlossaryBulkResponse)
async def bulk_upsert(
    body: GlossaryBulkRequest,
    session: AsyncSession = Depends(get_session),
) -> GlossaryBulkResponse:
    """Upsert many terms at once (one-click 'save selected'). Merges meanings into
    existing terms (union, primary preserved); creates new ones otherwise."""
    created = updated = skipped = 0
    for item in body.terms:
        te_term = item.te_term.strip()
        meanings = _clean_meanings(item.meanings)
        if not te_term or not meanings:
            skipped += 1
            continue
        category = item.category if item.category in VALID_CATEGORIES else "general"

        existing = (
            await session.execute(select(GlossaryTerm).where(GlossaryTerm.te_term == te_term))
        ).scalar_one_or_none()

        if existing:
            merged = _meanings_of(existing)
            for m in meanings:
                if m not in merged:
                    merged.append(m)
            existing.en_term = merged[0]
            existing.meanings = json.dumps(merged, ensure_ascii=False)
            if item.notes:
                existing.notes = item.notes
            updated += 1
        else:
            session.add(GlossaryTerm(
                te_term=te_term,
                en_term=meanings[0],
                meanings=json.dumps(meanings, ensure_ascii=False),
                category=category,
                notes=item.notes,
            ))
            created += 1
    await session.commit()
    return GlossaryBulkResponse(created=created, updated=updated, skipped=skipped)


@router.patch("/glossary/{term_id}", response_model=GlossaryResponse)
async def update_term(
    term_id: int,
    body: GlossaryPatch,
    session: AsyncSession = Depends(get_session),
) -> GlossaryResponse:
    """Update a glossary term (including its meanings list)."""
    result = await session.execute(select(GlossaryTerm).where(GlossaryTerm.id == term_id))
    term = result.scalar_one_or_none()
    if term is None:
        raise HTTPException(404, detail=f"Term {term_id} not found.")

    if body.te_term is not None:
        term.te_term = body.te_term.strip()
    if body.meanings is not None:
        meanings = _clean_meanings(body.meanings)
        if not meanings:
            raise HTTPException(422, detail="meanings cannot be empty.")
        term.meanings = json.dumps(meanings, ensure_ascii=False)
        term.en_term = meanings[0]
    elif body.en_term is not None:
        # Single-meaning edit: set primary, keep the rest of the list intact.
        rest = [m for m in _meanings_of(term) if m != term.en_term]
        meanings = _clean_meanings([body.en_term, *rest])
        term.en_term = meanings[0]
        term.meanings = json.dumps(meanings, ensure_ascii=False)
    if body.category is not None:
        if body.category not in VALID_CATEGORIES:
            raise HTTPException(422, detail=f"category must be one of {sorted(VALID_CATEGORIES)}")
        term.category = body.category
    if body.notes is not None:
        term.notes = body.notes

    await session.commit()
    await session.refresh(term)
    return _to_response(term)


@router.delete("/glossary/{term_id}", status_code=204, response_class=Response)
async def delete_term(
    term_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a glossary term."""
    result = await session.execute(select(GlossaryTerm).where(GlossaryTerm.id == term_id))
    term = result.scalar_one_or_none()
    if term is None:
        raise HTTPException(404, detail=f"Term {term_id} not found.")
    await session.delete(term)
    await session.commit()
    return Response(status_code=204)
