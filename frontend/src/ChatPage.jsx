import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Activity, Bot, Brain, Clock3, HelpCircle, MessageCircle, MessageSquare, User, Wrench } from 'lucide-react';

const ChatPage = () => {
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState('');
  const [selectedSessionId, setSelectedSessionId] = useState('');

  const [messages, setMessages] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesError, setMessagesError] = useState('');
  const [nextBeforeId, setNextBeforeId] = useState(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [typeFilter, setTypeFilter] = useState('all');
  const [providerFilter, setProviderFilter] = useState('all');
  const [modelFilter, setModelFilter] = useState('all');
  const [searchText, setSearchText] = useState('');
  const [searchSessions, setSearchSessions] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');

  const sessionTypeClass = (sessionType) => {
    const key = String(sessionType || '').toLowerCase();
    if (key === 'heartbeat') return 'bg-blue-900/40 text-blue-300 border-blue-800';
    if (key === 'whatsapp') return 'bg-emerald-900/40 text-emerald-300 border-emerald-800';
    if (key === 'cron') return 'bg-purple-900/40 text-purple-300 border-purple-800';
    if (key === 'conversation') return 'bg-orange-900/40 text-orange-300 border-orange-800';
    return 'bg-gray-800 text-gray-300 border-gray-700';
  };

  const sessionTypeIcon = (sessionType) => {
    const key = String(sessionType || '').toLowerCase();
    if (key === 'heartbeat') return Activity;
    if (key === 'whatsapp') return MessageCircle;
    if (key === 'cron') return Clock3;
    if (key === 'conversation') return MessageSquare;
    return HelpCircle;
  };

  const roleClass = (role) => {
    const key = String(role || '').toLowerCase();
    if (key === 'user') return 'text-cyan-300';
    if (key === 'assistant') return 'text-orange-300';
    if (key === 'tool' || key === 'toolresult') return 'text-emerald-300';
    if (key === 'system') return 'text-purple-300';
    return 'text-gray-300';
  };

  const roleIcon = (role) => {
    const key = String(role || '').toLowerCase();
    if (key === 'user') return User;
    if (key === 'assistant') return Bot;
    if (key === 'tool' || key === 'toolresult') return Wrench;
    return HelpCircle;
  };

  const safeParseJson = (rawJson) => {
    if (!rawJson || typeof rawJson !== 'string') return null;
    try {
      return JSON.parse(rawJson);
    } catch {
      return null;
    }
  };

  const prettyJson = (rawJson) => {
    const parsed = safeParseJson(rawJson);
    if (!parsed) return rawJson || '-';
    return JSON.stringify(parsed, null, 2);
  };

  const renderMessageBlocks = (message) => {
    const parsed = safeParseJson(message.raw_json);
    const content = parsed?.message?.content;
    if (!Array.isArray(content) || content.length === 0) {
      return (
        <pre className="text-[12px] text-gray-200 whitespace-pre-wrap break-words">
          {message.content_text || '(No text content captured)'}
        </pre>
      );
    }

    return (
      <div className="space-y-2">
        {content.map((item, index) => {
          if (!item || typeof item !== 'object') {
            return (
              <pre key={index} className="text-[12px] text-gray-200 whitespace-pre-wrap break-words">
                {String(item)}
              </pre>
            );
          }

          const itemType = String(item.type || '').toLowerCase();
          if (itemType === 'text') {
            return (
              <pre key={index} className="text-[12px] text-gray-200 whitespace-pre-wrap break-words">
                {item.text || ''}
              </pre>
            );
          }

          if (itemType === 'thinking') {
            return (
              <div key={index} className="bg-[#191919] border border-gray-800 rounded p-2">
                <p className="text-[11px] text-blue-300 mb-1 flex items-center gap-1.5">
                  <Brain size={12} />
                  thinking
                </p>
                <pre className="text-[12px] text-gray-200 whitespace-pre-wrap break-words">{item.thinking || ''}</pre>
              </div>
            );
          }

          if (itemType === 'toolcall') {
            return (
              <div key={index} className="bg-[#191919] border border-gray-800 rounded p-2">
                <p className="text-[11px] text-emerald-300 mb-1 flex items-center gap-1.5">
                  <Wrench size={12} />
                  toolCall · {item.name || 'unknown'}
                </p>
                <pre className="text-[12px] text-gray-200 whitespace-pre-wrap break-words">{JSON.stringify(item.arguments || {}, null, 2)}</pre>
              </div>
            );
          }

          return (
            <div key={index} className="bg-[#191919] border border-gray-800 rounded p-2">
              <p className="text-[11px] text-gray-400 mb-1">{item.type || 'content'}</p>
              <pre className="text-[12px] text-gray-200 whitespace-pre-wrap break-words">{JSON.stringify(item, null, 2)}</pre>
            </div>
          );
        })}
      </div>
    );
  };

  const currentSession = useMemo(
    () => sessions.find((row) => row.session_id === selectedSessionId) || null,
    [sessions, selectedSessionId],
  );

  const typeOptions = useMemo(
    () => ['all', ...new Set(sessions.map((row) => String(row.session_type || 'general').toLowerCase()))],
    [sessions],
  );

  const providerOptions = useMemo(
    () => ['all', ...new Set(sessions.map((row) => String(row.provider || 'unknown').toLowerCase()))],
    [sessions],
  );

  const modelOptions = useMemo(
    () => ['all', ...new Set(sessions.map((row) => String(row.model || 'unknown').toLowerCase()))],
    [sessions],
  );

  const filteredSessions = useMemo(() => {
    const searchSessionIds = new Set(searchSessions.map((row) => row.session_id));

    return sessions.filter((session) => {
      const typeValue = String(session.session_type || 'general').toLowerCase();
      const providerValue = String(session.provider || 'unknown').toLowerCase();
      const modelValue = String(session.model || 'unknown').toLowerCase();

      if (typeFilter !== 'all' && typeValue !== typeFilter) {
        return false;
      }
      if (providerFilter !== 'all' && providerValue !== providerFilter) {
        return false;
      }
      if (modelFilter !== 'all' && modelValue !== modelFilter) {
        return false;
      }

      if (!searchText.trim()) {
        return true;
      }
      if (searchSessionIds.size > 0) {
        return searchSessionIds.has(session.session_id);
      }

      const needle = searchText.toLowerCase();
      const metadata = [String(session.provider || ''), String(session.model || ''), String(session.session_type || '')]
        .join(' ')
        .toLowerCase();
      return metadata.includes(needle);
    });
  }, [sessions, typeFilter, providerFilter, modelFilter, searchText, searchSessions]);

  const filteredMessages = useMemo(() => {
    if (!searchText.trim()) {
      return messages;
    }
    const needle = searchText.toLowerCase();
    return messages.filter((message) => {
      const text = String(message.content_text || '').toLowerCase();
      const raw = String(message.raw_json || '').toLowerCase();
      return text.includes(needle) || raw.includes(needle);
    });
  }, [messages, searchText]);

  useEffect(() => {
    const trimmed = searchText.trim();
    if (trimmed.length < 2) {
      setSearchSessions([]);
      setSearchError('');
      setSearchLoading(false);
      return;
    }

    let cancelled = false;
    const timeout = setTimeout(async () => {
      try {
        setSearchLoading(true);
        setSearchError('');
        const response = await axios.get(`/api/chat/search?query=${encodeURIComponent(trimmed)}&limit=500`);
        if (cancelled) return;
        const rows = response.data?.sessions || [];
        setSearchSessions(rows);
      } catch (error) {
        if (cancelled) return;
        console.error(error);
        setSearchError('Search failed.');
        setSearchSessions([]);
      } finally {
        if (!cancelled) {
          setSearchLoading(false);
        }
      }
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(timeout);
    };
  }, [searchText]);

  const formatIso = (value) => {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  };

  const updateUrlSession = (sessionId) => {
    const url = new URL(window.location.href);
    if (sessionId) {
      url.searchParams.set('session', sessionId);
    } else {
      url.searchParams.delete('session');
    }
    window.history.replaceState({}, '', `${url.pathname}?${url.searchParams.toString()}`.replace(/\?$/, ''));
  };

  const fetchSessions = async () => {
    try {
      setSessionsLoading(true);
      setSessionsError('');
      const response = await axios.get('/api/chat/sessions?limit=200&offset=0');
      const rows = response.data?.rows || [];
      setSessions(rows);

      const querySession = new URLSearchParams(window.location.search).get('session') || '';
      const nextSessionId = querySession && rows.some((row) => row.session_id === querySession)
        ? querySession
        : (rows[0]?.session_id || '');
      setSelectedSessionId(nextSessionId);
    } catch (error) {
      console.error(error);
      setSessionsError('Failed to load chat sessions.');
    } finally {
      setSessionsLoading(false);
    }
  };

  const fetchMessages = async (sessionId) => {
    if (!sessionId) {
      setMessages([]);
      setNextBeforeId(null);
      return;
    }

    try {
      setMessagesLoading(true);
      setMessagesError('');
      const response = await axios.get(`/api/chat/session/${encodeURIComponent(sessionId)}?limit=200`);
      setMessages(response.data?.rows || []);
      setNextBeforeId(response.data?.next_before_id || null);
      updateUrlSession(sessionId);
    } catch (error) {
      console.error(error);
      setMessagesError('Failed to load chat messages.');
      setMessages([]);
      setNextBeforeId(null);
    } finally {
      setMessagesLoading(false);
    }
  };

  const loadOlder = async () => {
    if (!selectedSessionId || !nextBeforeId) return;

    try {
      setLoadingOlder(true);
      const response = await axios.get(
        `/api/chat/session/${encodeURIComponent(selectedSessionId)}?limit=200&before_id=${nextBeforeId}`,
      );
      const olderRows = response.data?.rows || [];
      setMessages((prev) => [...olderRows, ...prev]);
      setNextBeforeId(response.data?.next_before_id || null);
    } catch (error) {
      console.error(error);
      setMessagesError('Failed to load older messages.');
    } finally {
      setLoadingOlder(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  useEffect(() => {
    fetchMessages(selectedSessionId);
  }, [selectedSessionId]);

  return (
    <div className="bg-[#0a0a0a] min-h-screen text-gray-300 p-6 font-mono">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-xl font-bold text-white">Chat History</h1>
        <div className="flex items-center gap-3">
          <a
            href="/"
            className="bg-[#1a1a1a] border border-gray-800 px-3 py-1 rounded text-xs text-white hover:bg-gray-800 transition"
          >
            Back to Dashboard
          </a>
          <button
            onClick={fetchSessions}
            className="bg-[#1a1a1a] border border-gray-800 px-3 py-1 rounded text-xs text-white hover:bg-gray-800 transition"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="bg-[#141414] rounded border border-gray-900 p-3 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <select
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className="bg-[#1a1a1a] border border-gray-800 rounded px-3 py-2 text-xs text-gray-200"
          >
            {typeOptions.map((option) => (
              <option key={option} value={option}>
                Type: {option}
              </option>
            ))}
          </select>

          <select
            value={providerFilter}
            onChange={(event) => setProviderFilter(event.target.value)}
            className="bg-[#1a1a1a] border border-gray-800 rounded px-3 py-2 text-xs text-gray-200"
          >
            {providerOptions.map((option) => (
              <option key={option} value={option}>
                Provider: {option}
              </option>
            ))}
          </select>

          <select
            value={modelFilter}
            onChange={(event) => setModelFilter(event.target.value)}
            className="bg-[#1a1a1a] border border-gray-800 rounded px-3 py-2 text-xs text-gray-200"
          >
            {modelOptions.map((option) => (
              <option key={option} value={option}>
                Model: {option}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-3">
          <input
            type="text"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="Search text in sessions + messages"
            className="w-full bg-[#1a1a1a] border border-gray-800 rounded px-3 py-2 text-xs text-gray-200 placeholder:text-gray-500"
          />
        </div>
      </div>

      {(searchLoading || searchError || searchText.trim()) && (
        <div className="mb-4 text-[11px] text-gray-500">
          {searchLoading && <span>Searching message content...</span>}
          {!searchLoading && !searchError && searchText.trim() && (
            <span>Search matches in sessions: {searchSessions.length}</span>
          )}
          {!searchLoading && searchError && <span className="text-red-400">{searchError}</span>}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-4 bg-[#141414] rounded border border-gray-900 overflow-hidden">
          <div className="p-4 border-b border-gray-900">
            <h2 className="text-xs uppercase text-gray-500">Sessions</h2>
          </div>

          {sessionsLoading && <p className="text-xs text-gray-500 p-4">Loading sessions...</p>}
          {sessionsError && <p className="text-xs text-red-400 p-4">{sessionsError}</p>}

          {!sessionsLoading && !sessionsError && (
            <div className="max-h-[78vh] overflow-y-auto divide-y divide-gray-900">
              {filteredSessions.map((session) => (
                <button
                  key={session.session_id}
                  onClick={() => setSelectedSessionId(session.session_id)}
                  className={`w-full text-left px-4 py-3 transition ${
                    selectedSessionId === session.session_id ? 'bg-[#1f1608]' : 'hover:bg-[#1a1a1a]'
                  }`}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-xs text-white truncate">{session.display_title || session.session_id}</p>
                    {(() => {
                      const SessionTypeIcon = sessionTypeIcon(session.session_type);
                      return (
                    <span className={`text-[10px] uppercase border rounded px-2 py-[1px] ${sessionTypeClass(session.session_type)}`}>
                      <SessionTypeIcon size={11} className="inline-block mr-1 -mt-[1px]" />
                      {session.session_type || 'general'}
                    </span>
                      );
                    })()}
                  </div>
                  <p className="text-[11px] text-gray-600 mt-1 truncate">id={session.session_id}</p>
                  <p className="text-[11px] text-gray-500 mt-1">
                    {session.model || 'unknown model'} · {session.provider || 'unknown provider'}
                  </p>
                  <p className="text-[11px] text-gray-600 mt-1">
                    messages={session.message_count || 0} · user={session.user_messages || 0} · assistant={session.assistant_messages || 0}
                  </p>
                  <p className="text-[11px] text-gray-600 mt-1">
                    last={formatIso(session.last_event_ts)}
                  </p>
                </button>
              ))}
              {filteredSessions.length === 0 && (
                <p className="text-xs text-gray-600 p-4">No transcript sessions found yet.</p>
              )}
            </div>
          )}
        </div>

        <div className="xl:col-span-8 bg-[#141414] rounded border border-gray-900 overflow-hidden">
          <div className="p-4 border-b border-gray-900 flex items-center justify-between gap-3">
            <h2 className="text-xs uppercase text-gray-500">Conversation</h2>
            {currentSession && (
              <p className="text-[11px] text-gray-500 flex items-center gap-1.5 flex-wrap">
                {currentSession.display_title || currentSession.session_id} · {currentSession.model || 'unknown model'} · {currentSession.provider || 'unknown provider'} · type={currentSession.session_type || 'general'} · messages={currentSession.message_count || 0}
                {(() => {
                  const SessionTypeIcon = sessionTypeIcon(currentSession.session_type);
                  return <SessionTypeIcon size={12} className="inline-block" />;
                })()}
              </p>
            )}
          </div>

          <div className="p-4 max-h-[78vh] overflow-y-auto space-y-3">
            {messagesLoading && <p className="text-xs text-gray-500">Loading messages...</p>}
            {messagesError && <p className="text-xs text-red-400">{messagesError}</p>}

            {!messagesLoading && !messagesError && selectedSessionId && (
              <>
                {nextBeforeId && (
                  <button
                    onClick={loadOlder}
                    disabled={loadingOlder}
                    className="bg-[#1a1a1a] border border-gray-800 px-3 py-1 rounded text-xs text-white hover:bg-gray-800 transition disabled:opacity-60"
                  >
                    {loadingOlder ? 'Loading older...' : 'Load older messages'}
                  </button>
                )}

                {filteredMessages.map((message) => (
                  <div key={message.id} className="bg-[#111111] border border-gray-900 rounded p-3">
                    <p className="text-[11px] text-gray-500 mb-2 flex items-center gap-2 flex-wrap">
                      {(() => {
                        const RoleIcon = roleIcon(message.role);
                        return (
                          <span className={`${roleClass(message.role)} inline-flex items-center gap-1`}>
                            <RoleIcon size={12} />
                            {message.role || 'unknown'}
                          </span>
                        );
                      })()}
                      <span>· {formatIso(message.event_ts)}</span>
                      <span>· {message.message_type || '-'}</span>
                      <span>· {message.model || 'unknown model'}</span>
                    </p>
                    {renderMessageBlocks(message)}
                    <details className="mt-2">
                      <summary className="cursor-pointer text-[11px] text-gray-400 hover:text-gray-200">View raw JSON</summary>
                      <pre className="mt-2 text-[11px] text-gray-300 whitespace-pre-wrap break-words bg-[#0f0f0f] border border-gray-900 rounded p-2">{prettyJson(message.raw_json)}</pre>
                    </details>
                  </div>
                ))}

                {filteredMessages.length === 0 && (
                  <p className="text-xs text-gray-600">No messages found for this session.</p>
                )}
              </>
            )}

            {!selectedSessionId && !sessionsLoading && (
              <p className="text-xs text-gray-600">Select a session to view the full conversation log.</p>
            )}
          </div>
        </div>
      </div>

      <div className="mt-6 py-4 border-t border-gray-900 text-[11px] text-gray-500">
        Chat History shows transcript-based session archives from OpenClaw, including user, assistant, tool, and thinking blocks for debugging and audit.
      </div>
    </div>
  );
};

export default ChatPage;
