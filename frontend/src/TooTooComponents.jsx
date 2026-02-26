import React, { useState } from 'react';
import { ChevronDown, ChevronUp, MessageSquare, Shield, Sparkles, Target, Wrench } from 'lucide-react';

export const ScoreRing = ({ score, size = 72 }) => {
  const hasScore = typeof score === 'number' && !Number.isNaN(score);
  const pct = hasScore ? Math.max(0, Math.min(1, score)) : 0;
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - pct);
  const color = !hasScore ? '#6b7280' : pct >= 0.85 ? '#22c55e' : pct >= 0.7 ? '#f59e0b' : pct >= 0.5 ? '#f97316' : '#ef4444';
  const bgColor = !hasScore ? 'rgba(107,114,128,0.1)' : pct >= 0.85 ? 'rgba(34,197,94,0.1)' : pct >= 0.7 ? 'rgba(245,158,11,0.1)' : pct >= 0.5 ? 'rgba(249,115,22,0.1)' : 'rgba(239,68,68,0.1)';

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill={bgColor} stroke="rgba(255,255,255,0.06)" strokeWidth="3" />
        {hasScore && (
          <circle
            cx={size / 2} cy={size / 2} r={radius} fill="none"
            stroke={color} strokeWidth="3.5" strokeLinecap="round"
            strokeDasharray={circumference} strokeDashoffset={offset}
            style={{ transition: 'stroke-dashoffset 0.8s ease-out' }}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-lg font-bold" style={{ color }}>{hasScore ? (pct * 100).toFixed(0) : '—'}</span>
        <span className="text-[9px] text-gray-500 -mt-0.5">/ 100</span>
      </div>
    </div>
  );
};

