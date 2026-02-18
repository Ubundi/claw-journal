import React, { useEffect, useMemo, useState } from 'react';
import { Compass, Database, Feather, LineChart as LineChartIcon, Moon, RefreshCw, Sparkles, Sun } from 'lucide-react';

import ChatPage from './ChatPage';
import Dashboard from './Dashboard';
import MemoryPage from './MemoryPage';

function App() {
  const [pathname, setPathname] = useState(window.location.pathname);
  const [theme, setTheme] = useState(() => (typeof window !== 'undefined' && window.localStorage.getItem('cj_theme')) || 'dark');
  const [fontSize, setFontSize] = useState(() => (typeof window !== 'undefined' && window.localStorage.getItem('cj_font_size')) || 'normal');
  const [lastSyncAt, setLastSyncAt] = useState(() => (typeof window !== 'undefined' && window.localStorage.getItem('cj_last_sync_at')) || '');
  const [currency, setCurrency] = useState('USD');
  const [conversionRate, setConversionRate] = useState(1);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('cj_theme', theme);
      }
    } catch (_) {}
  }, [theme]);

  useEffect(() => {
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('cj_currency', currency);
      }
    } catch (_) {}
  }, [currency]);

  useEffect(() => {
    let cancelled = false;

    const loadRate = async () => {
      if (currency === 'USD') {
        setConversionRate(1);
        return;
      }

      try {
        const response = await fetch(`https://api.frankfurter.dev/v1/latest?base=USD&symbols=${encodeURIComponent(currency)}`);
        const payload = await response.json();
        const nextRate = Number(payload?.rates?.[currency] || 0);
        if (!cancelled && nextRate > 0) {
          setConversionRate(nextRate);
        }
      } catch (_) {
        if (!cancelled) {
          setConversionRate(1);
        }
      }
    };

    loadRate();

    return () => {
      cancelled = true;
    };
  }, [currency]);

  useEffect(() => {
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('cj_font_size', fontSize);
      }
    } catch (_) {}

    const html = document.documentElement;
    html.style.fontSize = fontSize === 'large' ? '18px' : '16px';

    return () => {
      html.style.fontSize = '';
    };
  }, [fontSize]);

  const isChat = pathname.startsWith('/chat');
  const isMemory = pathname.startsWith('/memory');

  const shellClass = useMemo(
    () => (theme === 'light' ? 'min-h-screen bg-white text-gray-900 font-mono' : 'min-h-screen bg-[#0a0a0a] text-gray-300 font-mono'),
    [theme],
  );

  const chromeButtonClass = useMemo(
    () => (theme === 'light'
      ? 'bg-white border border-gray-300 text-gray-900 hover:bg-gray-100'
      : 'bg-[#1a1a1a] border border-gray-800 text-white hover:bg-gray-800'),
    [theme],
  );

  const activeTabClass = useMemo(
    () => (theme === 'light' ? 'bg-gray-200 text-gray-900 border-gray-300' : 'bg-orange-900/40 text-orange-300 border-orange-800'),
    [theme],
  );

  const inactiveTabClass = useMemo(
    () => (theme === 'light' ? 'bg-white text-gray-900 border-gray-300 hover:bg-gray-100' : 'bg-[#1a1a1a] text-white border-gray-800 hover:bg-gray-800'),
    [theme],
  );

  const navigateTo = (targetPath) => {
    if (window.location.pathname === targetPath) return;
    window.history.pushState({}, '', targetPath);
    setPathname(targetPath);
  };

  const persistLastSyncAt = (timestamp) => {
    if (!timestamp) return;
    setLastSyncAt(timestamp);
    try {
      window.localStorage.setItem('cj_last_sync_at', timestamp);
    } catch (_) {}
  };

  const refreshLastSyncFromBackend = async () => {
    try {
      const response = await fetch('/api/system/connection');
      if (!response.ok) return;
      const payload = await response.json();
      const lastSuccessMs = Number(payload?.runtime?.session_sync_last_success_ms || 0);
      if (lastSuccessMs <= 0) return;
      const date = new Date(lastSuccessMs);
      if (Number.isNaN(date.getTime())) return;

      const nextIso = date.toISOString();
      setLastSyncAt((prev) => {
        const previousTime = new Date(prev).getTime();
        const nextTime = date.getTime();
        if (!Number.isNaN(previousTime) && nextTime < previousTime) {
          return prev;
        }
        try {
          window.localStorage.setItem('cj_last_sync_at', nextIso);
        } catch (_) {}
        return nextIso;
      });
    } catch (_) {}
  };

  useEffect(() => {
    refreshLastSyncFromBackend();
    const intervalId = window.setInterval(() => {
      refreshLastSyncFromBackend();
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, []);

  const triggerRefresh = () => {
    window.dispatchEvent(new CustomEvent('cj:refresh'));
    persistLastSyncAt(new Date().toISOString());
    window.setTimeout(() => {
      refreshLastSyncFromBackend();
    }, 1200);
  };

  const lastSyncLabel = useMemo(() => {
    if (!lastSyncAt) return 'Last sync: -';
    const date = new Date(lastSyncAt);
    if (Number.isNaN(date.getTime())) return 'Last sync: -';

    const pad = (value, size = 2) => String(value).padStart(size, '0');
    const formatted = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())},${pad(date.getMilliseconds(), 3)}`;
    return `Last sync: ${formatted}`;
  }, [lastSyncAt]);

  return (
    <div className={shellClass}>
      <div className="px-6 pt-6 pb-4 border-b border-gray-800/60">
        <div className={`flex flex-col md:flex-row md:justify-between md:items-center gap-4 border rounded-lg px-4 py-3 ${theme === 'light' ? 'border-gray-300 bg-gray-50' : 'border-gray-900 bg-[#121212]/90'}`}>
          <div className="flex items-start gap-3">
            <div className={`h-9 w-9 rounded border flex items-center justify-center ${theme === 'light' ? 'border-orange-300 bg-orange-100' : 'border-orange-800/60 bg-orange-950/40'}`}>
              <Feather size={16} className={theme === 'light' ? 'text-orange-700' : 'text-orange-300'} />
            </div>
            <div>
              <h1 className={`text-xl font-bold ${theme === 'light' ? 'text-gray-900' : 'text-white'}`}>Claw Journal</h1>
              <p className={`text-[11px] mt-0.5 flex items-center gap-1.5 ${theme === 'light' ? 'text-gray-600' : 'text-gray-500'}`}>
                <Sparkles size={12} className={theme === 'light' ? 'text-orange-600' : 'text-orange-400'} />
                OpenClaw observability dashboard
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <span className={`text-[11px] ${theme === 'light' ? 'text-gray-600' : 'text-gray-500'}`}>
                {lastSyncLabel}
              </span>
              <button
                onClick={triggerRefresh}
                className={`h-7 w-7 rounded border transition flex items-center justify-center ${chromeButtonClass}`}
                title="Refresh"
                aria-label="Refresh"
                type="button"
              >
                <RefreshCw size={14} />
              </button>
            </div>
            <button
              onClick={() => navigateTo('/')}
              className={`px-3 py-1 text-xs rounded border transition ${(isChat || isMemory) ? inactiveTabClass : activeTabClass}`}
            >
              Usage
            </button>
            <button
              onClick={() => navigateTo('/chat')}
              className={`px-3 py-1 text-xs rounded border transition ${isChat ? activeTabClass : inactiveTabClass}`}
            >
              Chat History
            </button>
            <button
              onClick={() => navigateTo('/memory')}
              className={`px-3 py-1 text-xs rounded border transition ${isMemory ? activeTabClass : inactiveTabClass}`}
            >
              Memory Explorer
            </button>
            <button
              onClick={() => setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))}
              className={`h-7 w-7 rounded border transition flex items-center justify-center ${chromeButtonClass}`}
              title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              type="button"
            >
              {theme === 'light' ? <Moon size={14} /> : <Sun size={14} />}
            </button>
            <button onClick={() => setShowSettings(true)} className={`px-3 py-1 text-xs rounded border transition ${chromeButtonClass}`}>
              Settings
            </button>
          </div>
        </div>
      </div>

      {showSettings && (
        <div className="fixed inset-0 z-40 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={() => setShowSettings(false)} />
          <div className="relative z-50 w-full max-w-lg p-4">
            <div className={`rounded shadow-lg p-4 ${theme === 'light' ? 'bg-white text-gray-900' : 'bg-[#0b0b0b] text-gray-200'}`}>
              <h3 className="text-lg font-semibold mb-2">Settings</h3>
              <label className="block text-sm mb-2">Font Size</label>
              <div className="flex items-center gap-4">
                <label className="inline-flex items-center gap-2">
                  <input type="radio" name="font-size" value="normal" checked={fontSize === 'normal'} onChange={() => setFontSize('normal')} />
                  <span>Normal</span>
                </label>
                <label className="inline-flex items-center gap-2">
                  <input type="radio" name="font-size" value="large" checked={fontSize === 'large'} onChange={() => setFontSize('large')} />
                  <span>Large</span>
                </label>
              </div>
              <div className="mt-4 flex justify-end">
                <button onClick={() => setShowSettings(false)} className="px-3 py-1 rounded bg-gray-600 text-white">Close</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {isChat ? <ChatPage theme={theme} /> : isMemory ? <MemoryPage theme={theme} /> : <Dashboard theme={theme} currency={currency} conversionRate={conversionRate} />}

      <footer className={`mt-8 py-8 px-5 border rounded mx-6 ${theme === 'light' ? 'bg-gray-100 border-gray-300' : 'bg-[#141414] border-gray-900'}`}>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <p className={`text-sm font-semibold mb-2 ${theme === 'light' ? 'text-gray-900' : 'text-white'}`}>Claw Journal</p>
            <p className={`text-xs leading-relaxed ${theme === 'light' ? 'text-gray-600' : 'text-gray-500'}`}>
              Local observability for OpenClaw sessions. Track token usage, cost trends, agent reasoning, and tool invocations in one place.
            </p>
          </div>

          <div>
            <p className={`text-xs uppercase mb-3 ${theme === 'light' ? 'text-gray-600' : 'text-gray-500'}`}>Product Focus</p>
            <div className={`space-y-2 text-xs ${theme === 'light' ? 'text-gray-700' : 'text-gray-400'}`}>
              <p className="flex items-center gap-2"><LineChartIcon size={14} className="text-orange-400" /> Analytics-first usage & cost tracking</p>
              <p className="flex items-center gap-2"><Database size={14} className="text-orange-400" /> Thinking process annotation & reasoning chains</p>
              <p className="flex items-center gap-2"><Compass size={14} className="text-orange-400" /> Conversation search, replay & tool diagnostics</p>
            </div>
          </div>

          <div>
            <p className={`text-xs uppercase mb-3 ${theme === 'light' ? 'text-gray-600' : 'text-gray-500'}`}>Navigate</p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <a href="/" className={`${theme === 'light' ? 'text-gray-700 hover:text-orange-600' : 'text-gray-400 hover:text-orange-400'} transition`}>Usage</a>
              <a href="/chat" className={`${theme === 'light' ? 'text-gray-700 hover:text-orange-600' : 'text-gray-400 hover:text-orange-400'} transition`}>Chat History</a>
              <a href="/memory" className={`${theme === 'light' ? 'text-gray-700 hover:text-orange-600' : 'text-gray-400 hover:text-orange-400'} transition`}>Memory Explorer</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App
