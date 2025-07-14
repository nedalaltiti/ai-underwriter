#!/usr/bin/env python3
# scripts/test_webhook_endpoints.py
"""Test script to verify webhook endpoints are properly configured."""

import asyncio
import httpx
import json
from datetime import datetime

async def test_endpoints():
    """Test all webhook endpoints."""
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        print("🧪 Testing webhook service endpoints...\n")
        
        # Test 1: Health check (API endpoint)
        try:
            response = await client.get(f"{base_url}/api/v1/health")
            print(f"✅ Health Check: {response.status_code}")
            if response.status_code == 200:
                health = response.json()
                print(f"   Status: {health.get('status')}")
                print(f"   Service: {health.get('service')}")
        except Exception as e:
            print(f"❌ Health Check Failed: {e}")
        
        # Test 2: Metrics (API endpoint)  
        try:
            response = await client.get(f"{base_url}/api/v1/metrics")
            print(f"✅ Metrics: {response.status_code}")
            if response.status_code == 200:
                metrics = response.json()
                print(f"   Total requests: {metrics.get('metrics', {}).get('total_requests', 0)}")
        except Exception as e:
            print(f"❌ Metrics Failed: {e}")
        
        # Test 3: Webhook verification (GET)
        try:
            response = await client.get(f"{base_url}/webhook/forth")
            print(f"✅ Webhook GET: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Status: {data.get('status')}")
        except Exception as e:
            print(f"❌ Webhook GET Failed: {e}")
        
        # Test 4: Webhook POST (simulate Forth CRM)
        test_payload = {
            "contact_id": "12345",
            "doc_id": "67890",
            "doc_type": "agreement",
            "doc_name": "test-contract.pdf",
            "source": "test"
        }
        
        try:
            response = await client.post(
                f"{base_url}/webhook/forth",
                json=test_payload,
                headers={"Content-Type": "application/json"}
            )
            print(f"✅ Webhook POST: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                print(f"   Status: {result.get('status')}")
                print(f"   Correlation ID: {result.get('correlation_id')}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"❌ Webhook POST Failed: {e}")
        
        print(f"\n🎯 Expected endpoints:")
        print(f"   Health: {base_url}/api/v1/health")
        print(f"   Metrics: {base_url}/api/v1/metrics") 
        print(f"   Webhook: {base_url}/webhook/forth")

if __name__ == "__main__":
    asyncio.run(test_endpoints()) 