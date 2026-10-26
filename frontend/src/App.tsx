import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import {
  Activity,
  AlertCircle,
  ArrowDownToLine,
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Copy,
  Database,
  Download,
  FileText,
  FlaskConical,
  Folder,
  GitBranch,
  Layers,
  Loader2,
  Menu,
  MessageSquare,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react';
import { api, connectToken, download, streamChat, uploadFile } from './api';
import type {
  Citation,
  Conversation,
  Document,
  Experiment,
  Message,
  TrainingSummary,
  View,
  Workspace,
} from './types';

const navigation = [
  { id: 'chat', name: 'Ask Atlas', icon: MessageSquare, label: 'Your knowledge, in conversation' },
  { id: 'knowledge', name: 'Knowledge', icon: BookOpen, label: 'A home for what your team knows' },
  {
    id: 'evaluations',
    name: 'Evaluations',
    icon: Activity,
    label: 'Measure the answer, inspect the evidence',
  },
  {
    id: 'tuning',
    name: 'Fine-tuning',
    icon: FlaskConical,
    label: 'Teach the behavior. Retrieve the facts.',
  },
] as const;
const prompts = [
  {
    icon: ShieldCheck,
    color: 'violet',
    title: 'Understand a policy',
    question: 'What is the refund window for annual plans, and are there exceptions?',
  },
  {
    icon: GitBranch,
    color: 'blue',
    title: 'Connect the dots',
    question: 'How do we handle an API rate-limit error and when should we retry?',
  },
  {
    icon: Layers,
    color: 'green',
    title: 'Find the right process',
    question: 'What steps should we follow when an employee reports a compromised account?',
  },
  {
    icon: MessageSquare,
    color: 'amber',
    title: 'Ask in Arabic',
    question: 'ما سياسة استرداد الاشتراكات السنوية؟',
  },
];

function Logo({ small = false }: { small?: boolean }) {
  return (
    <span className={`atlas-mark ${small ? 'small' : ''}`} aria-hidden="true">
      <svg viewBox="0 0 32 32" fill="none">
        <path d="M6 25 14 7h4l8 18h-5l-5-12-3 8h6l1.5 4H6Z" fill="currentColor" />
      </svg>
    </span>
  );
}
function formatSize(bytes: number) {
  return bytes >= 1048576
    ? `${(bytes / 1048576).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
function relative(timestamp: number) {
  const minutes = Math.floor((Date.now() / 1000 - timestamp) / 60);
  return minutes < 1
    ? 'Just now'
    : minutes < 60
      ? `${minutes}m ago`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)}h ago`
        : new Date(timestamp * 1000).toLocaleDateString();
}
function percent(value?: number) {
  return value === undefined ? '—' : `${Math.round(value * 100)}%`;
}
function duration(value?: number) {
  return value === undefined
    ? '—'
    : value < 1000
      ? `${Math.round(value)} ms`
      : `${(value / 1000).toFixed(1)} s`;
}
function errorText(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong';
}

function Modal({
  title,
  subtitle,
  children,
  close,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => {
      ref.current?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? 'wide' : ''}`}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
      aria-label={title}
    >
      <div className="modal-heading">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button className="icon-button" aria-label="Close dialog" onClick={close}>
          <X size={19} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

function AnswerText({ text, select }: { text: string; select: (ref: number) => void }) {
  return (
    <div className="answer-prose" dir="auto">
      {text.split(/\n\s*\n/).map((paragraph, i) => (
        <p key={i}>
          {paragraph.split(/(\[\d+\])/g).map((part, j) =>
            /^\[\d+\]$/.test(part) ? (
              <button
                className="inline-citation"
                key={j}
                onClick={() => select(Number(part.slice(1, -1)))}
                aria-label={`Open source ${part.slice(1, -1)}`}
              >
                {part.slice(1, -1)}
              </button>
            ) : (
              <span key={j}>
                {part
                  .split(/(\*\*[^*]+\*\*)/g)
                  .map((fragment, k) =>
                    fragment.startsWith('**') ? (
                      <strong key={k}>{fragment.slice(2, -2)}</strong>
                    ) : (
                      fragment
                    ),
                  )}
              </span>
            ),
          )}
        </p>
      ))}
    </div>
  );
}

function MiniChart({ values }: { values: number[] }) {
  if (values.length < 2)
    return <div className="chart-empty">A loss curve appears after a recorded training run.</div>;
  const low = Math.min(...values),
    high = Math.max(...values);
  const span = Math.max(high - low, 0.1);
  const points = values
    .map(
      (value, i) => `${40 + (i / (values.length - 1)) * 620},${168 - ((value - low) / span) * 132}`,
    )
    .join(' ');
  return (
    <svg
      viewBox="0 0 700 210"
      className="loss-chart"
      role="img"
      aria-label={`Training loss over ${values.length} steps, first ${values[0].toFixed(3)}, last ${values.at(-1)?.toFixed(3)}`}
    >
      <defs>
        <linearGradient id="loss-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6d5ce7" stopOpacity=".15" />
          <stop offset="100%" stopColor="#6d5ce7" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[40, 84, 128, 172].map((y) => (
        <line key={y} x1="40" x2="660" y1={y} y2={y} stroke="#ececf3" strokeDasharray="4 4" />
      ))}
      <polygon points={`40,180 ${points} 660,180`} fill="url(#loss-fill)" />
      <polyline
        points={points}
        fill="none"
        stroke="#6d5ce7"
        strokeWidth="2.5"
        strokeLinejoin="round"
      />
      <text x="40" y="202">
        Step 1
      </text>
      <text x="620" y="202">
        Step {values.length}
      </text>
      <text x="2" y="43">
        {high.toFixed(1)}
      </text>
      <text x="2" y="174">
        {low.toFixed(1)}
      </text>
    </svg>
  );
}

export default function App() {
  const initial = new URLSearchParams(window.location.search).get('view') as View;
  const [view, setViewState] = useState<View>(
    navigation.some((item) => item.id === initial) ? initial : 'chat',
  );
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [training, setTraining] = useState<TrainingSummary | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [mode, setMode] = useState<'base' | 'adapted'>('base');
  const modeInitialized = useRef(false);
  const [collection, setCollection] = useState('all');
  const [sourceOpen, setSourceOpen] = useState(
    () => window.matchMedia('(min-width:1051px)').matches,
  );
  const [sources, setSources] = useState<Citation[]>([]);
  const [sourceRef, setSourceRef] = useState<number | null>(null);
  const [activeMessage, setActiveMessage] = useState<Message | null>(null);
  const [generating, setGenerating] = useState(false);
  const [stage, setStage] = useState('');
  const [toast, setToast] = useState('');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadCollection, setUploadCollection] = useState('');
  const [uploading, setUploading] = useState('');
  const [newCollectionOpen, setNewCollectionOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [connectionOpen, setConnectionOpen] = useState(false);
  const [tokenInput, setTokenInput] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const [search, setSearch] = useState('');
  const [preview, setPreview] = useState<
    (Document & { passages: { id: string; text: string; page: number; heading: string }[] }) | null
  >(null);
  const [traceOpen, setTraceOpen] = useState(false);
  const [runId, setRunId] = useState('');
  const abort = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const notify = useCallback((message: string) => setToast(message), []);
  const refresh = useCallback(async () => {
    try {
      const [next, files, chats, runs, summary] = await Promise.all([
        api<Workspace>('/workspace'),
        api<Document[]>('/documents'),
        api<Conversation[]>('/conversations'),
        api<Experiment[]>('/experiments'),
        api<TrainingSummary>('/training/summary'),
      ]);
      setWorkspace(next);
      setDocuments(files);
      setConversations(chats);
      setExperiments(runs);
      setTraining(summary);
      if (next.models.ready && !modeInitialized.current) {
        setMode(next.models.adapted_available ? 'adapted' : 'base');
        modeInitialized.current = true;
      }
      setUploadCollection((current) => current || next.collections[0]?.id || '');
    } catch (error) {
      if (errorText(error).toLowerCase().includes('token')) setConnectionOpen(true);
      else notify(errorText(error));
    }
  }, [notify]);
  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => {
      void refresh();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [refresh]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(''), 6000);
    return () => window.clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: generating ? 'auto' : 'smooth', block: 'end' });
  }, [messages, generating]);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault();
        setViewState('chat');
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', listener);
    return () => window.removeEventListener('keydown', listener);
  }, []);
  const setView = (next: View) => {
    setViewState(next);
    setMobileNav(false);
    window.history.replaceState({}, '', next === 'chat' ? '/' : `/?view=${next}`);
  };
  const editAllowed = workspace?.identity.role !== 'viewer';
  const currentNavigation = navigation.find((item) => item.id === view)!;
  const visibleDocuments = documents.filter(
    (doc) =>
      (collection === 'all' || doc.collection_id === collection) &&
      `${doc.title} ${doc.filename}`.toLowerCase().includes(search.toLowerCase()),
  );
  const evaluations = experiments.filter((run) => run.kind === 'evaluation');
  const selectedRun = evaluations.find((run) => run.id === runId) || evaluations[0];
  const trainingRun = experiments.find((run) => run.kind === 'training');

  function newChat() {
    if (generating) {
      notify('Stop the current answer before starting another conversation.');
      return;
    }
    setConversationId(null);
    setMessages([]);
    setSources([]);
    setActiveMessage(null);
    setQuestion('');
    setView('chat');
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }
  async function openConversation(chat: Conversation) {
    if (generating) {
      notify('Stop the current answer before changing conversations.');
      return;
    }
    try {
      const rows = await api<Message[]>(`/conversations/${chat.id}/messages`);
      setMessages(rows);
      setConversationId(chat.id);
      const last = [...rows].reverse().find((row) => row.role === 'assistant');
      setSources(last?.citations || []);
      setActiveMessage(last || null);
      setView('chat');
    } catch (error) {
      notify(errorText(error));
    }
  }
  async function removeConversation(chat: Conversation) {
    if (!window.confirm(`Delete “${chat.title}” and its messages?`)) return;
    try {
      await api(`/conversations/${chat.id}`, 'DELETE');
      if (conversationId === chat.id) newChat();
      await refresh();
    } catch (error) {
      notify(errorText(error));
    }
  }
  async function submit(text = question) {
    const value = text.trim();
    if (!value || generating || abort.current) return;
    if (!workspace?.models.ready) {
      notify(
        workspace?.models.error || 'Models are still loading. Your sources will be ready shortly.',
      );
      return;
    }
    setGenerating(true);
    setStage('Finding the right evidence');
    setQuestion('');
    setSources([]);
    setSourceRef(null);
    setActiveMessage(null);
    setView('chat');
    const requestId = crypto.randomUUID();
    const draftId = `draft-${requestId}`;
    const controller = new AbortController();
    abort.current = controller;
    const user: Message = {
      id: `user-${requestId}`,
      role: 'user',
      content: value,
      state: 'complete',
      citations: [],
      trace: {},
    };
    const draft: Message = {
      id: draftId,
      role: 'assistant',
      content: '',
      state: 'generating',
      citations: [],
      trace: {},
    };
    setMessages((current) => [...current, user, draft]);
    try {
      let id = conversationId;
      if (!id) {
        const created = await api<Conversation>('/conversations', 'POST', {});
        id = created.id;
        setConversationId(id);
      }
      await streamChat(
        `/conversations/${id}/messages`,
        {
          question: value,
          request_id: requestId,
          mode,
          collection_ids: collection === 'all' ? [] : [collection],
        },
        controller.signal,
        (event, payload) => {
          if (event === 'status') setStage((payload as { label: string }).label);
          if (event === 'sources') {
            setSources(payload as Citation[]);
          }
          if (event === 'delta')
            setMessages((current) =>
              current.map((row) =>
                row.id === draftId
                  ? { ...row, content: row.content + (payload as { text: string }).text }
                  : row,
              ),
            );
          if (event === 'complete') {
            const answer = payload as Message;
            setMessages((current) => current.map((row) => (row.id === draftId ? answer : row)));
            setSources(answer.citations);
            setActiveMessage(answer);
            setStage('');
          }
          if (event === 'error') {
            const error = payload as { message: string };
            setMessages((current) =>
              current.map((row) =>
                row.id === draftId ? { ...row, content: error.message, state: 'failed' } : row,
              ),
            );
            notify(error.message);
          }
        },
      );
    } catch (error) {
      const cancelled = controller.signal.aborted;
      setMessages((current) =>
        current.map((row) =>
          row.id === draftId
            ? {
                ...row,
                content: cancelled ? 'Answer generation was stopped.' : errorText(error),
                state: cancelled ? 'cancelled' : 'failed',
              }
            : row,
        ),
      );
      if (!cancelled) notify(errorText(error));
    } finally {
      setGenerating(false);
      setStage('');
      abort.current = null;
      void refresh();
    }
  }
  async function upload(files: FileList | File[]) {
    if (!uploadCollection) {
      notify('Create a collection first.');
      return;
    }
    const items = Array.from(files);
    if (!items.length) return;
    try {
      for (let index = 0; index < items.length; index++) {
        if (items[index].size > 10 * 1024 * 1024)
          throw new Error(`${items[index].name} exceeds the 10 MB limit`);
        setUploading(`Uploading ${index + 1} of ${items.length}…`);
        await uploadFile(items[index], uploadCollection);
      }
      setUploadOpen(false);
      notify(
        `${items.length} source${items.length === 1 ? '' : 's'} added. Indexing continues in the background.`,
      );
      await refresh();
    } catch (error) {
      notify(errorText(error));
    } finally {
      setUploading('');
    }
  }
  async function inspectDocument(id: string) {
    try {
      setPreview(await api(`/documents/${id}`));
    } catch (error) {
      notify(errorText(error));
    }
  }
  function selectSource(ref: number, message?: Message) {
    if (message) {
      setSources(message.citations);
      setActiveMessage(message);
    }
    setSourceRef(ref);
    setSourceOpen(true);
    window.setTimeout(
      () =>
        document
          .getElementById(`source-${ref}`)
          ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }),
      50,
    );
  }
  async function feedback(message: Message, value: 'helpful' | 'unhelpful') {
    try {
      const next = message.feedback === value ? null : value;
      await api(`/messages/${message.id}/feedback`, 'PATCH', { value: next });
      setMessages((current) =>
        current.map((row) => (row.id === message.id ? { ...row, feedback: next } : row)),
      );
    } catch (error) {
      notify(errorText(error));
    }
  }
  async function copy(text: string, label = 'Copied to clipboard') {
    try {
      await navigator.clipboard.writeText(text);
      notify(label);
    } catch {
      notify('Clipboard access is unavailable in this browser.');
    }
  }

  return (
    <div className={`app-shell ${mobileNav ? 'nav-open' : ''}`}>
      {mobileNav && (
        <button
          className="nav-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside className="sidebar" aria-label="Main navigation">
        <button className="brand" onClick={newChat} aria-label="Atlas home">
          <Logo />
          <span>
            atlas<span className="brand-caption">KNOWLEDGE, CONNECTED.</span>
          </span>
        </button>
        <button className="workspace-switch" onClick={() => setSettingsOpen(true)}>
          <span className="workspace-avatar">
            N<span />
          </span>
          <span>
            <strong>{workspace?.name || 'Your workspace'}</strong>
            <small>
              {workspace?.identity.auth_mode === 'local'
                ? 'Local workspace'
                : 'Connected workspace'}
            </small>
          </span>
          <ChevronDown size={14} />
        </button>
        <div className="nav-group-label">WORKSPACE</div>
        <nav>
          {navigation.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${view === item.id ? 'active' : ''}`}
              aria-current={view === item.id ? 'page' : undefined}
              onClick={() => setView(item.id)}
            >
              <item.icon size={18} />
              <span>{item.name}</span>
              {item.id === 'knowledge' && (
                <span className="nav-count">{workspace?.stats.documents || 0}</span>
              )}
              {item.id === 'chat' && <span className="keyboard-hint">⌘ K</span>}
            </button>
          ))}
        </nav>
        <div className="nav-group-heading">
          <span className="nav-group-label">COLLECTIONS</span>
          <button
            className="icon-button"
            aria-label="New collection"
            title="New collection"
            disabled={!editAllowed}
            onClick={() => setNewCollectionOpen(true)}
          >
            <Plus size={15} />
          </button>
        </div>
        <div className="collection-nav">
          <button
            className={collection === 'all' ? 'selected' : ''}
            onClick={() => {
              setCollection('all');
              setView('knowledge');
            }}
          >
            <span className="collection-dot all" />
            All knowledge<span>{documents.length}</span>
          </button>
          {workspace?.collections.map((item) => (
            <button
              key={item.id}
              className={collection === item.id ? 'selected' : ''}
              onClick={() => {
                setCollection(item.id);
                setView('knowledge');
              }}
            >
              <span className={`collection-dot ${item.color}`} />
              <span className="truncate">{item.name}</span>
              <span>{item.document_count}</span>
            </button>
          ))}
        </div>
        <div className="nav-group-heading recent-label">
          <span className="nav-group-label">RECENT CONVERSATIONS</span>
          <button className="icon-button" aria-label="New conversation" onClick={newChat}>
            <Plus size={15} />
          </button>
        </div>
        <div className="conversation-nav">
          {conversations.length ? (
            conversations.slice(0, 8).map((chat) => (
              <div
                key={chat.id}
                className={`conversation-link ${conversationId === chat.id ? 'selected' : ''}`}
              >
                <button onClick={() => void openConversation(chat)}>
                  <MessageSquare size={14} />
                  <span>{chat.title}</span>
                </button>
                <button
                  className="delete-chat"
                  aria-label={`Delete conversation ${chat.title}`}
                  onClick={() => void removeConversation(chat)}
                >
                  <X size={13} />
                </button>
              </div>
            ))
          ) : (
            <p className="quiet-small">Your conversations will appear here.</p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="pipeline-card">
            <span className={`status-dot ${workspace?.models.ready ? 'ready' : 'loading'}`} />
            <span>
              <strong>
                {workspace?.models.ready
                  ? 'Knowledge engine online'
                  : workspace?.models.error
                    ? 'Engine needs attention'
                    : 'Preparing knowledge engine'}
              </strong>
              <small>Hybrid retrieval · cited generation</small>
            </span>
          </div>
          <button className="account" onClick={() => setSettingsOpen(true)}>
            <span className="user-avatar">MS</span>
            <span>
              <strong>Workspace owner</strong>
              <small>{workspace?.identity.role || 'Connecting…'}</small>
            </span>
            <Settings size={17} />
          </button>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobileNav(true)}
            >
              <Menu size={20} />
            </button>
            <span className="workspace-mini">N</span>
            <span className="crumb-workspace">
              {workspace?.name.replace(/ workspace$/, '') || 'Workspace'}
            </span>
            <ChevronRight size={14} />
            <strong>{currentNavigation.name}</strong>
          </div>
          <div className="topbar-actions">
            <span className="local-badge">
              <span className={`status-dot ${workspace?.models.ready ? 'ready' : 'loading'}`} />
              {workspace?.models.ready ? 'All systems ready' : 'Models loading'}
            </span>
            <button
              className="icon-button"
              aria-label="Workspace settings"
              onClick={() => setSettingsOpen(true)}
            >
              <SlidersHorizontal size={17} />
            </button>
            <span className="user-avatar small">MS</span>
          </div>
        </header>

        {view === 'chat' && (
          <div className={`chat-layout ${sourceOpen ? 'with-evidence' : ''}`}>
            <main className="chat-main">
              <div className="chat-toolbar">
                <div>
                  <span className="eyebrow">KNOWLEDGE ASSISTANT</span>
                  <h1>
                    {conversationId
                      ? conversations.find((chat) => chat.id === conversationId)?.title ||
                        'Your conversation'
                      : 'Ask Atlas'}
                  </h1>
                </div>
                <div className="toolbar-actions">
                  <button className="text-button" onClick={newChat}>
                    <Plus size={15} />
                    New chat
                  </button>
                  <button
                    className="icon-button"
                    onClick={() => setSourceOpen(!sourceOpen)}
                    aria-label={sourceOpen ? 'Hide sources' : 'Show sources'}
                  >
                    {sourceOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
                  </button>
                </div>
              </div>
              <div className={`chat-scroll ${messages.length ? 'has-messages' : ''}`}>
                {!messages.length ? (
                  <div className="welcome">
                    <div className="welcome-emblem">
                      <div className="orbit orbit-one" />
                      <div className="orbit orbit-two" />
                      <Logo />
                    </div>
                    <span className="section-kicker">LESS SEARCHING. MORE UNDERSTANDING.</span>
                    <h2>
                      Your team's knowledge.
                      <br />
                      <span>One thoughtful answer.</span>
                    </h2>
                    <p>
                      Bring your documents together. Ask a question.
                      <br className="desktop-break" /> Get a clear answer, with the evidence to back
                      it up.
                    </p>
                    <div className="capability-chips">
                      <span>
                        <Layers size={13} />
                        Hybrid search
                      </span>
                      <span>
                        <ShieldCheck size={13} />
                        Source citations
                      </span>
                      <span>
                        <Sparkles size={13} />
                        Fine-tuned behavior
                      </span>
                    </div>
                    <div className="prompt-grid">
                      {prompts.map((item) => (
                        <button
                          key={item.title}
                          onClick={() => {
                            setQuestion(item.question);
                            inputRef.current?.focus();
                          }}
                        >
                          <span className={`prompt-icon ${item.color}`}>
                            <item.icon size={18} />
                          </span>
                          <strong>{item.title}</strong>
                          <span className="prompt-question" dir="auto">
                            {item.question}
                          </span>
                          <ArrowUpRight size={15} className="prompt-arrow" />
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="messages" aria-live="polite" aria-relevant="additions text">
                    {messages.map((message) =>
                      message.role === 'user' ? (
                        <div className="user-message" key={message.id}>
                          <div className="user-bubble" dir="auto">
                            {message.content}
                          </div>
                        </div>
                      ) : (
                        <article
                          className={`assistant-message ${message.state === 'failed' ? 'failed' : ''}`}
                          key={message.id}
                        >
                          <div className="assistant-heading">
                            <Logo small />
                            <strong>Atlas</strong>
                            <span>
                              {message.state === 'generating'
                                ? 'Preparing an answer'
                                : message.trace.mode === 'adapted'
                                  ? 'Grounding adapter'
                                  : 'Knowledge assistant'}
                            </span>
                            {message.state === 'generating' && (
                              <span className="live-label">LIVE</span>
                            )}
                          </div>
                          {message.content ? (
                            <AnswerText
                              text={message.content}
                              select={(ref) =>
                                selectSource(
                                  ref,
                                  message.state === 'generating' ? undefined : message,
                                )
                              }
                            />
                          ) : (
                            <div className="thinking">
                              <span />
                              <span />
                              <span />
                              <span>{stage}</span>
                            </div>
                          )}
                          {message.state === 'generating' && message.content && (
                            <p className="draft-note">
                              <Loader2 size={12} className="spin" />
                              Streaming draft · references checked before saving
                            </p>
                          )}
                          {message.state === 'complete' && (
                            <>
                              <div className="answer-evidence">
                                {message.citations.length ? (
                                  <button
                                    onClick={() => {
                                      setSources(message.citations);
                                      setActiveMessage(message);
                                      setSourceOpen(true);
                                    }}
                                  >
                                    <ShieldCheck size={14} />
                                    {message.citations.length} cited source
                                    {message.citations.length !== 1 ? 's' : ''}
                                    <ChevronRight size={13} />
                                  </button>
                                ) : (
                                  <span className="muted">
                                    <BookOpen size={14} />
                                    No supporting evidence
                                  </span>
                                )}
                                <span>{duration(message.trace.total_ms)}</span>
                              </div>
                              <div className="message-actions">
                                <button
                                  className="icon-button"
                                  aria-label="Copy answer"
                                  onClick={() => void copy(message.content)}
                                >
                                  <Copy size={14} />
                                </button>
                                <button
                                  className={`icon-button ${message.feedback === 'helpful' ? 'pressed' : ''}`}
                                  aria-label="Mark answer helpful"
                                  onClick={() => void feedback(message, 'helpful')}
                                >
                                  <ThumbsUp size={14} />
                                </button>
                                <button
                                  className={`icon-button ${message.feedback === 'unhelpful' ? 'pressed' : ''}`}
                                  aria-label="Mark answer unhelpful"
                                  onClick={() => void feedback(message, 'unhelpful')}
                                >
                                  <ThumbsDown size={14} />
                                </button>
                                <button
                                  className="trace-button"
                                  onClick={() => {
                                    setActiveMessage(message);
                                    setTraceOpen(true);
                                  }}
                                >
                                  <Activity size={13} />
                                  Inspect run
                                </button>
                              </div>
                            </>
                          )}
                        </article>
                      ),
                    )}
                    <div ref={bottomRef} />
                  </div>
                )}
              </div>
              <div className="composer-area">
                {!workspace?.models.ready && (
                  <div className="engine-banner">
                    <Loader2 size={15} className="spin" />
                    <span>
                      {workspace?.models.error ||
                        'Loading the embedding, reranking, and language models. Your workspace remains available.'}
                    </span>
                  </div>
                )}
                <form
                  className="composer"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void submit();
                  }}
                >
                  <textarea
                    ref={inputRef}
                    aria-label="Ask your knowledge"
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder="Ask anything about your knowledge…"
                    maxLength={2000}
                    rows={2}
                    dir="auto"
                    onKeyDown={(event) => {
                      if (
                        event.key === 'Enter' &&
                        !event.shiftKey &&
                        !event.nativeEvent.isComposing
                      ) {
                        event.preventDefault();
                        void submit();
                      }
                    }}
                  />
                  <div className="composer-controls">
                    <div>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label="Add knowledge sources"
                        disabled={!editAllowed}
                        onClick={() => setUploadOpen(true)}
                      >
                        <Plus size={19} />
                      </button>
                      <span className="composer-divider" />
                      <label className="scope-select">
                        <Database size={13} />
                        <select
                          aria-label="Knowledge scope"
                          value={collection}
                          onChange={(event) => setCollection(event.target.value)}
                        >
                          <option value="all">All knowledge</option>
                          {workspace?.collections.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <div>
                      <label className="mode-select">
                        <Sparkles size={13} />
                        <select
                          aria-label="Answer model"
                          value={mode}
                          onChange={(event) => setMode(event.target.value as 'base' | 'adapted')}
                        >
                          <option value="base">Base model</option>
                          <option value="adapted" disabled={!workspace?.models.adapted_available}>
                            Grounding adapter
                          </option>
                        </select>
                      </label>
                      {generating ? (
                        <button
                          type="button"
                          className="send-button stop"
                          aria-label="Stop answer"
                          onClick={() => abort.current?.abort()}
                        >
                          <Square size={15} fill="currentColor" />
                        </button>
                      ) : (
                        <button
                          className="send-button"
                          aria-label="Send question"
                          disabled={!question.trim() || !workspace?.models.ready}
                        >
                          <ArrowUp size={19} />
                        </button>
                      )}
                    </div>
                  </div>
                </form>
                <p className="composer-footnote">
                  <ShieldCheck size={12} />
                  Grounded in your sources. Review citations for important decisions.
                  <span>Enter to send · Shift + Enter for a new line</span>
                </p>
              </div>
            </main>
            {sourceOpen && (
              <aside className="evidence-panel" aria-label="Source evidence">
                <div className="evidence-heading">
                  <div>
                    <BookOpen size={17} />
                    <h2>{sources.length ? 'Evidence' : 'Your knowledge'}</h2>
                    {sources.length > 0 && <span className="number-badge">{sources.length}</span>}
                  </div>
                  <button
                    className="icon-button evidence-close"
                    aria-label="Close sources"
                    onClick={() => setSourceOpen(false)}
                  >
                    <X size={16} />
                  </button>
                </div>
                {sources.length ? (
                  <>
                    <p className="panel-description">
                      The passages behind this answer. Select a citation to explore its source.
                    </p>
                    <div className="source-list">
                      {sources.map((source) => (
                        <article
                          id={`source-${source.ref}`}
                          className={`source-card ${sourceRef === source.ref ? 'highlighted' : ''}`}
                          key={source.ref}
                        >
                          <div className="source-card-title">
                            <span className="source-number">{source.ref}</span>
                            <FileText size={16} />
                            <strong>{source.title}</strong>
                          </div>
                          <div className="source-meta">
                            <span>Page {source.page}</span>
                            <span>•</span>
                            <span>{source.available ? 'Retrieved passage' : 'Source removed'}</span>
                          </div>
                          <p className="source-excerpt" dir="auto">
                            {source.text ||
                              'This document is no longer available in the workspace.'}
                          </p>
                          <button
                            className="source-open"
                            disabled={!source.available}
                            onClick={() => void inspectDocument(source.document_id)}
                          >
                            Open document
                            <ArrowUpRight size={13} />
                          </button>
                        </article>
                      ))}
                    </div>
                    {activeMessage && (
                      <div className="evidence-summary">
                        <span>
                          <ShieldCheck size={15} />
                          References validated
                        </span>
                        <small>
                          Reference validation checks source IDs, not the truth of every generated
                          claim.
                        </small>
                        <button className="text-button" onClick={() => setTraceOpen(true)}>
                          Explore retrieval trace
                          <ArrowUpRight size={13} />
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <p className="panel-description">
                      Connected sources make every conversation more useful.
                    </p>
                    <div className="knowledge-summary">
                      <div>
                        <span>{workspace?.stats.ready_documents || 0}</span>
                        <small>indexed sources</small>
                      </div>
                      <div>
                        <span>{workspace?.stats.chunks || 0}</span>
                        <small>searchable passages</small>
                      </div>
                    </div>
                    <div className="panel-section-heading">CONNECTED COLLECTIONS</div>
                    <div className="knowledge-collections">
                      {workspace?.collections.map((item) => (
                        <button
                          key={item.id}
                          onClick={() => {
                            setCollection(item.id);
                            setView('knowledge');
                          }}
                        >
                          <span className={`folder-box ${item.color}`}>
                            <Folder size={17} />
                          </span>
                          <span>
                            <strong>{item.name}</strong>
                            <small>
                              {item.document_count} source{item.document_count !== 1 ? 's' : ''}
                            </small>
                          </span>
                          <ChevronRight size={14} />
                        </button>
                      ))}
                    </div>
                    <button
                      className="add-sources-button"
                      disabled={!editAllowed}
                      onClick={() => setUploadOpen(true)}
                    >
                      <Plus size={15} />
                      Add knowledge sources
                    </button>
                    <div className="how-it-works">
                      <span className="section-kicker">BEHIND EVERY ANSWER</span>
                      <div>
                        <span>01</span>
                        <p>
                          <strong>Find the right context</strong>Semantic and keyword search work
                          together.
                        </p>
                      </div>
                      <div>
                        <span>02</span>
                        <p>
                          <strong>Put evidence first</strong>A reranker selects the most relevant
                          passages.
                        </p>
                      </div>
                      <div>
                        <span>03</span>
                        <p>
                          <strong>Answer with receipts</strong>The model responds using numbered
                          citations.
                        </p>
                      </div>
                    </div>
                  </>
                )}
              </aside>
            )}
          </div>
        )}

        {view === 'knowledge' && (
          <main className="page-main">
            <div className="page-heading">
              <div>
                <span className="eyebrow">YOUR SOURCE OF TRUTH</span>
                <h1>
                  Knowledge library<span className="heading-dot">.</span>
                </h1>
                <p>Give your team's knowledge a place to connect.</p>
              </div>
              <button
                className="primary-button"
                disabled={!editAllowed}
                onClick={() => setUploadOpen(true)}
              >
                <UploadCloud size={16} />
                Add sources
              </button>
            </div>
            <div className="stats-grid">
              <Stat
                label="Total sources"
                value={workspace?.stats.documents || 0}
                icon={<FileText size={18} />}
                detail="Across your collections"
              />
              <Stat
                label="Ready to retrieve"
                value={workspace?.stats.ready_documents || 0}
                icon={<CheckCircle2 size={18} />}
                detail="Indexed and searchable"
              />
              <Stat
                label="Knowledge passages"
                value={workspace?.stats.chunks || 0}
                icon={<Layers size={18} />}
                detail="With page-level references"
              />
              <Stat
                label="Collections"
                value={workspace?.collections.length || 0}
                icon={<Folder size={18} />}
                detail="Organized by your team"
              />
            </div>
            <div className="collection-cards">
              <button
                className={`collection-card ${collection === 'all' ? 'active' : ''}`}
                onClick={() => setCollection('all')}
              >
                <span className="folder-box indigo">
                  <Layers size={19} />
                </span>
                <strong>All knowledge</strong>
                <small>{documents.length} sources</small>
                <ChevronRight size={15} />
              </button>
              {workspace?.collections.map((item) => (
                <button
                  key={item.id}
                  className={`collection-card ${collection === item.id ? 'active' : ''}`}
                  onClick={() => setCollection(item.id)}
                >
                  <span className={`folder-box ${item.color}`}>
                    <Folder size={19} />
                  </span>
                  <strong>{item.name}</strong>
                  <small>{item.document_count} sources</small>
                  <ChevronRight size={15} />
                </button>
              ))}
            </div>
            <section className="library-table card">
              <div className="table-toolbar">
                <h2>
                  Sources <span className="number-badge">{visibleDocuments.length}</span>
                </h2>
                <label className="search-field">
                  <Search size={15} />
                  <input
                    aria-label="Search documents"
                    placeholder="Search your sources…"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                  />
                </label>
              </div>
              <div className="document-table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Collection</th>
                      <th>Status</th>
                      <th>Passages</th>
                      <th>Added</th>
                      <th>
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleDocuments.map((doc) => (
                      <tr key={doc.id}>
                        <td>
                          <button
                            className="document-name"
                            onClick={() => void inspectDocument(doc.id)}
                          >
                            <span
                              className={`file-icon ${doc.filename.endsWith('.pdf') ? 'pdf' : 'text'}`}
                            >
                              <FileText size={19} />
                            </span>
                            <span>
                              <strong>{doc.title}</strong>
                              <small>
                                {doc.filename.split('.').at(-1)?.toUpperCase()} ·{' '}
                                {formatSize(doc.bytes)}
                              </small>
                            </span>
                          </button>
                        </td>
                        <td>
                          <span className="collection-label">
                            <span
                              className={`collection-dot ${workspace?.collections.find((item) => item.id === doc.collection_id)?.color || 'indigo'}`}
                            />
                            {
                              workspace?.collections.find((item) => item.id === doc.collection_id)
                                ?.name
                            }
                          </span>
                        </td>
                        <td>
                          <span className={`document-status ${doc.status}`} title={doc.error}>
                            {doc.status === 'ready' ? (
                              <CheckCircle2 size={12} />
                            ) : doc.status === 'failed' ? (
                              <AlertCircle size={12} />
                            ) : (
                              <Loader2 size={12} className="spin" />
                            )}
                            {doc.status === 'ready'
                              ? 'Ready'
                              : doc.status === 'failed'
                                ? 'Needs attention'
                                : doc.status === 'queued'
                                  ? 'Queued'
                                  : 'Indexing'}
                          </span>
                        </td>
                        <td className="numeric">{doc.chunk_count || '—'}</td>
                        <td className="muted">{relative(doc.created_at)}</td>
                        <td>
                          <div className="row-actions">
                            {doc.status === 'ready' && (
                              <button
                                className="icon-button"
                                aria-label={`Reindex ${doc.title}`}
                                disabled={!editAllowed}
                                onClick={async () => {
                                  try {
                                    await api(`/documents/${doc.id}/reindex`, 'POST');
                                    await refresh();
                                    notify('Source queued for reindexing.');
                                  } catch (error) {
                                    notify(errorText(error));
                                  }
                                }}
                              >
                                <GitBranch size={15} />
                              </button>
                            )}
                            {doc.status === 'failed' && (
                              <button
                                className="icon-button"
                                aria-label={`Retry ${doc.title}`}
                                onClick={async () => {
                                  try {
                                    await api(`/documents/${doc.id}/retry`, 'POST');
                                    await refresh();
                                  } catch (error) {
                                    notify(errorText(error));
                                  }
                                }}
                              >
                                <GitBranch size={15} />
                              </button>
                            )}
                            <button
                              className="icon-button"
                              aria-label={`Download ${doc.title}`}
                              onClick={() =>
                                void download(`/documents/${doc.id}/download`, doc.filename).catch(
                                  (error) => notify(errorText(error)),
                                )
                              }
                            >
                              <Download size={15} />
                            </button>
                            <button
                              className="icon-button danger"
                              aria-label={`Delete ${doc.title}`}
                              disabled={!editAllowed}
                              onClick={async () => {
                                if (!window.confirm(`Remove “${doc.title}” from retrieval?`))
                                  return;
                                try {
                                  await api(`/documents/${doc.id}`, 'DELETE');
                                  await refresh();
                                } catch (error) {
                                  notify(errorText(error));
                                }
                              }}
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!visibleDocuments.length && (
                <Empty
                  icon={<BookOpen size={26} />}
                  title="Make room for what you know"
                  text={
                    search
                      ? 'No documents match your search.'
                      : 'Add a PDF, Markdown, or text document to start building your knowledge.'
                  }
                  action={
                    !search ? (
                      <button
                        className="primary-button"
                        disabled={!editAllowed}
                        onClick={() => setUploadOpen(true)}
                      >
                        <Plus size={15} />
                        Add your first source
                      </button>
                    ) : undefined
                  }
                />
              )}
              <div className="table-footer">
                <ShieldCheck size={13} />
                Sources are isolated to your workspace. Duplicate files are detected automatically.
                <span>PDF · Markdown · TXT</span>
              </div>
            </section>
            <div className="pipeline-explainer">
              <div className="folder-box indigo">
                <GitBranch size={22} />
              </div>
              <div>
                <h3>More than a document upload.</h3>
                <p>
                  Page-aware extraction, durable indexing, multilingual embeddings, and hybrid
                  search turn files into evidence your assistant can use.
                </p>
              </div>
              <button className="text-button" onClick={() => setSettingsOpen(true)}>
                View configuration
                <ArrowUpRight size={14} />
              </button>
            </div>
          </main>
        )}

        {view === 'evaluations' && (
          <main className="page-main">
            <div className="page-heading">
              <div>
                <span className="eyebrow">EVIDENCE OVER ASSUMPTIONS</span>
                <h1>
                  Know how well it works<span className="heading-dot">.</span>
                </h1>
                <p>Compare retrieval strategies and model behavior on held-out scenarios.</p>
              </div>
              <button className="secondary-button" onClick={() => void refresh()}>
                <Activity size={15} />
                Refresh results
              </button>
            </div>
            {selectedRun ? (
              <>
                <div className="run-selector">
                  <span className="status-dot ready" />
                  <span>Recorded evaluation</span>
                  <select
                    aria-label="Evaluation run"
                    value={selectedRun.id}
                    onChange={(event) => setRunId(event.target.value)}
                  >
                    {evaluations.map((run) => (
                      <option key={run.id} value={run.id}>
                        {run.name} · {new Date(run.created_at * 1000).toLocaleDateString()}
                      </option>
                    ))}
                  </select>
                  <small>Results from an actual run</small>
                </div>
                <div className="stats-grid">
                  {(() => {
                    const retrieval = selectedRun.report.retrieval?.reranked;
                    const generation =
                      selectedRun.report.generation?.adapted || selectedRun.report.generation?.base;
                    return (
                      <>
                        <Stat
                          label="Retrieval recall @5"
                          value={percent(retrieval?.recall_at_5)}
                          icon={<Search size={18} />}
                          detail="Expected source in the top five"
                        />
                        <Stat
                          label="Citation validity"
                          value={percent(generation?.citation_validity)}
                          icon={<ShieldCheck size={18} />}
                          detail="References to retrieved evidence"
                        />
                        <Stat
                          label="Abstention accuracy"
                          value={percent(generation?.abstention_accuracy)}
                          icon={<CheckCircle2 size={18} />}
                          detail="Supported vs. unsupported cases"
                        />
                        <Stat
                          label="Mean answer time"
                          value={duration(generation?.latency_ms)}
                          icon={<Clock3 size={18} />}
                          detail="Single-run workload measurement"
                        />
                      </>
                    );
                  })()}
                </div>
                <div className="two-column">
                  <section className="card report-card">
                    <div className="card-heading">
                      <h2>Retrieval, compared</h2>
                      <span className="soft-badge">Same questions</span>
                    </div>
                    <p className="card-subtitle">Recall @5 across the retrieval pipeline.</p>
                    <div className="metric-bars">
                      {Object.entries(selectedRun.report.retrieval || {}).map(([name, metrics]) => (
                        <MetricBar
                          key={name}
                          name={
                            name === 'reranked'
                              ? 'Hybrid + reranker'
                              : name === 'hybrid'
                                ? 'Hybrid RRF'
                                : name === 'dense'
                                  ? 'Dense embeddings'
                                  : 'Lexical search'
                          }
                          value={metrics.recall_at_5 || 0}
                        />
                      ))}
                    </div>
                    <div className="report-note">
                      MRR measures how early the expected document appears. Recall alone does not
                      establish answer correctness.
                    </div>
                  </section>
                  <section className="card report-card">
                    <div className="card-heading">
                      <h2>Base vs. grounding adapter</h2>
                      <FlaskConical size={17} />
                    </div>
                    <p className="card-subtitle">
                      Behavior measured on independently held-out cases.
                    </p>
                    <table className="comparison-table">
                      <thead>
                        <tr>
                          <th>Metric</th>
                          <th>Base</th>
                          <th>Adapted</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(
                          [
                            ['citation_validity', 'Citation validity'],
                            ['fact_coverage', 'Reference fact coverage'],
                            ['abstention_accuracy', 'Abstention accuracy'],
                          ] as const
                        ).map(([key, label]) => (
                          <tr key={key}>
                            <td>{label}</td>
                            <td>{percent(selectedRun.report.generation?.base?.[key])}</td>
                            <td>{percent(selectedRun.report.generation?.adapted?.[key])}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="report-note">
                      Fact coverage is a lexical proxy against reference facts, not a semantic
                      faithfulness score.
                    </div>
                  </section>
                </div>
                <section className="card examples-card">
                  <div className="card-heading">
                    <h2>Inspect individual cases</h2>
                    <span className="soft-badge">Transparent results</span>
                  </div>
                  {selectedRun.report.examples?.slice(0, 16).map((example, index) => (
                    <details className="evaluation-example" key={index}>
                      <summary>
                        <span className={`case-dot ${example.citation_valid ? 'ready' : ''}`} />
                        <span dir="auto">{example.question}</span>
                        <small>{example.mode || 'retrieval'}</small>
                        <ChevronDown size={15} />
                      </summary>
                      <div>
                        <label>Reference</label>
                        <p dir="auto">{example.expected}</p>
                        <label>Generated answer</label>
                        <p dir="auto">
                          {example.answer || 'No generation recorded for this case.'}
                        </p>
                      </div>
                    </details>
                  ))}
                </section>
                <p className="evaluation-disclaimer">
                  {selectedRun.report.limitation ||
                    'Recorded fixture results establish only this workload. Review responses with domain experts before deployment.'}
                </p>
              </>
            ) : (
              <section className="card empty-report">
                <Empty
                  icon={<Activity size={30} />}
                  title="Make quality measurable"
                  text="Run the evaluation suite to compare lexical, dense, hybrid, and reranked retrieval—then inspect base and adapted answers."
                  action={
                    <button
                      className="secondary-button"
                      onClick={() => void copy('python -m atlas_rag.evaluate --mode all')}
                    >
                      <Copy size={15} />
                      Copy evaluation command
                    </button>
                  }
                />
                <div className="evaluation-steps">
                  <span>
                    <Search size={18} />
                    <strong>Retrieval quality</strong>Recall and reciprocal rank
                  </span>
                  <span>
                    <ShieldCheck size={18} />
                    <strong>Grounding behavior</strong>Citations and abstention
                  </span>
                  <span>
                    <Clock3 size={18} />
                    <strong>Measured latency</strong>Real end-to-end runs
                  </span>
                </div>
              </section>
            )}
          </main>
        )}

        {view === 'tuning' && (
          <main className="page-main">
            <div className="page-heading">
              <div>
                <span className="eyebrow">ADAPT THE BEHAVIOR</span>
                <h1>
                  A model that knows how to answer<span className="heading-dot">.</span>
                </h1>
                <p>
                  Fine-tune grounding, citations, and abstention. Keep changing facts in retrieval.
                </p>
              </div>
              <span
                className={`adapter-state ${workspace?.models.adapted_available ? 'loaded' : ''}`}
              >
                <span
                  className={`status-dot ${workspace?.models.adapted_available ? 'ready' : ''}`}
                />
                {workspace?.models.adapted_available
                  ? 'Grounding adapter loaded'
                  : 'Base model available'}
              </span>
            </div>
            <div className="tuning-flow">
              <div>
                <span className="flow-number">01</span>
                <strong>Curate</strong>
                <small>Context + question + grounded answer</small>
              </div>
              <ChevronRight size={18} />
              <div>
                <span className="flow-number">02</span>
                <strong>Adapt</strong>
                <small>Response-only LoRA supervision</small>
              </div>
              <ChevronRight size={18} />
              <div>
                <span className="flow-number">03</span>
                <strong>Evaluate</strong>
                <small>Held-out scenarios and base comparison</small>
              </div>
              <ChevronRight size={18} />
              <div>
                <span className="flow-number">04</span>
                <strong>Serve</strong>
                <small>Use the adapter inside the RAG pipeline</small>
              </div>
            </div>
            <div className="two-column tuning-columns">
              <section className="card report-card">
                <div className="card-heading">
                  <h2>Grounding dataset</h2>
                  <Database size={18} />
                </div>
                <p className="card-subtitle">
                  Original bilingual examples with supported, unsupported, and adversarial contexts.
                </p>
                <div className="dataset-counts">
                  {['train', 'validation', 'test'].map((split) => (
                    <div key={split}>
                      <strong>{training?.counts[split] || 0}</strong>
                      <span>{split}</span>
                    </div>
                  ))}
                </div>
                <div className="dataset-split">
                  <span className="train" />
                  <span className="validation" />
                  <span className="test" />
                </div>
                <div className="info-row">
                  <CheckCircle2 size={15} />
                  <span>Scenario groups stay in a single split</span>
                </div>
                <div className="info-row">
                  <CheckCircle2 size={15} />
                  <span>English and Arabic, with explicit source references</span>
                </div>
                <div className="info-row">
                  <ShieldCheck size={15} />
                  <span>Synthetic fixture · no real customer records</span>
                </div>
                <button
                  className="secondary-button full"
                  onClick={() =>
                    void download('/training/dataset', 'atlas-grounding-train.jsonl').catch(
                      (error) => notify(errorText(error)),
                    )
                  }
                >
                  <ArrowDownToLine size={15} />
                  Download training JSONL
                </button>
              </section>
              <section className="card report-card">
                <div className="card-heading">
                  <h2>Training configuration</h2>
                  <span className="soft-badge">LoRA / QLoRA</span>
                </div>
                <div className="configuration-list">
                  <div>
                    <span>Base model</span>
                    <strong>{workspace?.models.base.split('/').at(-1) || 'Loading…'}</strong>
                  </div>
                  <div>
                    <span>Adaptation</span>
                    <strong>Rank 8 · query / value projections</strong>
                  </div>
                  <div>
                    <span>Training objective</span>
                    <strong>Response tokens only</strong>
                  </div>
                  <div>
                    <span>Reproducibility</span>
                    <strong>Dataset hashes · model revision · seed</strong>
                  </div>
                </div>
                <div className="command-card">
                  <span>TRAIN OUTSIDE THE SERVING PROCESS</span>
                  <code>
                    {training?.command || 'python -m atlas_rag.training --steps 64 --grad-accum 1'}
                  </code>
                  <button
                    className="icon-button"
                    aria-label="Copy training command"
                    onClick={() =>
                      void copy(
                        training?.command ||
                          'python -m atlas_rag.training --steps 64 --grad-accum 1',
                      )
                    }
                  >
                    <Copy size={15} />
                  </button>
                </div>
                <p className="fine-print">
                  Use <code>--qlora</code> with a compatible CUDA GPU. Restart model serving after
                  registering a new adapter.
                </p>
              </section>
            </div>
            <section className="card training-chart-card">
              <div className="card-heading">
                <div>
                  <h2>{trainingRun?.name || 'Training history'}</h2>
                  <p className="card-subtitle">
                    {trainingRun
                      ? 'Recorded response-token training loss'
                      : 'Training curves appear when an actual run is registered.'}
                  </p>
                </div>
                {trainingRun && (
                  <span className="document-status ready">
                    <CheckCircle2 size={12} />
                    Recorded run
                  </span>
                )}
              </div>
              <MiniChart values={trainingRun?.report.losses || []} />
              {trainingRun && (
                <div className="training-run-stats">
                  <span>
                    <small>Optimizer steps</small>
                    <strong>{trainingRun.report.steps}</strong>
                  </span>
                  <span>
                    <small>Trainable parameters</small>
                    <strong>{trainingRun.report.trainable_parameters?.toLocaleString()}</strong>
                  </span>
                  <span>
                    <small>Base validation loss</small>
                    <strong>{trainingRun.report.base_validation_loss?.toFixed(3) || '—'}</strong>
                  </span>
                  <span>
                    <small>Adapter validation loss</small>
                    <strong>{trainingRun.report.validation_loss?.toFixed(3) || '—'}</strong>
                  </span>
                </div>
              )}
            </section>
            <div className="method-note">
              <ShieldCheck size={19} />
              <div>
                <strong>Fine-tuning teaches a behavior. Retrieval supplies the facts.</strong>
                <p>
                  The adapter learns to use evidence, cite it, and decline unsupported questions.
                  Updating a document changes retrievable knowledge without retraining the model.
                </p>
              </div>
            </div>
          </main>
        )}
      </div>

      {toast && (
        <div className="toast" role="status">
          <span>{toast}</span>
          <button aria-label="Dismiss notification" onClick={() => setToast('')}>
            <X size={14} />
          </button>
        </div>
      )}
      {uploadOpen && (
        <Modal
          title="Add knowledge sources"
          subtitle="Bring your documents into the conversation."
          close={() => {
            if (!uploading) setUploadOpen(false);
          }}
        >
          <label className="field-label">
            Collection
            <select
              value={uploadCollection}
              onChange={(event) => setUploadCollection(event.target.value)}
            >
              <option value="" disabled>
                Choose a collection
              </option>
              {workspace?.collections.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label
            className={`dropzone ${uploading ? 'busy' : ''}`}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              if (!uploading) void upload(event.dataTransfer.files);
            }}
          >
            <input
              type="file"
              aria-label="Choose documents"
              accept=".pdf,.md,.txt"
              multiple
              disabled={!!uploading}
              onChange={(event) => {
                if (event.target.files) void upload(event.target.files);
              }}
            />
            <span className="upload-emblem">
              {uploading ? <Loader2 size={25} className="spin" /> : <UploadCloud size={25} />}
            </span>
            <strong>{uploading || 'Drop your files here, or browse'}</strong>
            <span>PDF, Markdown, or text · up to 10 MB per file</span>
          </label>
          <div className="upload-info">
            <ShieldCheck size={17} />
            <p>
              Files stay within your workspace. Extraction and indexing happen in the background;
              duplicate uploads are detected automatically.
            </p>
          </div>
          {!workspace?.collections.length && (
            <button
              className="secondary-button full"
              onClick={() => {
                setUploadOpen(false);
                setNewCollectionOpen(true);
              }}
            >
              <Plus size={15} />
              Create a collection first
            </button>
          )}
        </Modal>
      )}
      {newCollectionOpen && (
        <Modal
          title="Create a collection"
          subtitle="Organize sources around a team, product, or topic."
          close={() => setNewCollectionOpen(false)}
        >
          <form
            className="stack-form"
            onSubmit={async (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              try {
                const result = await api<{ id: string }>('/collections', 'POST', {
                  name: data.get('name'),
                  description: data.get('description'),
                  color: data.get('color'),
                });
                setUploadCollection(result.id);
                setNewCollectionOpen(false);
                await refresh();
                notify('Collection created. Add sources whenever you’re ready.');
              } catch (error) {
                notify(errorText(error));
              }
            }}
          >
            <label className="field-label">
              Name
              <input
                name="name"
                required
                maxLength={120}
                placeholder="e.g. Product documentation"
                autoFocus
              />
            </label>
            <label className="field-label">
              Description
              <textarea
                name="description"
                maxLength={500}
                placeholder="What belongs in this collection?"
                rows={3}
              />
            </label>
            <label className="field-label">
              Color
              <select name="color">
                <option value="indigo">Indigo</option>
                <option value="teal">Teal</option>
                <option value="amber">Amber</option>
                <option value="rose">Rose</option>
              </select>
            </label>
            <button className="primary-button">
              <Plus size={15} />
              Create collection
            </button>
          </form>
        </Modal>
      )}
      {preview && (
        <Modal
          title={preview.title}
          subtitle={`${preview.filename} · ${preview.pages} page${preview.pages !== 1 ? 's' : ''} · ${preview.chunk_count} passages`}
          close={() => setPreview(null)}
          wide
        >
          <div className="preview-meta">
            <span className={`document-status ${preview.status}`}>{preview.status}</span>
            <button
              className="secondary-button"
              onClick={() =>
                void download(`/documents/${preview.id}/download`, preview.filename).catch(
                  (error) => notify(errorText(error)),
                )
              }
            >
              <Download size={14} />
              Download original
            </button>
          </div>
          {preview.error && <div className="error-box">{preview.error}</div>}
          <div className="document-passages">
            {preview.passages.map((passage, i) => (
              <article key={passage.id}>
                <div>
                  <span>PASSAGE {i + 1}</span>
                  <small>Page {passage.page}</small>
                </div>
                <p dir="auto">{passage.text}</p>
              </article>
            ))}
            {!preview.passages.length && (
              <p className="muted">Passages appear when indexing finishes.</p>
            )}
          </div>
        </Modal>
      )}
      {traceOpen && activeMessage && (
        <Modal
          title="Inside this answer"
          subtitle="Inspect the retrieval path and measured runtime."
          close={() => setTraceOpen(false)}
          wide
        >
          <div className="trace-metrics">
            <Stat
              label="Total time"
              value={duration(activeMessage.trace.total_ms)}
              icon={<Clock3 size={16} />}
              detail="Retrieval + generation"
            />
            <Stat
              label="Retrieval"
              value={duration(activeMessage.trace.retrieval_ms)}
              icon={<Search size={16} />}
              detail={`${activeMessage.trace.candidate_count || 0} candidates`}
            />
            <Stat
              label="First token"
              value={duration(activeMessage.trace.ttft_ms)}
              icon={<Activity size={16} />}
              detail="From request processing"
            />
          </div>
          <div className="trace-query">
            <label>Retrieval query</label>
            <p dir="auto">{activeMessage.trace.retrieval_query}</p>
            <small>
              {activeMessage.trace.model} · {activeMessage.trace.mode} ·{' '}
              {activeMessage.trace.prompt_tokens ?? '—'} input tokens
            </small>
          </div>
          <div className="trace-table-scroll">
            <table className="trace-table">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Dense</th>
                  <th>RRF</th>
                  <th>Reranker</th>
                </tr>
              </thead>
              <tbody>
                {activeMessage.trace.candidates?.map((candidate, i) => (
                  <tr key={candidate.chunk_id}>
                    <td>
                      {i + 1}. {candidate.title}
                    </td>
                    <td>{candidate.dense_score.toFixed(3)}</td>
                    <td>{candidate.fusion_score.toFixed(4)}</td>
                    <td>{candidate.rerank_score.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="fine-print">
            Reranker outputs are relevance logits, not calibrated confidence percentages. Valid
            reference IDs do not prove semantic faithfulness.
          </p>
        </Modal>
      )}
      {settingsOpen && (
        <Modal
          title="Workspace configuration"
          subtitle="Your active retrieval and generation setup."
          close={() => setSettingsOpen(false)}
        >
          <div className="configuration-list settings-list">
            <div>
              <span>Identity</span>
              <strong>
                {workspace?.identity.auth_mode === 'local'
                  ? 'Local computer · workspace owner'
                  : 'Verified OIDC workspace'}
              </strong>
            </div>
            <div>
              <span>Language model</span>
              <strong>{workspace?.models.base}</strong>
            </div>
            <div>
              <span>Embedding model</span>
              <strong>{workspace?.models.embedding}</strong>
            </div>
            <div>
              <span>Reranker</span>
              <strong>{workspace?.models.reranker}</strong>
            </div>
            <div>
              <span>Serving backend</span>
              <strong>{workspace?.models.backend}</strong>
            </div>
            <div>
              <span>Grounding adapter</span>
              <strong>
                {workspace?.models.adapted_available ? 'Loaded and available' : 'Not loaded'}
              </strong>
            </div>
          </div>
          <div className="method-note compact">
            <ShieldCheck size={18} />
            <p>
              Local mode is restricted to this computer. Public deployments require verified
              workspace identity and production configuration.
            </p>
          </div>
          <a className="secondary-button full" href="/docs" target="_blank" rel="noreferrer">
            Explore the API
            <ArrowUpRight size={15} />
          </a>
        </Modal>
      )}
      {connectionOpen && (
        <Modal
          title="Connect your workspace"
          subtitle="Use an access token issued by your organization's identity provider."
          close={() => setConnectionOpen(false)}
        >
          <form
            className="stack-form"
            onSubmit={async (event) => {
              event.preventDefault();
              connectToken(tokenInput);
              setTokenInput('');
              setConnectionOpen(false);
              await refresh();
            }}
          >
            <label className="field-label">
              Workspace access token
              <input
                type="password"
                autoComplete="off"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
                required
              />
            </label>
            <p className="fine-print">
              The token is held in page memory and is never saved to browser storage.
            </p>
            <button className="primary-button">
              Connect workspace
              <ArrowUpRight size={15} />
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  icon,
  detail,
}: {
  label: string;
  value: number | string;
  icon: ReactNode;
  detail: string;
}) {
  return (
    <div className="stat-card">
      <div>
        <span>{label}</span>
        <span className="stat-icon">{icon}</span>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
function Empty({
  icon,
  title,
  text,
  action,
}: {
  icon: ReactNode;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon}</span>
      <h2>{title}</h2>
      <p>{text}</p>
      {action}
    </div>
  );
}
function MetricBar({ name, value }: { name: string; value: number }) {
  return (
    <div className="metric-bar">
      <div>
        <span>{name}</span>
        <strong>{percent(value)}</strong>
      </div>
      <div className="bar-track">
        <span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      </div>
    </div>
  );
}
