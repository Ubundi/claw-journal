import React, { useEffect, useState } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';
import { RefreshCcw } from 'lucide-react';
import axios from 'axios';

const Dashboard = () => {
  const [data, setData] = useState(null);
  const [legacyData, setLegacyData] = useState(null);
  const [pricingForm, setPricingForm] = useState({
    provider: '',
    model: '',
    input_per_million: '',
    output_per_million: ''
  });
  const [pricingMessage, setPricingMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const money = (value) => {
    const number = Number(value || 0);
    return `$${number.toFixed(6)}`;
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [dashboardResponse, sessionsResponse, reconciledResponse, dailyResponse, costSourcesResponse, profileResponse] = await Promise.all([
        axios.get('/api/dashboard-data'),
        axios.get('/api/usage/sessions?limit=20'),
        axios.get('/api/usage/reconciled?limit=20'),
        axios.get('/api/usage/daily?days=30'),
        axios.get('/api/usage/cost-sources'),
        axios.get('/api/system/profile')
      ]);

      setData(dashboardResponse.data);
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

  const savePricing = async (event) => {
    event.preventDefault();
    setPricingMessage('');
    try {
      const payload = {
        provider: pricingForm.provider.trim(),
        model: pricingForm.model.trim(),
        input_per_million: Number(pricingForm.input_per_million),
        output_per_million: Number(pricingForm.output_per_million)
      };
      await axios.post('/api/pricing/upsert', payload);
      setPricingMessage(`Saved ${payload.provider}/${payload.model}`);
      setPricingForm({ provider: '', model: '', input_per_million: '', output_per_million: '' });
      await fetchData();
    } catch (err) {
      console.error(err);
      setPricingMessage('Failed to save pricing.');
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) return <div className="bg-[#0a0a0a] min-h-screen text-orange-500 p-10 font-mono">Loading data...</div>;
  if (error) return <div className="bg-[#0a0a0a] min-h-screen text-red-500 p-10 font-mono">{error} <button onClick={fetchData} className="underline ml-4">Retry</button></div>;
  if (!data) return null;

  const profile = legacyData?.profile || {};
  const costSources = legacyData?.costSources || {};
  const notes = Array.isArray(profile.notes) ? profile.notes.join(' ') : '';
  const billingMode = profile.billing_mode || 'token';
  const showCostColumns = billingMode !== 'claude_max';

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
          <h3 className="text-xs uppercase text-gray-500 mb-4">Pricing Configuration</h3>
          <form onSubmit={savePricing} className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              value={pricingForm.provider}
              onChange={(event) => setPricingForm((prev) => ({ ...prev, provider: event.target.value }))}
              placeholder="provider (e.g. anthropic)"
              className="bg-[#1a1a1a] border border-gray-800 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-gray-700"
              required
            />
            <input
              value={pricingForm.model}
              onChange={(event) => setPricingForm((prev) => ({ ...prev, model: event.target.value }))}
              placeholder="model (e.g. claude-opus-4-5)"
              className="bg-[#1a1a1a] border border-gray-800 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-gray-700"
              required
            />
            <input
              type="number"
              min="0"
              step="0.0001"
              value={pricingForm.input_per_million}
              onChange={(event) => setPricingForm((prev) => ({ ...prev, input_per_million: event.target.value }))}
              placeholder="input_per_million"
              className="bg-[#1a1a1a] border border-gray-800 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-gray-700"
              required
            />
            <input
              type="number"
              min="0"
              step="0.0001"
              value={pricingForm.output_per_million}
              onChange={(event) => setPricingForm((prev) => ({ ...prev, output_per_million: event.target.value }))}
              placeholder="output_per_million"
              className="bg-[#1a1a1a] border border-gray-800 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-gray-700"
              required
            />
            <div className="md:col-span-2 flex items-center gap-3">
              <button
                type="submit"
                className="bg-[#1a1a1a] border border-gray-800 px-4 py-2 rounded text-xs text-white hover:bg-gray-800 transition"
              >
                Save Pricing
              </button>
              {pricingMessage && <span className="text-xs text-gray-500">{pricingMessage}</span>}
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
