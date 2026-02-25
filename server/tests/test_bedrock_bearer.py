"""
Test Bedrock Short-term API Key (Bearer Token Authentication).

This tests the simplified API key auth method from AWS Console:
Bedrock > Model access > Short-term API keys

Set the key in your environment:
  export AWS_BEARER_TOKEN_BEDROCK=bedrock-api-key-YmVkcm9jay...
"""

import os
import json
import sys

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)


REGION = "us-east-1"
ENDPOINT = f"https://bedrock-runtime.{REGION}.amazonaws.com"
MODEL_ID = "anthropic.claude-haiku-4-5-20251001-v1:0"


def get_api_key():
    """Get the bearer token from environment."""
    key = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
    if not key:
        # Try loading from .env file
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("AWS_BEARER_TOKEN_BEDROCK="):
                        key = line.split("=", 1)[1].strip()
                        break
    return key


def test_bearer_auth():
    """Test Bedrock API with bearer token authentication."""
    print("=" * 60)
    print("TEST: Bedrock Short-term API Key (Bearer Token)")
    print("=" * 60)

    api_key = get_api_key()
    if not api_key:
        print("ERROR: AWS_BEARER_TOKEN_BEDROCK not set")
        print("\nTo set it:")
        print("  1. Go to AWS Console > Bedrock > Model access > Short-term API keys")
        print("  2. Copy the API key")
        print("  3. Run: export AWS_BEARER_TOKEN_BEDROCK='bedrock-api-key-...'")
        return False

    print(f"  API Key: {api_key[:30]}...{api_key[-10:]}")
    print(f"  Endpoint: {ENDPOINT}")
    print(f"  Model: {MODEL_ID}")

    url = f"{ENDPOINT}/model/{MODEL_ID}/invoke"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Tell me a funny joke."}],
    }

    print(f"\n  Sending request...")

    try:
        response = requests.post(url, headers=headers, json=body, timeout=30)

        if response.status_code == 200:
            result = response.json()
            text = result["content"][0]["text"]
            usage = result.get("usage", {})

            print(f"  Status: {response.status_code} OK")
            print(f"  Response: {text}")
            print(f"  Tokens: {usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out")
            print("\n  PASS - Bearer token authentication works!")
            return True
        else:
            print(f"  Status: {response.status_code}")
            print(f"  Error: {response.text}")

            if response.status_code == 403:
                print("\n  HINT: Token may be expired (12 hour limit) - get a new one from AWS Console")
            elif response.status_code == 401:
                print("\n  HINT: Invalid token format - ensure you copied the full key")

            print("\n  FAIL")
            return False

    except requests.exceptions.RequestException as e:
        print(f"  Request failed: {e}")
        print("\n  FAIL")
        return False


def main():
    success = test_bearer_auth()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
