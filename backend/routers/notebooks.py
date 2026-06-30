"""
Notebooks — user-curated collections of messages (videos) to scope Q&A to.
The "NotebookLM" layer: build a collection, then ask questions answered only
from those sermons.

Mounted under /api/v1:
  POST   /notebooks                      {name, description?}
  GET    /notebooks                      — list with message_count
  GET    /notebooks/{nid}                — notebook + member messages
  DELETE /notebooks/{nid}
  POST   /notebooks/{nid}/messages       {message_id? | youtube_id?}
  DELETE /notebooks/{nid}/messages/{message_id}
  GET    /notebooks/messages/available   — indexed messages eligible to add
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import Chunk, Message, Notebook, NotebookMessage, Video

router = APIRouter(tags=["notebooks"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class NotebookCreate(BaseModel):
    name: str
    description: str | None = None


class AddMessageRequest(BaseModel):
    message_id: int | None = None
    youtube_id: str | None = None


class NotebookOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime | None = None
    message_count: int = 0


class NotebookMessageOut(BaseModel):
    message_id: int
    title: str | None = None
    youtube_id: str | None = None


class NotebookDetail(NotebookOut):
    messages: list[NotebookMessageOut] = []


# ---------------------------------------------------------------------------
# Shared helper (imported by routers/search.py to scope retrieval)
# ---------------------------------------------------------------------------

async def notebook_message_ids(session: AsyncSession, notebook_id: int) -> list[int]:
    """Return the message ids belonging to a notebook."""
    rows = (await session.execute(
        select(NotebookMessage.message_id).where(NotebookMessage.notebook_id == notebook_id)
    )).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/notebooks", response_model=NotebookOut)
async def create_notebook(
    body: NotebookCreate,
    session: AsyncSession = Depends(get_session),
) -> NotebookOut:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(422, detail="Notebook name is required.")
    nb = Notebook(name=name, description=body.description)
    session.add(nb)
    await session.commit()
    await session.refresh(nb)
    return NotebookOut(
        id=nb.id, name=nb.name, description=nb.description,
        created_at=nb.created_at, message_count=0,
    )


@router.get("/notebooks", response_model=list[NotebookOut])
async def list_notebooks(
    session: AsyncSession = Depends(get_session),
) -> list[NotebookOut]:
    notebooks = (await session.execute(
        select(Notebook).order_by(Notebook.id.desc())
    )).scalars().all()
    counts = dict((await session.execute(
        select(NotebookMessage.notebook_id, func.count(NotebookMessage.id))
        .group_by(NotebookMessage.notebook_id)
    )).all())
    return [
        NotebookOut(
            id=n.id, name=n.name, description=n.description,
            created_at=n.created_at, message_count=counts.get(n.id, 0),
        )
        for n in notebooks
    ]


@router.get("/notebooks/messages/available")
async def available_messages(
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Indexed messages (have >=1 chunk) eligible to add to a notebook."""
    counts = dict((await session.execute(
        select(Chunk.message_id, func.count(Chunk.id)).group_by(Chunk.message_id)
    )).all())
    if not counts:
        return []
    rows = (await session.execute(
        select(Message.id, Message.title, Video.youtube_id)
        .join(Video, Video.id == Message.video_id, isouter=True)
        .where(Message.id.in_(list(counts.keys())))
        .order_by(Message.title)
    )).all()
    return [
        {"message_id": r[0], "title": r[1], "youtube_id": r[2], "chunk_count": counts.get(r[0], 0)}
        for r in rows
    ]


@router.get("/notebooks/{nid}", response_model=NotebookDetail)
async def get_notebook(
    nid: int,
    session: AsyncSession = Depends(get_session),
) -> NotebookDetail:
    nb = (await session.execute(
        select(Notebook).where(Notebook.id == nid)
    )).scalar_one_or_none()
    if nb is None:
        raise HTTPException(404, detail="Notebook not found.")
    rows = (await session.execute(
        select(Message.id, Message.title, Video.youtube_id)
        .join(NotebookMessage, NotebookMessage.message_id == Message.id)
        .join(Video, Video.id == Message.video_id, isouter=True)
        .where(NotebookMessage.notebook_id == nid)
        .order_by(Message.id)
    )).all()
    messages = [NotebookMessageOut(message_id=r[0], title=r[1], youtube_id=r[2]) for r in rows]
    return NotebookDetail(
        id=nb.id, name=nb.name, description=nb.description,
        created_at=nb.created_at, message_count=len(messages), messages=messages,
    )


@router.delete("/notebooks/{nid}")
async def delete_notebook(
    nid: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await session.execute(delete(NotebookMessage).where(NotebookMessage.notebook_id == nid))
    await session.execute(delete(Notebook).where(Notebook.id == nid))
    await session.commit()
    return {"deleted": nid}


@router.post("/notebooks/{nid}/messages")
async def add_message(
    nid: int,
    body: AddMessageRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    nb = (await session.execute(
        select(Notebook.id).where(Notebook.id == nid)
    )).scalar_one_or_none()
    if nb is None:
        raise HTTPException(404, detail="Notebook not found.")

    mid = body.message_id
    if mid is None and body.youtube_id:
        mid = (await session.execute(
            select(Message.id)
            .join(Video, Video.id == Message.video_id)
            .where(Video.youtube_id == body.youtube_id)
        )).scalar_one_or_none()
        if mid is None:
            raise HTTPException(
                404,
                detail=f"No indexed message for video {body.youtube_id} — run build_chunks first.",
            )
    if mid is None:
        raise HTTPException(422, detail="Provide message_id or youtube_id.")

    exists = (await session.execute(
        select(Message.id).where(Message.id == mid)
    )).scalar_one_or_none()
    if exists is None:
        raise HTTPException(404, detail=f"Message {mid} not found.")

    dup = (await session.execute(
        select(NotebookMessage.id).where(
            NotebookMessage.notebook_id == nid, NotebookMessage.message_id == mid
        )
    )).scalar_one_or_none()
    added = dup is None
    if added:
        session.add(NotebookMessage(notebook_id=nid, message_id=mid))
        await session.commit()
    return {"notebook_id": nid, "message_id": mid, "added": added}


@router.delete("/notebooks/{nid}/messages/{message_id}")
async def remove_message(
    nid: int,
    message_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await session.execute(
        delete(NotebookMessage).where(
            NotebookMessage.notebook_id == nid, NotebookMessage.message_id == message_id
        )
    )
    await session.commit()
    return {"notebook_id": nid, "message_id": message_id, "removed": True}
