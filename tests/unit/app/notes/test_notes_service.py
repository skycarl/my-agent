"""
Test notes service (S3 operations).
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.agents.notes.notes_service import (
    list_notes,
    read_note,
    write_note,
    delete_note,
    list_folders,
    search_notes,
    _full_key,
    _strip_prefix,
    reset_client,
)


@pytest.fixture(autouse=True)
def reset_s3_client():
    """Reset the cached S3 client before each test."""
    reset_client()
    yield
    reset_client()


@pytest.fixture
def mock_s3():
    """Mock the boto3 S3 client."""
    with patch("app.agents.notes.notes_service._get_s3_client") as mock_get:
        client = MagicMock()
        mock_get.return_value = client
        yield client


class TestPrefixHandling:
    """Test S3 prefix prepending and stripping."""

    def test_full_key_no_prefix(self):
        with patch("app.agents.notes.notes_service.config") as mock_config:
            mock_config.obsidian_s3_prefix = ""
            assert _full_key("Recipes/Pasta.md") == "Recipes/Pasta.md"

    def test_full_key_with_prefix(self):
        with patch("app.agents.notes.notes_service.config") as mock_config:
            mock_config.obsidian_s3_prefix = "vault"
            assert _full_key("Recipes/Pasta.md") == "vault/Recipes/Pasta.md"

    def test_strip_prefix_no_prefix(self):
        with patch("app.agents.notes.notes_service.config") as mock_config:
            mock_config.obsidian_s3_prefix = ""
            assert _strip_prefix("Recipes/Pasta.md") == "Recipes/Pasta.md"

    def test_strip_prefix_with_prefix(self):
        with patch("app.agents.notes.notes_service.config") as mock_config:
            mock_config.obsidian_s3_prefix = "vault"
            assert _strip_prefix("vault/Recipes/Pasta.md") == "Recipes/Pasta.md"


class TestListNotes:
    """Test list_notes function."""

    def test_list_notes_empty(self, mock_s3):
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Contents": []}]
        mock_s3.get_paginator.return_value = paginator

        result = list_notes()
        assert result == []

    def test_list_notes_with_results(self, mock_s3):
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {
                        "Key": "Recipes/Pasta.md",
                        "Size": 500,
                        "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    }
                ]
            }
        ]
        mock_s3.get_paginator.return_value = paginator

        result = list_notes()
        assert len(result) == 1
        assert result[0]["path"] == "Recipes/Pasta.md"
        assert result[0]["size"] == 500

    def test_list_notes_skips_folder_markers(self, mock_s3):
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {
                        "Key": "Recipes/",
                        "Size": 0,
                        "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    },
                    {
                        "Key": "Recipes/Pasta.md",
                        "Size": 500,
                        "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    },
                ]
            }
        ]
        mock_s3.get_paginator.return_value = paginator

        result = list_notes()
        assert len(result) == 1
        assert result[0]["path"] == "Recipes/Pasta.md"


class TestReadNote:
    """Test read_note function."""

    def test_read_note_success(self, mock_s3):
        body = MagicMock()
        body.read.return_value = b"# My Note\n\nContent here"
        mock_s3.get_object.return_value = {"Body": body}

        result = read_note("Notes/test.md")
        assert result == "# My Note\n\nContent here"

    def test_read_note_not_found(self, mock_s3):
        error = type("NoSuchKey", (Exception,), {})
        mock_s3.exceptions.NoSuchKey = error
        mock_s3.get_object.side_effect = error("Not found")

        with pytest.raises(FileNotFoundError, match="Note not found"):
            read_note("missing.md")


class TestWriteNote:
    """Test write_note function."""

    def test_write_note_success(self, mock_s3):
        result = write_note("Recipes/New.md", "# New Recipe")
        mock_s3.put_object.assert_called_once()
        assert "saved" in result.lower()

    def test_write_note_content_type(self, mock_s3):
        write_note("test.md", "content")
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["ContentType"] == "text/markdown"


class TestDeleteNote:
    """Test delete_note function."""

    def test_delete_note_success(self, mock_s3):
        result = delete_note("old.md")
        mock_s3.delete_object.assert_called_once()
        assert "deleted" in result.lower()


class TestListFolders:
    """Test list_folders function."""

    def test_list_folders_success(self, mock_s3):
        mock_s3.list_objects_v2.return_value = {
            "CommonPrefixes": [
                {"Prefix": "Recipes/"},
                {"Prefix": "Journal/"},
            ]
        }
        result = list_folders()
        assert "Recipes" in result
        assert "Journal" in result

    def test_list_folders_empty(self, mock_s3):
        mock_s3.list_objects_v2.return_value = {}
        result = list_folders()
        assert result == []


class TestSearchNotes:
    """Test search_notes function."""

    def test_search_notes_finds_match(self, mock_s3):
        with (
            patch(
                "app.agents.notes.notes_service.list_notes",
                return_value=[
                    {
                        "path": "Recipes/Pasta.md",
                        "size": 100,
                        "last_modified": "2026-01-01",
                    }
                ],
            ),
            patch(
                "app.agents.notes.notes_service.read_note",
                return_value="# Pasta Recipe\n\nBoil the pasta in salted water",
            ),
        ):
            results = search_notes("pasta")
            assert len(results) == 1
            assert results[0]["path"] == "Recipes/Pasta.md"
            assert "pasta" in results[0]["snippet"].lower()

    def test_search_notes_no_match(self, mock_s3):
        with (
            patch(
                "app.agents.notes.notes_service.list_notes",
                return_value=[
                    {"path": "Notes/test.md", "size": 50, "last_modified": "2026-01-01"}
                ],
            ),
            patch(
                "app.agents.notes.notes_service.read_note",
                return_value="# Something Else",
            ),
        ):
            results = search_notes("pasta")
            assert results == []

    def test_search_notes_case_insensitive(self, mock_s3):
        with (
            patch(
                "app.agents.notes.notes_service.list_notes",
                return_value=[
                    {"path": "test.md", "size": 50, "last_modified": "2026-01-01"}
                ],
            ),
            patch(
                "app.agents.notes.notes_service.read_note",
                return_value="PASTA RECIPE HERE",
            ),
        ):
            results = search_notes("pasta")
            assert len(results) == 1
