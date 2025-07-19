#!/usr/bin/env python3
"""
Quick test to check if OpenAI Responses API is available directly on the client.
"""

import os
from openai import OpenAI


def test_responses_api():
    """Test if the Responses API is available directly on the client."""
    try:
        # Create client
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "test-key"))

        # Test if responses is available directly
        print("Testing OpenAI client structure...")
        print(f"Client has responses attribute: {hasattr(client, 'responses')}")

        if hasattr(client, "responses"):
            print("✅ Responses API is available directly on the client!")
            # Try to access the create method
            if hasattr(client.responses, "create"):
                print("✅ Responses API create method is available!")
                # Try a dry run (should fail gracefully if not configured)
                try:
                    resp = client.responses.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": "Hello"}],
                        max_tokens=5,
                    )
                    print(f"Response object: {resp}")
                except Exception as e:
                    print(f"(Expected) Error calling responses.create: {e}")
                return True
            else:
                print("❌ Responses API create method not found")
        else:
            print("❌ Responses API not found directly on client")
        return False
    except Exception as e:
        print(f"❌ Error testing Responses API: {e}")
        return False


if __name__ == "__main__":
    test_responses_api()