export const ConfidenceBar = ({ confidence, isLight }) => {
  const pct = Math.round(confidence * 100);
  const color = confidence >= 0.8 ? 'bg-amber-400' : confidence >= 0.6 ? 'bg-amber-500/70' : 'bg-amber-600/50';
  return (
    <div className="flex items-center gap-2 flex-1 min-w-0">
      <div className={`h-1.5 flex-1 rounded-full ${isLight ? 'bg-gray-200' : 'bg-gray-800'}`}>
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%`, transition: 'width 0.6s ease-out' }} />
      </div>
      <span className="text-[10px] text-gray-500 w-8 text-right shrink-0">{pct}%</span>
    </div>
  );
};

const sectionIcons = { beliefs: Shield, principles: Target, practices: Wrench, shadows: Sparkles };
const sectionLabels = { beliefs: 'Beliefs', principles: 'Principles', practices: 'Practices', shadows: 'Shadows' };

const patternColors = {
  'cold-open': { bg: 'bg-sky-900/30', border: 'border-sky-700/40', text: 'text-sky-300' },
  'warm': { bg: 'bg-emerald-900/30', border: 'border-emerald-700/40', text: 'text-emerald-300' },
  'playful': { bg: 'bg-violet-900/30', border: 'border-violet-700/40', text: 'text-violet-300' },
};

const renderMarkdownBold = (text, isLight) => {
  if (!text) return null;
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className={isLight ? 'text-gray-900' : 'text-white'}>{part.slice(2, -2)}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
};

export const TooTooFeedbackCard = ({ data, isLight, sessionId, onNavigate }) => {
  const [showReasoning, setShowReasoning] = useState(false);
  const {
    alignment_score, pattern_tag, agent, assessment,
    relevant_beliefs = [], feedback, reasoning, suggested_improvement,
  } = data;

  const hasValidScore = typeof alignment_score === 'number' && !Number.isNaN(alignment_score);
  const scoreLabel = !hasValidScore ? 'Unable to score'
    : alignment_score >= 0.85 ? 'Strong alignment'
    : alignment_score >= 0.7 ? 'Acceptable'
    : alignment_score >= 0.5 ? 'Needs work' : 'Misaligned';

  const patternStyle = patternColors[pattern_tag] || { bg: 'bg-gray-800/40', border: 'border-gray-700/40', text: 'text-gray-300' };

  const sectionsByType = {};
  for (const b of relevant_beliefs) {
    const sec = b.section || 'other';
    if (!sectionsByType[sec]) sectionsByType[sec] = [];
    sectionsByType[sec].push(b);
  }

  return (
    <div className={`rounded-lg overflow-hidden mb-3 ${isLight ? 'bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200' : 'bg-gradient-to-br from-[#1a1400] to-[#1a0f00] border border-amber-900/40'}`}>
      {/* Header bar */}
      <div className={`px-4 py-3 flex items-center gap-3 ${isLight ? 'bg-amber-100/60 border-b border-amber-200' : 'bg-amber-950/30 border-b border-amber-900/30'}`}>
        <div className={`h-7 w-7 rounded-md flex items-center justify-center ${isLight ? 'bg-amber-200' : 'bg-amber-900/50'}`}>
          <img src="/tootoo-icon.png" alt="TooToo" className="h-5 w-5 rounded-sm" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-xs font-bold ${isLight ? 'text-amber-900' : 'text-amber-200'}`}>TooToo Alignment Review</span>
            {pattern_tag && (
              <span className={`text-[10px] uppercase px-2 py-[1px] rounded border ${patternStyle.bg} ${patternStyle.border} ${patternStyle.text}`}>
                {pattern_tag}
              </span>
            )}
          </div>
          {agent && <span className="text-[10px] text-gray-500 mt-0.5">Reviewing agent: <span className={isLight ? 'text-gray-700' : 'text-gray-300'}>{agent}</span></span>}
        </div>
        {sessionId && onNavigate && (
          <button
            onClick={() => onNavigate(`/sessions/conversation/${sessionId}`)}
            className={`text-[10px] underline shrink-0 ${isLight ? 'text-amber-700 hover:text-amber-900' : 'text-amber-500/70 hover:text-amber-300'} transition`}
          >
            View session &rarr;
          </button>
        )}
      </div>

      <div className="p-4">
        {/* Score + Assessment row */}
        <div className="flex items-center gap-5 mb-5">
          <ScoreRing score={alignment_score} />
          <div className="flex-1 min-w-0">
            <p className="text-[10px] uppercase tracking-wider mb-1 text-gray-500">Alignment Score</p>
            <p className={`text-sm font-semibold ${isLight ? 'text-gray-900' : 'text-white'}`}>{scoreLabel}</p>
            {assessment && (
              <p className={`text-xs mt-1 ${isLight ? 'text-amber-800' : 'text-amber-300/80'}`}>{assessment}</p>
            )}
          </div>
        </div>

        {/* Relevant Beliefs */}
        {relevant_beliefs.length > 0 && (
          <div className="mb-4">
            <p className="text-[10px] uppercase tracking-wider mb-2 text-gray-500">Codex Signals</p>
            <div className="space-y-1.5">
              {Object.entries(sectionsByType).map(([section, beliefs]) => {
                const Icon = sectionIcons[section] || MessageSquare;
                const label = sectionLabels[section] || section;
                return beliefs.map((b, bi) => (
                  <div key={`${section}-${bi}`} className={`flex items-start gap-2 px-3 py-2 rounded ${isLight ? 'bg-white/70' : 'bg-black/20'}`}>
                    <Icon size={12} className={`mt-0.5 shrink-0 ${isLight ? 'text-amber-600' : 'text-amber-500/60'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className={`text-[10px] uppercase ${isLight ? 'text-amber-700' : 'text-amber-500/70'}`}>{label}</span>
                      </div>
                      <p className={`text-[11px] leading-relaxed ${isLight ? 'text-gray-700' : 'text-gray-300'}`}>{b.belief}</p>
                      <div className="mt-1">
                        <ConfidenceBar confidence={b.confidence} isLight={isLight} />
                      </div>
                    </div>
                  </div>
                ));
              })}
            </div>
          </div>
        )}

        {/* Feedback */}
        {feedback && (
          <div className="mb-4">
            <p className="text-[10px] uppercase tracking-wider mb-2 text-gray-500">Feedback</p>
            <div className={`text-[12px] leading-relaxed ${isLight ? 'text-gray-700' : 'text-gray-300'}`}>
              {feedback.split('\n\n').map((para, i) => (
                <p key={i} className={i > 0 ? 'mt-2' : ''}>{renderMarkdownBold(para, isLight)}</p>
              ))}
            </div>
          </div>
        )}

        {/* Suggested Improvement */}
        {suggested_improvement && (
          <div className="mb-4">
            <p className="text-[10px] uppercase tracking-wider mb-2 text-gray-500">Suggested Improvement</p>
            <div className={`rounded-md px-3 py-2.5 border-l-2 ${isLight ? 'bg-emerald-50 border-l-emerald-400 text-gray-700' : 'bg-emerald-950/20 border-l-emerald-500/50 text-gray-300'}`}>
              <div className="text-[12px] leading-relaxed">
                {suggested_improvement.split('\n\n').map((para, i) => (
                  <p key={i} className={i > 0 ? 'mt-2' : ''}>{renderMarkdownBold(para, isLight)}</p>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Reasoning (collapsible) */}
        {reasoning && (
          <div>
            <button
              onClick={() => setShowReasoning(!showReasoning)}
              className={`flex items-center gap-1.5 text-[10px] uppercase tracking-wider transition ${isLight ? 'text-gray-500 hover:text-gray-700' : 'text-gray-500 hover:text-gray-300'}`}
            >
              {showReasoning ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Scoring Rationale
            </button>
            {showReasoning && (
              <div className={`mt-2 text-[12px] leading-relaxed ${isLight ? 'text-gray-600' : 'text-gray-400'}`}>
                {reasoning.split('\n\n').map((para, i) => (
                  <p key={i} className={i > 0 ? 'mt-2' : ''}>{renderMarkdownBold(para, isLight)}</p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

/** Parse TooToo alignment feedback from a text block (handles malformed JSON). */
export const parseTooTooFeedback = (text) => {
  if (!text || !text.includes('alignment_score')) return null;
  const match = text.match(/```json\s*\n([\s\S]*?)\n```/);
  if (!match) return null;
  const raw = match[1];

  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed.alignment_score === 'number' && parsed.assessment) return parsed;
  } catch { /* lenient fallback */ }

  try {
    const fields = [
      'action_id', 'agent', 'alignment_score', 'relevant_beliefs',
      'assessment', 'feedback', 'reasoning', 'suggested_improvement', 'pattern_tag',
    ];
    const positions = [];
    for (const f of fields) {
      const idx = raw.indexOf(`\n  "${f}"`);
      if (idx !== -1) positions.push({ name: f, pos: idx });
    }
    positions.sort((a, b) => a.pos - b.pos);

    const result = {};
    for (let i = 0; i < positions.length; i++) {
      const { name, pos } = positions[i];
      const colonIdx = raw.indexOf(':', pos);
      if (colonIdx === -1) continue;
      const nextPos = i + 1 < positions.length ? positions[i + 1].pos : raw.lastIndexOf('}');
      let val = raw.slice(colonIdx + 1, nextPos).trim();
      if (val.endsWith(',')) val = val.slice(0, -1).trim();

      if (name === 'alignment_score') {
        result[name] = parseFloat(val);
      } else if (name === 'relevant_beliefs') {
        try { result[name] = JSON.parse(val); } catch { result[name] = []; }
      } else {
        if (val.startsWith('"')) val = val.slice(1);
        if (val.endsWith('"')) val = val.slice(0, -1);
        result[name] = val.replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\\\/g, '\\');
      }
    }
    if (typeof result.alignment_score === 'number' && result.assessment) return result;
  } catch { /* give up */ }
  return null;
};
