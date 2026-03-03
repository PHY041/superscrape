"""Benchmark API routes — category-level visual intelligence from 80K images."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.services.benchmark_service import (
    get_benchmark,
    get_categories,
    get_reverse_prompts,
    get_top_gaps,
)

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("/categories")
async def list_categories() -> list[dict]:
    """List all available benchmark categories with product/image counts."""
    return get_categories()


@router.get("/{category}")
async def category_benchmark(category: str) -> dict:
    """Get full benchmark data for a category (matched via keyword)."""
    bench = get_benchmark(category)
    if bench is None:
        return {"error": f"No benchmark data found for '{category}'"}
    return bench.model_dump()


@router.get("/{category}/top-gaps")
async def category_top_gaps(
    category: str,
    limit: int = Query(default=5, ge=1, le=20),
) -> list[dict]:
    """Get the biggest opportunity gaps for a category."""
    return get_top_gaps(category, limit=limit)


@router.get("/{category}/reverse-prompts")
async def category_reverse_prompts(
    category: str,
    type: str = Query(default="", description="Filter by image type (e.g. lifestyle, model)"),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict]:
    """Get reference reverse prompts for a category."""
    return get_reverse_prompts(category, image_type=type, limit=limit)
