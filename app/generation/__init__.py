"""Article generation: context, writing, verification, quality gates.

Import submodules directly (``from app.generation.pipeline import GenerationPipeline``).
This package intentionally exposes nothing at import time so that ``app.generation`` and
``app.telegram`` can depend on each other's submodules without a circular import.
"""
