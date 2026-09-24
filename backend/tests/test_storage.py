import asyncio
from pathlib import Path
from uuid import uuid4

from app.adapters.storage import LocalFilesystemUploadStorage


def test_local_upload_storage_uses_opaque_keys_and_deletes_expired_content(tmp_path: Path) -> None:
    storage = LocalFilesystemUploadStorage(root=tmp_path)
    upload_id = uuid4()

    key = asyncio.run(storage.put(upload_id=upload_id, content=b"sanitized-png"))

    assert key == f"{upload_id}.png"
    assert asyncio.run(storage.get(object_key=key)) == b"sanitized-png"
    asyncio.run(storage.delete(object_key=key))
    assert not (tmp_path / key).exists()
