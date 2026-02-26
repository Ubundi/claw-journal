import React, { useEffect, useState } from 'react';
import { AreaChart, Area, BarChart, Bar, ScatterChart, Scatter, CartesianGrid, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';
import { HelpCircle } from 'lucide-react';
import axios from 'axios';

const Dashboard = ({ theme = 'dark', currency = 'USD', conversionRate = 1 }) => {
  const [data, setData] = useState(null);
  const [legacyData, setLegacyData] = useState(null);
  const [modelCatalog, setModelCatalog] = useState({ available_models: [], used_models: [] });
  const [connectionInfo, setConnectionInfo] = useState(null);
  const [pricingSortBy, setPricingSortBy] = useState('input_per_million');
  const [pricingSortDir, setPricingSortDir] = useState('desc');
  const [pricingProviderScope, setPricingProviderScope] = useState('top_labs');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [explorerTab, setExplorerTab] = useState('raw-events');
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [sessionEventsData, setSessionEventsData] = useState({ rows: [] });
  const [sessionEventsLoading, setSessionEventsLoading] = useState(false);
  const [sessionEventsError, setSessionEventsError] = useState('');
  const [snapshotData, setSnapshotData] = useState({ rows: [] });
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState('');
  const [logsExplorerData, setLogsExplorerData] = useState(null);
  const [logsExplorerLoading, setLogsExplorerLoading] = useState(false);
  const [logsExplorerError, setLogsExplorerError] = useState('');
  const [forecast, setForecast] = useState(null);
  const [activeKpiTooltip, setActiveKpiTooltip] = useState('');
  const [connectionNotice, setConnectionNotice] = useState(null);

  const fxRate = Number(conversionRate || 1) > 0 ? Number(conversionRate) : 1;

  const convertUsd = (value) => Number(value || 0) * fxRate;

  const formatMoney = (value, minFraction = 2, maxFraction = 2) => {
    const numeric = convertUsd(value);
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: minFraction,
      maximumFractionDigits: maxFraction,
    }).format(numeric);
  };

  const formatIsoOrDash = (value) => {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  };

  const formatEpochMsOrDash = (value) => {
    const number = Number(value || 0);
    if (!number) return '-';
    const date = new Date(number);
    if (Number.isNaN(date.getTime())) return String(value || '-');
    return date.toLocaleString();
  };

  const deriveConnectionNotice = (info) => {
    const notice = info?.runtime?.update_notice;
    if (notice && notice.message) {
      return {
        level: notice.level || 'warning',
        title: notice.title || 'Connection Issue',
        message: notice.message,
      };
    }

    if (info?.runtime?.sync_lock_active) {
      return {
        level: 'warning',
        title: 'Update In Progress',
        message: 'A sync/deploy lock is active. A brief disconnect may occur while services restart.',
      };
    }

    return null;
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [
        dashboardResponse,
        sessionsResponse,
        reconciledResponse,
        dailyResponse,
        costSourcesResponse,
        profileResponse,
        modelsResponse,
        connectionResponse,
        forecastResponse,
      ] = await Promise.all([
        axios.get('/api/dashboard-data'),
        axios.get('/api/usage/sessions?limit=20'),
        axios.get('/api/usage/reconciled?limit=20'),
        axios.get('/api/usage/daily?days=30'),
        axios.get('/api/usage/cost-sources'),
        axios.get('/api/system/profile'),
        axios.get('/api/system/models'),
        axios.get('/api/system/connection'),
        axios.get('/api/usage/forecast'),
      ]);

      setData(dashboardResponse.data);
      setModelCatalog(modelsResponse.data || { available_models: [], used_models: [] });
      setConnectionInfo(connectionResponse.data || null);
      setConnectionNotice(deriveConnectionNotice(connectionResponse.data || null));
      setForecast(forecastResponse.data || null);
      setLegacyData({
        sessions: sessionsResponse.data?.rows || [],
        reconciled: reconciledResponse.data?.rows || [],
        daily: dailyResponse.data?.rows || [],
        costSources: costSourcesResponse.data?.rows || {},
        profile: profileResponse.data || {}
      });
    } catch (err) {
      console.error(err);
      setError("Failed to load dashboard data. Ensure backend is running.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    const onRefresh = () => {
      fetchData();
    };
    window.addEventListener('cj:refresh', onRefresh);
    window.addEventListener('cj:rescan', onRefresh);
    return () => {
      window.removeEventListener('cj:refresh', onRefresh);
      window.removeEventListener('cj:rescan', onRefresh);
    };
  }, []);

  useEffect(() => {
    const sessionIds = (legacyData?.reconciled || []).map((row) => row.session_id).filter(Boolean);
    if (!selectedSessionId && sessionIds.length > 0) {
      setSelectedSessionId(sessionIds[0]);
    }
  }, [legacyData, selectedSessionId]);

  useEffect(() => {
    const loadTabData = async () => {
      if (explorerTab === 'raw-events' && selectedSessionId) {
        try {
          setSessionEventsLoading(true);
          setSessionEventsError('');
          const response = await axios.get(`/api/usage/session/${encodeURIComponent(selectedSessionId)}?limit=120`);
          setSessionEventsData(response.data || { rows: [] });
        } catch (err) {
          console.error(err);
          setSessionEventsError('Failed to load session events.');
        } finally {
          setSessionEventsLoading(false);
        }
      }

      if (explorerTab === 'snapshots' && snapshotData.rows.length === 0 && !snapshotLoading) {
        try {
          setSnapshotLoading(true);
          setSnapshotError('');
          const response = await axios.get('/api/system/session-snapshots?limit=50');
          setSnapshotData(response.data || { rows: [] });
        } catch (err) {
          console.error(err);
          setSnapshotError('Failed to load session snapshots.');
        } finally {
          setSnapshotLoading(false);
        }
      }

      if ((explorerTab === 'log-files' || explorerTab === 'diagnostics') && !logsExplorerData && !logsExplorerLoading) {
        try {
          setLogsExplorerLoading(true);
          setLogsExplorerError('');
          const response = await axios.get('/api/system/logs-explorer?file_limit=12&tail_lines=60');
          setLogsExplorerData(response.data || null);
        } catch (err) {
          console.error(err);
          setLogsExplorerError('Failed to load log explorer diagnostics.');
        } finally {
          setLogsExplorerLoading(false);
        }
      }
    };

    loadTabData();
  }, [explorerTab, selectedSessionId, snapshotData.rows.length, snapshotLoading, logsExplorerData, logsExplorerLoading]);

  useEffect(() => {
    let cancelled = false;

    const pollConnection = async () => {
      try {
        const response = await axios.get('/api/system/connection');
        if (cancelled) return;
        const payload = response.data || null;
        setConnectionInfo(payload);
        setConnectionNotice(deriveConnectionNotice(payload));
      } catch (_error) {
        if (cancelled) return;
        setConnectionNotice({
          level: 'error',
          title: 'Connection Issue',
          message: 'Dashboard lost connection to the backend. If a deploy/restart is in progress, wait briefly and reconnect your SSH tunnel if needed.',
        });
      }
    };

    const intervalId = window.setInterval(pollConnection, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  if (loading) return <div className={`${theme === 'light' ? 'bg-white text-orange-600' : 'bg-[#0a0a0a] text-orange-500'} min-h-screen p-10`}>Loading data...</div>;
  if (error) return <div className="bg-[#0a0a0a] min-h-screen text-red-500 p-10">{error} <button onClick={fetchData} className="underline ml-4">Retry</button></div>;
  if (!data) return null;

  const profile = legacyData?.profile || {};
  const billingMode = profile.billing_mode || 'token';
  const showCostColumns = billingMode !== 'claude_max';
  const cardSurfaceClass = theme === 'light' ? 'bg-gray-100 border-gray-300' : 'bg-[#141414] border-gray-900';
  const panelSurfaceClass = theme === 'light' ? 'bg-gray-50 border-gray-300' : 'bg-[#111111] border-gray-900';
  const tableHeadClass = theme === 'light' ? 'bg-gray-100 text-gray-600 uppercase font-medium' : 'bg-[#1a1a1a] text-gray-500 uppercase font-medium';
  const tableBodyClass = theme === 'light' ? 'divide-y divide-gray-200' : 'divide-y divide-gray-900';
  const tableRowHoverClass = theme === 'light' ? 'hover:bg-gray-100 transition-colors' : 'hover:bg-[#1a1a1a] transition-colors';
  const runtimePillClass = theme === 'light'
    ? 'text-[11px] border rounded px-2 py-[2px] bg-orange-50 text-orange-800 border-orange-200'
    : 'text-[11px] border rounded px-2 py-[2px] bg-orange-900/20 text-orange-200 border-orange-800/70';
  const runtimeInfoButtonClass = `${runtimePillClass} inline-flex items-center gap-1`;
  const runtimeTooltipPanelClass = 'absolute left-0 top-full mt-1 z-20 min-w-[18rem] max-w-[26rem] text-[11px] leading-snug bg-[#101010] border border-gray-700 rounded px-3 py-2 text-gray-200 shadow-lg';
  const logsPreClass = `text-[11px] font-mono whitespace-pre-wrap break-words ${theme === 'light' ? 'text-gray-800' : 'text-gray-300'}`;
  const sessionOptions = (legacyData?.reconciled || []).map((row) => row.session_id).filter(Boolean);
  const availableModels = Array.isArray(modelCatalog?.available_models) ? modelCatalog.available_models : [];

  const topLabPrefixes = ['openai/', 'google/', 'meta-llama/', 'z-ai/', 'anthropic/'];
  const isTopLabModel = (row) => {
    const id = String(row?.id || row?.model || '').toLowerCase();
    return topLabPrefixes.some((prefix) => id.startsWith(prefix));
  };

  const visibleModels = pricingProviderScope === 'top_labs'
    ? availableModels.filter(isTopLabModel)
    : availableModels;

  const sortedModels = [...visibleModels].sort((left, right) => {
    if (pricingSortBy === 'model') {
      const leftValue = String(left.model || left.id || '').toLowerCase();
      const rightValue = String(right.model || right.id || '').toLowerCase();
      return pricingSortDir === 'asc'
        ? leftValue.localeCompare(rightValue)
        : rightValue.localeCompare(leftValue);
    }

    if (pricingSortBy === 'context_length') {
      const leftValue = Number(left.context_length || 0);
      const rightValue = Number(right.context_length || 0);
      return pricingSortDir === 'asc' ? leftValue - rightValue : rightValue - leftValue;
    }

    const leftValue = Number(left[pricingSortBy] || 0);
    const rightValue = Number(right[pricingSortBy] || 0);
    return pricingSortDir === 'asc' ? leftValue - rightValue : rightValue - leftValue;
  });

  const providerMap = new Map();
  for (const row of sortedModels) {
    const provider = String(row.provider || 'unknown');
    const list = providerMap.get(provider) || [];
    list.push(row);
    providerMap.set(provider, list);
  }

  const providerGroups = [...providerMap.entries()]
    .map(([provider, rows]) => ({
      provider,
      rows,
      usedCount: rows.filter((row) => row.used_by_openclaw).length,
    }))
    .sort((left, right) => left.provider.localeCompare(right.provider));

  const pricingScatterData = sortedModels
    .filter((row) => {
      const modelId = String(row.id || row.model || '').toLowerCase();
      return !modelId.includes('o1-pro');
    })
    .map((row) => {
      const input = Number(row.input_per_million || 0);
      const output = Number(row.output_per_million || 0);
      const cacheRaw = Number(row.cache_per_million || 0);
      const cacheWindowRaw = Number(row.cache_window_tokens || 0);
      const blended = (0.75 * input) + (0.25 * output);
      const cache = cacheRaw > 0 ? cacheRaw : input;
      const cacheWindowTokens = cacheWindowRaw > 0 ? cacheWindowRaw : Number(row.context_length || 0);
      return {
        id: row.id || `${row.provider || 'unknown'}/${row.model || 'unknown'}`,
        model: row.model || row.id || 'unknown',
        provider: row.provider || 'unknown',
        input,
        output,
        cache,
        cacheWindowTokens,
        blended,
        hasCache: cacheRaw > 0,
        hasCacheWindow: cacheWindowRaw > 0,
        used: Boolean(row.used_by_openclaw),
      };
    })
    .filter((row) => (row.input > 0 || row.output > 0) && row.cacheWindowTokens > 0);

  const inputOutputPlotData = pricingScatterData.map((row) => ({
    ...row,
    x: row.input,
    y: row.output,
  }));

  const cacheBlendedPlotData = pricingScatterData.map((row) => ({
    ...row,
    x: row.cacheWindowTokens,
    y: row.blended,
  }));

  const costTrendData = Array.isArray(data.costTrend)
    ? data.costTrend.map((row) => ({
      ...row,
      cost: Number(row?.cost || 0),
      cost_display: convertUsd(row?.cost || 0),
    }))
    : [];

  const costTrendCeiling = Math.max(...costTrendData.map((row) => Number(row.cost_display || 0)), 0);

  const toIsoDay = (value) => {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 10) || '-';
    return date.toISOString().slice(0, 10);
  };

  const formatConversationLabel = (sessionKey, lastActive, fallback = 'Unknown') => {
    const raw = String(sessionKey || '').trim();
    if (!raw) {
      return `${fallback} · default · ${toIsoDay(lastActive)}`;
    }

    if (raw.startsWith('agent:')) {
      const parts = raw.split(':');
      const agent = (parts[1] || fallback).replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
      const stream = (parts.slice(2).join(':') || 'default').replace(/_/g, ' ');
      return `${agent} · ${stream} · ${toIsoDay(lastActive)}`;
    }

    return `${raw} · default · ${toIsoDay(lastActive)}`;
  };

  const costByAgentRaw = Array.isArray(data?.costByAgent) ? data.costByAgent : [];
  const costByAgentLabels = new Set(
    costByAgentRaw.map((row) => String(row?.name || '').trim().toLowerCase()).filter(Boolean),
  );
  const needsLabelEnrichment = costByAgentRaw.length > 0 && costByAgentLabels.size <= 1;

  const recentSessionsByCost = Array.isArray(data?.recentSessions)
    ? [...data.recentSessions]
      .map((row) => ({
        ...row,
        numericCost: Number(row?.cost || 0),
      }))
      .sort((left, right) => right.numericCost - left.numericCost)
    : [];

  const costByAgentData = costByAgentRaw.map((row, index) => {
    const fallbackSession = recentSessionsByCost[index];
    const isGeneric = ['main', 'unknown', 'agent'].includes(String(row?.name || '').trim().toLowerCase());
    const shouldUseFallback = needsLabelEnrichment || isGeneric;

    const label = shouldUseFallback && fallbackSession
      ? formatConversationLabel(fallbackSession.sessionKey, fallbackSession.lastActive, fallbackSession.agent || row?.name || 'Unknown')
      : String(row?.name || `Conversation ${index + 1}`);

    return {
      ...row,
      name: label,
      cost_display: convertUsd(row?.cost || 0),
    };
  });

  const userPromptsByDayData = Array.isArray(data?.userPromptsByDay)
    ? data.userPromptsByDay.map((row) => ({
      ...row,
      day: String(row?.date || '').slice(5),
      count: Number(row?.count || 0),
    }))
    : [];

  const kpiDescription = (key) => {
    const normalized = String(key || '').toLowerCase();
    if (normalized.includes('spend')) return 'Sum of session costs in USD for the selected window.';
    if (normalized.includes('token')) return 'Sum of input and output tokens parsed from usage logs.';
    if (normalized.includes('session')) return 'Count of unique session IDs observed in ingested logs.';
    if (normalized.includes('message')) return 'Count of message events captured from transcripts/logs.';
    if (normalized.includes('avg')) return 'Arithmetic mean across the corresponding KPI in the current window.';
    if (normalized.includes('cost')) return 'Cost value aggregated from observed and estimated usage entries.';
    return 'Calculated from ingested OpenClaw usage events for the current dashboard window.';
  };

  const summaryKpis = data.summary
    ? Object.entries(data.summary).filter(([key]) => !String(key).toLowerCase().includes('cache'))
    : [];

  const dailyRows = Array.isArray(legacyData?.daily)
    ? [...legacyData.daily].sort((left, right) => String(left.usage_date || '').localeCompare(String(right.usage_date || '')))
    : [];
  const latestDay = dailyRows.length > 0 ? dailyRows[dailyRows.length - 1] : null;
  const previousDay = dailyRows.length > 1 ? dailyRows[dailyRows.length - 2] : null;

  const totalTokensForDay = (row) => {
    if (!row) return 0;
    const total = Number(row.total_tokens || 0);
    if (total > 0) return total;
    return Number(row.input_tokens || 0) + Number(row.output_tokens || 0);
  };

  const tokenSparklineData = dailyRows.slice(-10).map((row) => ({
    date: String(row?.usage_date || '').slice(5),
    value: totalTokensForDay(row),
  }));

  const costSparklineData = costTrendData.slice(-10).map((row) => ({
    date: String(row?.date || '').slice(5),
    value: Number(row?.cost_display || 0),
  }));

  const pricingTooltip = ({ active, payload }) => {
    if (!active || !payload || payload.length === 0) return null;
    const point = payload[0]?.payload;
    if (!point) return null;

    return (
      <div className="bg-[#101010] border border-gray-700 rounded px-3 py-2 text-[11px] text-gray-200 shadow-lg">
        <p className="text-white font-semibold">{point.model}</p>
        <p className="text-gray-400">provider: {point.provider}</p>
        <p>input: {formatMoney(point.input, 4, 4)} / 1M</p>
        <p>output: {formatMoney(point.output, 4, 4)} / 1M</p>
        <p>cache: {formatMoney(point.cache, 4, 4)} / 1M {point.hasCache ? '' : '(fallback=input)'}</p>
        <p>cache window: {Number(point.cacheWindowTokens || 0).toLocaleString()} tokens {point.hasCacheWindow ? '' : '(fallback=context)'}</p>
        <p>blended (75/25): {formatMoney(point.blended, 4, 4)} / 1M</p>
        {point.used && <p className="text-orange-400">Used on instance</p>}
      </div>
    );
  };

  const toggleRuntimeTooltip = (key) => {
    setActiveKpiTooltip((prev) => (prev === key ? '' : key));
  };

  return (
    <div className={`relative min-h-screen p-6 overflow-hidden ${theme === 'light' ? 'bg-white text-gray-900' : 'bg-[#0a0a0a] text-gray-300'}`}>
      <div className="pointer-events-none absolute inset-0">
        <div className="dashboard-glow dashboard-glow-primary" />
        <div className="dashboard-glow dashboard-glow-secondary" />
      </div>

      <div className="relative z-10">
      {connectionNotice && (
        <div className={`mb-4 border rounded p-4 ${connectionNotice.level === 'error'
          ? (theme === 'light' ? 'bg-red-50 border-red-200 text-red-800' : 'bg-red-900/25 border-red-800 text-red-200')
          : (theme === 'light' ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-amber-900/25 border-amber-800 text-amber-200')}`}>
          <p className="text-base font-bold uppercase tracking-wide">{connectionNotice.title}</p>
          <p className="text-sm mt-1">{connectionNotice.message}</p>
        </div>
      )}
      <div id="overview" className={`${cardSurfaceClass} p-4 rounded border mb-6 scroll-mt-24 relative`}>
        <div className="flex flex-nowrap items-center gap-2 whitespace-nowrap pb-1 overflow-visible">
          <p className={`text-sm font-semibold mr-1 whitespace-nowrap ${theme === 'light' ? 'text-gray-900' : 'text-white'}`}>Runtime Mode</p>
          {/* Runtime pills are currently informational only.
              Enabling selection requires service + API refactors (for example, updating the auto-sync lock, runtime profile persistence, and remote sync guards). */}
          <div className="relative inline-flex">
            <button type="button" className={runtimeInfoButtonClass} onClick={() => toggleRuntimeTooltip('runtime:llm')}>
              LLM: {profile.auth_mode || 'unknown'}
              <HelpCircle size={12} />
            </button>
            {activeKpiTooltip === 'runtime:llm' && (
              <div className={runtimeTooltipPanelClass}>Current model-access auth mode used by this instance. `oauth` means provider-managed auth flows.</div>
            )}
          </div>
          <div className="relative inline-flex">
            <button type="button" className={runtimeInfoButtonClass} onClick={() => toggleRuntimeTooltip('runtime:billing')}>
              Billing: {profile.billing_mode || 'unknown'}
              <HelpCircle size={12} />
            </button>
            {activeKpiTooltip === 'runtime:billing' && (
              <div className={runtimeTooltipPanelClass}>Active billing interpretation mode for dashboard cost calculations.</div>
            )}
          </div>
          {billingMode === 'claude_max' && (
            <div className="relative inline-flex">
              <button type="button" className={runtimeInfoButtonClass} onClick={() => toggleRuntimeTooltip('runtime:plan')}>
                Plan: {formatMoney(profile.claude_max_monthly_usd || 0, 2, 2)}/mo
                <HelpCircle size={12} />
              </button>
              {activeKpiTooltip === 'runtime:plan' && (
                <div className={runtimeTooltipPanelClass}>Configured Claude Max monthly plan amount used for subscription-aware cost context.</div>
              )}
            </div>
          )}
          <div className="relative inline-flex">
            <button type="button" className={runtimeInfoButtonClass} onClick={() => toggleRuntimeTooltip('runtime:host')}>
              Host: Adiis-Mac-mini.localdomain
              <HelpCircle size={12} />
            </button>
            {activeKpiTooltip === 'runtime:host' && (
              <div className={runtimeTooltipPanelClass}>Hostname where Claw Journal runtime and cron sync jobs are running.</div>
            )}
          </div>
          <div className="relative inline-flex">
            <button
              type="button"
              className={runtimeInfoButtonClass}
              onClick={() => toggleRuntimeTooltip('runtime:token-counting')}
            >
              Token Counting
              <HelpCircle size={12} />
            </button>
            {activeKpiTooltip === 'runtime:token-counting' && (
              <div className={runtimeTooltipPanelClass}>
                <p className="mb-1">Tokens are counted from provider/OpenClaw usage fields (input + output, plus context/cache when present).</p>
                <p className="mb-1">Other planned counting options are shown below, but not selectable yet.</p>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-gray-400">Value:</span>
                  <select disabled value="provider-reported" className="bg-[#151515] border border-gray-700 rounded px-2 py-[2px] text-[11px] disabled:opacity-100">
                    <option value="provider-reported">Provider-Reported (Current)</option>
                    <option value="retokenized">Re-Tokenized (Planned)</option>
                    <option value="hybrid">Hybrid (Planned)</option>
                  </select>
                </div>
                <p className="text-gray-400">Cross-model totals reflect provider-reported usage, not one universal tokenizer.</p>
              </div>
            )}
          </div>
          <div className="relative inline-flex">
            <button
              type="button"
              className={runtimeInfoButtonClass}
              onClick={() => toggleRuntimeTooltip('runtime:glossary')}
            >
              Glossary
              <HelpCircle size={12} />
            </button>
            {activeKpiTooltip === 'runtime:glossary' && (
              <div className={runtimeTooltipPanelClass}>
                <p><strong>Agent:</strong> Runtime identity (for example `main` or a subagent) inferred from session key.</p>
                <p><strong>Conversation:</strong> Channel/thread stream inside an agent (for example `whatsapp:dm:+number` or `cron:job-id`).</p>
                <p><strong>Session:</strong> A unique `session_id` timeline.</p>
                <p><strong>Message:</strong> One transcript event row (`user`, `assistant`, `tool`, or `system`).</p>
                <p><strong>Token:</strong> Provider-reported model usage unit, usually split into input and output tokens.</p>
              </div>
            )}
          </div>
          <div className="relative inline-flex">
            <button
              type="button"
              className={runtimeInfoButtonClass}
              onClick={() => toggleRuntimeTooltip('runtime:code-sync')}
            >
              Code Sync from GitHub: {formatIsoOrDash(connectionInfo?.runtime?.sync_last_run_at)}
              {connectionInfo?.runtime?.sync_last_run_message ? ` · ${connectionInfo.runtime.sync_last_run_message}` : ''}
              <HelpCircle size={12} />
            </button>
            {activeKpiTooltip === 'runtime:code-sync' && (
              <div className={runtimeTooltipPanelClass}>
                Code sync reflects the latest run of the host cron deploy task (`sync-claw-journal.sh`). It checks `origin/main`, pulls new commits when present, restarts services if needed, and logs whether it deployed, skipped, or recovered from lock contention.
              </div>
            )}
          </div>
          <div className="relative inline-flex">
            <button type="button" className={runtimeInfoButtonClass} onClick={() => toggleRuntimeTooltip('runtime:auto-sync-lock')}>
              Auto-Sync Lock: {connectionInfo?.runtime?.sync_lock_active ? `active (${connectionInfo?.runtime?.sync_lock_age_seconds ?? 0}s)` : 'not active.'}
              <HelpCircle size={12} />
            </button>
            {activeKpiTooltip === 'runtime:auto-sync-lock' && (
              <div className={runtimeTooltipPanelClass}>Lock that prevents overlapping cron sync/deploy runs. Active usually means an update or health-recovery cycle is running.</div>
            )}
          </div>
        </div>
      </div>

      <div id="usage-summary" className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6 scroll-mt-24">
        <div className={`${cardSurfaceClass} p-3 border rounded relative flex flex-col`}>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase text-gray-500 mb-1">Tokens Today</p>
            <button
              type="button"
              className="text-gray-500 hover:text-orange-400"
              title="Total input + output tokens for the latest usage date in daily aggregates."
              aria-label="How Tokens Today is calculated"
              onMouseEnter={() => setActiveKpiTooltip('summary:tokens-today')}
              onMouseLeave={() => setActiveKpiTooltip((prev) => (prev === 'summary:tokens-today' ? '' : prev))}
              onFocus={() => setActiveKpiTooltip('summary:tokens-today')}
              onBlur={() => setActiveKpiTooltip((prev) => (prev === 'summary:tokens-today' ? '' : prev))}
            >
              <HelpCircle size={13} />
            </button>
          </div>
          {activeKpiTooltip === 'summary:tokens-today' && (
            <div className="absolute right-2 top-7 z-20 max-w-[16rem] text-[11px] leading-snug bg-[#101010] border border-gray-700 rounded px-2 py-1 text-gray-200 shadow-lg">
              Total input + output tokens for the latest usage date in daily aggregates.
            </div>
          )}
          <p className="mt-auto text-[2rem] leading-none font-bold text-orange-500">{totalTokensForDay(latestDay).toLocaleString()}</p>
        </div>
        <div className={`${cardSurfaceClass} p-3 border rounded relative`}>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase text-gray-500 mb-1">Tokens Previous Day</p>
            <button
              type="button"
              className="text-gray-500 hover:text-orange-400"
              title="Total input + output tokens for the previous day before the latest usage date."
              aria-label="How Tokens Previous Day is calculated"
              onMouseEnter={() => setActiveKpiTooltip('summary:tokens-previous-day')}
              onMouseLeave={() => setActiveKpiTooltip((prev) => (prev === 'summary:tokens-previous-day' ? '' : prev))}
              onFocus={() => setActiveKpiTooltip('summary:tokens-previous-day')}
              onBlur={() => setActiveKpiTooltip((prev) => (prev === 'summary:tokens-previous-day' ? '' : prev))}
            >
              <HelpCircle size={13} />
            </button>
          </div>
          {activeKpiTooltip === 'summary:tokens-previous-day' && (
            <div className="absolute right-2 top-7 z-20 max-w-[16rem] text-[11px] leading-snug bg-[#101010] border border-gray-700 rounded px-2 py-1 text-gray-200 shadow-lg">
              Total input + output tokens for the previous day before the latest usage date.
            </div>
          )}
          <p className="text-lg font-bold text-orange-500">{totalTokensForDay(previousDay).toLocaleString()}</p>
          <div className="h-12 mt-2">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={tokenSparklineData}>
                <defs>
                  <linearGradient id="kpiPrevTokenSparklineFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f97316" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#f97316" stopOpacity={0.04} />
                  </linearGradient>
                </defs>
                <Area type="monotone" dataKey="value" stroke="#fb923c" strokeWidth={1.5} fill="url(#kpiPrevTokenSparklineFill)" dot={false} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className={`${cardSurfaceClass} p-3 border rounded relative`}>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase text-gray-500 mb-1">Projected Monthly Spend</p>
            <button
              type="button"
              className="text-gray-500 hover:text-orange-400"
              title="Projected end-of-month cost based on average daily spend over the last 7 days."
              aria-label="How Projected Monthly Spend is calculated"
              onMouseEnter={() => setActiveKpiTooltip('summary:forecast')}
              onMouseLeave={() => setActiveKpiTooltip((prev) => (prev === 'summary:forecast' ? '' : prev))}
              onFocus={() => setActiveKpiTooltip('summary:forecast')}
              onBlur={() => setActiveKpiTooltip((prev) => (prev === 'summary:forecast' ? '' : prev))}
            >
              <HelpCircle size={13} />
            </button>
          </div>
          {activeKpiTooltip === 'summary:forecast' && (
            <div className="absolute right-2 top-7 z-20 max-w-[18rem] text-[11px] leading-snug bg-[#101010] border border-gray-700 rounded px-2 py-1 text-gray-200 shadow-lg">
              Month-to-date spend plus remaining days projected at your 7-day average daily cost.
              {forecast && forecast.days_with_data > 0 && (
                <> Avg {formatMoney(forecast.avg_daily_cost_usd, 2, 4)}/day over {forecast.days_with_data} days. Day {forecast.day_of_month}/{forecast.days_in_month}.</>
              )}
            </div>
          )}
          <p className="text-lg font-bold text-orange-500">
            {forecast && forecast.projected_monthly_usd > 0 ? formatMoney(forecast.projected_monthly_usd, 2, 2) : '-'}
          </p>
          {forecast && forecast.month_to_date_usd > 0 && (
            <p className="text-[10px] text-gray-500 mt-0.5">MTD: {formatMoney(forecast.month_to_date_usd, 2, 2)}</p>
          )}
          <div className="h-12 mt-2">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={costSparklineData}>
                <defs>
                  <linearGradient id="kpiCostSparklineFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f97316" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#f97316" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <Area type="monotone" dataKey="value" stroke="#f97316" strokeWidth={1.5} fill="url(#kpiCostSparklineFill)" dot={false} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 mb-8" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        {summaryKpis.map(([key, val]) => (
          <div key={key} className={`${cardSurfaceClass} p-3 border rounded shadow-sm relative`}>
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] uppercase text-gray-500 mb-1">{key.replace(/([A-Z])/g, ' $1')}</p>
              <button
                type="button"
                className="text-gray-500 hover:text-orange-400"
                onMouseEnter={() => setActiveKpiTooltip(`summary:${key}`)}
                onMouseLeave={() => setActiveKpiTooltip((prev) => (prev === `summary:${key}` ? '' : prev))}
                onFocus={() => setActiveKpiTooltip(`summary:${key}`)}
                onBlur={() => setActiveKpiTooltip((prev) => (prev === `summary:${key}` ? '' : prev))}
                aria-label={`How ${key.replace(/([A-Z])/g, ' $1')} is calculated`}
              >
                <HelpCircle size={13} />
              </button>
            </div>
            {activeKpiTooltip === `summary:${key}` && (
              <div className="absolute right-2 top-7 z-20 max-w-[16rem] text-[11px] leading-snug bg-[#101010] border border-gray-700 rounded px-2 py-1 text-gray-200 shadow-lg">
                {kpiDescription(key)}
              </div>
            )}
            <p className="text-lg font-bold text-orange-500">{typeof val === 'number' && (key.toLowerCase().includes('spend') || key.toLowerCase().includes('avg') || key.toLowerCase().includes('cost')) ? formatMoney(val, 2, 4) : val}</p>
          </div>
        ))}
      </div>

      {/* Charts Row 1 */}
      <div id="analytics" className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6 scroll-mt-24">
        <div className={`md:col-span-2 ${cardSurfaceClass} p-4 rounded border`}>
          <h3 className="text-xs uppercase mb-4 text-gray-500">Cost by Day</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={costTrendData}>
                <defs>
                  <linearGradient id="costGradientFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f97316" stopOpacity={0.9} />
                    <stop offset="60%" stopColor="#f97316" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#f97316" stopOpacity={0.2} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis
                  stroke="#444"
                  fontSize={10}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, Math.max(costTrendCeiling * 1.2, 0.01)]}
                  tickFormatter={(val) => formatMoney(val, 0, 2)}
                />
                <Tooltip contentStyle={{backgroundColor: '#111', border: '1px solid #333', color: '#fff'}} itemStyle={{color: '#f97316'}} />
                <Area type="monotone" dataKey="cost_display" baseValue={0} stroke="#f97316" strokeWidth={2} fill="url(#costGradientFill)" fillOpacity={1} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className={`${cardSurfaceClass} p-4 rounded border flex flex-col justify-center`}>
          <h3 className="text-xs uppercase mb-4 text-gray-500">Cost Trend</h3>
          <div className="space-y-6">
             <div>
                <p className="text-xs text-gray-500 mb-1">TODAY</p>
                  <p className={`text-3xl font-bold ${theme === 'light' ? 'text-gray-900' : 'text-white'}`}>{formatMoney(costTrendData.length > 0 ? costTrendData[costTrendData.length - 1].cost : 0, 2, 2)}</p>
             </div>
             <div className="h-[2px] bg-gradient-to-r from-orange-500 to-transparent w-full opacity-50"></div>
             <div>
                <p className="text-xs text-gray-500 mb-1">7D TOTAL</p>
                  <p className={`text-3xl font-bold ${theme === 'light' ? 'text-gray-900' : 'text-white'}`}>{formatMoney(data?.summary?.totalSpend || 0, 2, 2)}</p>
             </div>
          </div>
        </div>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div className={`${cardSurfaceClass} p-4 rounded border`}>
          <h3 className="text-xs uppercase mb-1 text-gray-500">Cost by Conversation Stream</h3>
          <p className="text-[10px] text-gray-500 mb-3">Label format: agent · conversation · latest date</p>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart layout="vertical" data={costByAgentData} margin={{top: 0, right: 30, left: 40, bottom: 0}}>
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" stroke="#666" fontSize={10} width={220} tick={{fill: '#888'}} axisLine={false} tickLine={false} />
                <Tooltip cursor={{fill: 'transparent'}} contentStyle={{backgroundColor: '#111', border: '1px solid #333', color: '#fff'}} />
                <Bar dataKey="cost_display" fill="#f97316" radius={[0, 4, 4, 0]} barSize={20} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className={`${cardSurfaceClass} p-4 rounded border`}>
          <h3 className="text-xs uppercase mb-4 text-gray-500">User Prompts Per Day (Last 7 Days)</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={userPromptsByDayData} margin={{ top: 0, right: 8, left: 8, bottom: 0 }}>
                <defs>
                  <linearGradient id="userPromptsBarGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#fb923c" />
                    <stop offset="100%" stopColor="#ea580c" />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" stroke="#666" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis allowDecimals={false} stroke="#666" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip cursor={{ fill: 'transparent' }} contentStyle={{ backgroundColor: '#111', border: '1px solid #333', color: '#fff' }} />
                <Bar dataKey="count" fill="url(#userPromptsBarGradient)" radius={[4, 4, 0, 0]} barSize={22} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Recent Sessions Table */}
      <div id="recent-sessions" className={`${cardSurfaceClass} rounded border overflow-hidden scroll-mt-24`}>
        <div className="p-4 border-b border-gray-900">
            <h3 className="text-xs uppercase text-gray-500">Recent Sessions</h3>
        </div>
        <div className="overflow-x-auto">
            <table className={`w-full text-left text-xs ${theme === 'light' ? 'text-gray-700' : 'text-gray-400'}`}>
              <thead className={tableHeadClass}>
                    <tr>
                        <th className="px-4 py-3">Agent</th>
                        <th className="px-4 py-3">Session Key</th>
                        <th className="px-4 py-3 text-right">Msgs</th>
                        <th className="px-4 py-3 text-right">Cost</th>
                        <th className="px-4 py-3 text-right">Tokens</th>
                        <th className="px-4 py-3 text-right">Last Active</th>
                    </tr>
                </thead>
                <tbody className={tableBodyClass}>
                    {data.recentSessions && data.recentSessions.map((session, i) => (
                    <tr key={i} className={tableRowHoverClass}>
                      <td className={`px-4 py-3 font-bold ${theme === 'light' ? 'text-gray-900' : 'text-white'}`}>{session.agent}</td>
                            <td className="px-4 py-3 font-mono text-[10px] text-gray-500 truncate max-w-[200px]">{session.sessionKey}</td>
                            <td className="px-4 py-3 text-right">{session.msgs}</td>
                            <td className="px-4 py-3 text-right text-orange-500">{formatMoney(typeof session.cost === 'number' ? session.cost : 0, 2, 2)}</td>
                            <td className="px-4 py-3 text-right">{session.tokens}</td>
                            <td className="px-4 py-3 text-right text-gray-600">{new Date(session.lastActive).toLocaleString()}</td>
                        </tr>
                    ))}
                    {(!data.recentSessions || data.recentSessions.length === 0) && (
                        <tr>
                            <td colSpan={6} className="px-4 py-8 text-center text-gray-600 italic">No recent sessions found.</td>
                        </tr>
                    )}
                </tbody>
            </table>
        </div>
      </div>

      <div id="operations" className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-6 scroll-mt-24">
        <div className={`${cardSurfaceClass} rounded border overflow-hidden flex flex-col h-[24rem]`}>
          <div className="p-4 border-b border-gray-900">
            <h3 className="text-xs uppercase text-gray-500">Session Usage (Logs)</h3>
            {!legacyData?.sessions?.length && (
              <p className="text-xs text-gray-600 mt-2">No usage data detected yet.</p>
            )}
          </div>
          <div className="overflow-auto flex-1">
            <table className={`w-full text-left text-xs ${theme === 'light' ? 'text-gray-700' : 'text-gray-400'}`}>
              <thead className={tableHeadClass}>
                <tr>
                  <th className="px-4 py-3">Session</th>
                  <th className="px-4 py-3">Provider</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3 text-right">Tokens</th>
                  {showCostColumns && <th className="px-4 py-3 text-right">Input Cost</th>}
                  {showCostColumns && <th className="px-4 py-3 text-right">Output Cost</th>}
                  {showCostColumns && <th className="px-4 py-3 text-right">Total Cost</th>}
                </tr>
              </thead>
              <tbody className={tableBodyClass}>
                {(legacyData?.sessions || []).map((row) => (
                  <tr key={`${row.session_id}-${row.model || 'unknown'}`} className={tableRowHoverClass}>
                    <td className={`px-4 py-3 ${theme === 'light' ? 'text-gray-800' : 'text-gray-300'}`}>{row.session_id || '-'}</td>
                    <td className="px-4 py-3">{row.provider || '-'}</td>
                    <td className="px-4 py-3">{row.model || '-'}</td>
                    <td className="px-4 py-3 text-right">{row.total_tokens || 0}</td>
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{formatMoney(row.input_cost_usd, 6, 6)}</td>}
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{formatMoney(row.output_cost_usd, 6, 6)}</td>}
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{formatMoney(row.cost_usd, 6, 6)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className={`${cardSurfaceClass} rounded border overflow-hidden flex flex-col h-[24rem]`}>
          <div className="p-4 border-b border-gray-900">
            <h3 className="text-xs uppercase text-gray-500">Reconciled Sessions</h3>
          </div>
          <div className="overflow-auto flex-1">
            <table className={`w-full text-left text-xs ${theme === 'light' ? 'text-gray-700' : 'text-gray-400'}`}>
              <thead className={tableHeadClass}>
                <tr>
                  <th className="px-4 py-3">Session</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3 text-right">Total Tokens</th>
                  <th className="px-4 py-3 text-right">Observed Cost</th>
                </tr>
              </thead>
              <tbody className={tableBodyClass}>
                {(legacyData?.reconciled || []).map((row) => (
                  <tr key={`${row.session_id}-${row.model || 'unknown'}`} className={tableRowHoverClass}>
                    <td className={`px-4 py-3 ${theme === 'light' ? 'text-gray-800' : 'text-gray-300'}`}>{row.session_id || '-'}</td>
                    <td className="px-4 py-3">{row.model || '-'}</td>
                    <td className="px-4 py-3 text-right">{row.total_tokens || 0}</td>
                    <td className="px-4 py-3 text-right text-orange-500">{formatMoney(row.observed_cost_usd, 6, 6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className={`${cardSurfaceClass} rounded border overflow-hidden xl:col-span-2`}>
          <div className="p-4 border-b border-gray-900">
            <h3 className="text-xs uppercase text-gray-500">Daily Usage</h3>
          </div>
          <div className="overflow-x-auto">
            <table className={`w-full text-left text-xs ${theme === 'light' ? 'text-gray-700' : 'text-gray-400'}`}>
              <thead className={tableHeadClass}>
                <tr>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3 text-right">Input</th>
                  <th className="px-4 py-3 text-right">Output</th>
                  <th className="px-4 py-3 text-right">Total</th>
                  {showCostColumns && <th className="px-4 py-3 text-right">Input Cost</th>}
                  {showCostColumns && <th className="px-4 py-3 text-right">Output Cost</th>}
                  {showCostColumns && <th className="px-4 py-3 text-right">Total Cost</th>}
                </tr>
              </thead>
              <tbody className={tableBodyClass}>
                {(legacyData?.daily || []).map((row) => (
                  <tr key={row.usage_date} className={tableRowHoverClass}>
                    <td className={`px-4 py-3 ${theme === 'light' ? 'text-gray-800' : 'text-gray-300'}`}>{row.usage_date || '-'}</td>
                    <td className="px-4 py-3 text-right">{row.input_tokens || 0}</td>
                    <td className="px-4 py-3 text-right">{row.output_tokens || 0}</td>
                    <td className="px-4 py-3 text-right">{row.total_tokens || 0}</td>
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{formatMoney(row.input_cost_usd, 6, 6)}</td>}
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{formatMoney(row.output_cost_usd, 6, 6)}</td>}
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{formatMoney(row.cost_usd, 6, 6)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div id="pricing" className={`${cardSurfaceClass} rounded border p-4 xl:col-span-2 scroll-mt-24`}>
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h3 className="text-xs uppercase text-gray-500">OpenRouter Pricing Catalog</h3>
            <div className="flex items-center gap-2">
              <label htmlFor="pricing-provider-filter" className="sr-only">Filter pricing providers</label>
              <select
                id="pricing-provider-filter"
                name="pricing_provider_filter"
                value={pricingProviderScope}
                onChange={(event) => setPricingProviderScope(event.target.value)}
                className={`${theme === 'light' ? 'bg-white border-gray-300 text-gray-800' : 'bg-[#1a1a1a] border-gray-800 text-gray-200'} border rounded px-2 py-1 text-xs`}
              >
                <option value="top_labs">Top Labs</option>
                <option value="all">All Providers</option>
              </select>
              <label htmlFor="pricing-sort-select" className="sr-only">Sort pricing models</label>
              <select
                id="pricing-sort-select"
                name="pricing_sort"
                value={pricingSortBy}
                onChange={(event) => setPricingSortBy(event.target.value)}
                className={`${theme === 'light' ? 'bg-white border-gray-300 text-gray-800' : 'bg-[#1a1a1a] border-gray-800 text-gray-200'} border rounded px-2 py-1 text-xs`}
              >
                <option value="input_per_million">Sort: Input Price</option>
                <option value="output_per_million">Sort: Output Price</option>
                <option value="context_length">Sort: Context Length</option>
                <option value="model">Sort: Model Name</option>
              </select>
              <button
                onClick={() => setPricingSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'))}
                className={`${theme === 'light' ? 'bg-white border-gray-300 text-gray-800 hover:bg-gray-100' : 'bg-[#1a1a1a] border-gray-800 text-white hover:bg-gray-800'} border px-2 py-1 rounded text-xs transition`}
              >
                {pricingSortDir === 'asc' ? 'Asc' : 'Desc'}
              </button>
            </div>
          </div>

          <p className="text-xs text-gray-500 mb-3">
            Models shown: {visibleModels.length} of {availableModels.length} · used on this instance: {visibleModels.filter((row) => row.used_by_openclaw).length}
          </p>

          {pricingScatterData.length > 0 && (
            <>
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
                <div className={`${panelSurfaceClass} rounded p-3 border`}>
                  <p className="text-[11px] text-gray-500 mb-2 uppercase">Input vs Output Price</p>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                        <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
                        <XAxis type="number" dataKey="x" name="Input" stroke="#666" tick={{ fill: '#888', fontSize: 10 }} tickFormatter={(value) => formatMoney(value, 2, 2)} />
                        <YAxis type="number" dataKey="y" name="Output" stroke="#666" tick={{ fill: '#888', fontSize: 10 }} tickFormatter={(value) => formatMoney(value, 2, 2)} />
                        <Tooltip content={pricingTooltip} cursor={{ stroke: '#555' }} />
                        <Scatter data={inputOutputPlotData} fill="rgba(249, 115, 22, 0.3)" fillOpacity={0.5} />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className={`${panelSurfaceClass} rounded p-3 border`}>
                  <p className="text-[11px] text-gray-500 mb-1 uppercase">Cache vs Blended Rate</p>
                  <p className="text-[10px] text-gray-600 mb-2">Blended Rate = (0.75 × Input Price) + (0.25 × Output Price)</p>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                        <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
                        <XAxis type="number" dataKey="x" name="Cache Window Tokens" stroke="#666" tick={{ fill: '#888', fontSize: 10 }} tickFormatter={(value) => Number(value).toLocaleString()} />
                        <YAxis type="number" dataKey="y" name="Blended" stroke="#666" tick={{ fill: '#888', fontSize: 10 }} tickFormatter={(value) => formatMoney(value, 2, 2)} />
                        <Tooltip content={pricingTooltip} cursor={{ stroke: '#555' }} />
                        <Scatter data={cacheBlendedPlotData} fill="rgba(251, 146, 60, 0.3)" fillOpacity={0.5} />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </>
          )}

          {providerGroups.length === 0 && (
            <p className="text-xs text-gray-600">No OpenRouter catalog loaded yet. Enable startup sync or refresh pricing import.</p>
          )}

          <div className="space-y-3 max-h-[34rem] overflow-y-auto pr-1">
            {providerGroups.map((group) => (
              <details key={group.provider} open={group.usedCount > 0} className={`${panelSurfaceClass} rounded border`}>
                <summary className="cursor-pointer px-3 py-2 text-xs text-gray-300 flex items-center justify-between gap-2">
                  <span className={theme === 'light' ? 'text-gray-800' : ''}>{group.provider}</span>
                  <span className="text-gray-500">{group.rows.length} models · used {group.usedCount}</span>
                </summary>
                <div className="overflow-x-auto">
                  <table className={`w-full text-left text-xs ${theme === 'light' ? 'text-gray-700' : 'text-gray-400'}`}>
                    <thead className={theme === 'light' ? 'bg-gray-100 text-gray-600 uppercase font-medium' : 'bg-[#161616] text-gray-500 uppercase font-medium'}>
                      <tr>
                        <th className="px-3 py-2">Model</th>
                        <th className="px-3 py-2 text-right">Input / 1M</th>
                        <th className="px-3 py-2 text-right">Output / 1M</th>
                        <th className="px-3 py-2 text-right">Context</th>
                        <th className="px-3 py-2">Usage</th>
                      </tr>
                    </thead>
                    <tbody className={tableBodyClass}>
                      {group.rows.map((row) => (
                        <tr
                          key={row.id || `${row.provider}/${row.model}`}
                          className={row.used_by_openclaw
                            ? (theme === 'light' ? 'bg-orange-100' : 'bg-[#1f1608]')
                            : (theme === 'light' ? 'hover:bg-gray-100' : 'hover:bg-[#1a1a1a]')}
                        >
                          <td className={`px-3 py-2 ${theme === 'light' ? 'text-gray-800' : 'text-gray-300'}`}>{row.model || row.id || '-'}</td>
                          <td className="px-3 py-2 text-right">{formatMoney(row.input_per_million || 0, 4, 4)}</td>
                          <td className="px-3 py-2 text-right">{formatMoney(row.output_per_million || 0, 4, 4)}</td>
                          <td className="px-3 py-2 text-right">{Number(row.context_length || 0).toLocaleString()}</td>
                          <td className="px-3 py-2">
                            {row.used_by_openclaw
                              ? <span className="text-orange-400">Used on instance</span>
                              : <span className="text-gray-600">Not used</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            ))}
          </div>
        </div>

        <div id="explorer" className={`${cardSurfaceClass} rounded border p-4 xl:col-span-2 scroll-mt-24`}>
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h3 className="text-xs uppercase text-gray-500">Remote Logs Explorer</h3>
            <button
              onClick={() => {
                if (explorerTab === 'raw-events' && selectedSessionId) {
                  setSessionEventsData({ rows: [] });
                }
                if (explorerTab === 'snapshots') {
                  setSnapshotData({ rows: [] });
                }
                if (explorerTab === 'log-files' || explorerTab === 'diagnostics') {
                  setLogsExplorerData(null);
                }
              }}
              className={`${theme === 'light' ? 'bg-white border-gray-300 text-gray-800 hover:bg-gray-100' : 'bg-[#1a1a1a] border-gray-800 text-white hover:bg-gray-800'} border px-3 py-1 rounded text-xs transition`}
            >
              Refresh Tab
            </button>
          </div>

          <div className="flex flex-wrap gap-2 mb-4">
            {[
              { id: 'raw-events', label: 'Raw Session Events' },
              { id: 'snapshots', label: 'Session Snapshots' },
              { id: 'log-files', label: 'Log Files Tail' },
              { id: 'diagnostics', label: 'Diagnostics' }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setExplorerTab(tab.id)}
                className={`px-3 py-1 rounded text-xs border transition ${
                  explorerTab === tab.id
                    ? (theme === 'light' ? 'bg-orange-100 border-orange-300 text-orange-700' : 'bg-[#1f1f1f] border-gray-700 text-orange-400')
                    : (theme === 'light' ? 'bg-white border-gray-300 text-gray-700 hover:bg-gray-100' : 'bg-[#111111] border-gray-800 text-gray-400 hover:bg-[#1a1a1a]')
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {explorerTab === 'raw-events' && (
            <div>
              <div className="flex flex-wrap items-center gap-3 mb-3">
                <label htmlFor="raw-events-session-select" className="text-xs text-gray-500">Session</label>
                <select
                  id="raw-events-session-select"
                  name="raw_events_session"
                  value={selectedSessionId}
                  onChange={(event) => setSelectedSessionId(event.target.value)}
                  className={`${theme === 'light' ? 'bg-white border-gray-300 text-gray-800' : 'bg-[#1a1a1a] border-gray-800 text-gray-200'} border rounded px-3 py-1 text-xs`}
                >
                  {sessionOptions.length === 0 && <option value="">No reconciled sessions</option>}
                  {sessionOptions.map((sessionId) => (
                    <option key={sessionId} value={sessionId}>{sessionId}</option>
                  ))}
                </select>
              </div>

              {sessionEventsLoading && <p className="text-xs text-gray-500">Loading raw session events...</p>}
              {sessionEventsError && <p className="text-xs text-red-400">{sessionEventsError}</p>}

              {!sessionEventsLoading && !sessionEventsError && (
                <div className="space-y-3 max-h-[28rem] overflow-y-auto pr-1">
                  {(sessionEventsData.rows || []).map((row, index) => (
                    <div key={`${row.event_ts || 'na'}-${index}`} className={`${panelSurfaceClass} rounded p-3 border`}>
                      <p className="text-[11px] text-gray-500 mb-2">
                        {formatIsoOrDash(row.event_ts)} · {row.event_type || '-'} · tokens={row.total_tokens || 0} · source={row.cost_source || '-'}
                      </p>
                      <pre className={logsPreClass}>{row.raw_json || '-'}</pre>
                    </div>
                  ))}
                  {(sessionEventsData.rows || []).length === 0 && (
                    <p className="text-xs text-gray-600">No raw usage events found for this session.</p>
                  )}
                </div>
              )}
            </div>
          )}

          {explorerTab === 'snapshots' && (
            <div>
              {snapshotLoading && <p className="text-xs text-gray-500">Loading session snapshots...</p>}
              {snapshotError && <p className="text-xs text-red-400">{snapshotError}</p>}

              {!snapshotLoading && !snapshotError && (
                <div className="overflow-x-auto">
                  <table className={`w-full text-left text-xs ${theme === 'light' ? 'text-gray-700' : 'text-gray-400'}`}>
                    <thead className={tableHeadClass}>
                      <tr>
                        <th className="px-3 py-2">Session</th>
                        <th className="px-3 py-2">Provider</th>
                        <th className="px-3 py-2">Model</th>
                        <th className="px-3 py-2 text-right">Total Tokens</th>
                        <th className="px-3 py-2 text-right">Updated</th>
                        <th className="px-3 py-2">Raw Snapshot</th>
                      </tr>
                    </thead>
                    <tbody className={tableBodyClass}>
                      {(snapshotData.rows || []).map((row) => (
                        <tr key={row.session_id} className={`${tableRowHoverClass} align-top`}>
                          <td className={`px-3 py-2 ${theme === 'light' ? 'text-gray-800' : 'text-gray-300'}`}>{row.session_id || '-'}</td>
                          <td className="px-3 py-2">{row.provider || '-'}</td>
                          <td className="px-3 py-2">{row.model || '-'}</td>
                          <td className="px-3 py-2 text-right">{row.total_tokens || 0}</td>
                          <td className="px-3 py-2 text-right">{formatEpochMsOrDash(row.updated_at)}</td>
                          <td className="px-3 py-2">
                            <details>
                              <summary className="cursor-pointer text-orange-400">View</summary>
                              <pre className={`${logsPreClass} mt-2`}>{row.raw_json || '-'}</pre>
                            </details>
                          </td>
                        </tr>
                      ))}
                      {(snapshotData.rows || []).length === 0 && (
                        <tr>
                          <td colSpan={6} className="px-3 py-6 text-center text-gray-600 italic">No session snapshots found.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {explorerTab === 'log-files' && (
            <div>
              {logsExplorerLoading && <p className="text-xs text-gray-500">Loading log files...</p>}
              {logsExplorerError && <p className="text-xs text-red-400">{logsExplorerError}</p>}

              {!logsExplorerLoading && !logsExplorerError && logsExplorerData && (
                <div>
                  <p className="text-xs text-gray-500 mb-3">
                    Glob: {logsExplorerData.log_glob} · matched: {logsExplorerData.matched_files} · returned: {logsExplorerData.returned_files} · tail lines: {logsExplorerData.tail_lines}
                  </p>
                  <div className="space-y-4 max-h-[32rem] overflow-y-auto pr-1">
                    {(logsExplorerData.files || []).map((file) => (
                      <div key={file.path} className={`${panelSurfaceClass} rounded p-3 border`}>
                        <p className="text-[11px] text-gray-400 break-all">{file.path}</p>
                        <p className="text-[11px] text-gray-600 mt-1">
                          size={file.size_bytes} bytes · modified={formatIsoOrDash(file.modified_at)} · checkpoint={file.checkpoint?.cursor ?? 'none'}
                        </p>
                        <pre className={`${logsPreClass} mt-2 max-h-64 overflow-y-auto`}>{(file.tail_lines || []).join('\n') || '(No lines)'}</pre>
                      </div>
                    ))}
                    {(logsExplorerData.files || []).length === 0 && (
                      <p className="text-xs text-gray-600">No files matched the configured log glob.</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {explorerTab === 'diagnostics' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className={`${panelSurfaceClass} rounded p-3 border`}>
                <p className="text-xs text-gray-500 mb-2 uppercase">Data Status</p>
                <pre className={logsPreClass}>{JSON.stringify(profile.data_status || {}, null, 2)}</pre>
              </div>
              <div className={`${panelSurfaceClass} rounded p-3 border`}>
                <p className="text-xs text-gray-500 mb-2 uppercase">Cost Sources</p>
                <pre className={logsPreClass}>{JSON.stringify(costSources || {}, null, 2)}</pre>
              </div>
              <div className={`${panelSurfaceClass} rounded p-3 border md:col-span-2`}>
                <p className="text-xs text-gray-500 mb-2 uppercase">Connection</p>
                <pre className={logsPreClass}>{JSON.stringify(connectionInfo || {}, null, 2)}</pre>
              </div>
              <div className={`${panelSurfaceClass} rounded p-3 border md:col-span-2`}>
                <p className="text-xs text-gray-500 mb-2 uppercase">Ingest + File Diagnostics</p>
                {logsExplorerLoading && <p className="text-xs text-gray-500">Loading diagnostics...</p>}
                {logsExplorerError && <p className="text-xs text-red-400">{logsExplorerError}</p>}
                {!logsExplorerLoading && !logsExplorerError && (
                  <pre className={logsPreClass}>{JSON.stringify(logsExplorerData || {}, null, 2)}</pre>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      </div>
    </div>
  );
};

export default Dashboard;
