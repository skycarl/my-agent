"""S3-backed service for reading, writing, and searching Obsidian vault notes."""

import boto3
from loguru import logger

from app.core.settings import config

_s3_client = None


def _get_s3_client():
    """Get or create a cached boto3 S3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=config.obsidian_s3_region,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )
    return _s3_client


def _full_key(path: str) -> str:
    """Prepend the configured S3 prefix to a vault-relative path."""
    prefix = config.obsidian_s3_prefix.strip("/")
    if prefix:
        return f"{prefix}/{path}"
    return path


def _strip_prefix(key: str) -> str:
    """Remove the configured S3 prefix from an S3 key to get the vault-relative path."""
    prefix = config.obsidian_s3_prefix.strip("/")
    if prefix and key.startswith(f"{prefix}/"):
        return key[len(prefix) + 1 :]
    return key


def list_notes(folder: str = "") -> list[dict]:
    """List notes in the vault, optionally filtered by folder.

    Args:
        folder: Vault-relative folder path (e.g. "Recipes"). Empty for root.

    Returns:
        List of dicts with keys: path, size, last_modified.
    """
    s3 = _get_s3_client()
    prefix = _full_key(f"{folder}/" if folder else "")

    results = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=config.obsidian_s3_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            vault_path = _strip_prefix(obj["Key"])
            # Skip folder markers and non-markdown files
            if vault_path.endswith("/"):
                continue
            results.append(
                {
                    "path": vault_path,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
            )
    return results


def read_note(path: str) -> str:
    """Read a note's content from S3.

    Args:
        path: Vault-relative path (e.g. "Recipes/Chicken Tikka.md").

    Returns:
        The markdown content as a string.

    Raises:
        FileNotFoundError: If the note doesn't exist.
    """
    s3 = _get_s3_client()
    try:
        response = s3.get_object(Bucket=config.obsidian_s3_bucket, Key=_full_key(path))
        return response["Body"].read().decode("utf-8")
    except s3.exceptions.NoSuchKey:
        raise FileNotFoundError(f"Note not found: {path}")


def write_note(path: str, content: str) -> str:
    """Write (create or overwrite) a note in S3.

    Args:
        path: Vault-relative path (e.g. "Recipes/Chicken Tikka.md").
        content: Markdown content to write.

    Returns:
        Success message string.
    """
    s3 = _get_s3_client()
    s3.put_object(
        Bucket=config.obsidian_s3_bucket,
        Key=_full_key(path),
        Body=content.encode("utf-8"),
        ContentType="text/markdown",
    )
    logger.info(f"Wrote note: {path}")
    return f"Note saved: {path}"


def delete_note(path: str) -> str:
    """Delete a note from S3.

    Args:
        path: Vault-relative path.

    Returns:
        Success message string.
    """
    s3 = _get_s3_client()
    s3.delete_object(Bucket=config.obsidian_s3_bucket, Key=_full_key(path))
    logger.info(f"Deleted note: {path}")
    return f"Note deleted: {path}"


def list_folders() -> list[str]:
    """List top-level folders in the vault.

    Returns:
        List of folder names.
    """
    s3 = _get_s3_client()
    prefix = _full_key("")

    response = s3.list_objects_v2(
        Bucket=config.obsidian_s3_bucket,
        Prefix=prefix,
        Delimiter="/",
    )

    folders = []
    for cp in response.get("CommonPrefixes", []):
        folder_name = _strip_prefix(cp["Prefix"]).strip("/")
        if folder_name:
            folders.append(folder_name)
    return folders


def search_notes(query: str, folder: str = "", max_files: int = 500) -> list[dict]:
    """Search note contents for a query string.

    Lists notes in the given folder, downloads each, and checks for the query.
    Stops after scanning max_files files.

    Args:
        query: Text to search for (case-insensitive).
        folder: Vault-relative folder to search in. Empty for entire vault.
        max_files: Maximum number of files to scan.

    Returns:
        List of dicts with keys: path, snippet (context around match).
    """
    notes = list_notes(folder)
    query_lower = query.lower()
    results = []

    for note_meta in notes[:max_files]:
        try:
            content = read_note(note_meta["path"])
        except FileNotFoundError:
            continue

        content_lower = content.lower()
        idx = content_lower.find(query_lower)
        if idx == -1:
            continue

        # Extract a snippet around the match
        start = max(0, idx - 80)
        end = min(len(content), idx + len(query) + 80)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        results.append({"path": note_meta["path"], "snippet": snippet})

    return results


def reset_client():
    """Reset the cached S3 client. Used for testing."""
    global _s3_client
    _s3_client = None
