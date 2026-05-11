'use client';

import { useEffect, useRef, useState } from 'react';
import { useJarvis } from '../lib/jarvis';
import type { AnalyticsSummary } from '../types/jarvis';

export default function Page() {
  const { status, transcript, startListening, stopListening, sendText } = useJarvis();
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [textInput, setTextInput] = useState('');
  const [pinned, setPinned] = useState(false);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.jarvis) return;
    const refresh = async () => {
      try {
        const summary = await window.jarvis.analytics.summary();
        setAnalytics(summary);
      } catch {
        // bridge not ready
      }
    };
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [transcript.length]);

  const orbLabel =
    status === 'listening' ? 'LISTENING' :
    status === 'thinking' ? 'THINKING' :
    status === 'speaking' ? 'SPEAKING' :
    status === 'error' ? 'ERROR' : 'STANDBY';

  return (
    <div className="app">
      <div className="titlebar">
        <span className="title">J · A · R · V · I · S</span>
        <div className="controls">
          <button
            onClick={async () => {
              const next = await window.jarvis?.window.togglePin();
              setPinned(!!next);
            }}
          >
            {pinned ? 'Unpin' : 'Pin'}
          </button>
          <button onClick={() => window.jarvis?.window.minimize()}>—</button>
          <button onClick={() => window.jarvis?.window.close()}>×</button>
        </div>
      </div>

      <div className="main">
        <div className="orb-stage">
          <div
            className={`orb ${status === 'listening' ? 'listening' : ''} ${status === 'speaking' ? 'speaking' : ''} ${status === 'error' ? 'error' : ''}`}
            onClick={() => (status === 'listening' ? stopListening() : startListening())}
          >
            <svg width="80" height="80" viewBox="0 0 80 80">
              <circle cx="40" cy="40" r="6" fill="currentColor" opacity="0.8" />
              <circle cx="40" cy="40" r="18" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.5" />
              <circle cx="40" cy="40" r="30" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.3" />
            </svg>
            <div className="orb-label">{orbLabel}</div>
          </div>
        </div>

        <div className="panel transcript" data-label="Transcript">
          {transcript.map((entry) => (
            <div key={entry.id} className={`bubble ${entry.role}`}>
              {entry.text}
            </div>
          ))}
          <div ref={transcriptEndRef} />
        </div>

        <form
          className="controls-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (!textInput.trim()) return;
            sendText(textInput);
            setTextInput('');
          }}
        >
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Type a command or question…"
            style={{
              flex: 1,
              background: 'rgba(0, 30, 50, 0.4)',
              border: '1px solid var(--jarvis-cyan-dim)',
              color: 'var(--jarvis-text)',
              padding: '6px 10px',
              fontFamily: 'inherit',
              fontSize: '12px',
              outline: 'none',
            }}
          />
          <button type="submit">Send</button>
          <button
            type="button"
            onClick={() => (status === 'listening' ? stopListening() : startListening())}
          >
            {status === 'listening' ? 'Stop' : 'Listen'}
          </button>
        </form>
      </div>

      <div className="sidebar">
        <div className="panel" data-label="Analytics">
          {analytics ? (
            <>
              <div className="metric-row"><span>Events tracked</span><span>{analytics.totalEvents}</span></div>
              <div className="metric-row"><span>Last 24h</span><span>{analytics.last24h}</span></div>
              {Object.entries(analytics.byKind).map(([kind, stats]) => (
                <div key={kind} style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 10, color: 'var(--jarvis-text-dim)', textTransform: 'uppercase', letterSpacing: '0.2em' }}>{kind}</div>
                  <div className="metric-row"><span>Total</span><span>{stats.total}</span></div>
                  <div className="metric-row"><span>Success</span><span>{Math.round(stats.successRate * 100)}%</span></div>
                  <div className="metric-row"><span>Avg latency</span><span>{stats.avgMs}ms</span></div>
                </div>
              ))}
            </>
          ) : (
            <div className="empty">Awaiting telemetry…</div>
          )}
        </div>

        <div className="panel" data-label="Recent Activity">
          {analytics && analytics.recentCommands.length > 0 ? (
            analytics.recentCommands.map((cmd, i) => (
              <div key={i} className="log-entry">
                <span className={cmd.ok ? 'status-ok' : 'status-fail'}>{cmd.ok ? '◉' : '✗'}</span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {cmd.intent || cmd.transcript || cmd.kind}
                </span>
              </div>
            ))
          ) : (
            <div className="empty">No activity yet.</div>
          )}
        </div>

        <div className="panel" data-label="Help">
          <div style={{ fontSize: 11, lineHeight: 1.6, color: 'var(--jarvis-text-dim)' }}>
            Try: <span style={{ color: 'var(--jarvis-cyan)' }}>"system status"</span>,{' '}
            <span style={{ color: 'var(--jarvis-cyan)' }}>"search for…"</span>,{' '}
            <span style={{ color: 'var(--jarvis-cyan)' }}>"run the outreach workflow"</span>,{' '}
            <span style={{ color: 'var(--jarvis-cyan)' }}>"remember that…"</span>, or just chat.
          </div>
        </div>
      </div>
    </div>
  );
}
