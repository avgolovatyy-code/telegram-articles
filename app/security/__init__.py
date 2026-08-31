"""Secret handling: encrypted storage on disk and redaction in logs.

Import submodules directly. The package exposes nothing at import time because logging
imports the redactor, and a package-level import of the store would make logging depend
on configuration.
"""
