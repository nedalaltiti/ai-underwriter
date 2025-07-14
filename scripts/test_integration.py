# scripts/test_integration.py
import asyncio
import httpx
from loguru import logger

async def test_full_workflow():
    """Test complete document processing workflow."""
    
    # 1. Send webhook
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8001/api/v1/webhook/forth",
            json={
                "contact_id": "12345",
                "doc_id": "67890",
                "doc_type": "agreement"
            }
        )
        assert response.status_code == 200
        
    # 2. Wait for processing
    await asyncio.sleep(10)
    
    # 3. Check parser results
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8003/api/v1/contracts/12345"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        
    logger.info("Integration test passed!")

if __name__ == "__main__":
    asyncio.run(test_full_workflow())