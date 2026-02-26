import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from 'lucide-react';

const MemoryPage = ({ theme = 'dark' }) => {
  const [files, setFiles] = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(true);
  const [filesError, setFilesError] = useState('');
  const [memoryMeta, setMemoryMeta] = useState({
    remote_enabled: false,
    remote_ssh_host: null,
    workspace_dir: '~/.openclaw/workspace',
    memory_dir: '~/.openclaw/workspace/memory',
  });

  const [selectedPath, setSelectedPath] = useState('');
  const [content, setContent] = useState('');
  const [loadingContent, setLoadingContent] = useState(false);
  const [contentError, setContentError] = useState('');
  const [expandedFolders, setExpandedFolders] = useState({
    memory: true,
    workspace: true,
  });

  const isLight = theme === 'light';
  const panelBg = isLight ? 'bg-gray-50 rounded border border-gray-200' : 'bg-[#141414] rounded border border-gray-900';
  const itemBg = isLight ? 'hover:bg-gray-100 text-gray-800' : 'hover:bg-[#1b1b1b] text-gray-200';
  const selectedBg = isLight ? 'bg-orange-100 text-orange-800 border border-orange-200' : 'bg-orange-900/40 text-orange-300 border border-orange-800';

  const markdownComponents = useMemo(() => ({
    h1: ({ children }) => <h1 className={`text-2xl font-bold mt-4 mb-3 ${isLight ? 'text-gray-900' : 'text-white'}`}>{children}</h1>,
    h2: ({ children }) => <h2 className={`text-xl font-semibold mt-4 mb-2 ${isLight ? 'text-gray-900' : 'text-gray-100'}`}>{children}</h2>,
    h3: ({ children }) => <h3 className={`text-lg font-semibold mt-3 mb-2 ${isLight ? 'text-gray-800' : 'text-gray-200'}`}>{children}</h3>,
    h4: ({ children }) => <h4 className={`text-base font-semibold mt-3 mb-2 ${isLight ? 'text-gray-800' : 'text-gray-200'}`}>{children}</h4>,
    p: ({ children }) => <p className={`text-sm leading-6 mb-3 ${isLight ? 'text-gray-800' : 'text-gray-300'}`}>{children}</p>,
    ul: ({ children }) => <ul className={`list-disc pl-5 mb-3 text-sm ${isLight ? 'text-gray-800' : 'text-gray-300'}`}>{children}</ul>,
    ol: ({ children }) => <ol className={`list-decimal pl-5 mb-3 text-sm ${isLight ? 'text-gray-800' : 'text-gray-300'}`}>{children}</ol>,
    li: ({ children }) => <li className="mb-1">{children}</li>,
    blockquote: ({ children }) => (
      <blockquote className={`border-l-4 pl-3 py-1 mb-3 text-sm ${isLight ? 'border-gray-300 text-gray-700 bg-gray-100' : 'border-gray-700 text-gray-300 bg-[#111]'}`}>
        {children}
      </blockquote>
    ),
    hr: () => <hr className={`my-4 ${isLight ? 'border-gray-300' : 'border-gray-700'}`} />,
    a: ({ href, children }) => (
      <a href={href} target="_blank" rel="noreferrer" className={`underline text-sm ${isLight ? 'text-blue-700 hover:text-blue-800' : 'text-blue-300 hover:text-blue-200'}`}>
        {children}
      </a>
    ),
    code: ({ inline, children }) => (
      inline ? (
        <code className={`px-1 py-0.5 rounded text-[12px] ${isLight ? 'bg-gray-200 text-gray-900' : 'bg-[#1a1a1a] text-orange-300'}`}>
          {children}
        </code>
      ) : (
        <code className="block whitespace-pre-wrap break-words">{children}</code>
      )
    ),
    pre: ({ children }) => (
      <pre className={`text-xs rounded p-3 mb-3 overflow-x-auto ${isLight ? 'bg-gray-100 border border-gray-200 text-gray-900' : 'bg-[#111] border border-gray-800 text-gray-200'}`}>
        {children}
      </pre>
    ),
  }), [isLight]);

  const groupedFiles = useMemo(() => {
    const normalizePath = (value) => String(value || '').replace(/^\/+/, '').replace(/\\+/g, '/');

    const buildTree = (rows) => {
      const root = {
        path: '',
        folders: {},
        files: [],
      };

      for (const row of rows) {
        const normalized = normalizePath(row.path || row.name || '');
        const parts = normalized.split('/').filter(Boolean);
        if (parts.length === 0) {
          continue;
        }

        const fileName = parts[parts.length - 1];
        const folderParts = parts.slice(0, -1);

        let node = root;
        let folderPath = '';
        for (const part of folderParts) {
          folderPath = folderPath ? `${folderPath}/${part}` : part;
          if (!node.folders[part]) {
            node.folders[part] = {
              name: part,
              path: folderPath,
              folders: {},
              files: [],
            };
          }
          node = node.folders[part];
        }

        node.files.push({
          ...row,
          displayName: fileName,
          normalizedPath: normalized,
        });
      }

      const finalizeNode = (node) => {
        const folderArray = Object.values(node.folders)
          .map((child) => finalizeNode(child))
          .sort((left, right) => left.name.localeCompare(right.name));
        const fileArray = [...node.files]
          .sort((left, right) => String(left.displayName || '').localeCompare(String(right.displayName || '')));
        return {
          ...node,
          folders: folderArray,
          files: fileArray,
        };
      };

      return finalizeNode(root);
    };

    const memoryRows = files.filter((row) => row.group === 'memory');
    const workspaceRows = files.filter((row) => row.group === 'workspace');

    return {
      memoryTree: buildTree(memoryRows),
      workspaceTree: buildTree(workspaceRows),
    };
  }, [files]);

  const expandPathAncestors = (group, filePath) => {
    const normalized = String(filePath || '').replace(/^\/+/, '').replace(/\\+/g, '/');
    const parts = normalized.split('/').filter(Boolean);
    const folderParts = parts.slice(0, -1);

    if (folderParts.length === 0) return;

    setExpandedFolders((prev) => {
      const next = { ...prev };
      let current = group;
      next[current] = true;
      for (const part of folderParts) {
        current = `${current}/${part}`;
        next[current] = true;
      }
      return next;
    });
  };

  const fetchFiles = async () => {
    try {
      setLoadingFiles(true);
      setFilesError('');
      const response = await axios.get('/api/memory/files');
      const rows = response.data?.rows || [];
      setFiles(rows);
      setMemoryMeta({
        remote_enabled: Boolean(response.data?.remote_enabled),
        remote_ssh_host: response.data?.remote_ssh_host || null,
        workspace_dir: response.data?.workspace_dir || '~/.openclaw/workspace',
        memory_dir: response.data?.memory_dir || '~/.openclaw/workspace/memory',
      });

      if (!selectedPath || !rows.some((row) => row.path === selectedPath)) {
        const firstPath = rows[0]?.path || '';
        setSelectedPath(firstPath);
        if (rows[0]?.group && firstPath) {
          expandPathAncestors(rows[0].group, firstPath);
        }
      }
    } catch (error) {
      console.error(error);
      const status = error?.response?.status;
      if (status === 404) {
        setFilesError('Memory API route not found. Restart backend so the latest routes are loaded.');
      } else {
        setFilesError('Failed to load memory files.');
      }
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

  const selectedFile = files.find((row) => row.path === selectedPath);

  const toggleFolder = (folderKey) => {
    setExpandedFolders((prev) => ({
      ...prev,
      [folderKey]: !prev[folderKey],
    }));
  };

  const renderTree = (node, group, depth = 0) => {
    const folderItems = node.folders.map((folderNode) => {
      const folderKey = `${group}/${folderNode.path}`;
      const isExpanded = Boolean(expandedFolders[folderKey]);

      return (
        <div key={folderKey}>
          <button
            type="button"
            onClick={() => toggleFolder(folderKey)}
            className={`w-full text-left px-2 py-1 text-xs rounded transition flex items-center gap-1 ${itemBg}`}
            style={{ paddingLeft: `${0.5 + (depth * 0.85)}rem` }}
          >
            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {isExpanded ? <FolderOpen size={12} /> : <Folder size={12} />}
            <span>{folderNode.name}</span>
          </button>

          {isExpanded && (
            <div className="space-y-0.5">
              {renderTree(folderNode, group, depth + 1)}
            </div>
          )}
        </div>
      );
    });

    const fileItems = node.files.map((row) => (
      <button
        key={row.path}
        onClick={() => {
          setSelectedPath(row.path);
          expandPathAncestors(group, row.path);
        }}
        className={`w-full text-left px-2 py-1 text-xs rounded transition flex items-center gap-2 ${selectedPath === row.path ? selectedBg : itemBg}`}
        style={{ paddingLeft: `${1.75 + (depth * 0.85)}rem` }}
      >
        <FileText size={12} />
        <span className="truncate">{row.displayName}</span>
      </button>
    ));

    return (
      <>
        {folderItems}
        {fileItems}
      </>
    );
  };

  useEffect(() => {
    const onRefresh = () => fetchFiles();
    window.addEventListener('cj:refresh', onRefresh);
    return () => window.removeEventListener('cj:refresh', onRefresh);
  }, []);

  return (
    <div className={isLight ? 'bg-white min-h-screen text-gray-900 p-6' : 'bg-[#0a0a0a] min-h-screen text-gray-300 p-6'}>
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
              {files.length === 0 && (
                <div className={`text-xs rounded border p-2 ${isLight ? 'border-gray-200 text-gray-600 bg-white' : 'border-gray-800 text-gray-400 bg-[#111]'}`}>
                  <p className="mb-1">No files found in workspace.</p>
                  <p>Checked: {memoryMeta.workspace_dir}.</p>
                  {!memoryMeta.remote_enabled && (
                    <p className="mt-1">Remote mode is disabled. Set `CJ_REMOTE_ENABLED=true` and `CJ_REMOTE_SSH_HOST=user@your-host` to browse remote OpenClaw memory.</p>
                  )}
                </div>
              )}

              <div>
                <p className={`text-[11px] uppercase tracking-wide mb-2 ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>
                  <FolderOpen size={12} className="inline mr-1" /> memory/
                </p>
                <div className="space-y-0.5">
                  {renderTree(groupedFiles.memoryTree, 'memory')}
                </div>
              </div>

              <div>
                <p className={`text-[11px] uppercase tracking-wide mb-2 ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>
                  <FolderOpen size={12} className="inline mr-1" /> workspace/
                </p>
                <div className="space-y-0.5">
                  {renderTree(groupedFiles.workspaceTree, 'workspace')}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className={`${panelBg} lg:col-span-8 p-4 min-h-[520px]`}>
          <p className={`text-[11px] mb-3 ${isLight ? 'text-gray-600' : 'text-gray-500'}`}>
            {selectedFile?.path || selectedPath || 'Select a file from the explorer'}
          </p>

          {loadingContent && <p className="text-xs text-gray-500">Loading markdown...</p>}
          {!loadingContent && contentError && <p className="text-xs text-red-400">{contentError}</p>}
          {!loadingContent && !contentError && !selectedPath && <p className="text-xs text-gray-500">No file selected.</p>}

          {!loadingContent && !contentError && selectedPath && (
            <article className="max-w-none">
              <ReactMarkdown components={markdownComponents}>{content || '_Empty file_'}</ReactMarkdown>
            </article>
          )}
        </div>
      </div>
    </div>
  );
};

export default MemoryPage;
