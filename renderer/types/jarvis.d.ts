export type ChatMessage = { role: 'user' | 'assistant'; content: string };

export type ChatResult =
  | { ok: true; text: string; usage?: unknown; stop_reason?: string }
  | { ok: false; error: string };

export type AnalyticsSummary = {
  totalEvents: number;
  last24h: number;
  byKind: Record<string, { total: number; ok: number; failed: number; avgMs: number; successRate: number }>;
  recentCommands: Array<{ kind: string; ts: number; ok: boolean; transcript?: string; intent?: string }>;
};

export type SelfEditProposal = {
  id: string;
  request: string;
  summary: string;
  changes: Array<{ path: string; newContent: string }>;
  proposedAt: string;
};

export type JarvisBridge = {
  window: {
    minimize: () => Promise<void>;
    close: () => Promise<void>;
    togglePin: () => Promise<boolean>;
  };
  claude: {
    chat: (payload: { messages: ChatMessage[]; context?: Record<string, unknown> }) => Promise<ChatResult>;
  };
  memory: {
    get: (key: string) => Promise<unknown>;
    set: (key: string, value: unknown) => Promise<{ ok: true }>;
    learnPreference: (pref: Record<string, unknown>) => Promise<Record<string, unknown>>;
    learnAlias: (mapping: { spoken: string; intent: string }) => Promise<{ ok: true; count: number }>;
    resolveAlias: (spoken: string) => Promise<string | null>;
    exportAll: () => Promise<Record<string, unknown>>;
  };
  analytics: {
    summary: () => Promise<AnalyticsSummary>;
    record: (event: Record<string, unknown>) => Promise<{ ok: true }>;
  };
  system: {
    run: (command: string) => Promise<{ ok: boolean; stdout?: string; stderr?: string; error?: string; command: string }>;
    openUrl: (url: string) => Promise<{ ok: true }>;
  };
  selfEdit: {
    propose: (request: string) => Promise<{ ok: true; proposal: SelfEditProposal } | { ok: false; error: string }>;
    apply: (proposal: SelfEditProposal) => Promise<{ ok: boolean; error?: string; count?: number }>;
    history: () => Promise<unknown[]>;
  };
  workflow: {
    hubspotToOutreach: (params: { listId?: string; limit?: number; withCall?: boolean; withPostcard?: boolean }) => Promise<{ ok: boolean; processed?: number; succeeded?: number; failed?: number; error?: string }>;
  };
  onSummon: (callback: () => void) => () => void;
};

declare global {
  interface Window {
    jarvis: JarvisBridge;
    SpeechRecognition?: typeof SpeechRecognition;
    webkitSpeechRecognition?: typeof SpeechRecognition;
  }
}
