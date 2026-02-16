import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';

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

  const currentSession = useMemo(
    () => sessions.find((row) => row.session_id === selectedSessionId) || null,
    [sessions, selectedSessionId],
  );

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

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-4 bg-[#141414] rounded border border-gray-900 overflow-hidden">
          <div className="p-4 border-b border-gray-900">
            <h2 className="text-xs uppercase text-gray-500">Sessions</h2>
          </div>

          {sessionsLoading && <p className="text-xs text-gray-500 p-4">Loading sessions...</p>}
          {sessionsError && <p className="text-xs text-red-400 p-4">{sessionsError}</p>}

          {!sessionsLoading && !sessionsError && (
            <div className="max-h-[78vh] overflow-y-auto divide-y divide-gray-900">
              {sessions.map((session) => (
                <button
                  key={session.session_id}
                  onClick={() => setSelectedSessionId(session.session_id)}
                  className={`w-full text-left px-4 py-3 transition ${
                    selectedSessionId === session.session_id ? 'bg-[#1f1608]' : 'hover:bg-[#1a1a1a]'
                  }`}
                >
                  <p className="text-xs text-white truncate">{session.session_id}</p>
                  <p className="text-[11px] text-gray-500 mt-1">
                    {session.model || 'unknown model'} · {session.provider || 'unknown provider'}
                  </p>
                  <p className="text-[11px] text-gray-600 mt-1">
                    msgs={session.message_count || 0} · last={formatIso(session.last_event_ts)}
                  </p>
                </button>
              ))}
              {sessions.length === 0 && (
                <p className="text-xs text-gray-600 p-4">No transcript sessions found yet.</p>
              )}
            </div>
          )}
        </div>

        <div className="xl:col-span-8 bg-[#141414] rounded border border-gray-900 overflow-hidden">
          <div className="p-4 border-b border-gray-900 flex items-center justify-between gap-3">
            <h2 className="text-xs uppercase text-gray-500">Conversation</h2>
            {currentSession && (
              <p className="text-[11px] text-gray-500">
                {currentSession.model || 'unknown model'} · {currentSession.provider || 'unknown provider'} · messages={currentSession.message_count || 0}
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

                {messages.map((message) => (
                  <div key={message.id} className="bg-[#111111] border border-gray-900 rounded p-3">
                    <p className="text-[11px] text-gray-500 mb-2">
                      {message.role || 'unknown'} · {formatIso(message.event_ts)} · {message.message_type || '-'}
                    </p>
                    <pre className="text-[12px] text-gray-200 whitespace-pre-wrap break-words">{message.content_text || '(No text content captured)'}</pre>
                  </div>
                ))}

                {messages.length === 0 && (
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
    </div>
  );
};

export default ChatPage;
