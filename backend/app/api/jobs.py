import re
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from pydantic import BaseModel, field_validator

from app.core.config import settings
from app.schemas.story import StoryGenerationRequest
from app.services import temp_cleanup
from app.services.job_repository import (
    JobRepository,
    JobStoreUnavailable,
    UserJobLimitReached,
    public_view,
)


router = APIRouter()

UNAVAILABLE_MESSAGE = "قائمة الانتظار غير متاحة مؤقتًا. يرجى المحاولة بعد قليل."
LIMIT_MESSAGE = "وصلت إلى الحد الأقصى للطلبات قيد المعالجة ({limit}). يرجى انتظار اكتمال أحدها ثم المحاولة مرة أخرى."

_repository: Optional[JobRepository] = None


def get_job_repository() -> JobRepository:
    """One shared repository. Building it never touches MongoDB, so the API starts even if it is down."""
    global _repository
    if _repository is None:
        _repository = JobRepository.connect()
    return _repository


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class JobCreateRequest(StoryGenerationRequest):
    job_id: Optional[str] = None
    # Who is asking, as the web app knows them. Needed for the per-user limit and duplicate check.
    user_id: Optional[str] = None

    @field_validator("story_id")
    @classmethod
    def story_id_is_safe_in_a_path(cls, value):
        # The id names the Job's working folder, so it must never be able to point elsewhere.
        if value is not None and not SAFE_ID.match(value):
            raise ValueError("story_id must be letters, digits, '-' or '_' (at most 64 characters)")
        return value


class JobCancelRequest(BaseModel):
    user_id: str


@router.post("/jobs", status_code=202)
def create_job(req: JobCreateRequest, response: Response, repository: JobRepository = Depends(get_job_repository)):
    story_id = req.story_id
    if not story_id:
        raise HTTPException(status_code=422, detail="story_id مطلوب لإنشاء مهمة توليد.")
    request = req.model_dump(exclude={"job_id", "user_id"})
    try:
        job, duplicate = repository.submit(story_id, request, user_id=req.user_id, job_id=req.job_id)
    except UserJobLimitReached as exc:
        raise HTTPException(status_code=429, detail=LIMIT_MESSAGE.format(limit=exc.limit))
    except JobStoreUnavailable:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE)
    view = public_view(job)
    if duplicate:
        # The same request is already queued or running: nothing new was queued.
        response.status_code = 200
        view["duplicate"] = True
    return view


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, body: JobCancelRequest, repository: JobRepository = Depends(get_job_repository)):
    """Cancel a Job that is still waiting in the queue. One that is already running cannot be cancelled."""
    try:
        outcome = repository.cancel(job_id, body.user_id)
        job = repository.get(job_id)
    except JobStoreUnavailable:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE)
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="مهمة التوليد غير موجودة.")
    if outcome == "forbidden":
        raise HTTPException(status_code=403, detail="لا تملك صلاحية إلغاء هذه المهمة.")
    if outcome == "not_cancellable":
        if job and job["state"] == "running":
            raise HTTPException(status_code=409, detail="لا يمكن إلغاء مهمة قيد التنفيذ.")
        raise HTTPException(status_code=409, detail="لا يمكن إلغاء مهمة انتهت بالفعل.")
    if job.get("story_id"):
        temp_cleanup.remove_work_dir(job["story_id"])  # a cancelled Job's files are not needed any more
    return public_view(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, repository: JobRepository = Depends(get_job_repository)):
    try:
        job = repository.get(job_id)
    except JobStoreUnavailable:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE)
    if job is None:
        raise HTTPException(status_code=404, detail="مهمة التوليد غير موجودة.")
    return public_view(job)


@router.post("/jobs/{job_id}/requeue")
def requeue_job(
    job_id: str,
    x_admin_token: Optional[str] = Header(None),
    repository: JobRepository = Depends(get_job_repository),
):
    """Admin only: queue a failed or dead-lettered Job again. Stages that finished are reused."""
    token = settings.JOB_ADMIN_TOKEN
    if not token or not x_admin_token or not secrets.compare_digest(x_admin_token, token):
        raise HTTPException(status_code=403, detail="غير مصرح لك بإعادة تشغيل المهام.")
    try:
        job = repository.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="مهمة التوليد غير موجودة.")
        if not repository.requeue(job_id):
            raise HTTPException(status_code=409, detail="لا يمكن إعادة تشغيل إلا مهمة فشلت أو توقفت بعد استنفاد المحاولات.")
        return public_view(repository.get(job_id))
    except JobStoreUnavailable:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE)


@router.get("/notebooklm/status")
def notebooklm_status(repository: JobRepository = Depends(get_job_repository)):
    """Is NotebookLM usable? When a login has expired or the quota is reached this says so, and how many Jobs wait."""
    try:
        flag = repository.get_service_flag()
        parked = repository.parked_counts()
    except JobStoreUnavailable:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE)

    def iso(value):
        return value.isoformat() if value is not None else None

    return {
        "status": flag["status"] if flag else "ok",
        "since": iso(flag.get("since")) if flag else None,
        "resume_at": iso(flag.get("resume_at")) if flag else None,
        "message": flag.get("message") if flag else None,
        "parked_jobs": parked,
        "action": "run `npm run auth` to log in again" if flag and flag["status"] == "needs_login" else None,
    }
