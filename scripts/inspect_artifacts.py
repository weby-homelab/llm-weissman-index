"""Fail closed if built artifacts contain obvious secret or local-state payloads."""

from __future__ import annotations

import re
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN_NAME_PARTS = (".env", "credentials", "private_key", "id_rsa", "id_ed25519")
SECRET_PATTERNS = (
    re.compile(rb"BEGIN [A-Z ]+ PRIVATE KEY"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9_\-]{20,}"),
    re.compile(rb"sk-[A-Za-z0-9_\-]{20,}"),
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def artifact_paths() -> list[Path]:
    dist_dir = REPOSITORY_ROOT / "dist"
    if dist_dir.is_symlink() or dist_dir.resolve() != dist_dir:
        raise SystemExit("dist must be a repository-local directory")
    return sorted(dist_dir.glob("*.whl")) + sorted(dist_dir.glob("*.tar.gz"))


def members(path: Path) -> list[tuple[str, bytes]]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return [(info.filename, archive.read(info)) for info in archive.infolist()]
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path) as archive:
            return [
                (info.name, archive.extractfile(info).read() if info.isfile() else b"")
                for info in archive
            ]
    return []


def main() -> int:
    paths = artifact_paths()
    if not paths:
        raise SystemExit("no distributable artifacts found")
    violations: list[str] = []
    for artifact in paths:
        for name, content in members(artifact):
            lowered = name.lower()
            if any(part in lowered for part in FORBIDDEN_NAME_PARTS):
                violations.append(f"{artifact}:{name}: forbidden member name")
            if any(pattern.search(content) for pattern in SECRET_PATTERNS):
                violations.append(f"{artifact}:{name}: secret-like content")
    if violations:
        raise SystemExit("\n".join(violations))
    print(f"artifact inspection: PASS ({len(paths)} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
