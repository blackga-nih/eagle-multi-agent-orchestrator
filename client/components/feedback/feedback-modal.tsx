'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { usePathname } from 'next/navigation';
import html2canvas from 'html2canvas';
import { Check, Camera, X } from 'lucide-react';
import Modal from '@/components/ui/modal';
import { useAuth } from '@/contexts/auth-context';
import { useSession } from '@/contexts/session-context';
import { useFeedback } from '@/contexts/feedback-context';
import type { FeedbackType, FeedbackArea } from '@/types/schema';

const FEEDBACK_TYPES: { value: FeedbackType; label: string }[] = [
  { value: 'helpful', label: 'Helpful' },
  { value: 'inaccurate', label: 'Inaccurate' },
  { value: 'incomplete', label: 'Incomplete' },
  { value: 'too_verbose', label: 'Too verbose' },
];

const FEEDBACK_AREAS: { value: FeedbackArea; label: string }[] = [
  { value: 'network', label: 'Network' },
  { value: 'documents', label: 'Documents' },
  { value: 'knowledge_base', label: 'Knowledge Base' },
  { value: 'auth', label: 'Auth' },
  { value: 'streaming', label: 'Streaming' },
  { value: 'ui', label: 'UI/Display' },
  { value: 'performance', label: 'Performance' },
  { value: 'tools', label: 'Tools' },
];

