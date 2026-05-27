"""Template route namespace."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import TemplatesResponse
from core.templates import list_templates

router = APIRouter(prefix="/api", tags=["templates"])


@router.get("/templates", response_model=TemplatesResponse)
def get_templates() -> TemplatesResponse:
    """Return public template metadata."""

    return TemplatesResponse(items=list_templates())
