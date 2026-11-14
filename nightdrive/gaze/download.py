import contextlib
import ssl
import urllib.request
from pathlib import Path


def download(url: str, path: Path) -> None:
    """Download to `path` (atomically); uses certifi's CA bundle when available (python.org builds lack system CAs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    ctx = ssl.create_default_context()
    with contextlib.suppress(ImportError):
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(url, context=ctx) as r:
        tmp.write_bytes(r.read())
    tmp.rename(path)
