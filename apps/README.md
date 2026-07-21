# Application Entry Points

This folder contains deployable process entrypoints and composition roots only.
Business rules belong in `backend/src/tactiqo/`.

- `api`: FastAPI HTTP/SSE process.
- `web`: Next.js user interface.
- `worker`: bounded RabbitMQ command/job consumer.
- `parser-worker`: isolated Unstructured/OCR workload boundary.
