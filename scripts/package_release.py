"""Build reproducible release artifacts and verify their manifest."""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import csv
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import tomllib
import zipfile
from importlib import metadata as importlib_metadata
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
    _verify_build_toolchain()
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


def _verify_build_toolchain() -> None:
    """Require exact build backend versions before claiming reproducibility."""

    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)
    requirements = project.get("build-system", {}).get("requires", [])
    if not isinstance(requirements, list) or not requirements:
        raise RuntimeError("build-system.requires must contain exact package pins")
    for requirement in requirements:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)", str(requirement))
        if not match:
            raise RuntimeError(f"build-system requirement is not exactly pinned: {requirement}")
        package, expected = match.groups()
        try:
            actual = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                f"required build tool is not installed: {package}=={expected}"
            ) from exc
        if actual != expected:
            raise RuntimeError(
                f"build tool mismatch: {package}=={actual}; expected {package}=={expected}. "
                'Run: python -m pip install -e ".[dev]"'
            )


def _normalize_sdist(path: Path) -> None:
    """Rewrite archive ownership, modes, and timestamps deterministically."""

    epoch = int(SOURCE_DATE_EPOCH)
    tar_buffer = io.BytesIO()
    with (
        tarfile.open(path, mode="r:gz") as source,
        tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as target,
    ):
        for original in sorted(source.getmembers(), key=lambda item: item.name):
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
            payload = None
            if original.isfile():
                extracted = source.extractfile(original)
                if extracted is None:
                    raise RuntimeError(f"cannot read sdist member: {original.name}")
                payload_bytes = extracted.read()
                if original.name.endswith("PKG-INFO") or original.name.endswith("/setup.cfg"):
                    payload_bytes = _canonical_newlines(payload_bytes)
                member.size = len(payload_bytes)
                payload = io.BytesIO(payload_bytes)
            target.addfile(member, payload)

    _write_deterministic_gzip(path, tar_buffer.getvalue(), epoch)


def _normalize_wheel(path: Path) -> None:
    """Rewrite ZIP metadata so wheels match across host operating systems."""

    timestamp = time.gmtime(int(SOURCE_DATE_EPOCH))[:6]
    with zipfile.ZipFile(path, mode="r") as source:
        entries = {info.filename: (info.is_dir(), source.read(info)) for info in source.infolist()}

    for name, (is_directory, payload) in list(entries.items()):
        if not is_directory and (
            name.endswith(".dist-info/METADATA")
            or name.endswith(".dist-info/WHEEL")
            or name.endswith(".dist-info/entry_points.txt")
            or name.endswith(".dist-info/top_level.txt")
        ):
            entries[name] = (False, _canonical_newlines(payload))

    record_names = [name for name in entries if name.endswith(".dist-info/RECORD")]
    if len(record_names) != 1:
        raise RuntimeError(f"expected one wheel RECORD, found {len(record_names)}")
    record_name = record_names[0]
    record_buffer = io.StringIO(newline="")
    writer = csv.writer(record_buffer, lineterminator="\n")
    for name, (is_directory, payload) in sorted(entries.items()):
        if is_directory or name == record_name:
            continue
        encoded_hash = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
        writer.writerow([name, f"sha256={encoded_hash.decode('ascii')}", str(len(payload))])
    writer.writerow([record_name, "", ""])
    entries[record_name] = (False, record_buffer.getvalue().encode("utf-8"))

    temporary = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(
        temporary,
        mode="w",
        compression=zipfile.ZIP_STORED,
        strict_timestamps=True,
    ) as target:
        for name, (is_directory, payload) in sorted(entries.items()):
            info = zipfile.ZipInfo(filename=name, date_time=timestamp)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = ((0o40755 if is_directory else 0o100644) << 16) | (
                0x10 if is_directory else 0
            )
            target.writestr(info, payload, compress_type=zipfile.ZIP_STORED)
    temporary.replace(path)


def _canonical_newlines(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _write_deterministic_gzip(path: Path, payload: bytes, epoch: int) -> None:
    """Write gzip with uncompressed DEFLATE blocks, independent of zlib versions."""

    output = bytearray(b"\x1f\x8b\x08\x00")
    output.extend(struct.pack("<I", epoch))
    output.extend(b"\x00\xff")
    if payload:
        for offset in range(0, len(payload), 65535):
            block = payload[offset : offset + 65535]
            output.append(1 if offset + len(block) == len(payload) else 0)
            output.extend(struct.pack("<HH", len(block), len(block) ^ 0xFFFF))
            output.extend(block)
    else:
        output.extend(b"\x01\x00\x00\xff\xff")
    output.extend(
        struct.pack("<II", binascii.crc32(payload) & 0xFFFFFFFF, len(payload) & 0xFFFFFFFF)
    )
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(output)
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
