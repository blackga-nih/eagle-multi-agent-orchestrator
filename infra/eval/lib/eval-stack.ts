import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cw_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import { Construct } from 'constructs';

/** All 27 test names emitted by the eval suite. */
const TEST_NAMES = [
  '1_session_creation',
  '2_session_resume',
  '3_trace_observation',
  '4_subagent_orchestration',
  '5_cost_tracking',
  '6_tier_gated_tools',
  '7_skill_loading',
  '8_subagent_tool_tracking',
  '9_oa_intake_workflow',
  '10_legal_counsel_skill',
  '11_market_intelligence_skill',
  '12_tech_review_skill',
  '13_public_interest_skill',
  '14_document_generator_skill',
  '15_supervisor_multi_skill_chain',
  '16_s3_document_ops',
  '17_dynamodb_intake_ops',
  '18_cloudwatch_logs_ops',
  '19_document_generation',
  '20_cloudwatch_e2e_verification',
  '21_uc02_micro_purchase',
  '22_uc03_option_exercise',
  '23_uc04_contract_modification',
  '24_uc05_co_package_review',
  '25_uc07_contract_closeout',
  '26_uc08_shutdown_notification',
  '27_uc09_score_consolidation',
];

const METRIC_NAMESPACE = 'EAGLE/Eval';

export class EvalObservabilityStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ── S3 bucket for eval artifacts ────────────────────────────
    const bucket = new s3.Bucket(this, 'EvalArtifactsBucket', {
      bucketName: 'eagle-eval-artifacts',
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [
        {
          expiration: cdk.Duration.days(365),
        },
      ],
    });

    // ── CloudWatch Log Group (import existing or create) ───────
    // The log group /eagle/test-runs may already exist (auto-created
    // by the eval suite). Use fromLogGroupName to import it, or
    // create a new one. If deploying fresh, use the new LogGroup.
    // If the group already exists, delete it first or switch to
    // LogGroup.fromLogGroupName().
    const logGroup = new logs.LogGroup(this, 'EvalLogGroup', {
      logGroupName: '/eagle/test-runs',
      retention: logs.RetentionDays.THREE_MONTHS,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // ── SNS topic for eval alerts ──────────────────────────────
    const alertTopic = new sns.Topic(this, 'EvalAlertTopic', {
      topicName: 'eagle-eval-alerts',
      displayName: 'EAGLE Eval Alerts',
    });

    // ── CloudWatch metrics references ──────────────────────────
    const passRateMetric = new cloudwatch.Metric({
      namespace: METRIC_NAMESPACE,
      metricName: 'PassRate',
      statistic: 'Average',
      period: cdk.Duration.hours(1),
    });

    const passedMetric = new cloudwatch.Metric({
      namespace: METRIC_NAMESPACE,
      metricName: 'TestsPassed',
      statistic: 'Sum',
      period: cdk.Duration.hours(1),
    });

    const failedMetric = new cloudwatch.Metric({
      namespace: METRIC_NAMESPACE,
      metricName: 'TestsFailed',
      statistic: 'Sum',
      period: cdk.Duration.hours(1),
    });

    const skippedMetric = new cloudwatch.Metric({
      namespace: METRIC_NAMESPACE,
      metricName: 'TestsSkipped',
      statistic: 'Sum',
      period: cdk.Duration.hours(1),
    });

    const totalCostMetric = new cloudwatch.Metric({
      namespace: METRIC_NAMESPACE,
      metricName: 'TotalCost',
      statistic: 'Average',
      period: cdk.Duration.hours(1),
    });

    // ── CloudWatch Alarm: PassRate < 80% ───────────────────────
    const passRateAlarm = new cloudwatch.Alarm(this, 'EvalPassRateAlarm', {
      alarmName: 'EvalPassRate',
      alarmDescription: 'EAGLE eval pass rate dropped below 80%',
      metric: passRateMetric,
      threshold: 80,
      evaluationPeriods: 1,
      comparisonOperator:
        cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    passRateAlarm.addAlarmAction(new cw_actions.SnsAction(alertTopic));

    // ── Dashboard ──────────────────────────────────────────────
    const dashboard = new cloudwatch.Dashboard(this, 'EvalDashboard', {
      dashboardName: 'EAGLE-Eval-Dashboard',
    });

    // Row 1: PassRate + TestCounts
    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Pass Rate (%)',
        width: 12,
        height: 6,
        left: [passRateMetric],
      }),
      new cloudwatch.GraphWidget({
        title: 'Test Counts',
        width: 12,
        height: 6,
        stacked: true,
        left: [passedMetric, failedMetric, skippedMetric],
      }),
    );

    // Rows 2-6: Per-test status widgets (6 per row, 27 total)
    for (let i = 0; i < TEST_NAMES.length; i += 6) {
      const row = TEST_NAMES.slice(i, i + 6).map(
        (testName) =>
          new cloudwatch.SingleValueWidget({
            title: testName,
            width: 4,
            height: 3,
            metrics: [
              new cloudwatch.Metric({
                namespace: METRIC_NAMESPACE,
                metricName: 'TestStatus',
                dimensionsMap: { TestName: testName },
                statistic: 'Maximum',
                period: cdk.Duration.hours(24),
              }),
            ],
          }),
      );
      dashboard.addWidgets(...row);
    }

    // Row 7: TotalCost
    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Total Cost (USD)',
        width: 12,
        height: 6,
        left: [totalCostMetric],
      }),
    );

    // ── Outputs ────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'EvalBucketName', {
      value: bucket.bucketName,
    });
    new cdk.CfnOutput(this, 'EvalBucketArn', {
      value: bucket.bucketArn,
    });
    new cdk.CfnOutput(this, 'EvalAlertTopicArn', {
      value: alertTopic.topicArn,
    });
    new cdk.CfnOutput(this, 'EvalDashboardName', {
      value: dashboard.dashboardName,
    });
    new cdk.CfnOutput(this, 'EvalPassRateAlarmArn', {
      value: passRateAlarm.alarmArn,
    });
  }
}
