"""Custom exceptions for patch application."""


class PatchError(Exception):
    """Base exception for patching failures."""


class PatchPlanError(PatchError):
    """Raised when a patch plan is invalid."""


class PatchMatchError(PatchError):
    """Raised when a patch cannot be matched or applied."""


class PatchTransactionError(PatchError):
    """Raised when file updates fail during a transaction."""
