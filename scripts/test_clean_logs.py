#!/usr/bin/env python3
# scripts/test_clean_logs.py
"""Test the new clean logging format."""

import asyncio
import httpx
import time

async def test_webhook_with_logging():
    """Test webhook with clean logging output."""
    
    print("🧪 Testing webhook with improved logging...\n")
    
    # Test different document types to see logging in action
    test_cases = [
        {
            "name": "Simple Agreement",
            "payload": {
                "contact_id": "1001",
                "doc_id": "2001", 
                "doc_type": "agreement",
                "doc_name": "simple-contract.pdf"
            }
        },
        {
            "name": "Complex Contract Type",
            "payload": {
                "contact_id": "1002",
                "doc_id": "2002,2003,2004",  # Multiple IDs
                "doc_type": "contract / agreement",  # Complex type
                "doc_name": "complex-contract.pdf"
            }
        },
        {
            "name": "Hardship Document", 
            "payload": {
                "contact_id": "1003",
                "doc_id": "2005",
                "doc_type": "hardship",
                "doc_name": "hardship-letter.pdf",
                "hardship_description": "Medical emergency"
            }
        }
    ]
    
    async with httpx.AsyncClient() as client:
        for i, test_case in enumerate(test_cases, 1):
            print(f"Test {i}: {test_case['name']}")
            
            try:
                response = await client.post(
                    "http://localhost:8000/webhook/forth",
                    json=test_case["payload"],
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"✅ Status: {result['status']}")
                    print(f"   Processing time: {result['processing_time_ms']}ms")
                else:
                    print(f"❌ Failed: {response.status_code}")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
            
            print()
            time.sleep(1)  # Small delay between tests
    
    print("📋 Check the terminal output above for clean, readable logs!")

if __name__ == "__main__":
    asyncio.run(test_webhook_with_logging()) 