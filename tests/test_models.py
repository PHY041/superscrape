"""Tests for Pydantic data models."""

from superscrape.output.models import (
    AmazonProduct,
    AmazonSearchResult,
    CategoryVisualReport,
    ImageAnalysis,
    InstagramPost,
    InstagramProfile,
    ProductImage,
    RedditPost,
    ScrapedItem,
)


def test_product_image_creation():
    img = ProductImage(url="https://example.com/img.jpg", image_id="41ABC", hi_res_url="https://example.com/img_hi.jpg")
    assert img.url == "https://example.com/img.jpg"
    assert img.image_id == "41ABC"


def test_scraped_item_main_image_url():
    item = ScrapedItem(images=[
        ProductImage(url="u1", image_id="id1", hi_res_url="hi1"),
    ])
    assert item.main_image_url == "hi1"


def test_scraped_item_no_images():
    item = ScrapedItem()
    assert item.main_image_url is None


def test_amazon_product_syncs_asin_to_item_id():
    p = AmazonProduct(asin="B0CX23V2ZK", title="Test Product")
    assert p.item_id == "B0CX23V2ZK"
    assert p.platform == "amazon"


def test_amazon_product_syncs_item_id_to_asin():
    p = AmazonProduct(item_id="B0CX23V2ZK")
    assert p.asin == "B0CX23V2ZK"


def test_amazon_product_parses_price_cents():
    p = AmazonProduct(asin="B001", price="$29.99")
    assert p.price_cents == 2999


def test_amazon_product_parses_price_no_decimal():
    p = AmazonProduct(asin="B001", price="$30")
    assert p.price_cents == 3000


def test_amazon_product_main_image_skips_thumbnails():
    p = AmazonProduct(
        asin="B001",
        images=[
            ProductImage(url="u1", image_id="1xABC", hi_res_url="thumb"),
            ProductImage(url="u2", image_id="41DEF", hi_res_url="real"),
        ],
    )
    assert p.main_image_url == "real"


def test_amazon_search_result():
    r = AmazonSearchResult(asin="B001", title="Test", price="$10", rating=4.5, reviews_count=100)
    assert r.asin == "B001"
    assert r.rating == 4.5


def test_instagram_profile():
    p = InstagramProfile(username="testuser", followers=1000, is_verified=True)
    assert p.username == "testuser"
    assert p.is_verified is True


def test_instagram_post():
    p = InstagramPost(shortcode="ABC123", likes=500)
    assert p.shortcode == "ABC123"
    assert p.is_video is False


def test_reddit_post():
    p = RedditPost(id="abc123", title="Test Post", score=42, subreddit="test")
    assert p.score == 42
    assert p.subreddit == "test"


def test_image_analysis_syncs_ids():
    a = ImageAnalysis(image_url="http://example.com/img.jpg", asin="B001")
    assert a.item_id == "B001"

    a2 = ImageAnalysis(image_url="http://example.com/img.jpg", item_id="B002")
    assert a2.asin == "B002"


def test_category_visual_report_defaults():
    r = CategoryVisualReport(keyword="test")
    assert r.platform == "amazon"
    assert r.total_products == 0
    assert r.recommendations == []


def test_category_visual_report_with_data():
    r = CategoryVisualReport(
        keyword="blender",
        total_products=10,
        total_images=50,
        image_type_distribution={"white_bg": 60.0, "lifestyle": 30.0},
        has_person_ratio=25.0,
    )
    assert r.total_images == 50
    assert r.image_type_distribution["white_bg"] == 60.0
