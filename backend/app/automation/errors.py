from typing import Optional


class NotebookLMGenerationError(RuntimeError):
    """Base error for a failed NotebookLM generation.

    `retryable` tells a caller what to do: True means trying again can help,
    False means it cannot, None means the failure was never classified.
    """

    user_message = "تعذر إنشاء العرض التعليمي عبر NotebookLM. يرجى إعادة المحاولة."
    retryable: Optional[bool] = None

    # Folder holding the screenshot and DOM saved when this error happened.
    evidence_dir: Optional[str] = None


class TransientStepError(NotebookLMGenerationError):
    """A step failed in a way that a later attempt may well fix (timeout, selector miss)."""

    retryable = True


class PermanentStepError(NotebookLMGenerationError):
    """A step failed in a way that retrying cannot fix (empty source, unexpected layout)."""

    retryable = False


class NeedsLoginError(NotebookLMGenerationError):
    """The NotebookLM session has expired; a person must log in again."""

    retryable = False


class QuotaExhaustedError(NotebookLMGenerationError):
    """NotebookLM refused to create more Slide Decks for now."""

    retryable = False
