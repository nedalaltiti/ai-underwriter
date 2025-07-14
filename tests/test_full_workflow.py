# tests/integration/test_full_workflow.py
import pytest
import asyncio
import httpx
from datetime import datetime, UTC
import json

from tests.utils import wait_for_condition, create_test_document


@pytest.mark.integration
@pytest.mark.asyncio
class TestFullWorkflow:
    """Integration tests for the complete document processing workflow."""
    
    async def test_webhook_to_parsing_workflow(self, integration_env):
        """Test complete workflow from webhook to parsed contract."""
        # Step 1: Send webhook
        webhook_payload = {
            "contact_id": "test-12345",
            "doc_id": "test-67890",
            "doc_type": "agreement",
            "doc_name": "test_agreement.pdf",
            "correlation_id": f"test-{datetime.now(UTC).timestamp()}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{integration_env['webhook_url']}/api/v1/webhook/forth",
                json=webhook_payload
            )
            
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        correlation_id = result["correlation_id"]
        
        # Step 2: Wait for document to be downloaded
        await wait_for_condition(
            lambda: self._check_s3_upload(
                integration_env["s3_client"],
                webhook_payload["contact_id"],
                webhook_payload["doc_id"]
            ),
            timeout=30,
            interval=2
        )
        
        # Step 3: Wait for parsing to complete
        await wait_for_condition(
            lambda: self._check_parsing_complete(
                integration_env["parser_url"],
                webhook_payload["contact_id"]
            ),
            timeout=60,
            interval=5
        )
        
        # Step 4: Verify final results
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{integration_env['parser_url']}/api/v1/contracts/{webhook_payload['contact_id']}"
            )
        
        assert response.status_code == 200
        contracts = response.json()
        
        # Find our test contract
        test_contract = next(
            (c for c in contracts if c["doc_id"] == webhook_payload["doc_id"]),
            None
        )
        
        assert test_contract is not None
        assert test_contract["status"] == "completed"
        assert len(test_contract["entities"]) > 0
        assert len(test_contract["validations"]) > 0
    
    async def _check_s3_upload(self, s3_client, contact_id, doc_id):
        """Check if document was uploaded to S3."""
        try:
            # List objects with prefix
            response = s3_client.list_objects_v2(
                Bucket="forth-contracts",
                Prefix=f"contracts/"
            )
            
            # Look for our document
            for obj in response.get("Contents", []):
                if contact_id in obj["Key"] and doc_id in obj["Key"]:
                    return True
            
            return False
        except Exception:
            return False
    
    async def _check_parsing_complete(self, parser_url, contact_id):
        """Check if parsing is complete."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{parser_url}/api/v1/contracts/{contact_id}"
                )
                
                if response.status_code != 200:
                    return False
                
                contracts = response.json()
                return any(
                    c["status"] in ["completed", "validation_failed"]
                    for c in contracts
                )
        except Exception:
            return False