export default function FeedbackModal() {
  const [isOpen, setIsOpen] = useState(false);
  const [feedbackType, setFeedbackType] = useState<FeedbackType | null>(null);
  const [feedbackArea, setFeedbackArea] = useState<FeedbackArea | null>(null);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [capturingScreenshot, setCapturingScreenshot] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const pathname = usePathname();
  const { user, getToken } = useAuth();
  const { currentSessionId } = useSession();
  const { getSnapshot } = useFeedback();

  const resetForm = useCallback(() => {
    setFeedbackType(null);
    setFeedbackArea(null);
    setComment('');
    setError(null);
    setSuccess(false);
    setScreenshot(null);
  }, []);

  const captureScreenshot = useCallback(async () => {
    setCapturingScreenshot(true);
    try {
      const canvas = await html2canvas(document.body, {
        scale: 0.5,
        logging: false,
        useCORS: true,
        windowWidth: document.documentElement.scrollWidth,
        windowHeight: document.documentElement.scrollHeight,
      });
      setScreenshot(canvas.toDataURL('image/png', 0.8));
    } catch {
      // Screenshot is best-effort — don't block feedback
    } finally {
      setCapturingScreenshot(false);
    }
  }, []);

  // Ctrl+J toggle
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'j') {
        e.preventDefault();
        setIsOpen((prev) => {
          if (prev) {
            resetForm();
          } else {
            // Capture screenshot before modal renders over the page
            captureScreenshot();
          }
          return !prev;
        });
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [resetForm, captureScreenshot]);

  // Auto-focus textarea when modal opens
  useEffect(() => {
    if (isOpen && !success) {
      // Short delay to let the modal animate in
      const t = setTimeout(() => textareaRef.current?.focus(), 50);
      return () => clearTimeout(t);
    }
  }, [isOpen, success]);

  const handleClose = useCallback(() => {
    setIsOpen(false);
    resetForm();
  }, [resetForm]);

  const handleSubmit = async () => {
    if (!comment.trim() && !feedbackType && !feedbackArea) return;
    setSubmitting(true);
    setError(null);

    try {
      let token: string | null = null;
      try {
        token = await getToken();
      } catch {
        // explicit error path
      }
      if (!token) {
        setError('Session expired. Please sign in again to submit feedback.');
        setSubmitting(false);
        return;
      }

      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      // Backend expects `feedback_text`; build from comment + type + area tags
      const feedbackText = [
        comment.trim(),
        feedbackType ? `[${feedbackType}]` : '',
        feedbackArea ? `[${feedbackArea}]` : '',
      ]
        .filter(Boolean)
        .join(' ');

      const { messages, lastMessageId } = getSnapshot();

      // Truncate snapshot to avoid oversized payloads that fail at the proxy layer
      const MAX_SNAPSHOT_MESSAGES = 20;
      const MAX_CONTENT_LENGTH = 2000;
      const trimmedMessages = messages.slice(-MAX_SNAPSHOT_MESSAGES).map((m) => ({
        ...m,
        content:
          m.content.length > MAX_CONTENT_LENGTH
            ? m.content.slice(0, MAX_CONTENT_LENGTH) + '… [truncated]'
            : m.content,
      }));

      const res = await fetch('/api/feedback', {
        method: 'POST',
        headers,
        signal: AbortSignal.timeout(10_000),
        body: JSON.stringify({
          feedback_text: feedbackText,
          feedback_type: feedbackType,
          feedback_area: feedbackArea,
          session_id: currentSessionId || undefined,
          page: pathname,
          last_message_id: lastMessageId || undefined,
          conversation_snapshot: trimmedMessages,
          screenshot: screenshot || undefined,
        }),
      });

      if (!res.ok) {
        if (res.status === 401) {
          throw new Error('auth');
        }
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.error || `Submit failed (${res.status})`);
      }

      setSuccess(true);
      setTimeout(() => {
        setIsOpen(false);
        resetForm();
      }, 1500);
    } catch (err) {
      let msg = 'Could not submit feedback. Please try again.';
      if (err instanceof Error) {
        if (err.message === 'auth') {
          msg = 'Session expired. Please sign in again.';
        } else if (err.name === 'TimeoutError') {
          msg = 'Request timed out. Please try again.';
        } else if (err.message !== 'Submit failed') {
          msg = err.message;
        }
      }
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (!user) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Send Feedback"
      size="md"
      footer={
        success ? null : (
          <div className="flex justify-end gap-3">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={(!comment.trim() && !feedbackType && !feedbackArea) || submitting}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? 'Submitting...' : 'Submit'}
            </button>
          </div>
        )
      }
    >
      {success ? (
        <div className="flex flex-col items-center py-8 gap-3">
          <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center">
            <Check className="w-6 h-6 text-emerald-600" />
          </div>
          <p className="text-lg font-semibold text-gray-900">Thanks!</p>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Comment */}
          <div>
            <textarea
              ref={textareaRef}
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              onKeyDown={(e) => {
                if (e.ctrlKey && e.key === 'Enter') {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder="Tell us more... (Ctrl+Enter to submit)"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
            />
          </div>

          {/* Type pills */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Type</label>
            <div className="flex flex-wrap gap-2">
              {FEEDBACK_TYPES.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFeedbackType(feedbackType === value ? null : value)}
                  className={`px-3 py-1.5 text-sm rounded-full border transition-colors ${
                    feedbackType === value
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Area pills */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Area</label>
            <div className="flex flex-wrap gap-2">
              {FEEDBACK_AREAS.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFeedbackArea(feedbackArea === value ? null : value)}
                  className={`px-3 py-1.5 text-sm rounded-full border transition-colors ${
                    feedbackArea === value
                      ? 'bg-amber-600 text-white border-amber-600'
                      : 'bg-white text-gray-700 border-gray-300 hover:border-amber-400'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Screenshot preview */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Screenshot</label>
            {capturingScreenshot ? (
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <Camera className="w-4 h-4 animate-pulse" />
                <span>Capturing...</span>
              </div>
            ) : screenshot ? (
              <div className="relative inline-block">
                <img
                  src={screenshot}
                  alt="Screenshot preview"
                  className="max-h-32 rounded border border-gray-200 shadow-sm"
                />
                <button
                  type="button"
                  onClick={() => setScreenshot(null)}
                  className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={captureScreenshot}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 border border-gray-300 rounded-lg hover:border-blue-400 hover:text-blue-600 transition-colors"
              >
                <Camera className="w-4 h-4" />
                Capture
              </button>
            )}
          </div>

          {/* Page badge */}
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="px-2 py-1 bg-gray-100 rounded font-mono">{pathname}</span>
            <span>auto-captured</span>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
      )}
    </Modal>
  );
}
