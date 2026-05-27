"""Run route namespace."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/runs", tags=["runs"])
