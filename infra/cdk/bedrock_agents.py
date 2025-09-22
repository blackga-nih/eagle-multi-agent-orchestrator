from aws_cdk import (
    aws_bedrock as bedrock,
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_iam as iam,
    CfnOutput
)
from constructs import Construct

class BedrockAgentsConstruct(Construct):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # S3 bucket for agent schemas and knowledge base
        self.agent_bucket = s3.Bucket(
            self, "AgentBucket",
            bucket_name="multi-tenant-agent-assets",
            versioned=True
        )
        
        # Lambda for Action Groups
        self.action_lambda = lambda_.Function(
            self, "TenantActionLambda",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import json

def handler(event, context):
    # Extract tenant context from event
    tenant_id = event.get('sessionAttributes', {}).get('tenant_id', 'unknown')
    action = event.get('actionGroup', 'unknown')
    
    # Tenant-specific actions
    if action == 'get_tenant_info':
        return {
            'response': {
                'actionGroupInvocationOutput': {
                    'text': f'Information for tenant {tenant_id}: Active subscription, 100 users'
                }
            }
        }
    
    return {
        'response': {
            'actionGroupInvocationOutput': {
                'text': f'Action {action} executed for tenant {tenant_id}'
            }
        }
    }
            """)
        )
        
        # IAM role for Bedrock Agent
        self.agent_role = iam.Role(
            self, "BedrockAgentExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess")
            ]
        )
        
        # Grant Lambda invoke permissions
        self.action_lambda.grant_invoke(self.agent_role)
        
        # Bedrock Agent
        self.agent = bedrock.CfnAgent(
            self, "MultiTenantAgent",
            agent_name="multi-tenant-assistant",
            foundation_model="anthropic.claude-3-5-sonnet-20241022-v2:0",  # Latest Claude model
            instruction="""You are a multi-tenant AI assistant. Use the tenant_id from session attributes to provide tenant-specific responses. 

Key behaviors:
- Always acknowledge the tenant context
- Use action groups to fetch tenant-specific information
- Provide responses tailored to the organization
- Maintain conversation context per tenant session""",
            agent_resource_role_arn=self.agent_role.role_arn,
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="tenant_actions",
                    description="Actions for tenant-specific operations",
                    action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                        lambda_=self.action_lambda.function_arn
                    ),
                    function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                        functions=[
                            bedrock.CfnAgent.FunctionProperty(
                                name="get_tenant_info",
                                description="Get information about the current tenant",
                                parameters={
                                    "tenant_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        description="The tenant identifier"
                                    )
                                }
                            )
                        ]
                    )
                )
            ]
        )
        
        # Agent Alias
        self.agent_alias = bedrock.CfnAgentAlias(
            self, "MultiTenantAgentAlias",
            agent_alias_name="production",
            agent_id=self.agent.attr_agent_id,
            description="Production alias for multi-tenant agent"
        )
        
        # Outputs
        CfnOutput(self, "AgentId", value=self.agent.attr_agent_id)
        CfnOutput(self, "AgentAliasId", value=self.agent_alias.attr_agent_alias_id)