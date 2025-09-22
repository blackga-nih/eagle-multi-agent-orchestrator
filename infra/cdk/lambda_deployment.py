from aws_cdk import (
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_iam as iam,
    CfnOutput,
    Duration
)
from constructs import Construct

class LambdaDeploymentConstruct(Construct):
    def __init__(self, scope: Construct, construct_id: str, 
                 user_pool_id: str, client_id: str, agent_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # Lambda execution role
        self.lambda_role = iam.Role(
            self, "ChatAppLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonDynamoDBFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonCognitoPowerUser")
            ]
        )
        
        # Lambda function
        self.lambda_function = lambda_.Function(
            self, "ChatAppLambda",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="lambda_handler.handler",
            code=lambda_.Code.from_asset("../lambda_package"),  # Will be created
            role=self.lambda_role,
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "COGNITO_USER_POOL_ID": user_pool_id,
                "COGNITO_CLIENT_ID": client_id,
                "BEDROCK_AGENT_ID": agent_id,
                "SESSIONS_TABLE": "tenant-sessions",
                "USAGE_TABLE": "tenant-usage",
                "JWT_SECRET": "lambda-secret"
            }
        )
        
        # API Gateway
        self.api = apigw.LambdaRestApi(
            self, "ChatAppAPI",
            handler=self.lambda_function,
            proxy=True,
            cors_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"]
            )
        )
        
        # Outputs
        CfnOutput(self, "APIEndpoint", value=self.api.url)
        CfnOutput(self, "LambdaFunctionName", value=self.lambda_function.function_name)