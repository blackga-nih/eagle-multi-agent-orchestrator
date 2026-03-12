import { NextRequest, NextResponse } from 'next/server';
import {
  CloudWatchLogsClient,
  FilterLogEventsCommand,
} from '@aws-sdk/client-cloudwatch-logs';

const REGION = process.env.AWS_REGION || 'us-east-1';
const APP_LOG_GROUP = process.env.EAGLE_APP_LOG_GROUP || '/eagle/app';

function getClient() {
  return new CloudWatchLogsClient({ region: REGION });
}

/**
 * GET /api/logs/cloudwatch?session_id=<id>&limit=100
 *
 * Fetches recent CloudWatch logs filtered to the session.
 * Handles both structured telemetry events (event_type field) and
 * application logs (level/logger/msg fields).
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const sessionId = searchParams.get('session_id');
  const limit = Math.min(parseInt(searchParams.get('limit') || '100', 10), 500);
  const userId = searchParams.get('user_id') || 'dev-user';

  if (!sessionId) {
    return NextResponse.json(
      { error: 'session_id is required' },
      { status: 400 }
    );
  }

  try {
    const client = getClient();
    const filterPattern = `{ $.session_id = "${sessionId}" }`;
    const startTime = Date.now() - 60 * 60 * 1000;

    const response = await client.send(
      new FilterLogEventsCommand({
        logGroupName: APP_LOG_GROUP,
        filterPattern,
        startTime,
        limit,
        interleaved: true,
      })
    );

    const logs = (response.events || [])
      .map((e) => {
        let parsed: Record<string, unknown> | null = null;
        try {
          parsed = JSON.parse(e.message || '');
        } catch {
          parsed = {
            timestamp: e.timestamp ? new Date(e.timestamp).toISOString() : new Date().toISOString(),
            level: 'INFO',
            logger: 'raw',
            msg: e.message || '',
          };
        }

        // Telemetry events have event_type; app logs have level/logger/msg
        const eventType = parsed?.event_type as string | undefined;
        const isTelemetry = !!eventType;

        return {
          timestamp: parsed?.timestamp
            ? new Date(parsed.timestamp as number).toISOString()
            : parsed?.ts
              ? String(parsed.ts)
              : (e.timestamp ? new Date(e.timestamp).toISOString() : ''),
          // Map telemetry event_type to a level for display
          level: isTelemetry
            ? (eventType!.includes('error') ? 'ERROR' : 'INFO')
            : (parsed?.level as string) || 'INFO',
          logger: isTelemetry
            ? 'telemetry'
            : (parsed?.logger as string) || 'unknown',
          msg: isTelemetry
            ? eventType!
            : (parsed?.msg as string) || e.message || '',
          event_type: eventType || undefined,
          tenant_id: (parsed?.tenant_id as string) || '',
          user_id: (parsed?.user_id as string) || '',
          session_id: (parsed?.session_id as string) || '',
          exc: (parsed?.exc as string) || undefined,
          // Preserve all extra fields (tool_name, tool_input, result_preview, tokens, etc.)
          ...Object.fromEntries(
            Object.entries(parsed || {}).filter(
              ([k]) => ![
                'timestamp', 'ts', 'level', 'logger', 'msg',
                'event_type', 'tenant_id', 'user_id', 'session_id', 'exc',
              ].includes(k)
            )
          ),
        };
      })
      .filter((log) => !log.user_id || log.user_id === userId || userId === 'dev-user')
      .sort((a, b) => new Date(a.timestamp as string).getTime() - new Date(b.timestamp as string).getTime());

    return NextResponse.json({
      logs,
      log_group: APP_LOG_GROUP,
      count: logs.length,
      user_id: userId,
      session_id: sessionId,
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    const isNotFound =
      message.includes('ResourceNotFoundException') ||
      message.includes('does not exist');

    if (isNotFound) {
      return NextResponse.json({
        logs: [],
        log_group: APP_LOG_GROUP,
        count: 0,
        user_id: userId,
        session_id: sessionId,
        note: `Log group ${APP_LOG_GROUP} not found. Logs appear after the backend emits to CloudWatch.`,
      });
    }

    return NextResponse.json(
      { error: `CloudWatch error: ${message}`, logs: [], count: 0 },
      { status: 500 }
    );
  }
}
