import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { ChevronRight } from 'lucide-react';

const ToolsPage = ({ theme = 'dark', onNavigate }) => {
  const [summary, setSummary] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const isLight = theme === 'light';

  const fetchSummary = async () => {
    try {
      setLoading(true);
      setError('');
      const response = await axios.get('/api/tools/summary');
      setSummary(response.data?.rows || []);
    } catch (err) {
      console.error(err);
      setError('Failed to load tool summary.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchSummary(); }, []);

  useEffect(() => {
    const onRefresh = () => fetchSummary();
    window.addEventListener('cj:refresh', onRefresh);
    return () => window.removeEventListener('cj:refresh', onRefresh);
  }, []);

  return (
    <div className={`${isLight ? 'bg-white text-gray-900' : 'bg-[#0a0a0a] text-gray-300'} p-6 font-mono max-w-7xl mx-auto`}>
      <div className="mb-6">
        <h1 className={`text-xl font-bold ${isLight ? 'text-gray-900' : 'text-white'}`}>Tools</h1>
        <p className="text-[11px] mt-1 text-gray-500">All tools used by Rune across sessions.</p>
      </div>

      {loading && <p className="text-xs text-gray-500">Loading tools...</p>}
      {error && <p className="text-xs text-red-400">{error}</p>}

      {!loading && !error && summary.length > 0 && (
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
          {summary.map((s) => (
            <button
              key={s.tool_name}
              onClick={() => onNavigate(`/tools/detail/${encodeURIComponent(s.tool_name)}`)}
              className={`group text-left p-3 rounded transition block ${isLight ? 'bg-gray-50 border border-gray-200 hover:border-orange-400 hover:bg-gray-100' : 'bg-[#141414] border border-gray-900 hover:border-orange-800/60 hover:bg-[#1a1a1a]'}`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-semibold ${isLight ? 'text-gray-900' : 'text-white'}`}>{s.tool_name}</span>
                  {s.subagent_count > 0 && (
                    <span className="text-[10px] uppercase border rounded px-2 py-[1px] bg-purple-900/40 text-purple-300 border-purple-800">Subagent</span>
                  )}
                </div>
                <ChevronRight size={14} className={`shrink-0 transition ${isLight ? 'text-gray-400 group-hover:text-orange-500' : 'text-gray-700 group-hover:text-orange-400'}`} />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-lg font-bold text-orange-500">{s.invocation_count || 0}</span>
                <span className="text-[11px] text-gray-500">invocations</span>
                {s.error_count > 0 && (
                  <span className="text-[11px] text-red-400">{s.error_count} errors</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {!loading && !error && summary.length === 0 && (
        <p className="text-xs text-gray-600 mt-4">No tool invocations found.</p>
      )}
    </div>
  );
};

export default ToolsPage;
