import re
import shutil
from pathlib import Path
from uuid import uuid4


ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".mp4"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB


def safe_name(value: str, fallback: str = "item") -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    normalized = normalized.strip("._-")
    return normalized[:80] or fallback


def save_audio_upload(upload, directory: Path) -> tuple[Path, str]:
    original_name = Path((upload.filename or "upload").replace("\\", "/")).name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise ValueError(f"Unsupported audio file type: {extension or 'none'}")
    content_type = (upload.content_type or "").split(";", 1)[0].lower()
    valid_content_type = (
        not content_type
        or content_type == "application/octet-stream"
        or content_type.startswith("audio/")
        or (extension == ".mp4" and content_type.startswith("video/"))
    )
    if not valid_content_type:
        raise ValueError(f"Unsupported upload content type: {content_type}")

    directory.mkdir(parents=True, exist_ok=True)
    directory = directory.resolve()
    destination = (directory / f"{uuid4().hex}{extension}").resolve()
    if directory not in destination.parents:
        raise ValueError("Invalid upload path")

    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ValueError("Uploaded file exceeds the 2 GiB limit")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        upload.file.close()

    return destination, original_name


def remove_job_directory(path: Path):
    if path.exists():
        shutil.rmtree(path)
