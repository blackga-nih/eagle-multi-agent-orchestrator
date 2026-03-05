import * as cdk from 'aws-cdk-lib';
import * as backup from 'aws-cdk-lib/aws-backup';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as events from 'aws-cdk-lib/aws-events';
import { Construct } from 'constructs';
import { EagleConfig } from '../config/environments';

export interface EagleBackupStackProps extends cdk.StackProps {
  config: EagleConfig;
}

/**
 * EagleBackupStack
 *
 * Provides scheduled backups for the Eagle DynamoDB tables and S3 document bucket.
 *
 * NOTE: AWS Backup minimum schedule is 1 hour — true 15-minute snapshots are not
 * supported by any AWS service. Instead, we use two complementary strategies:
 *
 *   1. DynamoDB PITR (Point-in-Time Recovery) — continuous backup at the table level,
 *      enabled directly on each table. Allows restore to any second in the last 35 days.
 *      This surpasses a 15-minute snapshot schedule.
 *
 *   2. AWS Backup vault + plan:
 *      - Hourly rule  → explicit DynamoDB snapshots, 7-day retention
 *      - Daily rule   → DynamoDB + S3, 30-day retention
 *
 * Resources targeted:
 *   - eagle          (main single-table, sessions/messages/usage)
 *   - eagle-document-metadata-{env}  (document metadata)
 *   - eagle-documents-{account}-{env} (S3 document bucket)
 */
export class EagleBackupStack extends cdk.Stack {
  public readonly vault: backup.BackupVault;

  constructor(scope: Construct, id: string, props: EagleBackupStackProps) {
    super(scope, id, props);
    const { config } = props;

    // ── Backup Vault ─────────────────────────────────────────
    this.vault = new backup.BackupVault(this, 'BackupVault', {
      backupVaultName: `eagle-backup-vault-${config.env}`,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // ── IAM: Backup service role ──────────────────────────────
    // AWS Backup needs permission to read DynamoDB + S3 and write backup copies.
    const backupRole = new iam.Role(this, 'BackupRole', {
      roleName: `eagle-backup-role-${config.env}`,
      assumedBy: new iam.ServicePrincipal('backup.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSBackupServiceRolePolicyForBackup'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSBackupServiceRolePolicyForRestores'),
        // S3 backup requires this additional managed policy
        iam.ManagedPolicy.fromAwsManagedPolicyName('AWSBackupServiceRolePolicyForS3Backup'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AWSBackupServiceRolePolicyForS3Restore'),
      ],
    });

    // ── Resource ARNs ─────────────────────────────────────────
    const eagleTableArn = `arn:aws:dynamodb:${this.region}:${this.account}:table/${config.eagleTableName}`;
    const metadataTableArn = `arn:aws:dynamodb:${this.region}:${this.account}:table/${config.documentMetadataTableName}`;
    const documentBucketArn = `arn:aws:s3:::${config.documentBucketName}`;

    // ── Backup Plan ───────────────────────────────────────────
    const plan = new backup.BackupPlan(this, 'BackupPlan', {
      backupPlanName: `eagle-backup-plan-${config.env}`,
      backupVault: this.vault,
      backupPlanRules: [
        // Hourly snapshots of DynamoDB tables — 7-day retention.
        // Closest practical equivalent to "every 15 minutes"; PITR handles
        // sub-hour recovery within the 35-day continuous backup window.
        new backup.BackupPlanRule({
          ruleName: 'HourlyDynamoDB',
          backupVault: this.vault,
          scheduleExpression: events.Schedule.cron({ minute: '0', hour: '*' }),
          startWindow: cdk.Duration.hours(1),
          completionWindow: cdk.Duration.hours(2),
          deleteAfter: cdk.Duration.days(7),
          enableContinuousBackup: true,  // enables PITR-backed continuous on the backup job
        }),
        // Daily backup of all resources — 30-day retention.
        new backup.BackupPlanRule({
          ruleName: 'DailyAll',
          backupVault: this.vault,
          scheduleExpression: events.Schedule.cron({ minute: '0', hour: '2' }),  // 2 AM UTC
          startWindow: cdk.Duration.hours(1),
          completionWindow: cdk.Duration.hours(4),
          deleteAfter: cdk.Duration.days(30),
          enableContinuousBackup: true,
        }),
      ],
    });

    // ── Backup Selection: DynamoDB tables ─────────────────────
    plan.addSelection('DynamoDBSelection', {
      backupSelectionName: `eagle-dynamodb-${config.env}`,
      role: backupRole,
      resources: [
        backup.BackupResource.fromArn(eagleTableArn),
        backup.BackupResource.fromArn(metadataTableArn),
      ],
    });

    // ── Backup Selection: S3 document bucket ──────────────────
    // S3 backup requires bucket versioning (already enabled on documentBucket).
    plan.addSelection('S3Selection', {
      backupSelectionName: `eagle-s3-${config.env}`,
      role: backupRole,
      resources: [
        backup.BackupResource.fromArn(documentBucketArn),
      ],
    });

    // ── Outputs ───────────────────────────────────────────────
    new cdk.CfnOutput(this, 'BackupVaultName', {
      value: this.vault.backupVaultName,
      exportName: `eagle-backup-vault-name-${config.env}`,
    });
    new cdk.CfnOutput(this, 'BackupVaultArn', {
      value: this.vault.backupVaultArn,
      exportName: `eagle-backup-vault-arn-${config.env}`,
    });
    new cdk.CfnOutput(this, 'BackupPlanId', {
      value: plan.backupPlanId,
      exportName: `eagle-backup-plan-id-${config.env}`,
    });
  }
}
