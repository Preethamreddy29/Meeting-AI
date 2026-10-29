"""FastAPI routes for the reviewed Meeting-to-Action workflow."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.database import create_job, update_job
from src.jobs import submit_job
from src.meeting_actions import (
    change_item,
    create_notes,
    export_csv,
    extract_and_save,
    get_meeting_context,
    list_items,
    list_runs,
    set_meeting_context,
    source_document,
)


router = APIRouter(prefix="/api/actions", tags=["Meeting Actions"])


class NotesPayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=250_000)
    meeting_date: str | None = None
    timezone: str | None = Field(default=None, max_length=100)


class ExtractPayload(BaseModel):
    acknowledge_existing_reviewed: bool = False


class MeetingContextPayload(BaseModel):
    meeting_date: str | None = None
    timezone: str | None = Field(default=None, max_length=100)


class EvidencePayload(BaseModel):
    source_unit_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=2000)


class ItemChangePayload(BaseModel):
    version: int = Field(gt=0)
    description: str | None = Field(default=None, max_length=2000)
    owner: str | None = Field(default=None, max_length=250)
    due_date_text: str | None = Field(default=None, max_length=250)
    evidence: list[EvidencePayload] | None = Field(
        default=None, min_length=1, max_length=5
    )
    review_status: str | None = None


@router.post("/notes", status_code=201)
def notes(payload: NotesPayload):
    try:
        meeting_id = create_notes(
            payload.title,
            payload.text,
            payload.meeting_date,
            payload.timezone,
        )
        return {"meeting_id": meeting_id}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/meetings/{meeting_id}/runs")
def runs(meeting_id: int = Path(gt=0)):
    try:
        get_meeting_context(meeting_id)
        return {"runs": list_runs(meeting_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/meetings/{meeting_id}/context")
def meeting_context(meeting_id: int = Path(gt=0)):
    try:
        return get_meeting_context(meeting_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/meetings/{meeting_id}/context")
def update_meeting_context(
    payload: MeetingContextPayload,
    meeting_id: int = Path(gt=0),
):
    try:
        return set_meeting_context(
            meeting_id, payload.meeting_date, payload.timezone
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/meetings/{meeting_id}/extract", status_code=202)
def extract(payload: ExtractPayload, meeting_id: int = Path(gt=0)):
    try:
        source_document(meeting_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing_runs = list_runs(meeting_id)
    has_reviewed = any((run["reviewed_count"] or 0) > 0 for run in existing_runs)
    if has_reviewed and not payload.acknowledge_existing_reviewed:
        raise HTTPException(
            status_code=409,
            detail=(
                "This meeting has reviewed items. Regeneration creates a new draft run; "
                "existing runs remain available. Confirm regeneration to continue."
            ),
        )

    job_id = "actions-" + uuid4().hex
    create_job(job_id, "action_extraction", "Queued for Gemini extraction")

    def work():
        run_id = extract_and_save(meeting_id)
        update_job(
            job_id,
            status="done",
            message="Draft actions are ready for review",
            result={"run_id": run_id, "meeting_id": meeting_id},
        )

    submit_job(job_id, work)
    return {"job_id": job_id}


@router.get("/meetings/{meeting_id}/items")
def items(
    meeting_id: int = Path(gt=0),
    run_id: int | None = Query(default=None, gt=0),
):
    try:
        return list_items(meeting_id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/items/{item_id}")
def update_item(payload: ItemChangePayload, item_id: int = Path(gt=0)):
    fields = payload.model_dump(exclude_unset=True, exclude={"version"})
    if fields.get("evidence") is not None:
        fields["evidence"] = [entry.model_dump() for entry in payload.evidence]
    try:
        return change_item(item_id, payload.version, fields)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/meetings/{meeting_id}/export")
def export(
    meeting_id: int = Path(gt=0),
    run_id: int | None = Query(default=None, gt=0),
):
    try:
        content = export_csv(meeting_id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="meeting_{meeting_id}_approved_actions.csv"'
            )
        },
    )
