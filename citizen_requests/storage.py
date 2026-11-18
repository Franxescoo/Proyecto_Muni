import os
import uuid
import zipfile
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.text import get_valid_filename


MAX_ACTION_ATTACHMENT_SIZE = 50 * 1024 * 1024
MAX_ACTION_ATTACHMENTS = 5
ALLOWED_ACTION_ATTACHMENT_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".doc",
    ".docx",
}


def safe_action_attachment_name(name):
    basename = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    safe_name = get_valid_filename(basename).strip(".")
    if not safe_name or safe_name in {".", ".."}:
        raise ValidationError("El nombre del archivo no es válido.")
    return safe_name[:255]


def validate_action_attachment(uploaded_file, *, filename=None):
    safe_name = safe_action_attachment_name(
        filename if filename is not None else uploaded_file.name
    )
    extension = PurePosixPath(safe_name).suffix.lower()
    if extension not in ALLOWED_ACTION_ATTACHMENT_EXTENSIONS:
        raise ValidationError(
            "Solo se permiten archivos PDF, JPG, JPEG, PNG, DOC y DOCX."
        )

    file_object = getattr(uploaded_file, "file", uploaded_file)
    position = None
    close_after_validation = getattr(uploaded_file, "_committed", False)
    try:
        position = file_object.tell()
        file_object.seek(0, 2)
        actual_size = file_object.tell()
        file_object.seek(0)
        signature = file_object.read(8)
        if actual_size > MAX_ACTION_ATTACHMENT_SIZE:
            raise ValidationError(
                "Cada archivo debe pesar como máximo 50 MB."
            )

        valid_signature = (
            (extension == ".pdf" and signature.startswith(b"%PDF-"))
            or (
                extension in {".jpg", ".jpeg"}
                and signature.startswith(b"\xff\xd8\xff")
            )
            or (
                extension == ".png"
                and signature.startswith(b"\x89PNG\r\n\x1a\n")
            )
            or (
                extension == ".doc"
                and signature.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
            )
        )
        if extension == ".docx":
            file_object.seek(0)
            try:
                with zipfile.ZipFile(file_object) as archive:
                    valid_signature = "word/document.xml" in archive.namelist()
            except (OSError, zipfile.BadZipFile):
                valid_signature = False
        if not valid_signature:
            raise ValidationError(
                "El contenido del archivo no coincide con su extensión."
            )
    finally:
        if position is not None:
            file_object.seek(position)
        if close_after_validation:
            file_object.close()

    return safe_name, actual_size


def action_attachment_upload_to(instance, filename):
    safe_name = safe_action_attachment_name(filename)
    extension = PurePosixPath(safe_name).suffix.lower()
    return f"citizen_request_actions/{uuid.uuid4().hex}{extension}"


@deconstructible
class PrivateActionStorage(FileSystemStorage):
    def __init__(self, location=None, **kwargs):
        from django.conf import settings

        if location is None:
            location = settings.CITIZEN_REQUEST_ACTION_PRIVATE_ROOT
        kwargs.setdefault("base_url", None)
        kwargs.setdefault("file_permissions_mode", 0o600)
        kwargs.setdefault("directory_permissions_mode", 0o700)
        super().__init__(location=location, **kwargs)

    def url(self, name):
        raise ValueError("Los adjuntos de gestiones no tienen URL pública.")

    def _save(self, name, content):
        os.makedirs(
            self.location,
            mode=self.directory_permissions_mode or 0o700,
            exist_ok=True,
        )
        if self.directory_permissions_mode is not None:
            os.chmod(self.location, self.directory_permissions_mode)
        return super()._save(name, content)
