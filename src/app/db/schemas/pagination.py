"""Pagination schemas.

Based on BrowserStack Test Management API pagination pattern.
Provides PaginationParams, PaginationInfo, and PaginatedResponse.
"""

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination query parameters."""

    p: int = Field(
        default=1,
        ge=1,
        description="Page number, starting from 1",
    )
    page_size: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Per-page count, default 30, max 300",
    )

    @property
    def page(self) -> int:
        """Current page number (alias for p)."""
        return self.p

    @property
    def offset(self) -> int:
        """Calculate offset for database query."""
        return (self.p - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Limit for database query."""
        return self.page_size


class PaginationInfo(BaseModel):
    """Pagination metadata for responses."""

    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Per-page count")
    count: Optional[int] = Field(default=None, description="Records on current page")
    total: int = Field(..., description="Total record count")
    prev: Optional[str] = Field(default=None, description="Previous page URL")
    next: Optional[str] = Field(default=None, description="Next page URL")

    @classmethod
    def create(
        cls,
        page: int,
        page_size: int,
        total: int,
        base_url: str,
    ) -> "PaginationInfo":
        """Create PaginationInfo with computed prev/next links.

        Args:
            page: Current page number.
            page_size: Per-page count.
            total: Total record count.
            base_url: Base URL for link construction.

        Returns:
            PaginationInfo instance with computed links.
        """
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        count = min(page_size, max(0, total - (page - 1) * page_size))

        prev_url = None
        next_url = None

        if page > 1:
            prev_url = f"{base_url}?p={page - 1}&page_size={page_size}"

        if page < total_pages:
            next_url = f"{base_url}?p={page + 1}&page_size={page_size}"

        return cls(
            page=page,
            page_size=page_size,
            count=count,
            total=total,
            prev=prev_url,
            next=next_url,
        )


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response with data list and pagination metadata.

    Supports both `info` and `pagination` as field name (alias).
    """

    success: bool = Field(default=True, description="API call succeeded")
    info: PaginationInfo = Field(
        default=None,
        alias="pagination",
        description="Pagination info",
    )
    data: list[T] = Field(default_factory=list, description="Data list")

    model_config = {"populate_by_name": True}
