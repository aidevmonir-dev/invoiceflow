import uuid

from django.db import models


class Workspace(models.Model):
    """One visitor's private set of documents, tied to their session and deleted after the retention window."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.id)


class Document(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        EXTRACTED = "extracted", "Ready to review"
        APPROVED = "approved", "Approved"
        FAILED = "failed", "Could not read"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="documents")
    filename = models.CharField(max_length=200)
    media_type = models.CharField(max_length=40)
    stored_name = models.CharField(max_length=80, help_text="File name inside UPLOAD_DIR")
    size = models.PositiveIntegerField()
    sample_key = models.CharField(max_length=40, blank=True, help_text="Set when the visitor chose a built-in sample")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPLOADED)
    # What the model returned, kept unchanged so a reviewer's corrections can be compared with it.
    extracted = models.JSONField(null=True, blank=True)
    # The reviewed values. Starts as a copy of `extracted`; the reviewer edits this one.
    data = models.JSONField(null=True, blank=True)
    extraction_source = models.CharField(max_length=20, blank=True, help_text="'ai' or 'stored-example'")
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.filename
