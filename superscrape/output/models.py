"""Pydantic data models for scraped content."""

from __future__ import annotations

import re

from pydantic import BaseModel, model_validator


class ProductImage(BaseModel):
    url: str
    image_id: str
    hi_res_url: str


class Review(BaseModel):
    text: str
    stars: float
    author: str = ""
    date: str = ""
    verified: bool = False


class ScrapedItem(BaseModel):
    """Any scraped product/listing with images."""

    platform: str = ""
    item_id: str = ""
    title: str = ""
    price: str = ""
    price_cents: int | None = None
    rating: float = 0.0
    reviews_count: int = 0
    images: list[ProductImage] = []
    url: str = ""

    @property
    def main_image_url(self) -> str | None:
        """Return the first hi-res image URL, if any."""
        return self.images[0].hi_res_url if self.images else None


class AplusImage(BaseModel):
    """An A+ / Enhanced Brand Content image."""

    url: str
    module_type: str = ""  # e.g. "standard-image", "comparison", "brand-story"
    alt_text: str = ""
    width: int = 0
    height: int = 0


class AmazonProduct(ScrapedItem):
    platform: str = "amazon"
    asin: str = ""
    description: str = ""
    features: list[str] = []
    brand: str = ""
    category: str = ""
    bsr: str = ""
    aplus_images: list[AplusImage] = []
    reviews: list[Review] = []

    @model_validator(mode="after")
    def _sync_ids_and_parse_price(self) -> "AmazonProduct":
        # Sync asin <-> item_id
        if self.asin and not self.item_id:
            self.item_id = self.asin
        elif self.item_id and not self.asin:
            self.asin = self.item_id

        # Parse price cents
        if self.price_cents is None and self.price:
            match = re.search(r"[\d,]+\.?\d*", self.price.replace(",", ""))
            if match:
                try:
                    self.price_cents = round(float(match.group()) * 100)
                except ValueError:
                    pass
        return self

    @property
    def main_image_url(self) -> str | None:
        """Pick best main image -- skip tiny Amazon thumbnails.

        Amazon image IDs starting with 1x/2x/3x are often small UI elements.
        Real product photos start with 4x+ (41xxx, 51xxx, 61xxx, 71xxx, 81xxx, 91xxx).
        """
        for img in self.images:
            first_char = img.image_id[0] if img.image_id else "0"
            if first_char in ("4", "5", "6", "7", "8", "9", "A", "B", "C"):
                return img.hi_res_url
        return self.images[0].hi_res_url if self.images else None


class AmazonSearchResult(BaseModel):
    asin: str
    title: str
    price: str = ""
    rating: float = 0.0
    reviews_count: int = 0
    image_url: str = ""
    url: str = ""
    sponsored: bool = False


class InstagramProfile(BaseModel):
    username: str
    full_name: str = ""
    bio: str = ""
    followers: int = 0
    following: int = 0
    posts_count: int = 0
    profile_pic_url: str = ""
    is_verified: bool = False


class InstagramPost(BaseModel):
    shortcode: str
    image_url: str = ""
    caption: str = ""
    likes: int = 0
    comments: int = 0
    timestamp: str = ""
    is_video: bool = False
    url: str = ""


class RedditPost(BaseModel):
    id: str
    title: str
    author: str = ""
    score: int = 0
    num_comments: int = 0
    url: str = ""
    selftext: str = ""
    created_utc: float = 0.0
    subreddit: str = ""


class ImageAnalysis(BaseModel):
    """Result of AI visual analysis of a product image."""

    image_url: str
    asin: str = ""
    item_id: str = ""
    image_type: str = ""  # white_bg, lifestyle, infographic, model, flat_lay
    angle: str = ""  # front, 45deg, top, side
    has_text: bool = False
    has_person: bool = False
    background: str = ""  # white, scene, studio, outdoor
    dominant_colors: list[str] = []
    description: str = ""
    selling_point_angle: str = ""  # feature_highlight, benefit_demo, social_proof, etc.
    info_hierarchy: str = ""  # product_hero, primary_feature, secondary_detail, etc.
    text_coverage_pct: int = 0  # 0-100% of image area covered by text/graphics
    confidence: float | None = None

    @model_validator(mode="after")
    def _sync_ids(self) -> "ImageAnalysis":
        if self.asin and not self.item_id:
            self.item_id = self.asin
        elif self.item_id and not self.asin:
            self.asin = self.item_id
        return self


class CategoryVisualReport(BaseModel):
    """Aggregated visual intelligence for a product category."""

    keyword: str
    platform: str = "amazon"
    total_products: int = 0
    total_images: int = 0
    image_type_distribution: dict[str, float] = {}
    angle_distribution: dict[str, float] = {}
    has_person_ratio: float = 0.0
    has_text_ratio: float = 0.0
    background_distribution: dict[str, float] = {}
    recommendations: list[str] = []
    product_analyses: list[dict] = []


class BenchmarkData(BaseModel):
    """Category-level benchmark from 80K pre-analyzed clothing images."""

    category: str = ""
    matched_categories: list[str] = []
    total_products: int = 0
    total_images: int = 0
    image_type_distribution: dict[str, float] = {}
    angle_distribution: dict[str, float] = {}
    background_distribution: dict[str, float] = {}
    has_person_ratio: float = 0.0
    has_text_ratio: float = 0.0
    top_style_tags: list[str] = []
    quality_avg: float = 0.0
    missing_slots_ranking: dict[str, float] = {}
    aplus_adoption_rate: float = 0.0
    aplus_avg_score: float = 0.0
    price_tier_distribution: dict[str, float] = {}
    top_reverse_prompts: list[dict] = []


# Alias for generic usage
VisualReport = CategoryVisualReport
