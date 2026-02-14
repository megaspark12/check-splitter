"""
Storage backend abstraction for receipt image uploads.

Supports local filesystem (development) and Google Cloud Storage (production).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("storage")


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def save(self, data: bytes, filename: str) -> str:
        """
        Save file data and return a path/URL reference.

        Args:
            data: File bytes to save
            filename: Desired filename (will be sanitized)

        Returns:
            Storage path or URL for the saved file
        """
        ...

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """
        Delete a file by its storage path.

        Returns:
            True if deleted, False if not found
        """
        ...

    @abstractmethod
    async def get_url(self, path: str) -> str | None:
        """
        Get a URL to access the file (signed URL for GCS, local path otherwise).

        Returns:
            URL string or None if file doesn't exist
        """
        ...


class LocalStorage(StorageBackend):
    """Local filesystem storage for development."""

    def __init__(self):
        settings = get_settings()
        self.uploads_dir = Path(settings.uploads_dir)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"LocalStorage initialized: {self.uploads_dir}")

    async def save(self, data: bytes, filename: str) -> str:
        """Save file to local filesystem."""
        import aiofiles

        filepath = self.uploads_dir / filename
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(data)

        logger.info(f"Saved file locally: {filepath} ({len(data)} bytes)")
        return str(filepath)

    async def delete(self, path: str) -> bool:
        """Delete file from local filesystem."""
        try:
            filepath = Path(path)
            if filepath.exists():
                filepath.unlink()
                logger.info(f"Deleted local file: {path}")
                return True
            return False
        except OSError as e:
            logger.error(f"Failed to delete local file {path}: {e}")
            return False

    async def get_url(self, path: str) -> str | None:
        """Return local file path (no URL needed for dev)."""
        if Path(path).exists():
            return path
        return None


class GCSStorage(StorageBackend):
    """Google Cloud Storage backend for production."""

    def __init__(self):
        settings = get_settings()
        self.bucket_name = settings.gcs_bucket_name
        self._client = None
        self._bucket = None

        if not self.bucket_name:
            raise ValueError(
                "GCS_BUCKET_NAME must be set when using GCS storage backend"
            )

        logger.info(f"GCSStorage initialized: bucket={self.bucket_name}")

    def _get_bucket(self):
        """Lazy initialization of GCS client and bucket."""
        if self._bucket is None:
            from google.cloud import storage

            self._client = storage.Client()
            self._bucket = self._client.bucket(self.bucket_name)
        return self._bucket

    async def save(self, data: bytes, filename: str) -> str:
        """Upload file to GCS."""
        import asyncio

        bucket = self._get_bucket()
        blob_path = f"receipts/{filename}"
        blob = bucket.blob(blob_path)

        # Determine content type from extension
        ext = Path(filename).suffix.lower()
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        content_type = content_types.get(ext, "application/octet-stream")

        # Upload in a thread to avoid blocking
        await asyncio.to_thread(
            blob.upload_from_string,
            data,
            content_type=content_type,
        )

        logger.info(
            f"Uploaded to GCS: gs://{self.bucket_name}/{blob_path} ({len(data)} bytes)"
        )
        return f"gs://{self.bucket_name}/{blob_path}"

    async def delete(self, path: str) -> bool:
        """Delete file from GCS."""
        import asyncio

        try:
            bucket = self._get_bucket()
            # Extract blob path from gs:// URL
            blob_path = path.replace(f"gs://{self.bucket_name}/", "")
            blob = bucket.blob(blob_path)

            await asyncio.to_thread(blob.delete)
            logger.info(f"Deleted from GCS: {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete from GCS {path}: {e}")
            return False

    async def get_url(self, path: str) -> str | None:
        """Generate a signed URL for temporary access."""
        import asyncio
        from datetime import timedelta

        try:
            bucket = self._get_bucket()
            blob_path = path.replace(f"gs://{self.bucket_name}/", "")
            blob = bucket.blob(blob_path)

            url = await asyncio.to_thread(
                blob.generate_signed_url,
                expiration=timedelta(hours=1),
                method="GET",
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate signed URL for {path}: {e}")
            return None


def get_storage_backend() -> StorageBackend:
    """Factory function to get the configured storage backend."""
    settings = get_settings()

    if settings.storage_backend.lower() == "gcs":
        return GCSStorage()
    else:
        return LocalStorage()
