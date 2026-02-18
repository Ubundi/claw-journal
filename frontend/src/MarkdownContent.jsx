import React from 'react';
import ReactMarkdown from 'react-markdown';

const MarkdownContent = ({ content = '', theme = 'dark' }) => {
  const isLight = theme === 'light';

  const proseClass = isLight
    ? 'prose prose-sm max-w-none prose-headings:text-gray-900 prose-p:text-gray-800 prose-strong:text-gray-900 prose-code:text-gray-900 prose-pre:bg-gray-100 prose-pre:text-gray-900 prose-hr:border-gray-300 prose-a:text-blue-700'
    : 'prose prose-sm max-w-none prose-invert prose-headings:text-white prose-p:text-gray-300 prose-strong:text-gray-100 prose-code:text-orange-300 prose-pre:bg-[#111] prose-pre:text-gray-200 prose-hr:border-gray-700 prose-a:text-blue-300';

  return (
    <article className={proseClass}>
      <ReactMarkdown>{content || '_Empty file_'}</ReactMarkdown>
    </article>
  );
};

export default MarkdownContent;
