'use client';

import { useState, useEffect, useCallback } from 'react';
import { CheckCircle2, XCircle, ChevronDown, ChevronUp, FileText, Clock, AlertCircle } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import { useAuth } from '@/contexts/auth-context';

// Use relative paths — proxied through Next.js API routes to FastAPI backend
const API_BASE = '';

interface DiffOp {
  op: string;
  path: string;
  value?: unknown;
}

interface KBReview {
  review_id: string;
  filename: string;
  s3_key: string;
  status: 'pending' | 'approved' | 'rejected';
  analysis_summary: string;
  proposed_diff: DiffOp[];
  created_at: string;
  reviewed_by?: string;
  reviewed_at?: string;
}

function ReviewCard({ review, onApprove, onReject }: {
  review: KBReview;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState<'approve' | 'reject' | null>(null);

  const handleApprove = async () => {
    setLoading('approve');
    await onApprove(review.review_id);
    setLoading(null);
  };

  const handleReject = async () => {
    setLoading('reject');
    await onReject(review.review_id);
    setLoading(null);
  };

  const formattedDate = new Date(review.created_at).toLocaleString();

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
      {/* Card Header */}
      <div className="flex items-start justify-between p-4">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className="mt-0.5 shrink-0">
            <FileText className="w-5 h-5 text-blue-600" />
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-gray-900 truncate">{review.filename}</p>
            <p className="text-sm text-gray-500 flex items-center gap-1 mt-0.5">
              <Clock className="w-3.5 h-3.5" />
              {formattedDate}
            </p>
            <p className="text-sm text-gray-700 mt-2 leading-relaxed">{review.analysis_summary}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 ml-4">
          <button
            onClick={handleApprove}
            disabled={loading !== null}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading === 'approve' ? (
              <span className="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
            ) : (
              <CheckCircle2 className="w-3.5 h-3.5" />
            )}
            Approve
          </button>
          <button
            onClick={handleReject}
            disabled={loading !== null}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white text-sm font-medium rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading === 'reject' ? (
              <span className="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
            ) : (
              <XCircle className="w-3.5 h-3.5" />
            )}
            Reject
          </button>
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 text-gray-400 hover:text-gray-600 rounded transition-colors"
            title={expanded ? 'Collapse diff' : 'Expand diff'}
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Proposed diff */}
      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50 p-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Proposed Diff ({review.proposed_diff.length} operation{review.proposed_diff.length !== 1 ? 's' : ''})
          </p>
          {review.proposed_diff.length === 0 ? (
            <p className="text-sm text-gray-500 italic">No matrix changes proposed — informational update only.</p>
          ) : (
            <div className="space-y-1.5">
              {review.proposed_diff.map((op, i) => (
                <div key={i} className="flex items-start gap-2 text-sm font-mono bg-white border border-gray-200 rounded px-3 py-2">
                  <span className={`shrink-0 font-semibold ${
                    op.op === 'add' ? 'text-green-600' :
                    op.op === 'remove' ? 'text-red-600' :
                    'text-yellow-600'
                  }`}>{op.op}</span>
                  <span className="text-gray-600 flex-1 break-all">{op.path}</span>
                  {op.value !== undefined && (
                    <span className="text-blue-700 max-w-xs break-all">
                      → {JSON.stringify(op.value)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Toast({ message, type, onClose }: { message: string; type: 'success' | 'error'; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-white text-sm font-medium transition-all ${
      type === 'success' ? 'bg-green-600' : 'bg-red-600'
    }`}>
      {type === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
      {message}
    </div>
  );
}

export default function KBReviewsPage() {
  const [reviews, setReviews] = useState<KBReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const { getToken } = useAuth();

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type });
  };

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = await getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [getToken]);

  const fetchReviews = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/api/admin/kb-reviews?status=pending`, {
        headers: await authHeaders(),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setReviews(data.reviews || []);
    } catch (e) {
      setError(`Failed to load KB reviews: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    fetchReviews();
  }, [fetchReviews]);

  const handleApprove = async (reviewId: string) => {
    try {
      const resp = await fetch(`${API_BASE}/api/admin/kb-review/${reviewId}/approve`, {
        method: 'POST',
        headers: await authHeaders(),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${resp.status}`);
      }
      setReviews(prev => prev.filter(r => r.review_id !== reviewId));
      showToast('Review approved — matrix.json updated.', 'success');
    } catch (e) {
      showToast(`Approve failed: ${e instanceof Error ? e.message : String(e)}`, 'error');
    }
  };

  const handleReject = async (reviewId: string) => {
    try {
      const resp = await fetch(`${API_BASE}/api/admin/kb-review/${reviewId}/reject`, {
        method: 'POST',
        headers: await authHeaders(),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${resp.status}`);
      }
      setReviews(prev => prev.filter(r => r.review_id !== reviewId));
      showToast('Review rejected.', 'success');
    } catch (e) {
      showToast(`Reject failed: ${e instanceof Error ? e.message : String(e)}`, 'error');
    }
  };

  return (
    <AuthGuard>
      <div className="min-h-screen bg-gray-50">
        <TopNav />
        <main className="max-w-4xl mx-auto px-4 py-8">
          <PageHeader
            title="Knowledge Base Reviews"
            description="Review documents uploaded to the knowledge base and approve or reject proposed matrix updates."
          />

          <div className="mt-6">
            {loading && (
              <div className="flex items-center justify-center py-16 text-gray-500">
                <span className="animate-spin w-5 h-5 border-2 border-gray-400 border-t-blue-600 rounded-full mr-3" />
                Loading pending reviews…
              </div>
            )}

            {error && !loading && (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-red-700 text-sm">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {error}
                <button onClick={fetchReviews} className="ml-auto text-red-600 underline hover:no-underline text-xs">
                  Retry
                </button>
              </div>
            )}

            {!loading && !error && reviews.length === 0 && (
              <div className="text-center py-16 text-gray-500">
                <CheckCircle2 className="w-10 h-10 mx-auto mb-3 text-green-400" />
                <p className="font-medium">No pending reviews</p>
                <p className="text-sm mt-1">
                  Upload a document to <code className="bg-gray-100 px-1 rounded">eagle-knowledge-base/pending/</code> in S3 to create a review.
                </p>
              </div>
            )}

            {!loading && !error && reviews.length > 0 && (
              <div className="space-y-4">
                <p className="text-sm text-gray-600">
                  {reviews.length} pending review{reviews.length !== 1 ? 's' : ''}
                </p>
                {reviews.map(review => (
                  <ReviewCard
                    key={review.review_id}
                    review={review}
                    onApprove={handleApprove}
                    onReject={handleReject}
                  />
                ))}
              </div>
            )}
          </div>
        </main>
      </div>

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </AuthGuard>
  );
}
