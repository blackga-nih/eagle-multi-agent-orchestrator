import { NextResponse } from 'next/server';
import {
  CloudWatchLogsClient,
  DescribeLogStreamsCommand,
  GetLogEventsCommand,
} from '@aws-sdk/client-cloudwatch-logs';

const REGION = process.env.AWS_REGION || 'us-east-1';
const TEST_RUNS_LOG_GROUP = '/eagle/test-runs';
const APP_LOG_GROUP = '/eagle/app';

function getClient() {
  return new CloudWatchLogsClient({ region: REGION });
}

/**
 * GET /api/cloudwatch
 *
 * Query params:
 *   ?runs=1                          → list recent test-run log streams
 *   ?stream=<name>&group=test-runs   → fetch events from a specific stream
 *   ?group=app&limit=50              → fetch recent app log events
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const listRuns = searchParams.get('runs');
  const stream = searchParams.get('stream');
  const group = searchParams.get('group') || 'test-runs';
  const limit = parseInt(searchParams.get('limit') || '100', 10);

  const logGroup = group === 'app' ? APP_LOG_GROUP : TEST_RUNS_LOG_GROUP;

  try {
    const client = getClient();

    if (listRuns) {
      // List recent log streams (runs)
      const response = await client.send(
        new DescribeLogStreamsCommand({
          logGroupName: logGroup,
          orderBy: 'LastEventTime',
          descending: true,
          limit: Math.min(limit, 50),
        }),
      );

      const streams = (response.logStreams || []).map((s) => ({
        name: s.logStreamName,
        created: s.creationTime ? new Date(s.creationTime).toISOString() : null,
        lastEvent: s.lastEventTimestamp ? new Date(s.lastEventTimestamp).toISOString() : null,
        storedBytes: s.storedBytes,
      }));

      return NextResponse.json({ logGroup, streams });
    }

    if (stream) {
      // Fetch events from a specific stream
      const response = await client.send(
        new GetLogEventsCommand({
          logGroupName: logGroup,
          logStreamName: stream,
          startFromHead: true,
          limit: Math.min(limit, 500),
        }),
      );

      const events = (response.events || []).map((e) => {
        let parsed = null;
        try {
          parsed = JSON.parse(e.message || '');
        } catch {
          // not JSON, keep raw
        }
        return {
          timestamp: e.timestamp ? new Date(e.timestamp).toISOString() : null,
          message: parsed || e.message,
        };
      });

      return NextResponse.json({ logGroup, stream, events });
    }

    // Default: fetch most recent events from the log group's latest stream
    const streamsResp = await client.send(
      new DescribeLogStreamsCommand({
        logGroupName: logGroup,
        orderBy: 'LastEventTime',
        descending: true,
        limit: 1,
      }),
    );

    const latestStream = streamsResp.logStreams?.[0];
    if (!latestStream?.logStreamName) {
      return NextResponse.json({
        logGroup,
        stream: null,
        events: [],
        message: 'No log streams found',
      });
    }

    const eventsResp = await client.send(
      new GetLogEventsCommand({
        logGroupName: logGroup,
        logStreamName: latestStream.logStreamName,
        startFromHead: true,
        limit: Math.min(limit, 500),
      }),
    );

    const events = (eventsResp.events || []).map((e) => {
      let parsed = null;
      try {
        parsed = JSON.parse(e.message || '');
      } catch {
        // not JSON
      }
      return {
        timestamp: e.timestamp ? new Date(e.timestamp).toISOString() : null,
        message: parsed || e.message,
      };
    });

    return NextResponse.json({
      logGroup,
      stream: latestStream.logStreamName,
      events,
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    const isNotFound =
      message.includes('ResourceNotFoundException') || message.includes('does not exist');

    if (isNotFound) {
      return NextResponse.json(
        {
          logGroup,
          error: `Log group ${logGroup} not found. Run test_eagle_sdk_eval.py to create it.`,
          available: false,
        },
        { status: 404 },
      );
    }

    return NextResponse.json(
      {
        error: `CloudWatch error: ${message}`,
        available: false,
      },
      { status: 500 },
    );
  }
}
