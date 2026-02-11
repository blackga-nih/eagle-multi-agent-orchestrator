#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { EvalObservabilityStack } from '../lib/eval-stack';

const app = new cdk.App();
new EvalObservabilityStack(app, 'EagleEvalStack', {
  env: { region: 'us-east-1' },
});
