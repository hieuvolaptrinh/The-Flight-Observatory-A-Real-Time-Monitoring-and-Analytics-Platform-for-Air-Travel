import json
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from minio import Minio
from minio.error import S3Error

from app.core.exceptions_handler import AppError, ValidationError


class StorageService:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        public_url: str,
        secure: bool = False,
    ) -> None:
        self.bucket = bucket
        self.public_url = public_url.rstrip("/")
        self._bucket_ready = False
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    def upload_image(self, file: UploadFile, folder: str) -> str:

        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)

        extension = Path(file.filename or "").suffix.lower()
        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
            extension = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
            }[file.content_type]

        object_name = f"{folder}/{uuid4().hex}{extension}"
        try:
            self._ensure_public_bucket()
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=file.file,
                length=size,
                content_type=file.content_type,
            )
        except S3Error as exc:
            raise AppError(502, "STORAGE_ERROR", "Unable to store image") from exc

        return f"{self.public_url}/{self.bucket}/{object_name}"

    def _ensure_public_bucket(self) -> None:
        if self._bucket_ready:
            return
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{self.bucket}/*"],
                }
            ],
        }
        self.client.set_bucket_policy(self.bucket, json.dumps(policy))
        self._bucket_ready = True
