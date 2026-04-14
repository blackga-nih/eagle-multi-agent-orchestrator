import * as cdk from 'aws-cdk-lib';
import * as budgets from 'aws-cdk-lib/aws-budgets';
import { Construct } from 'constructs';
import { EagleConfig } from '../config/environments';

export interface EagleCostStackProps extends cdk.StackProps {
  config: EagleConfig;
  /** Email addresses to notify when the daily Bedrock spend threshold is breached. */
  alertEmails: string[];
  /** Daily Bedrock spend cap in USD that triggers the alert. */
  bedrockDailyLimitUsd: number;
}

/**
 * EagleCostStack
 *
 * AWS Budgets alerts for the Eagle account. Currently holds a single budget
 * that fires when daily Bedrock spend exceeds a configured USD amount.
 *
 * Notes:
 *   - AWS Budgets "DAILY" resets at UTC midnight (not a true 24h rolling window).
 *   - Subscribers receive a raw AWS Budgets email — no SNS topic required.
 *   - Budget names must be unique per account, so env is embedded in the name.
 */
export class EagleCostStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: EagleCostStackProps) {
    super(scope, id, props);
    const { config, alertEmails, bedrockDailyLimitUsd } = props;

    const subscribers: budgets.CfnBudget.SubscriberProperty[] = alertEmails.map(
      (address) => ({
        subscriptionType: 'EMAIL',
        address,
      }),
    );

    new budgets.CfnBudget(this, 'BedrockDailyBudget', {
      budget: {
        budgetName: `eagle-bedrock-daily-${config.env}`,
        budgetType: 'COST',
        timeUnit: 'DAILY',
        budgetLimit: {
          amount: bedrockDailyLimitUsd,
          unit: 'USD',
        },
        costFilters: {
          Service: ['Amazon Bedrock'],
        },
        costTypes: {
          includeCredit: false,
          includeDiscount: true,
          includeOtherSubscription: true,
          includeRecurring: true,
          includeRefund: false,
          includeSubscription: true,
          includeSupport: true,
          includeTax: true,
          includeUpfront: true,
          useBlended: false,
          useAmortized: false,
        },
      },
      notificationsWithSubscribers: [
        {
          notification: {
            notificationType: 'ACTUAL',
            comparisonOperator: 'GREATER_THAN',
            threshold: 100,
            thresholdType: 'PERCENTAGE',
          },
          subscribers,
        },
      ],
    });

    new cdk.CfnOutput(this, 'BedrockDailyBudgetName', {
      value: `eagle-bedrock-daily-${config.env}`,
      exportName: `eagle-bedrock-daily-budget-name-${config.env}`,
    });
  }
}
