"""Lightweight parser validation endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import ParseErrorResponse, ParseValidateRequest, ParseValidateResponse
from core.parser import ParseFailure, ParseSuccess, parse

router = APIRouter(prefix="/api/parse", tags=["parse"])


@router.post("/validate", response_model=ParseValidateResponse)
def validate_source(payload: ParseValidateRequest) -> ParseValidateResponse:
    """Parse source code into IR without queueing a run."""

    result = parse(payload.source_code)
    if isinstance(result, ParseSuccess):
        return ParseValidateResponse(ok=True, ir=result.ir.to_dict(), errors=[])
    if isinstance(result, ParseFailure):
        return ParseValidateResponse(
            ok=False,
            errors=[
                ParseErrorResponse(
                    message=error.message,
                    line=error.line,
                    column=error.column,
                )
                for error in result.errors
            ],
        )
    return ParseValidateResponse(
        ok=False,
        errors=[ParseErrorResponse(message="Unknown parser result")],
    )
