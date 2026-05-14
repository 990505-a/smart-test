"""Attachment API routes.

Provides attachment upload/download/list/delete endpoints.
Per D-07: local filesystem storage under workspace/{space_id}/attachments/.
Per D-04: no auth, uses DEFAULT_USER_ID.
"""

from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import FileResponse

from src.app.api.deps import AttachmentServiceDep, DbSessionDep
from src.app.db.schemas.attachment import AttachmentInfo
from src.app.db.schemas.common import SuccessResponse, MessageResponse
from src.app.db.schemas.enums import AttachmentEntityType

router = APIRouter(prefix="/attachments")


@router.post(
    "/upload",
    response_model=SuccessResponse[AttachmentInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Upload attachment",
    description="Upload a file attachment for an entity",
)
async def upload_attachment(
    file: UploadFile = File(..., description="File to upload"),
    entity_type: AttachmentEntityType = Form(..., description="Entity type"),
    entity_id: UUID = Form(..., description="Entity UUID"),
    project_id: UUID = Form(..., description="Project UUID"),
    description: str | None = Form(default=None, description="Description"),
    step_index: int | None = Form(default=None, description="Step index"),
    service: AttachmentServiceDep = None,
    db: DbSessionDep = None,
):
    """Upload a file attachment to local filesystem."""
    file_content = await file.read()
    attachment = await service.upload(
        file_content=file_content,
        file_name=file.filename or "unnamed",
        content_type=file.content_type or "application/octet-stream",
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        description=description,
        step_index=step_index,
    )
    await db.commit()
    return SuccessResponse(success=True, data=attachment)


@router.get(
    "/{attachment_id}/download",
    summary="Download attachment",
    description="Download an attachment file from local filesystem",
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "Attachment file content",
        }
    },
)
async def download_attachment(
    attachment_id: UUID,
    service: AttachmentServiceDep,
):
    """Download an attachment file."""
    file_content, file_name, content_type = await service.download(attachment_id)

    import tempfile
    from pathlib import Path

    # Write to a temporary file for FileResponse
    temp_dir = Path(tempfile.gettempdir()) / "smart_test_platform"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / file_name
    temp_path.write_bytes(file_content)

    return FileResponse(
        path=str(temp_path),
        filename=file_name,
        media_type=content_type,
    )


@router.get(
    "/entity/{entity_type}/{entity_id}",
    response_model=SuccessResponse[list[AttachmentInfo]],
    summary="List attachments by entity",
    description="List all attachments for an entity",
)
async def list_attachments_by_entity(
    entity_type: AttachmentEntityType,
    entity_id: UUID,
    service: AttachmentServiceDep,
):
    """List attachments by entity type and ID."""
    attachments = await service.get_by_entity(entity_type, entity_id)
    return SuccessResponse(success=True, data=attachments)


@router.delete(
    "/{attachment_id}",
    response_model=MessageResponse,
    summary="Delete attachment",
    description="Delete an attachment file and its metadata",
)
async def delete_attachment(
    attachment_id: UUID,
    service: AttachmentServiceDep,
    db: DbSessionDep,
):
    """Delete an attachment."""
    message = await service.delete(attachment_id)
    await db.commit()
    return MessageResponse(success=True, message=message)
