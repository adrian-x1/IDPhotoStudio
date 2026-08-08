"""Download the bundled inference models that are too large for git.

`isnet-general-use.onnx` is ~170 MB, which exceeds GitHub's 100 MB per-file
limit, so it is git-ignored and fetched here instead.  The other two models are
committed and only verified.  Every file is checked against a pinned SHA-256 so
a truncated download or an upstream asset swap fails the build loudly rather
than producing a broken installer.
"""

from __future__ import annotations

import hashlib
import ssl
from pathlib import Path
import sys
import urllib.request


MODEL_DIR = Path(__file__).resolve().parents[1] / "assets" / "models"

# name -> (sha256, download url or None when the file is committed to git)
MODELS: dict[str, tuple[str, str | None]] = {
    "isnet-general-use.onnx": (
        "60920e99c45464f2ba57bee2ad08c919a52bbf852739e96947fbb4358c0d964a",
        "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx",
    ),
    "face_landmarker.task": (
        "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
        None,
    ),
    "blaze_face_short_range.tflite": (
        "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f",
        None,
    ),
}

CHUNK_SIZE = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ssl_context() -> ssl.SSLContext:
    """Prefer certifi's CA bundle when available.

    This script runs before the project dependencies are installed, so certifi
    may be missing; python.org builds on macOS ship without a usable system CA
    bundle, which makes the default context fail with CERTIFICATE_VERIFY_FAILED.
    Certificates are always verified — only the source of the bundle varies.
    """
    try:
        import certifi
    except ModuleNotFoundError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def download(url: str, destination: Path) -> None:
    """Stream to a temporary file so an interrupted run leaves no partial model."""
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.urlopen(url, context=ssl_context())
    with request as response, temporary.open("wb") as handle:
        total = int(response.headers.get("content-length") or 0)
        written = 0
        while chunk := response.read(CHUNK_SIZE):
            handle.write(chunk)
            written += len(chunk)
            if total:
                print(f"\r  {written / total:6.1%} ({written >> 20} MiB)", end="")
        print()
    temporary.replace(destination)


def ensure(name: str, expected_sha: str, url: str | None) -> None:
    path = MODEL_DIR / name

    if path.is_file():
        actual = sha256_of(path)
        if actual == expected_sha:
            print(f"ok       {name}")
            return
        if url is None:
            raise SystemExit(
                f"checksum mismatch for committed model {name}\n"
                f"  expected {expected_sha}\n  actual   {actual}"
            )
        print(f"stale    {name} (checksum mismatch, re-downloading)")
        path.unlink()
    elif url is None:
        raise SystemExit(f"missing committed model: {path}")

    assert url is not None
    print(f"fetching {name}")
    download(url, path)

    actual = sha256_of(path)
    if actual != expected_sha:
        path.unlink(missing_ok=True)
        raise SystemExit(
            f"checksum mismatch after downloading {name}\n"
            f"  expected {expected_sha}\n  actual   {actual}"
        )
    print(f"ok       {name}")


def main() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, (expected_sha, url) in MODELS.items():
        ensure(name, expected_sha, url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
