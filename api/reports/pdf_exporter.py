"""PDF export via Playwright Chromium."""

from __future__ import annotations

import logging

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


def export_pdf(html_path: str, pdf_path: str) -> None:
    """Convert a self-contained HTML file to PDF using headless Chromium.

    Uses Playwright's Chromium for full CSS Grid, @media print,
    and custom header/footer support — matching browser rendering exactly.

    Args:
        html_path: Absolute path to the source HTML file.
        pdf_path: Absolute path where the PDF should be written.

    Raises:
        RuntimeError: If PDF generation fails.
    """
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(f"file://{html_path}", wait_until="networkidle", timeout=30_000)

            page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={
                    "top": "0.6in",
                    "bottom": "0.8in",
                    "left": "0.5in",
                    "right": "0.5in",
                },
                display_header_footer=True,
                header_template=(
                    '<div style="font-size:8px;color:#9CA3AF;width:100%;'
                    'text-align:center;font-family:Inter,sans-serif;">'
                    "SuperScrape — Visual Intelligence"
                    "</div>"
                ),
                footer_template=(
                    '<div style="font-size:8px;color:#9CA3AF;width:100%;'
                    'text-align:center;font-family:Inter,sans-serif;">'
                    'Page <span class="pageNumber"></span>'
                    ' of <span class="totalPages"></span>'
                    "</div>"
                ),
            )

            browser.close()

        logger.info("PDF exported via Playwright Chromium: %s", pdf_path)

    except Exception as exc:
        raise RuntimeError(f"Playwright PDF export failed: {exc}") from exc
