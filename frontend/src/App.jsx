import { useEffect, useState } from 'react';

import ChatPage from './ChatPage';
import Dashboard from './Dashboard';

function App() {
  const [pathname, setPathname] = useState(window.location.pathname);

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  if (pathname.startsWith('/chat')) {
    return <ChatPage />;
  }

  return <Dashboard />;
}

export default App
