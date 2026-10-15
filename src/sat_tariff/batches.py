"""Batch preparation for master HS code files larger than a single batch.

``MAX_LINES`` (500) stays a hard limit **per file**: the master file configured
by ``SAT_INPUT_FILE`` is split into deterministic batch files of at most
``SAT_BATCH_SIZE`` codes plus a versioned ``manifest.json``. The manifest is the
single source of truth about *which* codes must be processed; SQLite remains the
single source of truth about *what has already been processed*.

Everything in this module is pure/offline: no browser and no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile

from .config import AppConfig
from .models import HsCodeEntry
from .validation.input_validator import (
    MAX_LINES,
    InputValidationError,
    validate_hs_code_file,
)

MANIFEST_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
BATCH_FILENAME_TEMPLATE = "HS_codes_{number:03d}.txt"
BATCH_FILENAME_PATTERN = re.compile(r"^HS_codes_\d{3,}\.txt$")

REPREPARE_HINT = "Vuelve a ejecutar 'python -m sat_tariff prepare-batches'."


class BatchError(RuntimeError):
    """Base error for batch preparation and batch loading problems."""


class ManifestError(BatchError):
    """Raised when the manifest is missing, corrupt, outdated or incompatible."""


@dataclass(slots=True, frozen=True)
class BatchInfo:
    """A single prepared batch file."""

    number: int
    path: str
    count: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {"number": self.number, "path": self.path, "count": self.count, "sha256": self.sha256}


@dataclass(slots=True)
class BatchManifest:
    """The versioned description of a prepared batch set."""

    version: int
    master_file: str
    master_sha256: str
    created_at: str
    batch_size: int
    total_lines: int
    total_codes: int
    duplicates_skipped: list[str]
    suspicious_codes: list[str]
    invalid_line_policy: str
    batches: list[BatchInfo]
    directory: Path = field(default=Path("."), compare=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "master_file": self.master_file,
            "master_sha256": self.master_sha256,
            "created_at": self.created_at,
            "batch_size": self.batch_size,
            "total_lines": self.total_lines,
            "total_codes": self.total_codes,
            "duplicates_skipped": list(self.duplicates_skipped),
            "suspicious_codes": list(self.suspicious_codes),
            "invalid_line_policy": self.invalid_line_policy,
            "batches": [batch.to_dict() for batch in self.batches],
        }

    def batch_path(self, batch: BatchInfo) -> Path:
        """Resolve a batch path relative to the manifest directory.

        Paths are stored relative to the manifest with ``/`` separators, so a
        prepared batch set keeps working after the repository is moved, cloned
        or shared between Windows, macOS and Linux.
        """

        return self.directory / Path(batch.path)

    def master_path(self) -> Path:
        candidate = Path(self.master_file)
        if candidate.is_absolute():
            return candidate
        return candidate


@dataclass(slots=True, frozen=True)
class BatchPlan:
    """A batch and the entries that still need processing inside it."""

    number: int
    total_batches: int
    entries: list[HsCodeEntry]
    size: int


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def chunk_entries(entries: list[HsCodeEntry], batch_size: int) -> list[list[HsCodeEntry]]:
    """Split ``entries`` into chunks of at most ``batch_size`` items."""

    if batch_size < 1 or batch_size > MAX_LINES:
        raise BatchError(f"El tamaño de lote debe estar entre 1 y {MAX_LINES} (recibido {batch_size}).")
    return [entries[index : index + batch_size] for index in range(0, len(entries), batch_size)]


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _clear_managed_batch_files(directory: Path) -> None:
    """Remove only the files this tool generates, never arbitrary files."""

    if not directory.exists():
        return
    for item in directory.iterdir():
        if item.is_file() and (BATCH_FILENAME_PATTERN.match(item.name) or item.name == MANIFEST_FILENAME):
            item.unlink()


def prepare_batches(
    config: AppConfig,
    *,
    batch_size: int | None = None,
    directory: Path | str | None = None,
) -> BatchManifest:
    """Split the configured master file into batch files plus a manifest."""

    size = config.batch_size if batch_size is None else int(batch_size)
    if size < 1 or size > MAX_LINES:
        raise BatchError(f"El tamaño de lote debe estar entre 1 y {MAX_LINES} (recibido {size}).")

    master_path = Path(config.input_file)
    if not master_path.exists():
        raise BatchError(f"No se encontró el archivo maestro '{master_path}'.")

    result = validate_hs_code_file(master_path, invalid_policy=config.invalid_line_policy, max_lines=None)
    entries = result.entries
    if not entries:
        raise BatchError(
            f"El archivo maestro '{master_path}' no contiene códigos procesables "
            f"(política '{config.invalid_line_policy}')."
        )

    target_dir = Path(directory) if directory is not None else Path(config.batch_directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    _clear_managed_batch_files(target_dir)

    chunks = chunk_entries(entries, size)
    batches: list[BatchInfo] = []
    for number, chunk in enumerate(chunks, start=1):
        file_name = BATCH_FILENAME_TEMPLATE.format(number=number)
        batch_path = target_dir / file_name
        _atomic_write_text(batch_path, "".join(f"{entry.raw_code}\n" for entry in chunk))
        # The generated file must pass the regular validator, limit included.
        validate_hs_code_file(batch_path, invalid_policy=config.invalid_line_policy)
        batches.append(
            BatchInfo(number=number, path=file_name, count=len(chunk), sha256=sha256_file(batch_path))
        )

    manifest = BatchManifest(
        version=MANIFEST_VERSION,
        master_file=master_path.as_posix(),
        master_sha256=sha256_file(master_path),
        created_at=datetime.now(timezone.utc).isoformat(),
        batch_size=size,
        total_lines=result.total_lines,
        total_codes=len(entries),
        duplicates_skipped=list(result.duplicate_codes),
        suspicious_codes=list(result.suspicious_codes),
        invalid_line_policy=config.invalid_line_policy,
        batches=batches,
        directory=target_dir,
    )
    _atomic_write_text(
        target_dir / MANIFEST_FILENAME,
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def manifest_path_for(directory: Path | str) -> Path:
    return Path(directory) / MANIFEST_FILENAME


def load_manifest(directory: Path | str) -> BatchManifest:
    """Read and structurally validate ``manifest.json``."""

    target_dir = Path(directory)
    path = manifest_path_for(target_dir)
    if not path.exists():
        raise ManifestError(f"No se encontró el manifiesto '{path}'. {REPREPARE_HINT}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"El manifiesto '{path}' está corrupto ({exc}). {REPREPARE_HINT}") from exc
    if not isinstance(payload, dict):
        raise ManifestError(f"El manifiesto '{path}' está corrupto. {REPREPARE_HINT}")
    version = payload.get("version")
    if version != MANIFEST_VERSION:
        raise ManifestError(
            f"El manifiesto '{path}' usa la versión {version!r}, incompatible con la versión "
            f"{MANIFEST_VERSION} soportada. {REPREPARE_HINT}"
        )
    try:
        batches = [
            BatchInfo(
                number=int(item["number"]),
                path=str(item["path"]),
                count=int(item["count"]),
                sha256=str(item.get("sha256", "")),
            )
            for item in payload["batches"]
        ]
        manifest = BatchManifest(
            version=int(payload["version"]),
            master_file=str(payload["master_file"]),
            master_sha256=str(payload["master_sha256"]),
            created_at=str(payload.get("created_at", "")),
            batch_size=int(payload["batch_size"]),
            total_lines=int(payload.get("total_lines", 0)),
            total_codes=int(payload.get("total_codes", 0)),
            duplicates_skipped=list(payload.get("duplicates_skipped", [])),
            suspicious_codes=list(payload.get("suspicious_codes", [])),
            invalid_line_policy=str(payload.get("invalid_line_policy", "skip")),
            batches=sorted(batches, key=lambda batch: batch.number),
            directory=target_dir,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"El manifiesto '{path}' está corrupto ({exc}). {REPREPARE_HINT}") from exc
    if not manifest.batches:
        raise ManifestError(f"El manifiesto '{path}' no contiene lotes. {REPREPARE_HINT}")
    return manifest


def verify_manifest(manifest: BatchManifest) -> None:
    """Fail before opening a browser when the prepared set is stale."""

    master_path = manifest.master_path()
    if not master_path.exists():
        raise ManifestError(
            f"El archivo maestro '{master_path}' del manifiesto ya no existe. {REPREPARE_HINT}"
        )
    if sha256_file(master_path) != manifest.master_sha256:
        raise ManifestError(
            f"El archivo maestro '{master_path}' cambió después de preparar los lotes. {REPREPARE_HINT}"
        )
    for batch in manifest.batches:
        batch_path = manifest.batch_path(batch)
        if not batch_path.exists():
            raise ManifestError(f"Falta el archivo de lote '{batch_path}'. {REPREPARE_HINT}")
        if batch.sha256 and sha256_file(batch_path) != batch.sha256:
            raise ManifestError(f"El archivo de lote '{batch_path}' fue modificado. {REPREPARE_HINT}")


def load_batch_entries(manifest: BatchManifest, *, invalid_policy: str | None = None) -> list[tuple[BatchInfo, list[HsCodeEntry]]]:
    """Load every batch in order, validating each file with the normal rules."""

    policy = manifest.invalid_line_policy if invalid_policy is None else invalid_policy
    loaded: list[tuple[BatchInfo, list[HsCodeEntry]]] = []
    for batch in manifest.batches:
        batch_path = manifest.batch_path(batch)
        try:
            result = validate_hs_code_file(batch_path, invalid_policy=policy)
        except (InputValidationError, OSError) as exc:
            raise ManifestError(f"El archivo de lote '{batch_path}' no es válido ({exc}). {REPREPARE_HINT}") from exc
        loaded.append((batch, result.entries))
    return loaded


def manifest_entries(manifest: BatchManifest, *, invalid_policy: str | None = None) -> list[HsCodeEntry]:
    """Return every manifest entry in the original global order."""

    entries: list[HsCodeEntry] = []
    seen: set[str] = set()
    for _batch, batch_entries in load_batch_entries(manifest, invalid_policy=invalid_policy):
        for entry in batch_entries:
            if entry.normalized_code in seen:
                continue
            seen.add(entry.normalized_code)
            entries.append(entry)
    return entries


def build_batch_plans(
    loaded: list[tuple[BatchInfo, list[HsCodeEntry]]],
    pending_codes: set[str],
) -> list[BatchPlan]:
    """Keep only pending entries, preserving batch numbering and global order."""

    total_batches = len(loaded)
    plans: list[BatchPlan] = []
    seen: set[str] = set()
    for batch, entries in loaded:
        selected: list[HsCodeEntry] = []
        for entry in entries:
            if entry.normalized_code in seen or entry.normalized_code not in pending_codes:
                continue
            seen.add(entry.normalized_code)
            selected.append(entry)
        if selected:
            plans.append(
                BatchPlan(
                    number=batch.number,
                    total_batches=total_batches,
                    entries=selected,
                    size=batch.count,
                )
            )
    return plans
