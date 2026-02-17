import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Activity, Bot, Brain, Clock3, HelpCircle, MessageCircle, MessageSquare, User, Wrench } from 'lucide-react';

const ChatPage = ({ theme = 'dark' }) => {
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

  const isLight = theme === 'light';
  const panelBg = isLight ? 'bg-gray-50 rounded border border-gray-200' : 'bg-[#141414] rounded border border-gray-900';
  const inputBg = isLight ? 'bg-white border border-gray-200 text-gray-900' : 'bg-[#1a1a1a] border border-gray-800 text-gray-200';

  const sessionTypeClass = (sessionType) => {
    const key = String(sessionType || '').toLowerCase();
    if (key === 'heartbeat') return isLight ? 'bg-blue-100 text-blue-700 border-blue-200' : 'bg-blue-900/40 text-blue-300 border-blue-800';
    if (key === 'whatsapp') return isLight ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-emerald-900/40 text-emerald-300 border-emerald-800';
    if (key === 'cron') return isLight ? 'bg-purple-100 text-purple-700 border-purple-200' : 'bg-purple-900/40 text-purple-300 border-purple-800';
    if (key === 'conversation') return isLight ? 'bg-orange-100 text-orange-700 border-orange-200' : 'bg-orange-900/40 text-orange-300 border-orange-800';
    return isLight ? 'bg-gray-100 text-gray-700 border-gray-300' : 'bg-gray-800 text-gray-300 border-gray-700';
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
    if (key === 'user') return isLight ? 'text-cyan-700' : 'text-cyan-300';
    if (key === 'assistant') return isLight ? 'text-orange-700' : 'text-orange-300';
    if (key === 'tool' || key === 'toolresult') return isLight ? 'text-emerald-700' : 'text-emerald-300';
    if (key === 'system') return isLight ? 'text-purple-700' : 'text-purple-300';
    return isLight ? 'text-gray-700' : 'text-gray-300';
  };

  const roleLabel = (role) => {
    const key = String(role || '').toLowerCase();
    if (key === 'user') return 'user';
    if (key === 'assistant') return 'assistant';
    if (key === 'tool') return 'tool';
    if (key === 'toolresult') return 'tool result';
    if (key === 'system') return 'system';
    return 'event';
  };

  const isUnknownRole = (role) => {
    const key = String(role || '').toLowerCase();
    return !['user', 'assistant', 'tool', 'toolresult', 'system'].includes(key);
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
        <pre className={`text-[12px] whitespace-pre-wrap break-words ${isLight ? 'text-gray-900' : 'text-gray-200'}`}>
          {message.content_text || '(No text content captured)'}
        </pre>
      );
    }

    return (
      <div className="space-y-2">
        {content.map((item, index) => {
          if (!item || typeof item !== 'object') {
            return (
              <pre key={index} className={`text-[12px] whitespace-pre-wrap break-words ${isLight ? 'text-gray-900' : 'text-gray-200'}`}>
                {String(item)}
              </pre>
            );
          }

          const itemType = String(item.type || '').toLowerCase();
          if (itemType === 'text') {
            return (
              <pre key={index} className={`text-[12px] whitespace-pre-wrap break-words ${isLight ? 'text-gray-900' : 'text-gray-200'}`}>
                {item.text || ''}
              </pre>
            );
          }

          if (itemType === 'thinking') {
            return (
              <div key={index} className={`${isLight ? 'bg-white border border-gray-200' : 'bg-[#191919] border border-gray-800'} rounded p-2`}>
                <div className="flex items-start gap-2">
                  <div className="w-8 shrink-0 pt-0.5 flex justify-center">
                    <Brain size={18} className={isLight ? 'text-blue-700' : 'text-blue-300'} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className={`text-[11px] mb-1 ${isLight ? 'text-blue-700' : 'text-blue-300'}`}>thinking</p>
                    <pre className={`text-[12px] whitespace-pre-wrap break-words ${isLight ? 'text-gray-900' : 'text-gray-200'}`}>{item.thinking || ''}</pre>
                  </div>
                </div>
              </div>
            );
          }

          if (itemType === 'toolcall') {
            return (
              <div key={index} className={`${isLight ? 'bg-white border border-gray-200' : 'bg-[#191919] border border-gray-800'} rounded p-2`}>
                <div className="flex items-start gap-2">
                  <div className="w-8 shrink-0 pt-0.5 flex justify-center">
                    <Wrench size={18} className={isLight ? 'text-emerald-700' : 'text-emerald-300'} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className={`text-[11px] mb-1 ${isLight ? 'text-emerald-700' : 'text-emerald-300'}`}>toolCall · {item.name || 'unknown'}</p>
                    <pre className={`text-[12px] whitespace-pre-wrap break-words ${isLight ? 'text-gray-900' : 'text-gray-200'}`}>{JSON.stringify(item.arguments || {}, null, 2)}</pre>
                  </div>
                </div>
              </div>
            );
          }

          return (
            <div key={index} className={`${isLight ? 'bg-white border border-gray-200' : 'bg-[#191919] border border-gray-800'} rounded p-2`}>
              <p className={`text-[11px] mb-1 ${isLight ? 'text-gray-500' : 'text-gray-400'}`}>{item.type || 'content'}</p>
              <pre className={`text-[12px] whitespace-pre-wrap break-words ${isLight ? 'text-gray-900' : 'text-gray-200'}`}>{JSON.stringify(item, null, 2)}</pre>
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

      if (typeFilter !== 'all' && typeValue !== typeFilter) return false;
      if (providerFilter !== 'all' && providerValue !== providerFilter) return false;
      if (modelFilter !== 'all' && modelValue !== modelFilter) return false;

      if (!searchText.trim()) return true;
      if (searchSessionIds.size > 0) return searchSessionIds.has(session.session_id);

      const needle = searchText.toLowerCase();
      const metadata = [String(session.provider || ''), String(session.model || ''), String(session.session_type || '')].join(' ').toLowerCase();
      return metadata.includes(needle);
    });
  }, [sessions, typeFilter, providerFilter, modelFilter, searchText, searchSessions]);

  const filteredMessages = useMemo(() => {
    if (!searchText.trim()) return messages;
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
        setSearchSessions(response.data?.sessions || []);
      } catch (error) {
        if (cancelled) return;
        console.error(error);
        setSearchError('Search failed.');
        setSearchSessions([]);
      } finally {
        if (!cancelled) setSearchLoading(false);
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

  useEffect(() => {
    const onRescan = () => fetchSessions();
    window.addEventListener('cj:rescan', onRescan);
    return () => window.removeEventListener('cj:rescan', onRescan);
  }, []);

  return (
    <div className={`p-6 ${isLight ? 'text-gray-900' : 'text-gray-300'}`}>
      <div className="mb-4">
        <h1 className={`text-xl font-bold ${isLight ? 'text-gray-900' : 'text-white'}`}>Chat History</h1>
      </div>

      <div className={`${panelBg} p-3 mb-6`}> 
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className={`${inputBg} rounded px-3 py-2 text-xs`}>
            {typeOptions.map((option) => (
              <option key={option} value={option}>Type: {option}</option>
            ))}
          </select>

          <select value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)} className={`${inputBg} rounded px-3 py-2 text-xs`}>
            {providerOptions.map((option) => (
              <option key={option} value={option}>Provider: {option}</option>
            ))}
          </select>

          <select value={modelFilter} onChange={(event) => setModelFilter(event.target.value)} className={`${inputBg} rounded px-3 py-2 text-xs`}>
            {modelOptions.map((option) => (
              <option key={option} value={option}>Model: {option}</option>
            ))}
          </select>
        </div>

        <div className="mt-3">
          <input
            type="text"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="Search text in sessions + messages"
            className={`w-full ${inputBg} rounded px-3 py-2 text-xs placeholder:text-gray-500`}
          />
        </div>
      </div>

      {(searchLoading || searchError || searchText.trim()) && (
        <div className={`mb-4 text-[11px] ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>
          {searchLoading && <span>Searching message content...</span>}
          {!searchLoading && !searchError && searchText.trim() && <span>Search matches in sessions: {searchSessions.length}</span>}
          {!searchLoading && searchError && <span className="text-red-400">{searchError}</span>}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className={`xl:col-span-4 ${panelBg} overflow-hidden`}>
          <div className={`p-4 border-b ${isLight ? 'border-gray-200' : 'border-gray-900'}`}>
            <h2 className={`text-xs uppercase ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>Sessions</h2>
          </div>

          {sessionsLoading && <p className={`text-xs p-4 ${isLight ? 'text-gray-500' : 'text-gray-500'}`}>Loading sessions...</p>}
          {sessionsError && <p className="text-xs text-red-400 p-4">{sessionsError}</p>}

          {!sessionsLoading && !sessionsError && (
            <div className={`max-h-[78vh] overflow-y-auto divide-y ${isLight ? 'divide-gray-200' : 'divide-gray-900'}`}>
              {filteredSessions.map((session) => (
                <button
                  key={session.session_id}
                  onClick={() => setSelectedSessionId(session.session_id)}
                  className={`w-full text-left px-4 py-3 transition ${selectedSessionId === session.session_id ? (isLight ? 'bg-gray-100' : 'bg-[#1f1608]') : (isLight ? 'hover:bg-gray-50' : 'hover:bg-[#1a1a1a]')}`}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className={`text-xs truncate ${isLight ? 'text-black' : 'text-white'}`}>{session.display_title || session.session_id}</p>
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
                  <p className={`text-[11px] mt-1 truncate ${isLight ? 'text-gray-500' : 'text-gray-600'}`}>id={session.session_id}</p>
                  <p className={`text-[11px] mt-1 ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>{session.model || 'unknown model'} · {session.provider || 'unknown provider'}</p>
                  <p className={`text-[11px] mt-1 ${isLight ? 'text-gray-600' : 'text-gray-600'}`}>messages={session.message_count || 0} · user={session.user_messages || 0} · assistant={session.assistant_messages || 0}</p>
                  <p className={`text-[11px] mt-1 ${isLight ? 'text-gray-600' : 'text-gray-600'}`}>last={formatIso(session.last_event_ts)}</p>
                </button>
              ))}
              {filteredSessions.length === 0 && <p className={`text-xs p-4 ${isLight ? 'text-gray-500' : 'text-gray-600'}`}>No transcript sessions found yet.</p>}
            </div>
          )}
        </div>

        <div className={`xl:col-span-8 ${panelBg} overflow-hidden`}>
          <div className={`p-4 border-b flex items-center justify-between gap-3 ${isLight ? 'border-gray-200' : 'border-gray-900'}`}>
            <h2 className={`text-xs uppercase ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>Conversation</h2>
            {currentSession && (
              <p className={`text-[11px] flex items-center gap-1.5 flex-wrap ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>
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
                    className="bg-gray-700 border border-gray-600 px-3 py-1 rounded text-xs text-white hover:bg-gray-600 transition disabled:opacity-60"
                  >
                    {loadingOlder ? 'Loading older...' : 'Load older messages'}
                  </button>
                )}

                {filteredMessages.map((message) => (
                  <div key={message.id} className={`${isLight ? 'bg-white border border-gray-200' : 'bg-[#111111] border border-gray-900'} rounded p-3`}>
                    {(() => {
                      const RoleIcon = roleIcon(message.role);
                      const unknownRole = isUnknownRole(message.role);
                      return (
                        <div className="flex items-start gap-3">
                          <div className="w-16 shrink-0 pt-0.5 flex justify-center">
                            <div className={`rounded-full p-2 ${isLight ? 'bg-gray-100' : ''}`}>
                              <RoleIcon size={26} className={roleClass(message.role)} />
                            </div>
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className={`text-[11px] mb-2 flex items-center gap-2 flex-wrap ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>
                              <span className={roleClass(message.role)}>{roleLabel(message.role)}</span>
                              <span>· {formatIso(message.event_ts)}</span>
                              <span>· {message.message_type || '-'}</span>
                              <span>· {message.model || 'model n/a'}</span>
                            </p>

                            {unknownRole ? (
                              <details>
                                <summary className={`cursor-pointer text-[11px] ${isLight ? 'text-gray-600 hover:text-gray-800' : 'text-gray-400 hover:text-gray-200'}`}>Expand event details</summary>
                                <div className="mt-2">
                                  {renderMessageBlocks(message)}
                                  <details className="mt-2">
                                    <summary className={`cursor-pointer text-[11px] ${isLight ? 'text-gray-600 hover:text-gray-800' : 'text-gray-400 hover:text-gray-200'}`}>View raw JSON</summary>
                                    <pre className={`mt-2 text-[11px] whitespace-pre-wrap break-words rounded p-2 ${isLight ? 'text-gray-900 bg-gray-50 border border-gray-200' : 'text-gray-300 bg-[#0f0f0f] border border-gray-900'}`}>{prettyJson(message.raw_json)}</pre>
                                  </details>
                                </div>
                              </details>
                            ) : (
                              <>
                                {renderMessageBlocks(message)}
                                <details className="mt-2">
                                  <summary className={`cursor-pointer text-[11px] ${isLight ? 'text-gray-600 hover:text-gray-800' : 'text-gray-400 hover:text-gray-200'}`}>View raw JSON</summary>
                                  <pre className={`mt-2 text-[11px] whitespace-pre-wrap break-words rounded p-2 ${isLight ? 'text-gray-900 bg-gray-50 border border-gray-200' : 'text-gray-300 bg-[#0f0f0f] border border-gray-900'}`}>{prettyJson(message.raw_json)}</pre>
                                </details>
                              </>
                            )}
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                ))}

                {filteredMessages.length === 0 && <p className={`text-xs ${isLight ? 'text-gray-500' : 'text-gray-600'}`}>No messages found for this session.</p>}
              </>
            )}

            {!selectedSessionId && !sessionsLoading && <p className={`text-xs ${isLight ? 'text-gray-500' : 'text-gray-600'}`}>Select a session to view the full conversation log.</p>}
          </div>
        </div>
      </div>

      <div className={`mt-6 py-4 border-t text-[11px] ${isLight ? 'border-gray-200 text-gray-500' : 'border-gray-900 text-gray-500'}`}>
        Chat History shows transcript-based session archives from OpenClaw, including user, assistant, tool, and thinking blocks for debugging and audit.
      </div>
    </div>
  );
};

export default ChatPage;
