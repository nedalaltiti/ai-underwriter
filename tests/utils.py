# tests/utils.py - Test utilities
import asyncio
from typing import Callable, Any


async def wait_for_condition(
    condition: Callable[[], bool],
    timeout: float = 30,
    interval: float = 1
) -> bool:
    """Wait for a condition to become true."""
    start_time = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start_time < timeout:
        if await asyncio.coroutine(condition)() if asyncio.iscoroutinefunction(condition) else condition():
            return True
        
        await asyncio.sleep(interval)
    
    raise TimeoutError(f"Condition not met within {timeout} seconds")


def create_test_document(content: str = None) -> bytes:
    """Create a test PDF document."""
    # This would use a library like reportlab to create actual PDFs
    # For testing, we'll just return mock content
    if content is None:
        content = """
        CONTRACT AGREEMENT
        
        Client Name: John Doe
        Date of Birth: 01/15/1980
        SSN: XXX-XX-1234
        
        Address: 123 Main St, Los Angeles, CA 90001
        
        Financial Hardship: Loss of employment due to company downsizing.
        
        Enrolled Debts:
        1. Chase Credit Card - $10,000
        2. Bank of America Personal Loan - $15,000
        
        Total Debt: $25,000
        Monthly Payment: $500
        Program Length: 48 months
        
        Signatures:
        Client: /s/ John Doe
        Date: 01/01/2024
        """
    
    return content.encode('utf-8')