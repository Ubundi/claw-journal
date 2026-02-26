import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { TooTooFeedbackCard, ScoreRing, parseTooTooFeedback } from './TooTooComponents';

const TooTooPage = ({ theme = 'dark', onNavigate }) => {
  const [rawReviews, setRawReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const isLight = theme === 'light';

  useEffect(() => {
    let cancelled = false;
    const fetchReviews = async () => {
      try {
        setLoading(true);
        setError('');
        const res = await axios.get('/api/tootoo/reviews');
        if (!cancelled) setRawReviews(res.data?.rows || []);
      } catch (err) {
        console.error(err);
        if (!cancelled) setError('Failed to load TooToo reviews.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchReviews();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const onRefresh = () => {
      axios.get('/api/tootoo/reviews').then(res => setRawReviews(res.data?.rows || [])).catch(() => {});
    };
    window.addEventListener('cj:refresh', onRefresh);
    return () => window.removeEventListener('cj:refresh', onRefresh);
  }, []);

  // Parse alignment data from each review's content_json
  const reviews = useMemo(() => {
    const parsed = [];
    for (const row of rawReviews) {
      const cj = row.content_json;
      if (!cj) continue;
      let blocks = [];
      try {
        const p = JSON.parse(cj);
        if (Array.isArray(p)) blocks = p;
        else if (p?.message?.content) blocks = p.message.content;
      } catch { continue; }

      for (const block of blocks) {
        if (block.type === 'text') {
          const data = parseTooTooFeedback(block.text);
          if (data) {
            parsed.push({
              ...data,
              session_id: row.session_id,
              message_ts: row.message_ts,
              model: row.model,
            });
            break;
          }
        }
      }
    }
    return parsed;
  }, [rawReviews]);

  // Summary stats
  const stats = useMemo(() => {
    if (reviews.length === 0) return null;
    const scores = reviews.map(r => r.alignment_score).filter(s => typeof s === 'number' && !Number.isNaN(s));
    if (scores.length === 0) return null;
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
    const high = Math.max(...scores);
    const low = Math.min(...scores);
    const patterns = {};
    for (const r of reviews) {
      const p = r.pattern_tag || 'none';
      patterns[p] = (patterns[p] || 0) + 1;
    }
    return { avg, high, low, count: reviews.length, patterns };
  }, [reviews]);

  const formatTs = (value) => {
    if (!value) return '';
    try {
      const dt = new Date(value);
      if (Number.isNaN(dt.getTime())) return String(value).slice(0, 16);
      const now = new Date();
      const diffDays = Math.floor((now.getTime() - dt.getTime()) / 86400000);
      if (diffDays === 0) return `Today ${dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      if (diffDays === 1) return `Yesterday ${dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      if (diffDays < 7) return dt.toLocaleDateString([], { weekday: 'short' }) + ' ' + dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      return dt.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ', ' + dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return String(value).slice(0, 16);
    }
  };

  const cardBg = isLight ? 'bg-gray-100 border border-gray-300' : 'bg-[#141414] border border-gray-900';

  return (
    <div className={`${isLight ? 'bg-white text-gray-900' : 'bg-[#0a0a0a] text-gray-300'} p-6 max-w-7xl mx-auto`}>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <div className={`h-9 w-9 rounded-md flex items-center justify-center ${isLight ? 'bg-amber-100 border border-amber-300' : 'bg-amber-900/30 border border-amber-800/40'}`}>
            <img src="/tootoo-icon.png" alt="TooToo" className="h-6 w-6 rounded-sm" />
          </div>
          <div>
            <h1 className={`text-xl font-bold ${isLight ? 'text-gray-900' : 'text-white'}`}>TooToo</h1>
            <p className="text-[11px] text-gray-500">Codex alignment reviews for Rune's sub-agents</p>
          </div>
        </div>
      </div>

      {/* Summary stats */}
      {!loading && stats && (
        <div className="grid gap-4 mb-8" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
          <div className={`${cardBg} p-4 rounded shadow-sm flex items-center gap-4`}>
            <ScoreRing score={stats.avg} size={56} />
            <div>
              <p className="text-[10px] uppercase text-gray-500 mb-0.5">Avg Score</p>
              <p className={`text-sm font-bold ${isLight ? 'text-gray-900' : 'text-white'}`}>{(stats.avg * 100).toFixed(0)} / 100</p>
            </div>
          </div>
          <div className={`${cardBg} p-4 rounded shadow-sm`}>
            <p className="text-[10px] uppercase text-gray-500 mb-1">Total Reviews</p>
            <p className="text-lg font-bold text-amber-500">{stats.count}</p>
          </div>
          <div className={`${cardBg} p-4 rounded shadow-sm`}>
            <p className="text-[10px] uppercase text-gray-500 mb-1">Highest</p>
            <p className="text-lg font-bold text-emerald-400">{(stats.high * 100).toFixed(0)}</p>
          </div>
          <div className={`${cardBg} p-4 rounded shadow-sm`}>
            <p className="text-[10px] uppercase text-gray-500 mb-1">Lowest</p>
            <p className="text-lg font-bold text-orange-400">{(stats.low * 100).toFixed(0)}</p>
          </div>
        </div>
      )}

      {/* Loading / Error */}
      {loading && <p className="text-xs text-gray-500">Loading alignment reviews...</p>}
      {error && <p className="text-xs text-red-400">{error}</p>}

      {/* Review cards */}
      {!loading && !error && reviews.length > 0 && (
        <div className="space-y-4">
          {reviews.map((review, i) => (
            <div key={review.session_id || i}>
              {review.message_ts && (
                <p className={`text-[10px] mb-1.5 ${isLight ? 'text-gray-500' : 'text-gray-600'}`}>
                  {formatTs(review.message_ts)}
                  {review.model && <span> &middot; {review.model}</span>}
                </p>
              )}
              <TooTooFeedbackCard
                data={review}
                isLight={isLight}
                sessionId={review.session_id}
                onNavigate={onNavigate}
              />
            </div>
          ))}
        </div>
      )}

      {!loading && !error && reviews.length === 0 && (
        <div className={`text-center py-12 rounded ${isLight ? 'bg-gray-50' : 'bg-[#111]'}`}>
          <img src="/tootoo-icon.png" alt="TooToo" className="h-12 w-12 rounded-md mb-3 mx-auto" />
          <p className={`text-sm ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>No TooToo alignment reviews yet.</p>
          <p className="text-[11px] text-gray-600 mt-1">Reviews will appear here once TooToo evaluates agent actions.</p>
        </div>
      )}
    </div>
  );
};

export default TooTooPage;
