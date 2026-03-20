/**
 * Message feedback component - thumbs up/down for individual messages.
 */

'use client';

import { useState } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';

interface MessageFeedbackProps {
  messageId: string;
  sessionId: string;
}

export default function MessageFeedback({ messageId, sessionId }: MessageFeedbackProps) {
  const [feedback, setFeedback] = useState<'thumbs_up' | 'thumbs_down' | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submitFeedback = async (type: 'thumbs_up' | 'thumbs_down') => {
    if (isSubmitting || feedback === type) return;

    setIsSubmitting(true);
    try {
      const response = await fetch('/api/feedback/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          message_id: messageId,
          feedback_type: type,
        }),
      });

      if (response.ok) {
        setFeedback(type);
      }
    } catch (error) {
      console.error('Failed to submit feedback:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      <button
        onClick={() => submitFeedback('thumbs_up')}
        disabled={isSubmitting}
        className={`p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${
          feedback === 'thumbs_up' ? 'text-green-600' : 'text-gray-400'
        }`}
        title="Helpful"
      >
        <ThumbsUp className="w-4 h-4" />
      </button>
      <button
        onClick={() => submitFeedback('thumbs_down')}
        disabled={isSubmitting}
        className={`p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${
          feedback === 'thumbs_down' ? 'text-red-600' : 'text-gray-400'
        }`}
        title="Not helpful"
      >
        <ThumbsDown className="w-4 h-4" />
      </button>
    </div>
  );
}
