import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { FileText, FolderOpen } from 'lucide-react';

const MemoryPage = ({ theme = 'dark' }) => {
  const [files, setFiles] = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(true);
  const [filesError, setFilesError] = useState('');

  const [selectedPath, setSelectedPath] = useState('');
  const [content, setContent] = useState('');
  const [loadingContent, setLoadingContent] = useState(false);
  const [contentError, setContentError] = useState('');

  const isLight = theme === 'light';
  const panelBg = isLight ? 'bg-gray-50 rounded border border-gray-200' : 'bg-[#141414] rounded border border-gray-900';
  const itemBg = isLight ? 'hover:bg-gray-100 text-gray-800' : 'hover:bg-[#1b1b1b] text-gray-200';
  const selectedBg = isLight ? 'bg-orange-100 text-orange-800 border border-orange-200' : 'bg-orange-900/40 text-orange-300 border border-orange-800';

  const groupedFiles = useMemo(() => {
    const memoryRows = files.filter((row) => row.group === 'memory');
    const workspaceRows = files.filter((row) => row.group === 'workspace');
    return { memoryRows, workspaceRows };
  }, [files]);

  const fetchFiles = async () => {
    try {
      setLoadingFiles(true);
      setFilesError('');
      const response = await axios.get('/api/memory/files');
      const rows = response.data?.rows || [];
      setFiles(rows);

      if (!selectedPath || !rows.some((row) => row.path === selectedPath)) {
        setSelectedPath(rows[0]?.path || '');
      }
    } catch (error) {
      console.error(error);
      setFilesError('Failed to load memory files.');
      setFiles([]);
    } finally {
      setLoadingFiles(false);
    }
  };

  const fetchContent = async (path) => {
    if (!path) {
      setContent('');
      return;
    }

    try {
      setLoadingContent(true);
      setContentError('');
      const response = await axios.get(`/api/memory/file?path=${encodeURIComponent(path)}`);
      if (!response.data?.exists) {
        setContent('');
        setContentError('File not found on remote/local OpenClaw workspace.');
        return;
      }
      setContent(String(response.data?.content || ''));
    } catch (error) {
      console.error(error);
      setContent('');
      setContentError('Failed to load file content.');
    } finally {
      setLoadingContent(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  useEffect(() => {
    fetchContent(selectedPath);
  }, [selectedPath]);

  useEffect(() => {
    const onRefresh = () => fetchFiles();
    window.addEventListener('cj:refresh', onRefresh);
    return () => window.removeEventListener('cj:refresh', onRefresh);
  }, []);

  return (
    <div className={isLight ? 'bg-white min-h-screen text-gray-900 p-6 font-mono' : 'bg-[#0a0a0a] min-h-screen text-gray-300 p-6 font-mono'}>
      <div className="flex justify-between items-center mb-6">
        <h1 className={`text-xl font-bold ${isLight ? 'text-gray-900' : 'text-white'}`}>Memory Explorer</h1>
        <button
          onClick={fetchFiles}
          className={isLight ? 'px-3 py-1 text-xs rounded border border-gray-300 bg-white hover:bg-gray-100' : 'px-3 py-1 text-xs rounded border border-gray-800 bg-[#1a1a1a] hover:bg-gray-800 text-gray-200'}
        >
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className={`${panelBg} lg:col-span-4 p-3 min-h-[520px]`}>
          {loadingFiles && <p className="text-xs text-gray-500">Loading files...</p>}
          {!loadingFiles && filesError && <p className="text-xs text-red-400">{filesError}</p>}

          {!loadingFiles && !filesError && (
            <div className="space-y-4">
              <div>
                <p className={`text-[11px] uppercase tracking-wide mb-2 ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>
                  <FolderOpen size={12} className="inline mr-1" /> memory/
                </p>
                <div className="space-y-1">
                  {groupedFiles.memoryRows.map((row) => (
                    <button
                      key={row.path}
                      onClick={() => setSelectedPath(row.path)}
                      className={`w-full text-left px-2 py-1 text-xs rounded transition ${selectedPath === row.path ? selectedBg : itemBg}`}
                    >
                      <FileText size={12} className="inline mr-2" />
                      {row.name}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <p className={`text-[11px] uppercase tracking-wide mb-2 ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>
                  <FolderOpen size={12} className="inline mr-1" /> workspace/
                </p>
                <div className="space-y-1">
                  {groupedFiles.workspaceRows.map((row) => (
                    <button
                      key={row.path}
                      onClick={() => setSelectedPath(row.path)}
                      className={`w-full text-left px-2 py-1 text-xs rounded transition ${selectedPath === row.path ? selectedBg : itemBg}`}
                    >
                      <FileText size={12} className="inline mr-2" />
                      {row.name}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className={`${panelBg} lg:col-span-8 p-4 min-h-[520px]`}>
          <p className={`text-[11px] mb-3 ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>
            {selectedPath || 'Select a file from the explorer'}
          </p>

          {loadingContent && <p className="text-xs text-gray-500">Loading markdown...</p>}
          {!loadingContent && contentError && <p className="text-xs text-red-400">{contentError}</p>}
          {!loadingContent && !contentError && !selectedPath && <p className="text-xs text-gray-500">No file selected.</p>}

          {!loadingContent && !contentError && selectedPath && (
            <article className={`prose prose-sm max-w-none ${isLight ? 'prose-gray' : 'prose-invert'}`}>
              <ReactMarkdown>{content || '_Empty file_'}</ReactMarkdown>
            </article>
          )}
        </div>
      </div>
    </div>
  );
};

export default MemoryPage;
