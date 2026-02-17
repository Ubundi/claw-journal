import React, { useEffect, useState } from 'react';
import { LineChart, Line, Area, BarChart, Bar, ScatterChart, Scatter, CartesianGrid, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';
import { Compass, Database, HelpCircle, LineChart as LineChartIcon } from 'lucide-react';
import axios from 'axios';

const Dashboard = ({ theme = 'dark' }) => {
  const [data, setData] = useState(null);
  const [legacyData, setLegacyData] = useState(null);
  const [modelCatalog, setModelCatalog] = useState({ available_models: [], used_models: [] });
  const [connectionInfo, setConnectionInfo] = useState(null);
  const [pricingSortBy, setPricingSortBy] = useState('input_per_million');
  const [pricingSortDir, setPricingSortDir] = useState('desc');
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

  const money = (value) => {
    const number = Number(value || 0);
    return `$${number.toFixed(6)}`;
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
      ] = await Promise.all([
        axios.get('/api/dashboard-data'),
        axios.get('/api/usage/sessions?limit=20'),
        axios.get('/api/usage/reconciled?limit=20'),
        axios.get('/api/usage/daily?days=30'),
        axios.get('/api/usage/cost-sources'),
        axios.get('/api/system/profile'),
        axios.get('/api/system/models'),
        axios.get('/api/system/connection')
      ]);

      setData(dashboardResponse.data);
      setModelCatalog(modelsResponse.data || { available_models: [], used_models: [] });
      setConnectionInfo(connectionResponse.data || null);
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
    const onRescan = () => {
      fetchData();
    };
    window.addEventListener('cj:rescan', onRescan);
    return () => window.removeEventListener('cj:rescan', onRescan);
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

  if (loading) return <div className="bg-[#0a0a0a] min-h-screen text-orange-500 p-10 font-mono">Loading data...</div>;
  if (error) return <div className="bg-[#0a0a0a] min-h-screen text-red-500 p-10 font-mono">{error} <button onClick={fetchData} className="underline ml-4">Retry</button></div>;
  if (!data) return null;

  const profile = legacyData?.profile || {};
  const costSources = legacyData?.costSources || {};
  const notes = Array.isArray(profile.notes) ? profile.notes.join(' ') : '';
  const billingMode = profile.billing_mode || 'token';
  const showCostColumns = billingMode !== 'claude_max';
  const sessionOptions = (legacyData?.reconciled || []).map((row) => row.session_id).filter(Boolean);
  const availableModels = Array.isArray(modelCatalog?.available_models) ? modelCatalog.available_models : [];

  const sortedModels = [...availableModels].sort((left, right) => {
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

  const pricingTooltip = ({ active, payload }) => {
    if (!active || !payload || payload.length === 0) return null;
    const point = payload[0]?.payload;
    if (!point) return null;

    return (
      <div className="bg-[#101010] border border-gray-700 rounded px-3 py-2 text-[11px] text-gray-200 shadow-lg">
        <p className="text-white font-semibold">{point.model}</p>
        <p className="text-gray-400">provider: {point.provider}</p>
        <p>input: ${point.input.toFixed(4)} / 1M</p>
        <p>output: ${point.output.toFixed(4)} / 1M</p>
        <p>cache: ${point.cache.toFixed(4)} / 1M {point.hasCache ? '' : '(fallback=input)'}</p>
        <p>cache window: {Number(point.cacheWindowTokens || 0).toLocaleString()} tokens {point.hasCacheWindow ? '' : '(fallback=context)'}</p>
        <p>blended (75/25): ${point.blended.toFixed(4)} / 1M</p>
        {point.used && <p className="text-orange-400">Used on instance</p>}
      </div>
    );
  };

  const costTrendData = Array.isArray(data.costTrend)
    ? data.costTrend.map((row) => ({
      ...row,
      cost: Number(row?.cost || 0),
    }))
    : [];

  const costTrendCeiling = Math.max(...costTrendData.map((row) => Number(row.cost || 0)), 0);

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

  return (
    <div className={`relative min-h-screen p-6 font-mono overflow-hidden ${theme === 'light' ? 'bg-white text-gray-900' : 'bg-[#0a0a0a] text-gray-300'}`}>
      <div className="pointer-events-none absolute inset-0">
        <div className="dashboard-glow dashboard-glow-primary" />
        <div className="dashboard-glow dashboard-glow-secondary" />
      </div>

      <div className="relative z-10">
      <div id="overview" className="bg-[#141414] p-4 rounded border border-gray-900 mb-6 scroll-mt-24">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-white font-semibold">Runtime Mode</p>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-[11px] uppercase border rounded px-2 py-[2px] ${String(profile.auth_mode || 'unknown').toLowerCase() === 'oauth' ? 'bg-blue-900/40 text-blue-300 border-blue-800' : 'bg-orange-900/40 text-orange-300 border-orange-800'}`}>
              auth: {profile.auth_mode || 'unknown'}
            </span>
            <span className={`text-[11px] uppercase border rounded px-2 py-[2px] ${String(profile.billing_mode || 'unknown').toLowerCase() === 'claude_max' ? 'bg-purple-900/40 text-purple-300 border-purple-800' : 'bg-emerald-900/40 text-emerald-300 border-emerald-800'}`}>
              billing: {profile.billing_mode || 'unknown'}
            </span>
            {billingMode === 'claude_max' && (
              <span className="text-[11px] uppercase border rounded px-2 py-[2px] bg-purple-900/30 text-purple-300 border-purple-800">
                plan: ${profile.claude_max_monthly_usd || 0}/mo
              </span>
            )}
          </div>
        </div>
        {notes && <p className="text-xs text-gray-500 mt-1">{notes}</p>}
        <p className="text-xs text-gray-500 mt-2">
          Local: {connectionInfo?.local?.user || '-'}@{connectionInfo?.local?.hostname || '-'} ({connectionInfo?.local?.ip || 'n/a'})
        </p>
        <p className="text-xs text-gray-500 mt-1">
          Remote: {connectionInfo?.remote?.ssh_user ? `${connectionInfo.remote.ssh_user}@` : ''}{connectionInfo?.remote?.ssh_host || '-'}
          {connectionInfo?.remote?.ssh_host_ip ? ` (${connectionInfo.remote.ssh_host_ip})` : ''} · mode={connectionInfo?.remote?.ingest_mode || '-'} · sync={String(connectionInfo?.remote?.session_sync_enabled ?? false)}
        </p>
      </div>

      <div id="usage-summary" className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-8 scroll-mt-24">
        <div className="bg-[#141414] p-3 border border-gray-900 rounded">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase text-gray-500 mb-1">Observed</p>
            <button type="button" className="text-gray-500 hover:text-orange-400" title="Count of sessions with directly observed provider cost from logs.">
              <HelpCircle size={13} />
            </button>
          </div>
          <p className="text-lg font-bold text-orange-500">{costSources.observed || 0}</p>
        </div>
        <div className="bg-[#141414] p-3 border border-gray-900 rounded">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase text-gray-500 mb-1">Estimated</p>
            <button type="button" className="text-gray-500 hover:text-orange-400" title="Count of sessions where cost was estimated from token totals and pricing table.">
              <HelpCircle size={13} />
            </button>
          </div>
          <p className="text-lg font-bold text-orange-500">{costSources.estimated || 0}</p>
        </div>
        <div className="bg-[#141414] p-3 border border-gray-900 rounded">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase text-gray-500 mb-1">Missing</p>
            <button type="button" className="text-gray-500 hover:text-orange-400" title="Count of sessions with no observed or estimable cost.">
              <HelpCircle size={13} />
            </button>
          </div>
          <p className="text-lg font-bold text-orange-500">{costSources.missing || 0}</p>
        </div>
        <div className="bg-[#141414] p-3 border border-gray-900 rounded">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase text-gray-500 mb-1">Subscription</p>
            <button type="button" className="text-gray-500 hover:text-orange-400" title="Count of sessions attributed to subscription-inclusive billing mode.">
              <HelpCircle size={13} />
            </button>
          </div>
          <p className="text-lg font-bold text-orange-500">{costSources.subscription || 0}</p>
        </div>
        <div className="bg-[#141414] p-3 border border-gray-900 rounded">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase text-gray-500 mb-1">Tokens Today</p>
            <button type="button" className="text-gray-500 hover:text-orange-400" title="Total input + output tokens for the latest usage date in daily aggregates.">
              <HelpCircle size={13} />
            </button>
          </div>
          <p className="text-lg font-bold text-orange-500">{totalTokensForDay(latestDay).toLocaleString()}</p>
        </div>
        <div className="bg-[#141414] p-3 border border-gray-900 rounded">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase text-gray-500 mb-1">Tokens Prev Day</p>
            <button type="button" className="text-gray-500 hover:text-orange-400" title="Total input + output tokens for the day prior to the latest usage date.">
              <HelpCircle size={13} />
            </button>
          </div>
          <p className="text-lg font-bold text-orange-500">{totalTokensForDay(previousDay).toLocaleString()}</p>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4 mb-8">
        {summaryKpis.map(([key, val]) => (
          <div key={key} className="bg-[#141414] p-3 border border-gray-900 rounded shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] uppercase text-gray-500 mb-1">{key.replace(/([A-Z])/g, ' $1')}</p>
              <button type="button" className="text-gray-500 hover:text-orange-400" title={kpiDescription(key)}>
                <HelpCircle size={13} />
              </button>
            </div>
            <p className="text-lg font-bold text-orange-500">{typeof val === 'number' && key.toLowerCase().includes('spend') ? `$${val}` : typeof val === 'number' && key.toLowerCase().includes('avg') ? `$${val}` : val}</p>
          </div>
        ))}
      </div>

      {/* Charts Row 1 */}
      <div id="analytics" className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6 scroll-mt-24">
        <div className="md:col-span-2 bg-[#141414] p-4 rounded border border-gray-900">
          <h3 className="text-xs uppercase mb-4 text-gray-500">Cost by Day</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={costTrendData}>
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
                  tickFormatter={(val) => `$${val}`}
                />
                <Tooltip contentStyle={{backgroundColor: '#111', border: '1px solid #333', color: '#fff'}} itemStyle={{color: '#f97316'}} />
                <Area type="monotone" dataKey="cost" baseValue={0} stroke="none" fill="url(#costGradientFill)" fillOpacity={1} />
                <Line type="monotone" dataKey="cost" stroke="#f97316" strokeWidth={2} dot={false} activeDot={{r: 4, strokeWidth: 0}} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[#141414] p-4 rounded border border-gray-900 flex flex-col justify-center">
          <h3 className="text-xs uppercase mb-4 text-gray-500">Cost Trend</h3>
          <div className="space-y-6">
             <div>
                <p className="text-xs text-gray-500 mb-1">TODAY</p>
                 <p className="text-3xl text-white font-bold">${costTrendData.length > 0 ? costTrendData[costTrendData.length - 1].cost : '0.00'}</p>
             </div>
             <div className="h-[2px] bg-gradient-to-r from-orange-500 to-transparent w-full opacity-50"></div>
             <div>
                <p className="text-xs text-gray-500 mb-1">7D TOTAL</p>
                <p className="text-3xl text-white font-bold">${data.summary.totalSpend}</p>
             </div>
          </div>
        </div>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div className="bg-[#141414] p-4 rounded border border-gray-900">
          <h3 className="text-xs uppercase mb-4 text-gray-500">Cost By Agent</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart layout="vertical" data={data.costByAgent} margin={{top: 0, right: 30, left: 40, bottom: 0}}>
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" stroke="#666" fontSize={11} width={80} tick={{fill: '#888'}} axisLine={false} tickLine={false} />
                <Tooltip cursor={{fill: 'transparent'}} contentStyle={{backgroundColor: '#111', border: '1px solid #333', color: '#fff'}} />
                <Bar dataKey="cost" fill="#f97316" radius={[0, 4, 4, 0]} barSize={20} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[#141414] p-4 rounded border border-gray-900">
          <h3 className="text-xs uppercase mb-4 text-gray-500">Top Tools</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart layout="vertical" data={data.topTools} margin={{top: 0, right: 30, left: 40, bottom: 0}}>
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" stroke="#666" fontSize={11} width={100} tick={{fill: '#888'}} axisLine={false} tickLine={false} />
                <Tooltip cursor={{fill: 'transparent'}} contentStyle={{backgroundColor: '#111', border: '1px solid #333', color: '#fff'}} />
                <Bar dataKey="count" fill="#ea580c" radius={[0, 4, 4, 0]} barSize={20} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Recent Sessions Table */}
      <div id="recent-sessions" className="bg-[#141414] rounded border border-gray-900 overflow-hidden scroll-mt-24">
        <div className="p-4 border-b border-gray-900">
            <h3 className="text-xs uppercase text-gray-500">Recent Sessions</h3>
        </div>
        <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-gray-400">
                <thead className="bg-[#1a1a1a] text-gray-500 uppercase font-medium">
                    <tr>
                        <th className="px-4 py-3">Agent</th>
                        <th className="px-4 py-3">Session Key</th>
                        <th className="px-4 py-3 text-right">Msgs</th>
                        <th className="px-4 py-3 text-right">Cost</th>
                        <th className="px-4 py-3 text-right">Tokens</th>
                        <th className="px-4 py-3 text-right">Last Active</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-gray-900">
                    {data.recentSessions && data.recentSessions.map((session, i) => (
                        <tr key={i} className="hover:bg-[#1a1a1a] transition-colors">
                            <td className="px-4 py-3 font-bold text-white">{session.agent}</td>
                            <td className="px-4 py-3 font-mono text-[10px] text-gray-500 truncate max-w-[200px]">{session.sessionKey}</td>
                            <td className="px-4 py-3 text-right">{session.msgs}</td>
                            <td className="px-4 py-3 text-right text-orange-500">${typeof session.cost === 'number' ? session.cost.toFixed(2) : session.cost}</td>
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
        <div className="bg-[#141414] rounded border border-gray-900 overflow-hidden flex flex-col h-[24rem]">
          <div className="p-4 border-b border-gray-900">
            <h3 className="text-xs uppercase text-gray-500">Session Usage (Logs)</h3>
            {!legacyData?.sessions?.length && (
              <p className="text-xs text-gray-600 mt-2">No usage data detected yet.</p>
            )}
          </div>
          <div className="overflow-auto flex-1">
            <table className="w-full text-left text-xs text-gray-400">
              <thead className="bg-[#1a1a1a] text-gray-500 uppercase font-medium">
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
              <tbody className="divide-y divide-gray-900">
                {(legacyData?.sessions || []).map((row) => (
                  <tr key={`${row.session_id}-${row.model || 'unknown'}`} className="hover:bg-[#1a1a1a] transition-colors">
                    <td className="px-4 py-3 text-gray-300">{row.session_id || '-'}</td>
                    <td className="px-4 py-3">{row.provider || '-'}</td>
                    <td className="px-4 py-3">{row.model || '-'}</td>
                    <td className="px-4 py-3 text-right">{row.total_tokens || 0}</td>
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{money(row.input_cost_usd)}</td>}
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{money(row.output_cost_usd)}</td>}
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{money(row.cost_usd)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-[#141414] rounded border border-gray-900 overflow-hidden flex flex-col h-[24rem]">
          <div className="p-4 border-b border-gray-900">
            <h3 className="text-xs uppercase text-gray-500">Reconciled Sessions</h3>
          </div>
          <div className="overflow-auto flex-1">
            <table className="w-full text-left text-xs text-gray-400">
              <thead className="bg-[#1a1a1a] text-gray-500 uppercase font-medium">
                <tr>
                  <th className="px-4 py-3">Session</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3 text-right">Total Tokens</th>
                  <th className="px-4 py-3 text-right">Observed Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-900">
                {(legacyData?.reconciled || []).map((row) => (
                  <tr key={`${row.session_id}-${row.model || 'unknown'}`} className="hover:bg-[#1a1a1a] transition-colors">
                    <td className="px-4 py-3 text-gray-300">{row.session_id || '-'}</td>
                    <td className="px-4 py-3">{row.model || '-'}</td>
                    <td className="px-4 py-3 text-right">{row.total_tokens || 0}</td>
                    <td className="px-4 py-3 text-right text-orange-500">{money(row.observed_cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-[#141414] rounded border border-gray-900 overflow-hidden xl:col-span-2">
          <div className="p-4 border-b border-gray-900">
            <h3 className="text-xs uppercase text-gray-500">Daily Usage</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-gray-400">
              <thead className="bg-[#1a1a1a] text-gray-500 uppercase font-medium">
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
              <tbody className="divide-y divide-gray-900">
                {(legacyData?.daily || []).map((row) => (
                  <tr key={row.usage_date} className="hover:bg-[#1a1a1a] transition-colors">
                    <td className="px-4 py-3 text-gray-300">{row.usage_date || '-'}</td>
                    <td className="px-4 py-3 text-right">{row.input_tokens || 0}</td>
                    <td className="px-4 py-3 text-right">{row.output_tokens || 0}</td>
                    <td className="px-4 py-3 text-right">{row.total_tokens || 0}</td>
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{money(row.input_cost_usd)}</td>}
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{money(row.output_cost_usd)}</td>}
                    {showCostColumns && <td className="px-4 py-3 text-right text-orange-500">{money(row.cost_usd)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div id="pricing" className="bg-[#141414] rounded border border-gray-900 p-4 xl:col-span-2 scroll-mt-24">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h3 className="text-xs uppercase text-gray-500">OpenRouter Pricing Catalog</h3>
            <div className="flex items-center gap-2">
              <select
                value={pricingSortBy}
                onChange={(event) => setPricingSortBy(event.target.value)}
                className="bg-[#1a1a1a] border border-gray-800 rounded px-2 py-1 text-xs text-gray-200"
              >
                <option value="input_per_million">Sort: Input Price</option>
                <option value="output_per_million">Sort: Output Price</option>
                <option value="context_length">Sort: Context Length</option>
                <option value="model">Sort: Model Name</option>
              </select>
              <button
                onClick={() => setPricingSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'))}
                className="bg-[#1a1a1a] border border-gray-800 px-2 py-1 rounded text-xs text-white hover:bg-gray-800 transition"
              >
                {pricingSortDir === 'asc' ? 'Asc' : 'Desc'}
              </button>
            </div>
          </div>

          <p className="text-xs text-gray-500 mb-3">
            Models from OpenRouter: {availableModels.length} · used on this instance: {availableModels.filter((row) => row.used_by_openclaw).length}
          </p>

          {pricingScatterData.length > 0 && (
            <>
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
                <div className="bg-[#111111] border border-gray-900 rounded p-3">
                  <p className="text-[11px] text-gray-500 mb-2 uppercase">Input vs Output Price</p>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                        <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
                        <XAxis type="number" dataKey="x" name="Input" stroke="#666" tick={{ fill: '#888', fontSize: 10 }} tickFormatter={(value) => `$${Number(value).toFixed(2)}`} />
                        <YAxis type="number" dataKey="y" name="Output" stroke="#666" tick={{ fill: '#888', fontSize: 10 }} tickFormatter={(value) => `$${Number(value).toFixed(2)}`} />
                        <Tooltip content={pricingTooltip} cursor={{ stroke: '#555' }} />
                        <Scatter data={inputOutputPlotData} fill="rgba(249, 115, 22, 0.3)" fillOpacity={0.5} />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="bg-[#111111] border border-gray-900 rounded p-3">
                  <p className="text-[11px] text-gray-500 mb-1 uppercase">Cache vs Blended Rate</p>
                  <p className="text-[10px] text-gray-600 mb-2">Blended Rate = (0.75 × Input Price) + (0.25 × Output Price)</p>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                        <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
                        <XAxis type="number" dataKey="x" name="Cache Window Tokens" stroke="#666" tick={{ fill: '#888', fontSize: 10 }} tickFormatter={(value) => Number(value).toLocaleString()} />
                        <YAxis type="number" dataKey="y" name="Blended" stroke="#666" tick={{ fill: '#888', fontSize: 10 }} tickFormatter={(value) => `$${Number(value).toFixed(2)}`} />
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
              <details key={group.provider} open={group.usedCount > 0} className="bg-[#111111] border border-gray-900 rounded">
                <summary className="cursor-pointer px-3 py-2 text-xs text-gray-300 flex items-center justify-between gap-2">
                  <span>{group.provider}</span>
                  <span className="text-gray-500">{group.rows.length} models · used {group.usedCount}</span>
                </summary>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs text-gray-400">
                    <thead className="bg-[#161616] text-gray-500 uppercase font-medium">
                      <tr>
                        <th className="px-3 py-2">Model</th>
                        <th className="px-3 py-2 text-right">Input / 1M</th>
                        <th className="px-3 py-2 text-right">Output / 1M</th>
                        <th className="px-3 py-2 text-right">Context</th>
                        <th className="px-3 py-2">Usage</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-900">
                      {group.rows.map((row) => (
                        <tr
                          key={row.id || `${row.provider}/${row.model}`}
                          className={row.used_by_openclaw ? 'bg-[#1f1608]' : 'hover:bg-[#1a1a1a]'}
                        >
                          <td className="px-3 py-2 text-gray-300">{row.model || row.id || '-'}</td>
                          <td className="px-3 py-2 text-right">${Number(row.input_per_million || 0).toFixed(4)}</td>
                          <td className="px-3 py-2 text-right">${Number(row.output_per_million || 0).toFixed(4)}</td>
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

        <div id="explorer" className="bg-[#141414] rounded border border-gray-900 p-4 xl:col-span-2 scroll-mt-24">
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
              className="bg-[#1a1a1a] border border-gray-800 px-3 py-1 rounded text-xs text-white hover:bg-gray-800 transition"
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
                    ? 'bg-[#1f1f1f] border-gray-700 text-orange-400'
                    : 'bg-[#111111] border-gray-800 text-gray-400 hover:bg-[#1a1a1a]'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {explorerTab === 'raw-events' && (
            <div>
              <div className="flex flex-wrap items-center gap-3 mb-3">
                <label className="text-xs text-gray-500">Session</label>
                <select
                  value={selectedSessionId}
                  onChange={(event) => setSelectedSessionId(event.target.value)}
                  className="bg-[#1a1a1a] border border-gray-800 rounded px-3 py-1 text-xs text-gray-200"
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
                    <div key={`${row.event_ts || 'na'}-${index}`} className="bg-[#111111] border border-gray-900 rounded p-3">
                      <p className="text-[11px] text-gray-500 mb-2">
                        {formatIsoOrDash(row.event_ts)} · {row.event_type || '-'} · tokens={row.total_tokens || 0} · source={row.cost_source || '-'}
                      </p>
                      <pre className="text-[11px] text-gray-300 whitespace-pre-wrap break-words">{row.raw_json || '-'}</pre>
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
                  <table className="w-full text-left text-xs text-gray-400">
                    <thead className="bg-[#1a1a1a] text-gray-500 uppercase font-medium">
                      <tr>
                        <th className="px-3 py-2">Session</th>
                        <th className="px-3 py-2">Provider</th>
                        <th className="px-3 py-2">Model</th>
                        <th className="px-3 py-2 text-right">Total Tokens</th>
                        <th className="px-3 py-2 text-right">Updated</th>
                        <th className="px-3 py-2">Raw Snapshot</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-900">
                      {(snapshotData.rows || []).map((row) => (
                        <tr key={row.session_id} className="hover:bg-[#1a1a1a] transition-colors align-top">
                          <td className="px-3 py-2 text-gray-300">{row.session_id || '-'}</td>
                          <td className="px-3 py-2">{row.provider || '-'}</td>
                          <td className="px-3 py-2">{row.model || '-'}</td>
                          <td className="px-3 py-2 text-right">{row.total_tokens || 0}</td>
                          <td className="px-3 py-2 text-right">{formatEpochMsOrDash(row.updated_at)}</td>
                          <td className="px-3 py-2">
                            <details>
                              <summary className="cursor-pointer text-orange-400">View</summary>
                              <pre className="text-[11px] text-gray-300 whitespace-pre-wrap break-words mt-2">{row.raw_json || '-'}</pre>
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
                      <div key={file.path} className="bg-[#111111] border border-gray-900 rounded p-3">
                        <p className="text-[11px] text-gray-400 break-all">{file.path}</p>
                        <p className="text-[11px] text-gray-600 mt-1">
                          size={file.size_bytes} bytes · modified={formatIsoOrDash(file.modified_at)} · checkpoint={file.checkpoint?.cursor ?? 'none'}
                        </p>
                        <pre className="mt-2 text-[11px] text-gray-300 whitespace-pre-wrap break-words max-h-64 overflow-y-auto">{(file.tail_lines || []).join('\n') || '(No lines)'}</pre>
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
              <div className="bg-[#111111] border border-gray-900 rounded p-3">
                <p className="text-xs text-gray-500 mb-2 uppercase">Data Status</p>
                <pre className="text-[11px] text-gray-300 whitespace-pre-wrap break-words">{JSON.stringify(profile.data_status || {}, null, 2)}</pre>
              </div>
              <div className="bg-[#111111] border border-gray-900 rounded p-3">
                <p className="text-xs text-gray-500 mb-2 uppercase">Cost Sources</p>
                <pre className="text-[11px] text-gray-300 whitespace-pre-wrap break-words">{JSON.stringify(costSources || {}, null, 2)}</pre>
              </div>
              <div className="bg-[#111111] border border-gray-900 rounded p-3 md:col-span-2">
                <p className="text-xs text-gray-500 mb-2 uppercase">Connection</p>
                <pre className="text-[11px] text-gray-300 whitespace-pre-wrap break-words">{JSON.stringify(connectionInfo || {}, null, 2)}</pre>
              </div>
              <div className="bg-[#111111] border border-gray-900 rounded p-3 md:col-span-2">
                <p className="text-xs text-gray-500 mb-2 uppercase">Ingest + File Diagnostics</p>
                {logsExplorerLoading && <p className="text-xs text-gray-500">Loading diagnostics...</p>}
                {logsExplorerError && <p className="text-xs text-red-400">{logsExplorerError}</p>}
                {!logsExplorerLoading && !logsExplorerError && (
                  <pre className="text-[11px] text-gray-300 whitespace-pre-wrap break-words">{JSON.stringify(logsExplorerData || {}, null, 2)}</pre>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <footer className="mt-8 py-8 px-5 bg-[#141414] border border-gray-900 rounded">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <p className="text-sm text-white font-semibold mb-2">Claw Journal</p>
            <p className="text-xs text-gray-500 leading-relaxed">
              Local observability for OpenClaw sessions. Track token usage, cost trends, model mix, and raw event detail in one place.
            </p>
          </div>

          <div>
            <p className="text-xs uppercase text-gray-500 mb-3">Product Focus</p>
            <div className="space-y-2 text-xs text-gray-400">
              <p className="flex items-center gap-2"><LineChartIcon size={14} className="text-orange-400" /> Analytics-first usage tracking</p>
              <p className="flex items-center gap-2"><Database size={14} className="text-orange-400" /> Raw logs + snapshots + reconciled totals</p>
              <p className="flex items-center gap-2"><Compass size={14} className="text-orange-400" /> Fast diagnostics for local + remote runs</p>
            </div>
          </div>

          <div>
            <p className="text-xs uppercase text-gray-500 mb-3">Navigate Sections</p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <a href="#overview" className="text-gray-400 hover:text-orange-400 transition">Overview</a>
              <a href="#usage-summary" className="text-gray-400 hover:text-orange-400 transition">Summary</a>
              <a href="#analytics" className="text-gray-400 hover:text-orange-400 transition">Analytics</a>
              <a href="#recent-sessions" className="text-gray-400 hover:text-orange-400 transition">Sessions</a>
              <a href="#pricing" className="text-gray-400 hover:text-orange-400 transition">Pricing</a>
              <a href="#explorer" className="text-gray-400 hover:text-orange-400 transition">Explorer</a>
            </div>
          </div>
        </div>
      </footer>
      </div>
    </div>
  );
};

export default Dashboard;
