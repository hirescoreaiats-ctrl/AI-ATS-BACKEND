from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.core.config import get_settings
from backend.core.security import get_current_user
from backend.utils.upload_security import malware_scan, safe_upload_name, validate_upload_metadata

router = APIRouter(prefix="/uploads", tags=["chunked-uploads"])


@router.post("/chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    file_name: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    chunk: UploadFile = File(...),
    user=Depends(get_current_user),
):
    settings = get_settings()
    safe_id = "".join(ch for ch in upload_id if ch.isalnum() or ch in "-_")[:80]
    chunk_dir = Path(settings.upload_dir) / "chunks" / safe_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    content = await chunk.read()
    if len(content) > settings.upload_bytes_limit:
        raise HTTPException(status_code=413, detail="Chunk exceeds upload size limit")
    (chunk_dir / f"{chunk_index:06d}.part").write_bytes(content)

    received = len(list(chunk_dir.glob("*.part")))
    if received < total_chunks:
        return {"upload_id": safe_id, "received": received, "complete": False}

    final_name = safe_upload_name(file_name)
    final_path = Path(settings.upload_dir) / final_name
    with final_path.open("wb") as output:
        for index in range(total_chunks):
            part = chunk_dir / f"{index:06d}.part"
            if not part.exists():
                raise HTTPException(status_code=400, detail=f"Missing chunk {index}")
            output.write(part.read_bytes())

    validate_upload_metadata(file_name, chunk.content_type, final_path.stat().st_size)
    malware_scan(str(final_path))
    for part in chunk_dir.glob("*.part"):
        part.unlink(missing_ok=True)
    try:
        chunk_dir.rmdir()
    except OSError:
        pass

    return {"upload_id": safe_id, "file_path": str(final_path), "complete": True}
