#!/usr/bin/env python3
"""
Generate a secure webhook secret for authentication.

This script generates a cryptographically secure random secret
that meets the minimum requirements for webhook authentication.
"""

import secrets
import string

def generate_webhook_secret(length: int = 64) -> str:
    """
    Generate a cryptographically secure webhook secret.
    
    Args:
        length: Length of the secret (minimum 32 characters)
        
    Returns:
        Secure random string suitable for webhook authentication
    """
    if length < 32:
        raise ValueError("Webhook secret must be at least 32 characters long")
    
    # Use a mix of letters, digits, and safe symbols
    alphabet = string.ascii_letters + string.digits + "_-"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

if __name__ == "__main__":
    secret = generate_webhook_secret()
    print("Generated webhook secret (save this securely):")
    print(f"WEBHOOK_SECRET={secret}")
    print(f"\nSecret length: {len(secret)} characters")
    print("Add this to your environment variables or .env file")
