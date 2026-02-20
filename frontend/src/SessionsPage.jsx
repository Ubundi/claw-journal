import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';

const SessionsPage = ({ theme = 'dark', onNavigate }) => {
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState('');
  const [daily, setDaily] = useState([]);
  const [toolNames, setToolNames] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFilter, setDateFilter] = useState('');
  const [toolFilter, setToolFilter] = useState('');

  const isLight = theme === 'light';

  const cleanTitle = (text) => {
    if (!text) return '';
    let t = String(text).trim().replace(/\s*\n\s*/g, ' ');
    t = t.replace(/^System:\s*/i, '');
    t = t.replace(/^(\[[^\]]*\]\s*)+/, '');
    t = t.replace(/^Read HEARTBEAT\.md if it exists \(workspace context\)\.\s*(Follow it strictly\.\s*Do not infer or repeat old tasks from prior chat\s*)?/i, '');
    t = t.replace(/\s*HEARTBEAT_OK\b/, '');
    t = t.replace(/^🦞\s*OpenClaw\s+[\d.]+\S*\s*\([\w]+\)\s*🕒.*$/, '');
    t = t.trim();
    if (!t) return '';
    if (t.length > 80) t = t.slice(0, 80) + '...';
    return t;
  };

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

  const totals = useMemo(() => {
    let input = 0, output = 0, cost = 0;
    for (const d of daily) {
      input += d.input_tokens || 0;
      output += d.output_tokens || 0;
      cost += d.cost_usd || 0;
    }
    return { input, output, cost };
  }, [daily]);

  const fetchData = async () => {
    try {
      setSessionsLoading(true);
      setSessionsError('');

      const params = new URLSearchParams({ limit: '100' });
      if (toolFilter) params.set('tool', toolFilter);
      if (dateFilter) params.set('date', dateFilter);

      const endpoint = toolFilter
        ? `/api/sessions/transcripts?${params.toString()}`
        : `/api/sessions/transcripts?${params.toString()}`;

      const [sessionsRes, dailyRes, toolsRes] = await Promise.all([
        axios.get(endpoint),
        axios.get('/api/usage/daily?days=14'),
        axios.get('/api/tools/names'),
      ]);

      setSessions(sessionsRes.data?.rows || []);
      setDaily(dailyRes.data?.rows || []);
      setToolNames(toolsRes.data?.rows || []);
    } catch (err) {
      console.error(err);
      setSessionsError('Failed to load sessions.');
    } finally {
      setSessionsLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [dateFilter, toolFilter]);

  useEffect(() => {
    const onRefresh = () => fetchData();
    window.addEventListener('cj:refresh', onRefresh);
    return () => window.removeEventListener('cj:refresh', onRefresh);
  }, [dateFilter, toolFilter]);

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      onNavigate(`/sessions/search?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  const handleSessionClick = (sessionId) => {
    onNavigate(`/sessions/conversation/${sessionId}`);
  };

  const cardBg = isLight ? 'bg-gray-100 border border-gray-300' : 'bg-[#141414] border border-gray-900';
  const panelBg = isLight ? 'bg-gray-50 border border-gray-200' : 'bg-[#141414] border border-gray-900';
  const inputBg = isLight ? 'bg-white border border-gray-200 text-gray-900' : 'bg-[#1a1a1a] border border-gray-800 text-gray-200';

  return (
    <div className={`${isLight ? 'bg-white text-gray-900' : 'bg-[#0a0a0a] text-gray-300'} p-6 max-w-7xl mx-auto`}>
      <div className="relative overflow-hidden">
        <div className="relative z-10">
          {/* Header */}
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <h1 className={`text-xl font-bold ${isLight ? 'text-gray-900' : 'text-white'}`}>Sessions</h1>
            <form onSubmit={handleSearch} className="flex gap-2">
              <input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search conversations..."
                className={`${inputBg} rounded px-3 py-1.5 text-xs placeholder:text-gray-500 focus:outline-none w-64 ${isLight ? 'focus:border-orange-400' : 'focus:border-orange-800'}`}
              />
              <button
                type="submit"
                className={`px-3 py-1.5 rounded text-xs transition ${isLight ? 'bg-orange-100 border border-orange-300 text-orange-700 hover:bg-orange-200' : 'bg-orange-900/40 border border-orange-800 text-orange-300 hover:bg-orange-900/60'}`}
              >
                Search
              </button>
            </form>
          </div>

          {/* Stats cards */}
          {daily.length > 0 && (
            <div className="grid gap-4 mb-8" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
              <div className={`${cardBg} p-3 rounded shadow-sm`}>
                <p className="text-[10px] uppercase text-gray-500 mb-1">14-Day Input Tokens</p>
                <p className="text-lg font-bold text-orange-500">{totals.input.toLocaleString()}</p>
              </div>
              <div className={`${cardBg} p-3 rounded shadow-sm`}>
                <p className="text-[10px] uppercase text-gray-500 mb-1">14-Day Output Tokens</p>
                <p className="text-lg font-bold text-orange-500">{totals.output.toLocaleString()}</p>
              </div>
              <div className={`${cardBg} p-3 rounded shadow-sm`}>
                <p className="text-[10px] uppercase text-gray-500 mb-1">14-Day Cost</p>
                <p className="text-lg font-bold text-orange-500">${totals.cost.toFixed(2)}</p>
              </div>
              <div className={`${cardBg} p-3 rounded shadow-sm`}>
                <p className="text-[10px] uppercase text-gray-500 mb-1">Sessions</p>
                <p className="text-lg font-bold text-orange-500">{sessions.length}</p>
              </div>
            </div>
          )}

          {/* Sessions list */}
          <div className={`${panelBg} rounded overflow-hidden mb-6`}>
            <div className={`p-4 border-b flex flex-wrap items-center justify-between gap-3 ${isLight ? 'border-gray-200' : 'border-gray-900'}`}>
              <h3 className="text-xs uppercase text-gray-500">Recent Sessions</h3>
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  value={dateFilter}
                  onChange={(e) => setDateFilter(e.target.value)}
                  className={`${inputBg} rounded px-3 py-1 text-xs`}
                />
                <select
                  value={toolFilter}
                  onChange={(e) => setToolFilter(e.target.value)}
                  className={`${inputBg} rounded px-3 py-1 text-xs min-w-[160px]`}
                >
                  <option value="">All tools</option>
                  {toolNames.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
            </div>

            {(toolFilter || dateFilter) && (
              <div className={`px-4 py-2 text-[11px] text-gray-500 border-b ${isLight ? 'border-gray-200' : 'border-gray-900'}`}>
                Showing sessions
                {dateFilter && <> from <span className="text-orange-400 font-semibold">{dateFilter}</span></>}
                {toolFilter && <> using <span className="text-orange-400 font-semibold">{toolFilter}</span></>}
                {' '}&middot;{' '}
                <button onClick={() => { setDateFilter(''); setToolFilter(''); }} className="text-orange-400 hover:text-orange-300">
                  Clear filters
                </button>
              </div>
            )}

            {sessionsLoading && <p className="text-xs text-gray-500 p-4">Loading sessions...</p>}
            {sessionsError && <p className="text-xs text-red-400 p-4">{sessionsError}</p>}

            {!sessionsLoading && !sessionsError && sessions.length > 0 && (
              <div className={`divide-y ${isLight ? 'divide-gray-200' : 'divide-gray-900'}`}>
                {sessions.map((s) => {
                  const title = cleanTitle(s.display_title) || cleanTitle(s.assistant_title) || (s.display_title ? 'Rune heartbeat check' : (s.session_id || '').slice(0, 8));
                  const isTooToo = (s.source_path || '').includes('/agents/tootoo/');
                  const agentName = isTooToo ? null : ((s.source_path || '').match(/\/agents\/([^/]+)\//) || [])[1];
                  return (
                    <button
                      key={s.session_id}
                      onClick={() => handleSessionClick(s.session_id)}
                      className={`block w-full text-left px-4 py-3 transition ${isTooToo ? (isLight ? 'hover:bg-amber-50 border-l-2 border-l-amber-400' : 'hover:bg-amber-950/20 border-l-2 border-l-amber-600/50') : (isLight ? 'hover:bg-gray-100' : 'hover:bg-[#1a1a1a]')}`}
                    >
                      <div className="flex items-center gap-3 mb-1 min-w-0">
                        <span className={`text-xs truncate min-w-0 flex-1 ${isLight ? 'text-gray-900' : 'text-white'}`}>{title}</span>
                        {isTooToo && (
                          <span className={`text-[10px] uppercase px-2 py-[1px] rounded border shrink-0 ${isLight ? 'bg-amber-100 border-amber-300 text-amber-700' : 'bg-amber-900/30 border-amber-800/50 text-amber-300'}`}>
                            TooToo
                          </span>
                        )}
                        {!isTooToo && agentName && agentName !== 'main' && (
                          <span className={`text-[10px] uppercase px-2 py-[1px] rounded border shrink-0 ${isLight ? 'bg-purple-100 border-purple-300 text-purple-700' : 'bg-purple-900/30 border-purple-800/50 text-purple-300'}`}>
                            {agentName}
                          </span>
                        )}
                        <span className="text-[11px] text-gray-600 shrink-0">{formatTs(s.last_message_ts)}</span>
                      </div>
                      <div className="flex items-center gap-3 text-[11px]">
                        <span className="text-gray-500">{(s.session_id || '').slice(0, 8)}</span>
                        <span className="text-orange-400">{s.model || 'unknown'}</span>
                        <span className="text-gray-600 ml-auto">{s.message_count || 0} msgs &middot; {s.thinking_count || 0} thinking &middot; {s.tool_use_count || 0} tools</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {!sessionsLoading && !sessionsError && sessions.length === 0 && (
              <p className="text-xs text-gray-600 p-4">No transcript data yet. Waiting for session JSONL files...</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SessionsPage;
