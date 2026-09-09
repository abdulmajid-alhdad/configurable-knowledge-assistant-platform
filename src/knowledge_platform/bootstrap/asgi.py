"""Production ASGI entrypoint owned by the composition root."""

from knowledge_platform.delivery.app import create_app

from .application import create_runtime

# Invalid production configuration intentionally fails startup; no demo fallback.
app = create_app(runtime=create_runtime())
