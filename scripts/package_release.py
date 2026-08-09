"""Build reproducible release artifacts and verify their manifest."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import tomllib
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RELEASE = ROOT / "release"
STAGE_A = ROOT / ".package-build-a"
STAGE_B = ROOT / ".package-build-b"
BUILD = ROOT / "build"
EGG_INFO = ROOT / "src" / "clockwork_canary.egg-info"
SOURCE_DATE_EPOCH = "1786147200"  # 2026-08-08T00:00:00Z


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def version() -> str:
    init = (ROOT / "src" / "clockwork_canary" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', init, re.MULTILINE)
    if not match:
        raise RuntimeError("package version not found")
    package_version = match.group(1)
    with (ROOT / "pyproject.toml").open("rb") as handle:
        metadata = tomllib.load(handle)
    project_version = str(metadata["project"]["version"])
    if project_version != package_version:
        raise RuntimeError(
            f"version mismatch: pyproject={project_version}, package={package_version}"
        )
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{package_version}]" not in changelog:
        raise RuntimeError(f"CHANGELOG has no {package_version} section")
    return package_version


def build(clean: bool) -> None:
    if clean:
        for path in (DIST, RELEASE, STAGE_A, STAGE_B, BUILD, EGG_INFO):
            _remove_tree(path)
    for path in (STAGE_A, STAGE_B):
        path.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONHASHSEED": "0",
            "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
            "TZ": "UTC",
        }
    )
    for stage in (STAGE_A, STAGE_B):
        for generated in (BUILD, EGG_INFO):
            _remove_tree(generated)
        subprocess.run(
            [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(stage)],
            cwd=ROOT,
            env=environment,
            check=True,
        )
        for archive in stage.glob("*.tar.gz"):
            _normalize_sdist(archive)
        for archive in stage.glob("*.whl"):
            _normalize_wheel(archive)
    first = {path.name: digest(path) for path in sorted(STAGE_A.iterdir()) if path.is_file()}
    second = {path.name: digest(path) for path in sorted(STAGE_B.iterdir()) if path.is_file()}
    if first != second:
        differences = sorted(set(first) | set(second))
        detail = ", ".join(
            f"{name}: {first.get(name, 'missing')} != {second.get(name, 'missing')}"
            for name in differences
            if first.get(name) != second.get(name)
        )
        raise RuntimeError(f"release build is not reproducible: {detail}")

    DIST.mkdir(parents=True, exist_ok=True)
    RELEASE.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for source in sorted(STAGE_A.iterdir()):
        if not source.is_file():
            continue
        dist_target = DIST / source.name
        release_target = RELEASE / source.name
        shutil.copyfile(source, dist_target)
        shutil.copyfile(source, release_target)
        artifacts.append(
            {"name": source.name, "sha256": digest(source), "size": source.stat().st_size}
        )

    release_version = version()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "project": "clockwork-canary",
        "version": release_version,
        "source_date_epoch": int(SOURCE_DATE_EPOCH),
        "artifacts": artifacts,
    }
    (RELEASE / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    checksum_lines = [f"{item['sha256']}  {item['name']}" for item in artifacts]
    (RELEASE / "SHA256SUMS").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n"
    )
    for path in (STAGE_A, STAGE_B):
        _remove_tree(path)
    print(f"release package: built {len(artifacts)} reproducible artifacts")


def verify() -> None:
    manifest_path = RELEASE / "release-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("release-manifest.json not found; run with --clean first")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("version") != version():
        raise RuntimeError("release manifest version does not match package")
    expected_lines: list[str] = []
    expected_names: set[str] = set()
    for item in payload.get("artifacts", []):
        name = item["name"]
        expected_names.add(name)
        path = RELEASE / name
        if not path.is_file():
            raise RuntimeError(f"release artifact missing: {name}")
        actual_hash = digest(path)
        actual_size = path.stat().st_size
        if actual_hash != item["sha256"] or actual_size != item["size"]:
            raise RuntimeError(f"release artifact mismatch: {name}")
        expected_lines.append(f"{actual_hash}  {name}")
    actual_names = {
        path.name
        for path in RELEASE.iterdir()
        if path.is_file() and path.name not in {"release-manifest.json", "SHA256SUMS"}
    }
    if actual_names != expected_names:
        raise RuntimeError("release directory contains unmanifested artifacts")
    checksums = (RELEASE / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    if checksums != expected_lines:
        raise RuntimeError("SHA256SUMS does not match the release manifest")
    print(f"release package: PASS ({len(expected_names)} artifacts verified)")


def _remove_tree(path: Path) -> None:
    resolved = path.resolve()
    allowed = {item.resolve() for item in (DIST, RELEASE, STAGE_A, STAGE_B, BUILD, EGG_INFO)}
    if resolved not in allowed:
        raise RuntimeError(f"refusing to remove path outside repository: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def _normalize_sdist(path: Path) -> None:
    """Rewrite archive ownership, modes, and timestamps deterministically."""

    epoch = int(SOURCE_DATE_EPOCH)
    tar_buffer = io.BytesIO()
    with (
        tarfile.open(path, mode="r:gz") as source,
        tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as target,
    ):
        for original in source.getmembers():
            member = copy.copy(original)
            member.mtime = epoch
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.pax_headers = {}
            if original.isdir():
                member.mode = 0o755
            elif original.issym() or original.islnk():
                member.mode = 0o777
            else:
                member.mode = 0o644
            payload = source.extractfile(original) if original.isfile() else None
            target.addfile(member, payload)

    temporary = path.with_name(path.name + ".tmp")
    with (
        temporary.open("wb") as raw,
        gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=epoch,
        ) as compressed,
    ):
        compressed.write(tar_buffer.getvalue())
    temporary.replace(path)


def _normalize_wheel(path: Path) -> None:
    """Rewrite ZIP metadata so wheels match across host operating systems."""

    timestamp = time.gmtime(int(SOURCE_DATE_EPOCH))[:6]
    with zipfile.ZipFile(path, mode="r") as source:
        entries = [(info.filename, info.is_dir(), source.read(info)) for info in source.infolist()]

    temporary = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(
        temporary,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as target:
        for name, is_directory, payload in sorted(entries):
            info = zipfile.ZipInfo(filename=name, date_time=timestamp)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED if is_directory else zipfile.ZIP_DEFLATED
            info.external_attr = ((0o40755 if is_directory else 0o100644) << 16) | (
                0x10 if is_directory else 0
            )
            target.writestr(info, payload, compress_type=info.compress_type, compresslevel=9)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--clean", action="store_true", help="clean and build twice")
    group.add_argument("--verify", action="store_true", help="verify existing release files")
    args = parser.parse_args(argv)
    if args.clean:
        build(clean=True)
        verify()
    else:
        verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
