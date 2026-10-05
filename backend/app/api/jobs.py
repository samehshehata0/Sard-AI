from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.story import StoryGenerationRequest
from app.services.job_repository import JobRepository, JobStoreUnavailable, public_view


router = APIRouter()

UNAVAILABLE_MESSAGE = "قائمة الانتظار غير متاحة مؤقتًا. يرجى المحاولة بعد قليل."

_repository: Optional[JobRepository] = None


def get_job_repository() -> JobRepository:
    """One shared repository. Building it never touches MongoDB, so the API starts even if it is down."""
    global _repository
    if _repository is None:
        _repository = JobRepository.connect()
    return _repository


class JobCreateRequest(StoryGenerationRequest):
    job_id: Optional[str] = None


@router.post("/jobs", status_code=202)
def create_job(req: JobCreateRequest, repository: JobRepository = Depends(get_job_repository)):
    story_id = req.story_id
    if not story_id:
        raise HTTPException(status_code=422, detail="story_id مطلوب لإنشاء مهمة توليد.")
    request = req.model_dump(exclude={"job_id"})
    try:
        job = repository.enqueue(story_id, request, job_id=req.job_id)
    except JobStoreUnavailable:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE)
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
