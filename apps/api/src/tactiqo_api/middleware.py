"""Request correlation middleware for safe cross-process tracing."""

from contextvars import ContextVar
from uuid import UUID, uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CORRELATION_HEADER = "X-Correlation-ID"
correlation_id_context: ContextVar[str | None] = ContextVar(
    "correlation_id",
    default=None,
)


class CorrelationIdMiddleware:
    """Validate or create a correlation ID and return it on every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap an ASGI application.

        Args:
            app: Downstream ASGI application.

        """
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Attach a bounded correlation ID for an HTTP request.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.

        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        correlation_id = self._resolve_correlation_id(Headers(scope=scope))
        token = correlation_id_context.set(correlation_id)
        try:
            await self._app(
                scope,
                receive,
                self._send_with_correlation_id(send, correlation_id),
            )
        finally:
            correlation_id_context.reset(token)

    @staticmethod
    def _resolve_correlation_id(headers: Headers) -> str:
        """Accept only UUID correlation values to prevent log/header injection.

        Args:
            headers: Request headers supplied by the ASGI server.

        Returns:
            Canonical UUID from the caller or a newly generated identifier.

        """
        raw_value = headers.get(CORRELATION_HEADER)
        if raw_value is not None:
            try:
                return str(UUID(raw_value))
            except ValueError:
                pass
        return str(uuid4())

    @staticmethod
    def _send_with_correlation_id(send: Send, correlation_id: str) -> Send:
        """Build an ASGI sender that adds the correlation response header.

        Args:
            send: Original ASGI send callable.
            correlation_id: Validated request correlation identifier.

        Returns:
            Wrapped asynchronous ASGI sender.

        """

        async def wrapped_send(message: Message) -> None:
            """Add the correlation header to the response start message."""
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[CORRELATION_HEADER] = correlation_id
            await send(message)

        return wrapped_send


def get_correlation_id() -> str | None:
    """Return the current request correlation ID for logging and tracing."""
    return correlation_id_context.get()
