"""Croatia (HR) — Narodne novine HTML + ELI JSON-LD fetcher."""

from legalize.fetcher.hr.client import NarodneNovineClient
from legalize.fetcher.hr.discovery import NarodneNovineDiscovery
from legalize.fetcher.hr.parser import (
    NarodneNovineMetadataParser,
    NarodneNovineTextParser,
)

__all__ = [
    "NarodneNovineClient",
    "NarodneNovineDiscovery",
    "NarodneNovineTextParser",
    "NarodneNovineMetadataParser",
]
