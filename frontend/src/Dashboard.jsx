import React, { useEffect, useState } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';
import { RefreshCcw } from 'lucide-react';
import axios from 'axios';

const Dashboard = () => {
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

  return (
    <div className="bg-[#0a0a0a] min-h-screen text-gray-300 p-6 font-mono">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-xl font-bold text-white">ClawDash <span className="text-gray-500">Local</span></h1>
        <div className="flex gap-4 items-center">
            <span className="text-xs text-gray-500">Last scan: Just now</span>
            <button onClick={fetchData} className="bg-[#1a1a1a] border border-gray-800 px-4 py-1 rounded flex items-center gap-2 hover:bg-gray-800 transition text-xs text-white">
            <RefreshCcw size={14} /> Rescan
            </button>
        </div>
      </div>

      <div className="bg-[#141414] p-4 rounded border border-gray-900 mb-6">
        <p className="text-sm text-white font-semibold">Mode: auth={profile.auth_mode || 'unknown'} · billing={profile.billing_mode || 'unknown'}</p>
        <p className="text-xs text-gray-500 mt-2">
          {billingMode === 'claude_max'
            ? `Claude Max monthly plan: $${profile.claude_max_monthly_usd || 0} (token costs shown as subscription-included).`
            : 'Token billing mode: costs shown from observed or estimated per-token rates.'}
        </p>
        {notes && <p className="text-xs text-gray-500 mt-1">{notes}</p>}
        <p className="text-xs text-gray-500 mt-2">
          Local: {connectionInfo?.local?.user || '-'}@{connectionInfo?.local?.hostname || '-'} ({connectionInfo?.local?.ip || 'n/a'})
        </p>
        <p className="text-xs text-gray-500 mt-1">
          Remote: {connectionInfo?.remote?.ssh_user ? `${connectionInfo.remote.ssh_user}@` : ''}{connectionInfo?.remote?.ssh_host || '-'}
          {connectionInfo?.remote?.ssh_host_ip ? ` (${connectionInfo.remote.ssh_host_ip})` : ''} · mode={connectionInfo?.remote?.ingest_mode || '-'} · sync={String(connectionInfo?.remote?.session_sync_enabled ?? false)}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-[#141414] p-3 border border-gray-900 rounded">
          <p className="text-[10px] uppercase text-gray-500 mb-1">Observed</p>
          <p className="text-lg font-bold text-orange-500">{costSources.observed || 0}</p>
        </div>
        <div className="bg-[#141414] p-3 border border-gray-900 rounded">
          <p className="text-[10px] uppercase text-gray-500 mb-1">Estimated</p>
          <p className="text-lg font-bold text-orange-500">{costSources.estimated || 0}</p>
        </div>
        <div className="bg-[#141414] p-3 border border-gray-900 rounded">
          <p className="text-[10px] uppercase text-gray-500 mb-1">Missing</p>
          <p className="text-lg font-bold text-orange-500">{costSources.missing || 0}</p>
        </div>
        <div className="bg-[#141414] p-3 border border-gray-900 rounded">
          <p className="text-[10px] uppercase text-gray-500 mb-1">Subscription</p>
          <p className="text-lg font-bold text-orange-500">{costSources.subscription || 0}</p>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4 mb-8">
        {data.summary && Object.entries(data.summary).map(([key, val]) => (
          <div key={key} className="bg-[#141414] p-3 border border-gray-900 rounded shadow-sm">
            <p className="text-[10px] uppercase text-gray-500 mb-1">{key.replace(/([A-Z])/g, ' $1')}</p>
            <p className="text-lg font-bold text-orange-500">{typeof val === 'number' && key.toLowerCase().includes('spend') ? `$${val}` : typeof val === 'number' && key.toLowerCase().includes('avg') ? `$${val}` : val}</p>
          </div>
        ))}
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div className="md:col-span-2 bg-[#141414] p-4 rounded border border-gray-900">
          <h3 className="text-xs uppercase mb-4 text-gray-500">Cost by Day</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.costTrend}>
                <XAxis dataKey="date" stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#444" fontSize={10} tickLine={false} axisLine={false} tickFormatter={(val) => `$${val}`} />
                <Tooltip contentStyle={{backgroundColor: '#111', border: '1px solid #333', color: '#fff'}} itemStyle={{color: '#f97316'}} />
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
                <p className="text-3xl text-white font-bold">${data.costTrend && data.costTrend.length > 0 ? data.costTrend[data.costTrend.length - 1].cost : '0.00'}</p>
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
      <div className="bg-[#141414] rounded border border-gray-900 overflow-hidden">
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

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-6">
        <div className="bg-[#141414] rounded border border-gray-900 overflow-hidden">
          <div className="p-4 border-b border-gray-900">
            <h3 className="text-xs uppercase text-gray-500">Session Usage (Logs)</h3>
            {!legacyData?.sessions?.length && (
              <p className="text-xs text-gray-600 mt-2">No usage data detected yet.</p>
            )}
          </div>
          <div className="overflow-x-auto">
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

        <div className="bg-[#141414] rounded border border-gray-900 overflow-hidden">
          <div className="p-4 border-b border-gray-900">
            <h3 className="text-xs uppercase text-gray-500">Reconciled Sessions</h3>
          </div>
          <div className="overflow-x-auto">
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

        <div className="bg-[#141414] rounded border border-gray-900 p-4 xl:col-span-2">
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

        <div className="bg-[#141414] rounded border border-gray-900 p-4 xl:col-span-2">
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
    </div>
  );
};

export default Dashboard;
