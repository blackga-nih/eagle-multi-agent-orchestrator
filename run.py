#!/usr/bin/env python3
"""
Multi-Tenant Bedrock Chat Application Runner
"""
import uvicorn
from config import Config

def main():
    """Run the multi-tenant chat application"""
    
    # Validate configuration
    config_check = Config.validate_config()
    
    if not config_check["valid"]:
        print("❌ Configuration errors:")
        for error in config_check["errors"]:
            print(f"  - {error}")
        print("\n📋 Required environment variables:")
        print("  - BEDROCK_AGENT_ID: Your Bedrock Agent ID")
        print("  - AWS_REGION: AWS region (default: us-east-1)")
        print("\n💡 Example:")
        print("  export BEDROCK_AGENT_ID=your-agent-id")
        print("  export AWS_REGION=us-east-1")
        return
    
    print("✅ Configuration valid")
    print(f"🤖 Agent ID: {config_check['config']['agent_id']}")
    print(f"🌍 Region: {config_check['config']['aws_region']}")
    print(f"🚀 Starting server on http://{Config.APP_HOST}:{Config.APP_PORT}")
    
    # Run the application
    uvicorn.run(
        "app.main:app",
        host=Config.APP_HOST,
        port=Config.APP_PORT,
        reload=True
    )

if __name__ == "__main__":
    main()