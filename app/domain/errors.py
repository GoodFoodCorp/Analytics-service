"""Typed business errors, mapped to HTTP codes only in the adapter layer."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    VALIDATION = "VALIDATION_ERROR"
    FORBIDDEN = "FORBIDDEN"
    UPSTREAM = "UPSTREAM_ERROR"


class DomainError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message

    @staticmethod
    def validation(message: str) -> DomainError:
        return DomainError(ErrorCode.VALIDATION, message)

    @staticmethod
    def forbidden(message: str) -> DomainError:
        return DomainError(ErrorCode.FORBIDDEN, message)

    @staticmethod
    def upstream(message: str) -> DomainError:
        return DomainError(ErrorCode.UPSTREAM, message)
