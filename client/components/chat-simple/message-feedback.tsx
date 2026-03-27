'use client';

import { useState, useCallback } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { useAuth } from '@/contexts/auth-context';

interface MessageFeedbackProps {
  messageId: string;
  sessionId: string;
}

export default function MessageFeedback({ messageId, sessionId }: MessageFeedbackProps) {
  const { getToken } = useAuth();
  const [feedback, setFeedback] = useState<'thumbs_up' | 'thumbs_down' | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = useCallback(
    async (type: 'thumbs_up' | 'thumbs_down') => {
      if (submitting || feedback === type) return;
      setSubmitting(true);
      try {
        const token = await getToken();
        const res = await fetch('/api/feedback/message', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            session_id: sessionId,
            message_id: messageId,
            feedback_type: type,
          }),
        });
        if (res.ok) {
          setFeedback(type);
        }
      } catch {
        // Silent fail — feedback is non-critical
      } finally {
        setSubmitting(false);
      }
    },
    [getToken, messageId, sessionId, feedback, submitting],
  );

  return (
    <div className="flex items-center gap-1 mt-1">
      <button
        onClick={() => submit('thumbs_up')}
        disabled={submitting}
        className={`p-1 rounded transition-colors ${
          feedback === 'thumbs_up'
            ? 'text-green-600 bg-green-50'
            : 'text-gray-300 hover:text-gray-500 hover:bg-gray-50'
        }`}
        title="Helpful"
      >
        <ThumbsUp className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={() => submit('thumbs_down')}
        disabled={submitting}
        className={`p-1 rounded transition-colors ${
          feedback === 'thumbs_down'
            ? 'text-red-600 bg-red-50'
            : 'text-gray-300 hover:text-gray-500 hover:bg-gray-50'
        }`}
        title="Not helpful"
      >
        <ThumbsDown className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
