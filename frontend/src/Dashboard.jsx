import React, { useEffect, useState } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell, PieChart, Pie } from 'recharts';
import { RefreshCcw } from 'lucide-react';
import axios from 'axios';

const COLORS = ['#f97316', '#fb923c', '#fdba74', '#fed7aa'];

const Dashboard = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      // In development processing through Vite proxy to http://localhost:8000
      const response = await axios.get('/api/dashboard-data');
      setData(response.data);
    } catch (err) {
      console.error(err);
      setError("Failed to load dashboard data. Ensure backend is running.");
      // Fallback to mock data for demo purposes if backend fails?
      // For now, show error.
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) return <div className="bg-[#0a0a0a] min-h-screen text-orange-500 p-10 font-mono">Loading data...</div>;
  if (error) return <div className="bg-[#0a0a0a] min-h-screen text-red-500 p-10 font-mono">{error} <button onClick={fetchData} className="underline ml-4">Retry</button></div>;
  if (!data) return null;

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
    </div>
  );
};

export default Dashboard;
