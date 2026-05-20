class AppIndemnizacionesError(Exception):
    """Base exception for domain/application errors."""


class IpcImportError(AppIndemnizacionesError):
    """Raised when an IPC file cannot be imported or normalized."""


class IpcNotFoundError(AppIndemnizacionesError):
    """Raised when an IPC value is not found for a requested year-month."""


class LiquidacionError(AppIndemnizacionesError):
    """Raised when calculation input is invalid."""
