#!/usr/bin/env python3
# scripts/test_imports.py
# Test script to verify all imports work correctly

import sys
import os
from pathlib import Path

# Add project paths to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "services" / "webhook-ingestion" / "src"))
sys.path.insert(0, str(project_root / "services" / "shared"))

def test_shared_imports():
    """Test importing from forth_shared library."""
    print("🧪 Testing forth_shared imports...")
    
    try:
        from forth_shared.models.queue import QueueMessage, MessageType
        print("✅ forth_shared.models.queue imported successfully")
        
        from forth_shared.adapters.queue import QueueAdapter, SQSAdapter
        print("✅ forth_shared.adapters.queue imported successfully")
        
        from forth_shared.config.base import BaseServiceConfig
        print("✅ forth_shared.config.base imported successfully")
        
        from forth_shared.utils.logging import setup_logging
        print("✅ forth_shared.utils.logging imported successfully")
        
        from forth_shared.utils.error_handling import ServiceError
        print("✅ forth_shared.utils.error_handling imported successfully")
        
        return True
    except ImportError as e:
        print(f"❌ Failed to import from forth_shared: {e}")
        return False

def test_webhook_imports():
    """Test importing webhook service modules."""
    print("\n🧪 Testing webhook service imports...")
    
    try:
        from config import WebhookConfig
        print("✅ config imported successfully")
        
        from core.processor import WebhookProcessor
        print("✅ core.processor imported successfully")
        
        from core.validators import WebhookValidator
        print("✅ core.validators imported successfully")
        
        from core.exceptions import WebhookError
        print("✅ core.exceptions imported successfully")
        
        from core.security import RateLimiter
        print("✅ core.security imported successfully")
        
        return True
    except ImportError as e:
        print(f"❌ Failed to import webhook modules: {e}")
        return False

def test_integration():
    """Test that webhook service can use shared library."""
    print("\n🧪 Testing integration...")
    
    try:
        from config import WebhookConfig
        from forth_shared.models.queue import QueueMessage, MessageType
        
        # Create a simple test instance
        config = WebhookConfig()
        message = QueueMessage(
            message_type=MessageType.CONTRACT_DOWNLOAD,
            contact_id="12345",
            data={"test": "data"}
        )
        
        print("✅ Integration test passed - webhook service can use shared library")
        print(f"   Config service name: {config.service_name}")
        print(f"   Message type: {message.message_type}")
        return True
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Testing import resolution for webhook-ingestion service\n")
    
    shared_ok = test_shared_imports()
    webhook_ok = test_webhook_imports()
    integration_ok = test_integration()
    
    print(f"\n📊 Test Results:")
    print(f"   Shared library imports: {'✅ PASS' if shared_ok else '❌ FAIL'}")
    print(f"   Webhook service imports: {'✅ PASS' if webhook_ok else '❌ FAIL'}")
    print(f"   Integration test: {'✅ PASS' if integration_ok else '❌ FAIL'}")
    
    if all([shared_ok, webhook_ok, integration_ok]):
        print("\n🎉 All tests passed! Imports are working correctly.")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed. Check the errors above.")
        sys.exit(1) 