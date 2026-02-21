import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import { execSync } from 'child_process';
import * as path from 'path';
import { Construct } from 'constructs';
import { EagleConfig } from '../config/environments';

export interface EagleStorageStackProps extends cdk.StackProps {
  config: EagleConfig;
  appRole: iam.Role;
}

export class EagleStorageStack extends cdk.Stack {
  public readonly documentBucket: s3.Bucket;
  public readonly metadataTable: dynamodb.Table;
  public readonly metadataExtractorFn: lambda.Function;

  constructor(scope: Construct, id: string, props: EagleStorageStackProps) {
    super(scope, id, props);
    const { config, appRole } = props;

    // ── S3 Document Bucket ──────────────────────────────────
    this.documentBucket = new s3.Bucket(this, 'DocumentBucket', {
      bucketName: config.documentBucketName,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [
        {
          noncurrentVersionTransitions: [
            {
              storageClass: s3.StorageClass.INFREQUENT_ACCESS,
              transitionAfter: cdk.Duration.days(90),
            },
          ],
          noncurrentVersionExpiration: cdk.Duration.days(365),
        },
      ],
      cors: [
        {
          allowedMethods: [s3.HttpMethods.GET, s3.HttpMethods.PUT],
          allowedOrigins: ['*'],
          allowedHeaders: ['*'],
          maxAge: 3600,
        },
      ],
    });

    // ── DynamoDB Metadata Table ─────────────────────────────
    this.metadataTable = new dynamodb.Table(this, 'MetadataTable', {
      tableName: config.documentMetadataTableName,
      partitionKey: { name: 'document_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    this.metadataTable.addGlobalSecondaryIndex({
      indexName: 'primary_topic-index',
      partitionKey: { name: 'primary_topic', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'last_updated', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    this.metadataTable.addGlobalSecondaryIndex({
      indexName: 'primary_agent-index',
      partitionKey: { name: 'primary_agent', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'last_updated', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    this.metadataTable.addGlobalSecondaryIndex({
      indexName: 'document_type-index',
      partitionKey: { name: 'document_type', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'last_updated', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // ── Lambda Log Group ────────────────────────────────────
    const lambdaLogGroup = new logs.LogGroup(this, 'MetadataExtractorLogGroup', {
      logGroupName: `/eagle/lambda/metadata-extraction-${config.env}`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ── Lambda: Metadata Extractor ──────────────────────────
    this.metadataExtractorFn = new lambda.Function(this, 'MetadataExtractorFn', {
      functionName: `eagle-metadata-extractor-${config.env}`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset('lambda/metadata-extraction', {
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          command: [
            'bash', '-c',
            'pip install -r requirements.txt -t /asset-output && cp -au . /asset-output',
          ],
          local: {
            tryBundle(outputDir: string) {
              // Use bundle-lambda.py for cross-platform compatibility.
              // On Windows, pip installs Windows binary wheels by default — Lambda needs Linux
              // manylinux wheels. The bundler script detects the host OS and uses
              // `pip --platform manylinux2014_x86_64 --only-binary :all:` on Windows to ensure
              // native C extensions (numpy, cryptography, etc.) are Linux-compatible.
              // See: infrastructure/cdk-eagle/scripts/bundle-lambda.py
              const bundlerScript = path.join(__dirname, '..', 'scripts', 'bundle-lambda.py');
              const lambdaDir = path.join(__dirname, '..', 'lambda', 'metadata-extraction');
              const reqsFile = path.join(lambdaDir, 'requirements.txt');

              // Detect Python executable (Windows may not have 'python3' in PATH)
              let pythonExe = 'python3';
              try {
                execSync('python3 --version', { stdio: 'ignore' });
              } catch {
                try {
                  execSync('python --version', { stdio: 'ignore' });
                  pythonExe = 'python';
                } catch {
                  return false; // No Python available, fall back to Docker
                }
              }

              try {
                execSync(
                  `"${pythonExe}" "${bundlerScript}" "${reqsFile}" "${outputDir}" "${lambdaDir}"`,
                  { stdio: 'inherit' },
                );
                return true;
              } catch (err) {
                console.error('[storage-stack] bundle-lambda.py failed:', err);
                return false; // Fall back to Docker bundling
              }
            },
          },
        },
      }),
      memorySize: config.metadataLambdaMemory,
      timeout: cdk.Duration.seconds(config.metadataLambdaTimeout),
      tracing: lambda.Tracing.ACTIVE,
      logGroup: lambdaLogGroup,
      environment: {
        DOCUMENT_BUCKET: this.documentBucket.bucketName,
        METADATA_TABLE: this.metadataTable.tableName,
        BEDROCK_MODEL_ID: config.bedrockMetadataModelId,
        CATALOG_KEY: 'metadata/metadata-catalog.json',
        AWS_REGION_NAME: config.region,
      },
    });

    // ── S3 Event Notifications → Lambda ─────────────────────
    const suffixes = ['.txt', '.md', '.pdf', '.doc', '.docx'];
    for (const suffix of suffixes) {
      this.documentBucket.addEventNotification(
        s3.EventType.OBJECT_CREATED,
        new s3n.LambdaDestination(this.metadataExtractorFn),
        { suffix },
      );
    }

    // ── Lambda IAM: S3 read docs + write catalog ────────────
    this.documentBucket.grantRead(this.metadataExtractorFn);
    this.documentBucket.grantPut(this.metadataExtractorFn);

    // ── Lambda IAM: DynamoDB write metadata ─────────────────
    this.metadataTable.grantWriteData(this.metadataExtractorFn);

    // ── Lambda IAM: Bedrock Marketplace invoke ──────────────
    this.metadataExtractorFn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'BedrockInvoke',
      actions: ['bedrock:InvokeModel'],
      resources: [
        // Cross-region inference profiles (required for Claude 3.5+ on-demand)
        `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/us.anthropic.*`,
        // Underlying foundation models (Bedrock routes to these across regions)
        `arn:aws:bedrock:*::foundation-model/anthropic.*`,
      ],
    }));

    // ── Cross-stack IAM: Backend (appRole) reads ────────────
    // Construct ARNs from config values to avoid cyclic cross-stack references.
    // Using CDK construct refs (bucketArn/tableArn) would create CloudFormation
    // exports from StorageStack referenced by CoreStack, causing a cycle.
    const bucketArn = `arn:aws:s3:::${config.documentBucketName}`;
    const tableArn = `arn:aws:dynamodb:${this.region}:${this.account}:table/${config.documentMetadataTableName}`;

    appRole.addToPolicy(new iam.PolicyStatement({
      sid: 'DocumentBucketRead',
      actions: ['s3:GetObject', 's3:GetBucketLocation', 's3:ListBucket'],
      resources: [bucketArn, `${bucketArn}/*`],
    }));

    appRole.addToPolicy(new iam.PolicyStatement({
      sid: 'MetadataTableRead',
      actions: [
        'dynamodb:GetItem',
        'dynamodb:Query',
        'dynamodb:Scan',
        'dynamodb:BatchGetItem',
      ],
      resources: [tableArn, `${tableArn}/index/*`],
    }));

    // ── CloudWatch Alarms ───────────────────────────────────
    new cloudwatch.Alarm(this, 'LambdaErrorAlarm', {
      alarmName: `eagle-metadata-extractor-errors-${config.env}`,
      metric: this.metadataExtractorFn.metricErrors({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum',
      }),
      threshold: 3,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      alarmDescription: 'Metadata extractor Lambda errors >= 3 in 5 minutes',
    });

    new cloudwatch.Alarm(this, 'LambdaDurationAlarm', {
      alarmName: `eagle-metadata-extractor-duration-${config.env}`,
      metric: this.metadataExtractorFn.metricDuration({
        period: cdk.Duration.minutes(5),
        statistic: 'p99',
      }),
      threshold: config.metadataLambdaTimeout * 1000 * 0.8,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      alarmDescription: 'Metadata extractor Lambda p99 duration >= 80% of timeout',
    });

    new cloudwatch.Alarm(this, 'LambdaThrottleAlarm', {
      alarmName: `eagle-metadata-extractor-throttles-${config.env}`,
      metric: this.metadataExtractorFn.metricThrottles({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum',
      }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      alarmDescription: 'Metadata extractor Lambda throttled',
    });

    // ── Outputs ─────────────────────────────────────────────
    new cdk.CfnOutput(this, 'DocumentBucketName', {
      value: this.documentBucket.bucketName,
      exportName: `eagle-document-bucket-name-${config.env}`,
    });
    new cdk.CfnOutput(this, 'DocumentBucketArn', {
      value: this.documentBucket.bucketArn,
      exportName: `eagle-document-bucket-arn-${config.env}`,
    });
    new cdk.CfnOutput(this, 'MetadataTableName', {
      value: this.metadataTable.tableName,
      exportName: `eagle-metadata-table-name-${config.env}`,
    });
    new cdk.CfnOutput(this, 'MetadataTableArn', {
      value: this.metadataTable.tableArn,
      exportName: `eagle-metadata-table-arn-${config.env}`,
    });
    new cdk.CfnOutput(this, 'MetadataExtractorFnName', {
      value: this.metadataExtractorFn.functionName,
      exportName: `eagle-metadata-extractor-fn-${config.env}`,
    });
    new cdk.CfnOutput(this, 'MetadataExtractorFnArn', {
      value: this.metadataExtractorFn.functionArn,
      exportName: `eagle-metadata-extractor-fn-arn-${config.env}`,
    });
  }
}
