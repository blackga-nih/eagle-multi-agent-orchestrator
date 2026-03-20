'use client';

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Loader2, ThumbsUp, ThumbsDown, MessageSquare, TrendingUp } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import { useAuth } from '@/contexts/auth-context';

interface FeedbackItem {
  feedback_id: string;
  message_id: string;
  session_id: string;
  user_id: string;
  feedback_type: string;
  comment: string;
  created_at: string;
}

interface FeedbackSummary {
  total: number;
  thumbs_up: number;
  thumbs_down: number;
  thumbs_up_pct: number;
}

export default function FeedbackPage() {
  const { getToken } = useAuth();
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [summary, setSummary] = useState<FeedbackSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const token = await getToken();
      const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

      const [itemsRes, summaryRes] = await Promise.all([
        fetch('/api/feedback/messages', { headers }),
        fetch('/api/feedback/messages/summary', { headers }),
      ]);

      if (itemsRes.ok) {
        const data = await itemsRes.json();
        setItems(data.feedback || []);
      }
      if (summaryRes.ok) {
        setSummary(await summaryRes.json());
      }
    } catch {
      // Silent fail
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <AuthGuard>
      <div className="flex flex-col h-screen bg-gray-50">
        <TopNav />
        <main className="flex-1 overflow-y-auto">
          <div className="p-8">
            <PageHeader
              title="Message Feedback"
              description="Per-message thumbs up/down feedback from users"
              breadcrumbs={[
                { label: 'Admin', href: '/admin' },
                { label: 'Feedback' },
              ]}
              actions={
                <button
                  onClick={fetchData}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              }
            />

            {/* Summary cards */}
            {summary && (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                <div className="bg-white rounded-2xl border border-gray-200 p-5">
                  <div className="p-3 rounded-xl bg-[#003149] text-white w-fit mb-4">
                    <MessageSquare className="w-5 h-5" />
                  </div>
                  <p className="text-2xl font-bold text-gray-900">{summary.total}</p>
                  <p className="text-sm text-gray-500">Total Feedback</p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-5">
                  <div className="p-3 rounded-xl bg-green-500 text-white w-fit mb-4">
                    <ThumbsUp className="w-5 h-5" />
                  </div>
                  <p className="text-2xl font-bold text-gray-900">{summary.thumbs_up}</p>
                  <p className="text-sm text-gray-500">Thumbs Up</p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-5">
                  <div className="p-3 rounded-xl bg-red-500 text-white w-fit mb-4">
                    <ThumbsDown className="w-5 h-5" />
                  </div>
                  <p className="text-2xl font-bold text-gray-900">{summary.thumbs_down}</p>
                  <p className="text-sm text-gray-500">Thumbs Down</p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-5">
                  <div className="p-3 rounded-xl bg-blue-500 text-white w-fit mb-4">
                    <TrendingUp className="w-5 h-5" />
                  </div>
                  <p className="text-2xl font-bold text-gray-900">{summary.thumbs_up_pct}%</p>
                  <p className="text-sm text-gray-500">Approval Rate</p>
                </div>
              </div>
            )}

            {/* Recent feedback list */}
            <div className="bg-white rounded-2xl border border-gray-200">
              <div className="p-4 border-b border-gray-100">
                <h3 className="font-bold text-gray-900">Recent Feedback</h3>
              </div>
              {loading ? (
                <div className="p-12 text-center">
                  <Loader2 className="w-6 h-6 text-[#003149] animate-spin mx-auto mb-3" />
                  <p className="text-sm text-gray-500">Loading feedback...</p>
                </div>
              ) : items.length === 0 ? (
                <div className="p-12 text-center">
                  <MessageSquare className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                  <p className="text-sm text-gray-500">No message feedback yet</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-50 max-h-[60vh] overflow-y-auto">
                  {items.map((item) => (
                    <div key={item.feedback_id} className="p-4 flex items-start gap-3">
                      {item.feedback_type === 'thumbs_up' ? (
                        <div className="p-1.5 rounded-lg bg-green-50">
                          <ThumbsUp className="w-4 h-4 text-green-600" />
                        </div>
                      ) : (
                        <div className="p-1.5 rounded-lg bg-red-50">
                          <ThumbsDown className="w-4 h-4 text-red-600" />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium text-gray-900">{item.user_id}</span>
                          <span className="text-xs text-gray-400">{new Date(item.created_at).toLocaleString()}</span>
                        </div>
                        <p className="text-xs text-gray-500 truncate">
                          Session: {item.session_id} / Message: {item.message_id}
                        </p>
                        {item.comment && (
                          <p className="text-sm text-gray-600 mt-1">{item.comment}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
