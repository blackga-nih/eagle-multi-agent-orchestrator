'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { Check } from 'lucide-react';
import Modal from '@/components/ui/modal';
import { useAuth } from '@/contexts/auth-context';
import { useSession } from '@/contexts/session-context';
import type { FeedbackType } from '@/types/schema';

const FEEDBACK_TYPES: { value: FeedbackType; label: string }[] = [
  { value: 'helpful', label: 'Helpful' },
  { value: 'inaccurate', label: 'Inaccurate' },
  { value: 'incomplete', label: 'Incomplete' },
  { value: 'too_verbose', label: 'Too verbose' },
];

export default function FeedbackModal() {
  const [isOpen, setIsOpen] = useState(false);
  const [feedbackType, setFeedbackType] = useState<FeedbackType | null>(null);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const pathname = usePathname();
  const { user, getToken } = useAuth();
  const { currentSessionId } = useSession();

  const resetForm = useCallback(() => {
    setFeedbackType(null);
    setComment('');
    setError(null);
    setSuccess(false);
  }, []);

  // Ctrl+J toggle
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'j') {
        e.preventDefault();
        setIsOpen((prev) => {
          if (prev) resetForm();
          return !prev;
        });
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [resetForm]);

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
    if (!comment.trim() && !feedbackType) return;
    setSubmitting(true);
    setError(null);

    try {
      const token = await getToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch('/api/feedback', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          rating: 0,
          page: pathname,
          feedback_type: feedbackType,
          comment: comment.trim() || undefined,
          session_id: currentSessionId || undefined,
        }),
      });

      if (!res.ok) throw new Error('Submit failed');

      setSuccess(true);
      setTimeout(() => {
        setIsOpen(false);
        resetForm();
      }, 1500);
    } catch {
      setError('Could not submit feedback. Please try again.');
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
              disabled={(!comment.trim() && !feedbackType) || submitting}
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
              placeholder="Tell us more..."
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

          {/* Page badge */}
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="px-2 py-1 bg-gray-100 rounded font-mono">{pathname}</span>
            <span>auto-captured</span>
          </div>

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}
        </div>
      )}
    </Modal>
  );
}
