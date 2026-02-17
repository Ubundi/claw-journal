import { useEffect, useMemo, useState } from 'react';

import ChatPage from './ChatPage';
import Dashboard from './Dashboard';

function App() {
  const [pathname, setPathname] = useState(window.location.pathname);
  const [theme, setTheme] = useState(() => (typeof window !== 'undefined' && window.localStorage.getItem('cj_theme')) || 'dark');
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

  const isChat = pathname.startsWith('/chat');

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
    () => (theme === 'light' ? 'bg-gray-900 text-white border-gray-900' : 'bg-orange-900/40 text-orange-300 border-orange-800'),
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

  const triggerRescan = () => {
    window.dispatchEvent(new CustomEvent('cj:rescan'));
  };

  return (
    <div className={shellClass}>
      <div className="px-6 pt-6 pb-4 border-b border-gray-800/60">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigateTo('/')}
              className={`px-3 py-1 text-xs rounded border transition ${isChat ? inactiveTabClass : activeTabClass}`}
            >
              Dashboard
            </button>
            <button
              onClick={() => navigateTo('/chat')}
              className={`px-3 py-1 text-xs rounded border transition ${isChat ? activeTabClass : inactiveTabClass}`}
            >
              Chat History
            </button>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={triggerRescan} className={`px-3 py-1 text-xs rounded border transition ${chromeButtonClass}`}>
              Rescan
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
              <label className="block text-sm mb-2">Theme</label>
              <div className="flex items-center gap-4">
                <label className="inline-flex items-center gap-2">
                  <input type="radio" name="theme" value="dark" checked={theme === 'dark'} onChange={() => setTheme('dark')} />
                  <span>Dark</span>
                </label>
                <label className="inline-flex items-center gap-2">
                  <input type="radio" name="theme" value="light" checked={theme === 'light'} onChange={() => setTheme('light')} />
                  <span>Light</span>
                </label>
              </div>
              <div className="mt-4 flex justify-end">
                <button onClick={() => setShowSettings(false)} className="px-3 py-1 rounded bg-gray-600 text-white">Close</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {isChat ? <ChatPage theme={theme} /> : <Dashboard theme={theme} />}
    </div>
  );
}

export default App
