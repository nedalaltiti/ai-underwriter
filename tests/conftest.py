# tests/conftest.py - Shared test fixtures
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from unittest.mock import Mock, AsyncMock
import tempfile
from pathlib import Path

from libs.forth_shared.models.queue import QueueMessage, MessageType
from libs.forth_shared.adapters.queue import QueueAdapter


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest_asyncio.fixture
async def mock_queue_adapter() -> AsyncMock:
    """Mock queue adapter for testing."""
    adapter = AsyncMock(spec=QueueAdapter)
    adapter.send_message.return_value = "mock-message-id"
    adapter.receive_messages.return_value = []
    adapter.delete_message.return_value = True
    adapter.health_check.return_value = {"status": "healthy"}
    return adapter


@pytest_asyncio.fixture
async def mock_llm_provider() -> AsyncMock:
    """Mock LLM provider for testing."""
    from contract_parser.infrastructure.llm.base import LLMProvider, LLMResponse
    
    provider = AsyncMock(spec=LLMProvider)
    provider.generate.return_value = LLMResponse(
        content='{"result": "test"}',
        model="test-model",
        usage={"prompt_tokens": 100, "completion_tokens": 50}
    )
    provider.health_check.return_value = True
    return provider


@pytest.fixture
def sample_webhook_payload():
    """Sample webhook payload for testing."""
    return {
        "contact_id": "12345",
        "doc_id": "67890",
        "doc_type": "agreement",
        "doc_name": "test_agreement.pdf",
        "correlation_id": "test-correlation-id"
    }


@pytest.fixture
def sample_queue_message():
    """Sample queue message for testing."""
    return QueueMessage(
        message_type=MessageType.CONTRACT_DOWNLOAD,
        contact_id="12345",
        correlation_id="test-correlation-id",
        data={
            "doc_id": "67890",
            "doc_type": "agreement",
            "doc_name": "test_agreement.pdf"
        }
    )