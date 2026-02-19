import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Bot, Settings, User, Wrench } from 'lucide-react';

const ConversationPage = ({ theme = 'dark', sessionId }) => {
  const [messages, setMessages] = useState([]);
  const [modelTimeline, setModelTimeline] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const isLight = theme === 'light';

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

  const parseSender = (msg) => {
    const role = msg.role || '';
    if (role === 'assistant') return { label: 'Rune', channel: '', color: 'orange' };
    const text = msg.text_content || '';
    const hasToolResult = msg.has_tool_result;
    if (hasToolResult && role === 'user') {
      if (/^🦞\s*OpenClaw\s/.test(text)) return { label: 'System', channel: 'OpenClaw', color: 'gray' };
      return { label: 'Tool Result', channel: '', color: 'emerald' };
    }
    if (/^\[WhatsApp\s/.test(text)) return { label: 'Adii', channel: 'WhatsApp', color: 'green' };
    if (/Slack\s+(?:DM\s+from\s+)?([A-Z][a-z]+)/i.test(text)) return { label: RegExp.$1 || 'User', channel: 'Slack', color: 'purple' };
    if (/^System:\s/i.test(text)) return { label: 'System', channel: '', color: 'gray' };
    if (/^Read HEARTBEAT\.md/i.test(text)) return { label: 'System', channel: 'Heartbeat', color: 'gray' };
    if (/^🦞\s*OpenClaw\s/.test(text)) return { label: 'System', channel: 'OpenClaw', color: 'gray' };
    return { label: 'Adii', channel: '', color: 'cyan' };
  };

  const senderTextColor = (color) => {
    const map = {
      orange: 'text-orange-300', cyan: 'text-cyan-300', green: 'text-green-300',
      purple: 'text-purple-300', emerald: 'text-emerald-300', gray: 'text-gray-500',
    };
    if (isLight) {
      const lightMap = {
        orange: 'text-orange-700', cyan: 'text-cyan-700', green: 'text-green-700',
        purple: 'text-purple-700', emerald: 'text-emerald-700', gray: 'text-gray-500',
      };
      return lightMap[color] || 'text-gray-700';
    }
    return map[color] || 'text-gray-300';
  };

  const borderColor = (color) => {
    const map = {
      orange: 'border-l-orange-600', cyan: 'border-l-cyan-600', green: 'border-l-green-600',
      purple: 'border-l-purple-600', emerald: 'border-l-emerald-600', gray: 'border-l-gray-600',
    };
    return map[color] || '';
  };

  const SenderIcon = ({ sender }) => {
    const iconClass = `${senderTextColor(sender.color)}`;
    if (sender.label === 'Rune') return <Bot size={22} className={iconClass} />;
    if (sender.label === 'Tool Result') return <Wrench size={22} className={iconClass} />;
    if (sender.label === 'System') return <Settings size={22} className={iconClass} />;
    return <User size={22} className={iconClass} />;
  };

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    const fetchConversation = async () => {
      try {
        setLoading(true);
        setError('');
        const [convRes, modelRes] = await Promise.all([
          axios.get(`/api/conversations/${encodeURIComponent(sessionId)}?limit=500`),
          axios.get(`/api/model-changes/${encodeURIComponent(sessionId)}`),
        ]);
        if (!cancelled) {
          setMessages(convRes.data?.rows || []);
          setModelTimeline(modelRes.data?.rows || []);
        }
      } catch (err) {
        console.error(err);
        if (!cancelled) setError('Failed to load conversation.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchConversation();
    return () => { cancelled = true; };
  }, [sessionId]);

  const parseContentBlocks = (contentJson) => {
    if (!contentJson) return [];
    try {
      const parsed = JSON.parse(contentJson);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  };

  const renderMessage = (msg, idx) => {
    const sender = parseSender(msg);
    const blocks = parseContentBlocks(msg.content_json);

    // Count reasoning chain steps
    let chainCount = 0;
    if (sender.label === 'Rune') {
      for (const block of blocks) {
        if (['thinking', 'tool_use', 'toolCall'].includes(block.type)) chainCount++;
      }
    }

    return (
      <div key={msg.id || idx} className={`${isLight ? 'bg-white border border-gray-200' : 'bg-[#111111] border border-gray-900'} rounded p-3 border-l-2 ${borderColor(sender.color)}`}>
        <div className="flex items-start gap-3">
          <div className="w-10 shrink-0 pt-0.5 flex justify-center">
            <SenderIcon sender={sender} />
          </div>
          <div className="min-w-0 flex-1">
            {/* Sender line */}
            <p className="text-[11px] mb-2 flex items-center gap-2 flex-wrap text-gray-500">
              <span className={senderTextColor(sender.color)}>{sender.label}</span>
              {sender.channel && (
                <span className={`text-[10px] uppercase border rounded px-1.5 py-[1px] ${isLight ? 'border-gray-300 text-gray-600' : 'border-gray-700 text-gray-400'}`}>
                  {sender.channel}
                </span>
              )}
              {msg.model && <span>&middot; {msg.model}</span>}
              {msg.message_ts && <span>&middot; {formatTs(msg.message_ts)}</span>}
            </p>

            {/* Reasoning chain header */}
            {chainCount > 1 && (
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] uppercase text-blue-400/60 tracking-wider font-semibold">Reasoning chain</span>
                <span className="text-[10px] text-gray-700">&middot;</span>
                <span className="text-[10px] text-gray-600">{chainCount} steps</span>
              </div>
            )}

            {/* Content blocks with optional chain timeline */}
            {chainCount > 1 ? (
              <div className="relative pl-5 ml-1">
                <div className="absolute left-[4px] top-1 bottom-1 w-px bg-gradient-to-b from-blue-700/40 via-emerald-700/40 to-orange-700/30" />
                {blocks.map((block, bi) => renderBlock(block, bi, blocks, true))}
              </div>
            ) : (
              blocks.map((block, bi) => renderBlock(block, bi, blocks, false))
            )}

            {/* Fallback text if no content blocks */}
            {blocks.length === 0 && msg.text_content && (
              <pre className={`text-[12px] whitespace-pre-wrap break-words ${isLight ? 'text-gray-800' : 'text-gray-200'}`}>
                {msg.text_content}
              </pre>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderBlock = (block, index, allBlocks, inChain) => {
    const dotColor = block.type === 'thinking'
      ? 'bg-blue-500'
      : ['tool_use', 'toolCall'].includes(block.type)
        ? 'bg-emerald-500'
        : ['tool_result', 'toolResult'].includes(block.type)
          ? 'bg-emerald-400/40'
          : 'bg-orange-500';

    const wrapper = (children) => {
      if (!inChain) return <div key={index}>{children}</div>;
      return (
        <div key={index} className="relative">
          <div className={`absolute -left-[16px] top-3 w-[9px] h-[9px] rounded-full ring-2 ${isLight ? 'ring-white' : 'ring-[#111111]'} ${dotColor}`} />
          {children}
        </div>
      );
    };

    if (block.type === 'thinking') {
      // Find tools that follow this thinking block
      const toolsAfter = [];
      for (let i = index + 1; i < allBlocks.length; i++) {
        if (['tool_use', 'toolCall'].includes(allBlocks[i].type)) {
          toolsAfter.push(allBlocks[i].name || allBlocks[i].toolName || 'unknown');
        } else if (allBlocks[i].type === 'thinking') break;
      }

      return wrapper(
        <div className={`${isLight ? 'bg-gray-100 border border-gray-200' : 'bg-[#191919] border border-gray-800'} rounded p-2 mb-2`}>
          <ThinkingDetails
            text={block.thinking || block.text || ''}
            toolsAfter={toolsAfter}
            isLight={isLight}
          />
        </div>
      );
    }

    if (block.type === 'text') {
      return wrapper(
        <pre className={`text-[12px] whitespace-pre-wrap break-words mb-2 ${isLight ? 'text-gray-800' : 'text-gray-200'}`}>
          {block.text}
        </pre>
      );
    }

    if (['tool_use', 'toolCall'].includes(block.type)) {
      return wrapper(
        <div className={`${isLight ? 'bg-gray-100 border border-gray-200' : 'bg-[#191919] border border-gray-800'} rounded p-2 mb-2`}>
          <div className="flex items-start gap-2">
            <Wrench size={14} className="text-emerald-300 mt-0.5 flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="text-[11px] text-emerald-300 mb-1">toolCall &middot; {block.name || block.toolName}</p>
              <details>
                <summary className={`text-[11px] cursor-pointer ${isLight ? 'text-gray-500 hover:text-gray-700' : 'text-gray-400 hover:text-gray-200'}`}>Input</summary>
                <pre className={`text-[12px] mt-1 max-h-72 overflow-y-auto ${isLight ? 'text-gray-800' : 'text-gray-200'}`}>
                  {block.input ? JSON.stringify(block.input, null, 2) : ''}
                </pre>
              </details>
            </div>
          </div>
        </div>
      );
    }

    if (['tool_result', 'toolResult'].includes(block.type)) {
      return wrapper(
        <div className={`${isLight ? 'bg-gray-100 border border-gray-200' : 'bg-[#191919] border border-gray-800'} rounded p-2 mb-2`}>
          <details>
            <summary className={`text-[11px] cursor-pointer ${block.is_error ? 'text-red-400' : (isLight ? 'text-emerald-700' : 'text-emerald-300')}`}>
              Tool Result{block.is_error ? ' (error)' : ''}
            </summary>
            <pre className={`text-[12px] mt-1 max-h-72 overflow-y-auto ${isLight ? 'text-gray-800' : 'text-gray-200'}`}>
              {typeof block.content === 'string' ? block.content : (block.content ? JSON.stringify(block.content, null, 2) : '')}
            </pre>
          </details>
        </div>
      );
    }

    // Default: render as JSON
    return wrapper(
      <pre className={`text-[12px] whitespace-pre-wrap break-words mb-2 ${isLight ? 'text-gray-800' : 'text-gray-200'}`}>
        {JSON.stringify(block, null, 2)}
      </pre>
    );
  };

  return (
    <div className={`${isLight ? 'bg-white text-gray-900' : 'bg-[#0a0a0a] text-gray-300'} p-6 font-mono max-w-7xl mx-auto`}>
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className={`text-xl font-bold ${isLight ? 'text-gray-900' : 'text-white'}`}>Conversation</h1>
          <p className="text-[11px] mt-1 flex items-center gap-2 text-gray-500">
            <code className={`rounded px-2 py-0.5 ${isLight ? 'bg-gray-100 border border-gray-200 text-gray-700' : 'bg-[#1a1a1a] border border-gray-800 text-gray-300'}`}>
              {(sessionId || '').slice(0, 12)}
            </code>
          </p>
        </div>
      </div>

      {/* Model timeline */}
      {modelTimeline.length > 0 && (
        <div className={`${isLight ? 'bg-gray-50 border border-gray-200' : 'bg-[#141414] border border-gray-900'} rounded p-3 mb-6`}>
          <div className="flex flex-wrap gap-2">
            {modelTimeline.map((mc, i) => (
              <div key={i} className={`flex items-center gap-2 rounded-md px-3 py-1.5 ${isLight ? 'bg-gray-100' : 'bg-[#1a1a1a]'}`}>
                <span className="w-2 h-2 bg-orange-500 rounded-full flex-shrink-0" />
                <span className="text-xs">
                  <strong className={isLight ? 'text-gray-900' : 'text-white'}>{mc.model_id}</strong>
                  {' '}<span className="text-gray-500">({mc.provider})</span>
                  {mc.timestamp && <span className="text-gray-600"> {formatTs(mc.timestamp)}</span>}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      {loading && <p className="text-xs text-gray-500">Loading conversation...</p>}
      {error && <p className="text-xs text-red-400">{error}</p>}

      {!loading && !error && (
        <div className="space-y-3">
          {messages.map((msg, idx) => renderMessage(msg, idx))}
        </div>
      )}

      {!loading && !error && messages.length === 0 && (
        <p className="text-xs text-gray-600 mt-4">No messages found for this session.</p>
      )}
    </div>
  );
};

const ThinkingDetails = ({ text, toolsAfter, isLight }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <details open={expanded} onToggle={(e) => setExpanded(e.target.open)}>
      <summary className="text-[11px] text-blue-300 cursor-pointer flex items-center gap-2">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>
          <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>
          <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>
        </svg>
        <span>Thinking...</span>
        {toolsAfter.length > 0 && (
          <span className="text-emerald-400 text-[10px] italic ml-auto">Led to: {toolsAfter.join(', ')}</span>
        )}
      </summary>
      <pre className={`text-[12px] mt-2 max-h-96 overflow-y-auto whitespace-pre-wrap break-words ${isLight ? 'text-gray-800' : 'text-gray-200'}`}>
        {text}
      </pre>
    </details>
  );
};

export default ConversationPage;
