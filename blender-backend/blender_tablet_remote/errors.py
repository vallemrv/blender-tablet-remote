"""Errores del protocolo."""

from __future__ import annotations


class CommandError(Exception):
    """Error controlado de un comando: se traduce en {"ok": false, "error": ...}."""

    def __init__(self, message: str, code: str = "command_failed"):
        super().__init__(message)
        self.message = message
        self.code = code


class AuthError(CommandError):
    def __init__(self, message: str = "Invalid or missing token"):
        super().__init__(message, code="auth_failed")


class UnknownCommand(CommandError):
    def __init__(self, name: str):
        super().__init__(f"Unknown command: {name}", code="unknown_command")


class BadPayload(CommandError):
    def __init__(self, message: str):
        super().__init__(message, code="bad_payload")
