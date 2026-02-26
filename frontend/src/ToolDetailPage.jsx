import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';

const ToolDetailPage = ({ theme = 'dark', toolName, onNavigate }) => {
  const [invocations, setInvocations] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterText, setFilterText] = useState('');

  const isLight = theme === 'light';
  const inputBg = isLight ? 'bg-white border border-gray-200 text-gray-900' : 'bg-[#1a1a1a] border border-gray-800 text-gray-200';

  const formatTs = (value) => {
    if (!value) return '';
    try {
      const dt = new Date(value);
      if (Number.isNaN(dt.getTime())) return String(value).slice(0, 16);
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const dtDay = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
      const diffDays = Math.round((today.getTime() - dtDay.getTime()) / 86400000);
      if (diffDays === 0) return `Today ${dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      if (diffDays === 1) return `Yesterday ${dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      if (diffDays < 7) return dt.toLocaleDateString([], { weekday: 'short' }) + ' ' + dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      return dt.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ', ' + dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return String(value).slice(0, 16);
    }
  };

  const parseTrigger = (text) => {
    if (!text) return null;
    const trimmed = String(text).trim();
    if (trimmed.startsWith('{')) {
      try {
        const obj = JSON.parse(trimmed);
        if (obj.name) return { name: obj.name, description: (obj.description || '').slice(0, 200) };
      } catch { /* ignore */ }
    }
    let cleaned = trimmed.replace(/\s*\n\s*/g, ' ');
    cleaned = cleaned.replace(/^System:\s*/i, '');
    cleaned = cleaned.replace(/^(\[[^\]]*\]\s*)+/, '');
    if (cleaned.length > 150) cleaned = cleaned.slice(0, 150) + '...';
    return cleaned ? { raw: cleaned } : null;
  };

  useEffect(() => {
    if (!toolName) return;
    let cancelled = false;
    const fetchDetail = async () => {
      try {
        setLoading(true);
        setError('');
        const response = await axios.get(`/api/tools/detail/${encodeURIComponent(toolName)}?limit=200`);
        if (!cancelled) {
          setInvocations(response.data?.rows || []);
          setSummary(response.data?.summary || null);
        }
      } catch (err) {
        console.error(err);
        if (!cancelled) setError('Failed to load tool detail.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchDetail();
    return () => { cancelled = true; };
  }, [toolName]);

  const filteredInvocations = useMemo(() => {
    if (!filterText.trim()) return invocations;
    const needle = filterText.toLowerCase();
    return invocations.filter((inv) => {
      const haystack = [
        inv.reasoning || '',
        inv.trigger_text || '',
        inv.tool_input || '',
        inv.tool_result || '',
        inv.session_id || '',
      ].join(' ').toLowerCase();
      return haystack.includes(needle);
    });
  }, [invocations, filterText]);

  return (
    <div className={`${isLight ? 'bg-white text-gray-900' : 'bg-[#0a0a0a] text-gray-300'} p-6 max-w-7xl mx-auto`}>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h1 className={`text-xl font-bold ${isLight ? 'text-gray-900' : 'text-white'}`}>{toolName}</h1>
          <p className="text-[11px] mt-1 text-gray-500">
            {summary && <>{summary.invocation_count || 0} invocations &middot; {summary.error_count || 0} errors</>}
            {summary?.subagent_count > 0 && (
              <> &middot; <span className="text-[10px] uppercase border rounded px-2 py-[1px] bg-purple-900/40 text-purple-300 border-purple-800">Subagent</span></>
            )}
            {' '}&middot;{' '}
            <button
              onClick={() => onNavigate('/tools')}
              className="text-orange-400 hover:text-orange-300"
            >
              Back to all tools
            </button>
          </p>
        </div>
        <div className="flex items-center gap-3">
          {filterText.trim() && (
            <span className="text-[11px] text-gray-600">{filteredInvocations.length} of {invocations.length}</span>
          )}
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Type to filter by keyword..."
            className={`${inputBg} rounded px-3 py-1.5 text-xs placeholder:text-gray-500 focus:outline-none w-56 ${isLight ? 'focus:border-orange-400' : 'focus:border-orange-800'}`}
          />
        </div>
      </div>

      {loading && <p className="text-xs text-gray-500">Loading invocations...</p>}
      {error && <p className="text-xs text-red-400">{error}</p>}

      {!loading && !error && filteredInvocations.length > 0 && (
        <div className="space-y-3">
          {filteredInvocations.map((inv, idx) => {
            const trigger = parseTrigger(inv.trigger_text);
            const reasoningFlat = inv.reasoning ? inv.reasoning.replace(/\n/g, ' ') : '';

            return (
              <div
                key={inv.id || idx}
                className={`rounded overflow-hidden ${inv.is_error ? 'border-l-2 border-l-red-500' : ''} ${isLight ? 'bg-gray-50 border border-gray-200' : 'bg-[#141414] border border-gray-900'}`}
              >
                {/* Timestamp + session */}
                <div className={`px-3 py-2 border-b flex items-center gap-3 flex-wrap ${isLight ? 'border-gray-200' : 'border-gray-900'}`}>
                  <span className="text-[11px] text-gray-500">{formatTs(inv.invocation_ts)}</span>
                  <span className="text-gray-700">&middot;</span>
                  <button
                    onClick={() => onNavigate(`/sessions/conversation/${inv.session_id}`)}
                    className="text-[11px] text-orange-400 hover:text-orange-300"
                  >
                    {(inv.session_id || '').slice(0, 8)}
                  </button>
                </div>

                {/* Reasoning */}
                {reasoningFlat && (
                  <div className={`px-3 py-2 border-b text-[12px] ${isLight ? 'bg-white border-gray-200' : 'bg-[#111111] border-gray-900'}`}>
                    <ReasoningBlock text={reasoningFlat} isLight={isLight} />
                  </div>
                )}

                {/* Trigger */}
                {trigger && (
                  <div className={`px-3 py-2 border-b text-[11px] ${isLight ? 'bg-white border-gray-200' : 'bg-[#111111] border-gray-900'}`}>
                    <span className="text-cyan-400 font-semibold">Triggered by: </span>
                    {trigger.name ? (
                      <span className={isLight ? 'text-gray-900 font-medium' : 'text-white font-medium'}>{trigger.name}</span>
                    ) : (
                      <span className="text-gray-400">{trigger.raw}</span>
                    )}
                  </div>
                )}

                {/* Input / Result */}
                <div className="p-3 space-y-1">
                  {inv.tool_input && (
                    <details>
                      <summary className={`text-[11px] cursor-pointer ${isLight ? 'text-gray-500 hover:text-gray-700' : 'text-gray-400 hover:text-gray-200'}`}>Input</summary>
                      <pre className={`text-[11px] mt-1 rounded p-2 max-h-48 overflow-y-auto ${isLight ? 'bg-gray-100 border border-gray-200 text-gray-800' : 'bg-[#0f0f0f] border border-gray-900 text-gray-300'}`}>
                        {inv.tool_input.slice(0, 1000)}
                      </pre>
                    </details>
                  )}
                  {inv.tool_result && (
                    <details>
                      <summary className={`text-[11px] cursor-pointer ${inv.is_error ? 'text-red-400' : (isLight ? 'text-gray-500 hover:text-gray-700' : 'text-gray-400 hover:text-gray-200')}`}>
                        Result{inv.is_error ? ' (error)' : ''}
                      </summary>
                      <pre className={`text-[11px] mt-1 rounded p-2 max-h-48 overflow-y-auto ${isLight ? 'bg-gray-100 border border-gray-200 text-gray-800' : 'bg-[#0f0f0f] border border-gray-900 text-gray-300'}`}>
                        {inv.tool_result.slice(0, 1000)}
                      </pre>
                    </details>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!loading && !error && filteredInvocations.length === 0 && filterText.trim() && (
        <p className="text-xs text-gray-600 mt-4">No invocations match your filter.</p>
      )}

      {!loading && !error && invocations.length === 0 && (
        <p className="text-xs text-gray-600 mt-4">No invocations found for <strong className={isLight ? 'text-gray-900' : 'text-white'}>{toolName}</strong>.</p>
      )}
    </div>
  );
};

const ReasoningBlock = ({ text, isLight }) => {
  const [showFull, setShowFull] = useState(false);
  const isLong = text.length > 200;

  return (
    <>
      <span className="text-amber-400 font-semibold">Reasoning: </span>
      {isLong && !showFull ? (
        <span className={isLight ? 'text-gray-800' : 'text-gray-300'}>
          {text.slice(0, 200)}…{' '}
          <button onClick={() => setShowFull(true)} className="text-orange-400 hover:text-orange-300 ml-1 underline underline-offset-2">See more</button>
        </span>
      ) : isLong && showFull ? (
        <span className={isLight ? 'text-gray-800' : 'text-gray-300'}>
          {text}{' '}
          <button onClick={() => setShowFull(false)} className="text-orange-400 hover:text-orange-300 ml-1 underline underline-offset-2">See less</button>
        </span>
      ) : (
        <span className={isLight ? 'text-gray-800' : 'text-gray-300'}>{text}</span>
      )}
    </>
  );
};

export default ToolDetailPage;
