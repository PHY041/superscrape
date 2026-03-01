"""Amazon SP-API integration stub — placeholder for Selling Partner API access.

Agent 4 dependency: requires customer OAuth authorization to access
Business Reports, Brand Analytics, advertising data, and FBA reports.

This module provides the interface definitions and mock implementations
so that the rest of the system can be built against it. Real SP-API
integration requires:
1. Amazon Developer registration
2. SP-API application approval
3. Customer OAuth consent flow
4. LWA (Login with Amazon) token refresh
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SPAPIStatus(str, Enum):
    not_configured = "not_configured"
    pending_auth = "pending_auth"
    authorized = "authorized"
    expired = "expired"


@dataclass
class SPAPIConfig:
    """SP-API connection configuration."""

    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    marketplace_id: str = "ATVPDKIKX0DER"  # US marketplace
    status: SPAPIStatus = SPAPIStatus.not_configured


@dataclass
class BusinessReport:
    """Daily business report metrics for an ASIN."""

    asin: str = ""
    date: str = ""
    sessions: int = 0
    page_views: int = 0
    units_ordered: int = 0
    ordered_product_sales: float = 0.0
    conversion_rate: float = 0.0
    buy_box_pct: float = 0.0


@dataclass
class BrandAnalyticsData:
    """Brand Analytics search term data."""

    search_term: str = ""
    search_frequency_rank: int = 0
    top_clicked_asins: list[str] = field(default_factory=list)
    top_converted_asins: list[str] = field(default_factory=list)
    click_share: float = 0.0
    conversion_share: float = 0.0


class SPAPIClient:
    """Stub SP-API client — returns mock data until real credentials are configured."""

    def __init__(self, config: SPAPIConfig | None = None) -> None:
        self._config = config or SPAPIConfig()

    @property
    def is_configured(self) -> bool:
        return self._config.status == SPAPIStatus.authorized

    def get_auth_url(self) -> str:
        """Return OAuth consent URL for customer authorization."""
        if not self._config.client_id:
            return ""
        return (
            f"https://sellercentral.amazon.com/apps/authorize/consent"
            f"?application_id={self._config.client_id}"
        )

    def get_business_report(
        self,
        asin: str,
        start_date: date,
        end_date: date,
    ) -> list[BusinessReport]:
        """Fetch daily business reports for an ASIN.

        Requires: SP-API Reports API with reportType=GET_SALES_AND_TRAFFIC_REPORT
        """
        if not self.is_configured:
            logger.info("SP-API not configured — returning mock business report")
            return [
                BusinessReport(
                    asin=asin,
                    date=start_date.isoformat(),
                    sessions=0,
                    page_views=0,
                    units_ordered=0,
                    conversion_rate=0.0,
                ),
            ]
        # TODO: Implement real SP-API call
        raise NotImplementedError("Real SP-API integration pending")

    def get_brand_analytics(
        self,
        search_term: str,
        report_date: date,
    ) -> BrandAnalyticsData | None:
        """Fetch Brand Analytics search term report.

        Requires: Brand Analytics API access (brand-registered sellers only).
        """
        if not self.is_configured:
            logger.info("SP-API not configured — returning mock brand analytics")
            return BrandAnalyticsData(search_term=search_term)
        raise NotImplementedError("Real SP-API integration pending")

    def get_return_reasons(
        self,
        asin: str,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Fetch FBA return reasons for an ASIN.

        Requires: FBA Reports API with reportType=GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA
        """
        if not self.is_configured:
            logger.info("SP-API not configured — returning empty returns data")
            return []
        raise NotImplementedError("Real SP-API integration pending")

    def get_advertising_report(
        self,
        campaign_ids: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        """Fetch Sponsored Products advertising performance.

        Requires: Amazon Ads API (separate from SP-API).
        """
        if not self.is_configured:
            logger.info("SP-API not configured — returning empty ad data")
            return []
        raise NotImplementedError("Real Ads API integration pending")


# Module-level singleton
sp_api = SPAPIClient()
