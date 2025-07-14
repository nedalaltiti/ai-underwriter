# tests/unit/test_webhook_processor.py
import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, UTC

from webhook_ingestion.core.processor import WebhookProcessor, ProcessingResult
from webhook_ingestion.config import WebhookConfig


@pytest.mark.asyncio
class TestWebhookProcessor:
    """Test webhook processor functionality."""
    
    async def test_process_webhook_success(
        self, 
        mock_queue_adapter, 
        sample_webhook_payload
    ):
        """Test successful webhook processing."""
        # Setup
        config = WebhookConfig(
            service_name="test-webhook",
            output_queue_name="test-queue"
        )
        processor = WebhookProcessor(config)
        processor.queue_adapter = mock_queue_adapter
        
        # Execute
        result = await processor.process_webhook(sample_webhook_payload)
        
        # Assert
        assert result.success is True
        assert result.message_id == "mock-message-id"
        assert result.processing_time_ms > 0
        assert mock_queue_adapter.send_message.called
        
        # Verify queue message
        call_args = mock_queue_adapter.send_message.call_args
        message = call_args[0][0]
        assert message.message_type == MessageType.CONTRACT_DOWNLOAD
        assert message.contact_id == "12345"
        assert message.data["doc_id"] == "67890"
    
    async def test_process_webhook_validation_error(self, mock_queue_adapter):
        """Test webhook processing with validation error."""
        config = WebhookConfig(service_name="test-webhook")
        processor = WebhookProcessor(config)
        processor.queue_adapter = mock_queue_adapter
        
        # Invalid payload (missing required fields)
        invalid_payload = {"doc_id": "12345"}  # Missing contact_id
        
        result = await processor.process_webhook(invalid_payload)
        
        assert result.success is False
        assert "validation" in result.error_message.lower()
        assert not mock_queue_adapter.send_message.called
    
    async def test_process_webhook_queue_error(
        self, 
        mock_queue_adapter, 
        sample_webhook_payload
    ):
        """Test webhook processing with queue error."""
        # Setup queue to fail
        mock_queue_adapter.send_message.side_effect = Exception("Queue error")
        
        config = WebhookConfig(service_name="test-webhook")
        processor = WebhookProcessor(config)
        processor.queue_adapter = mock_queue_adapter
        
        result = await processor.process_webhook(sample_webhook_payload)
        
        assert result.success is False
        assert result.error_message == "Internal processing error"
        assert processor.metrics["queue_errors"] == 1
    
    async def test_health_check(self, mock_queue_adapter):
        """Test health check functionality."""
        config = WebhookConfig(service_name="test-webhook")
        processor = WebhookProcessor(config)
        processor.queue_adapter = mock_queue_adapter
        
        health = await processor.health_check()
        
        assert health["status"] == "healthy"
        assert health["service"] == "test-webhook"
        assert "queue" in health
        assert "timestamp" in health