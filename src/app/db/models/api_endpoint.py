"""API endpoint model definition.

Stores OpenAPI/Swagger parsed API endpoint information with JSON
for flexible parameter, response, and security schemas.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class APIEndpoint(Base, UUIDMixin, TimestampMixin):
    """API endpoint definition table.

    Stores parsed API endpoint information from OpenAPI/Swagger docs.
    Supports folder organization and association with test cases/scripts.
    """

    __tablename__ = "api_endpoints"
    __table_args__ = {"comment": "API endpoint definition table"}

    # Basic info
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Project ID",
    )
    folder_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Folder ID (optional, for organization)",
    )

    # API endpoint identity
    display_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Display name: method + path, e.g. 'GET /api/v1/Activities'",
    )

    # API details
    path: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        index=True,
        comment="API path, e.g. /api/v1/Activities",
    )
    method: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
        comment="HTTP method: GET, POST, PUT, DELETE, PATCH, etc.",
    )
    summary: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Endpoint summary (short description)",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Endpoint detailed description",
    )

    # OpenAPI Schema reference
    schema_file_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("attachments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated OpenAPI Schema file ID",
    )

    # Endpoint config (JSON)
    parameters: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Parameter definitions [{name, in, required, schema, description}]",
    )
    request_body: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Request body definition {content_type, schema, required}",
    )
    responses: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Response definitions {200: {schema, description}, 400: {...}}",
    )
    security: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Security config [{type, scheme, scopes}]",
    )
    tags: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Tags list [tag1, tag2, ...]",
    )

    # Grouping
    tag_group: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
        comment="Tag group (e.g. 'Activities', 'Users') for organization",
    )

    # Associated test cases/scripts
    test_case_ids: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Associated test case ID list",
    )
    api_test_ids: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Associated API test script ID list",
    )

    # Extended config
    custom_config: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        comment="Custom config {deprecated, servers, extensions}",
    )

    # Stats
    total_test_cases: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total associated test cases",
    )
    total_test_runs: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total test runs",
    )
    last_run_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Last test run status",
    )

    # Sort order
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Sort order",
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="api_endpoints",
    )
    folder: Mapped["Folder | None"] = relationship(
        "Folder",
        back_populates="api_endpoints",
    )
    schema_file: Mapped["Attachment | None"] = relationship(
        "Attachment",
        foreign_keys=[schema_file_id],
    )
