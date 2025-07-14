# tests/unit/test_document_downloader.py
from datetime import UTC
import pytest
from unittest.mock import Mock, AsyncMock, patch
import tempfile
from pathlib import Path
from datetime import datetime, UTC

from document_downloader.core.downloader import DocumentDownloader
from document_downloader.models.download import DownloadTask
from document_downloader.config import DocumentConfig


@pytest.mark.asyncio
class TestDocumentDownloader:
    """Test document downloader functionality."""
    
    async def test_download_document_success(self, temp_dir):
        """Test successful document download."""
        # Setup
        config = DocumentConfig(
            service_name="test-downloader",
            temp_dir=str(temp_dir)
        )
        
        # Mock dependencies
        mock_forth_client = AsyncMock()
        mock_forth_client.get_document.return_value = {
            "download_url": "https://example.com/doc.pdf"
        }
        
        mock_s3_adapter = AsyncMock()
        mock_s3_adapter.upload_file.return_value = {
            "url": "https://s3.example.com/doc.pdf",
            "content_type": "application/pdf"
        }
        
        downloader = DocumentDownloader(config, mock_forth_client, mock_s3_adapter)
        
        # Mock HTTP download
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b"PDF content"
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            # Create task
            task = DownloadTask(
                contact_id="12345",
                doc_id="67890",
                doc_name="test.pdf"
            )
            
            # Execute
            result = await downloader.download_document(task)
        
        # Assert
        assert result.success is True
        assert result.s3_key is not None
        assert result.file_size == 11  # len(b"PDF content")
        assert result.processing_time_ms > 0
        
        # Verify S3 upload was called
        mock_s3_adapter.upload_file.assert_called_once()
        upload_call = mock_s3_adapter.upload_file.call_args
        assert "12345" in upload_call[1]["s3_key"]  # contact_id in key
        assert "67890" in upload_call[1]["s3_key"]  # doc_id in key
    
    async def test_download_document_http_error(self, temp_dir):
        """Test document download with HTTP error."""
        config = DocumentConfig(temp_dir=str(temp_dir))
        
        mock_forth_client = AsyncMock()
        mock_forth_client.get_document.return_value = {
            "download_url": "https://example.com/doc.pdf"
        }
        
        mock_s3_adapter = AsyncMock()
        
        downloader = DocumentDownloader(config, mock_forth_client, mock_s3_adapter)
        
        # Mock HTTP error
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            task = DownloadTask(contact_id="12345", doc_id="67890")
            result = await downloader.download_document(task)
        
        assert result.success is False
        assert "Download failed" in result.error_message
        assert not mock_s3_adapter.upload_file.called
    
    async def test_generate_s3_key(self):
        """Test S3 key generation."""
        config = DocumentConfig(s3_prefix="contracts")
        downloader = DocumentDownloader(config, None, None)
        
        task = DownloadTask(
            contact_id="12345",
            doc_id="67890",
            doc_name="test document.pdf"
        )
        
        s3_key = downloader._generate_s3_key(task)
        
        # Verify key structure
        assert s3_key.startswith("contracts/")
        assert "12345" in s3_key  # contact_id
        assert "67890" in s3_key  # doc_id
        assert s3_key.endswith("test document.pdf")
        
        # Verify date partitioning
        date_part = datetime.now(UTC).strftime("%Y/%m/%d")
        assert date_part in s3_key