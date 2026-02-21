"""Pydantic models for the Scout API."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Language(str, Enum):
    en = "en"
    zh = "zh"


class Platform(str, Enum):
    amazon = "amazon"
    walmart = "walmart"
    ebay = "ebay"
    etsy = "etsy"
    shopee = "shopee"
    tiktok_shop = "tiktok_shop"


class JobRequest(BaseModel):
    """Input model for creating a new scraping job."""

    platform: Platform = Field(
        default=Platform.amazon,
        description="Target platform: 'amazon', 'shopee', or 'tiktok_shop'",
    )
    query: str = Field(
        default="",
        description="Search keyword, product ID, or URL",
        examples=["portable blender", "B0ABC12345"],
    )
    asin_or_url: str = Field(
        default="",
        description="(Deprecated) Use 'query' instead. Amazon ASIN or URL.",
    )
    top_n: int = Field(
        default=10,
        ge=10,
        le=50,
        description="Number of top products to scrape (10-50)",
    )
    language: Language = Field(
        default=Language.en,
        description="Report language: 'en' or 'zh'",
    )
    generate_lifestyle: bool = Field(
        default=False,
        description="Generate Seedream lifestyle images for top products",
    )

    @model_validator(mode="after")
    def _finalize(self) -> "JobRequest":
        # Legacy backward compat: copy asin_or_url -> query
        if not self.query and self.asin_or_url:
            self.query = self.asin_or_url

        self.query = self.query.strip()

        if not self.query:
            raise ValueError("'query' is required (or legacy 'asin_or_url')")

        # Amazon-specific: extract ASIN from full URL
        if self.platform == Platform.amazon:
            match = re.search(r"(?:/dp/|/gp/product/|/product/)([A-Z0-9]{10})", self.query)
            if match:
                self.query = match.group(1)

        return self


class PipelineStep(str, Enum):
    queued = "queued"
    scraping = "scraping"
    analyzing = "analyzing"
    generating = "generating"
    building_report = "building_report"
    done = "done"
    failed = "failed"


class ProgressEvent(BaseModel):
    """A single SSE progress event pushed to the client."""

    step: PipelineStep
    message: str
    progress: int = Field(ge=0, le=100, description="Overall progress (0-100)")
    detail: dict[str, Any] = Field(default_factory=dict)


class JobStatus(BaseModel):
    """Full status snapshot for a job, returned on poll or at stream end."""

    job_id: str
    step: PipelineStep = PipelineStep.queued
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    report_url: str | None = None
    pdf_url: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    completed_at: datetime | None = None
