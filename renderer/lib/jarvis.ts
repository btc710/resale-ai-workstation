'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatMessage } from '../types/jarvis';
import { routeCommand } from './commands';

export type Status = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

export type TranscriptEntry = {
  id: number;
  role: 'user' | 'assistant' | 'system';
  text: string;
};

let nextId = 1;

export function useJarvis() {
  const [status, setStatus] = useState<Status>('idle');
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([
    { id: nextId++, role: 'system', text: 'Jarvis online. Click the orb or press Ctrl+Shift+J to speak.' },
  ]);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const historyRef = useRef<ChatMessage[]>([]);

  const append = useCallback((entry: Omit<TranscriptEntry, 'id'>) => {
    setTranscript((prev) => [...prev, { id: nextId++, ...entry }]);
  }, []);

  const speak = useCallback((text: string): Promise<void> => {
    return new Promise((resolve) => {
      if (!text || typeof window === 'undefined' || !window.speechSynthesis) {
        resolve();
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.05;
      utterance.pitch = 0.95;
      const voices = window.speechSynthesis.getVoices();
      const british = voices.find((v) => /en-GB|UK English/i.test(v.lang + ' ' + v.name));
      if (british) utterance.voice = british;
      setStatus('speaking');
      utterance.onend = () => {
        setStatus('idle');
        resolve();
      };
      utterance.onerror = () => {
        setStatus('idle');
        resolve();
      };
      window.speechSynthesis.speak(utterance);
    });
  }, []);

  const handleUserInput = useCallback(
    async (text: string) => {
      if (!text.trim()) return;
      append({ role: 'user', text });
      setStatus('thinking');

      // Try local command routing first (system commands, workflow triggers, etc.)
      const routed = await routeCommand(text);
      if (routed.handled) {
        append({ role: 'assistant', text: routed.reply });
        await window.jarvis.analytics.record({
          kind: 'command',
          ok: routed.ok ?? true,
          intent: routed.intent,
          transcript: text,
        });
        await speak(routed.reply);
        return;
      }

      // Otherwise, hand to Claude
      historyRef.current.push({ role: 'user', content: text });
      const result = await window.jarvis.claude.chat({
        messages: historyRef.current.slice(-20),
      });

      if (!result.ok) {
        const msg = `My apologies — ${result.error}`;
        append({ role: 'system', text: msg });
        setError(result.error);
        setStatus('error');
        await speak(msg);
        return;
      }

      historyRef.current.push({ role: 'assistant', content: result.text });
      append({ role: 'assistant', text: result.text });
      await speak(result.text);
    },
    [append, speak],
  );

  const startListening = useCallback(() => {
    if (typeof window === 'undefined') return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      const msg = 'Speech recognition not available in this browser. Try Chrome/Edge.';
      append({ role: 'system', text: msg });
      setError(msg);
      setStatus('error');
      return;
    }

    if (recognitionRef.current) {
      recognitionRef.current.abort();
    }

    const recognition = new SR();
    recognition.lang = 'en-US';
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setStatus('listening');
    recognition.onerror = (e: SpeechRecognitionErrorEvent) => {
      setStatus('error');
      setError(e.error);
      append({ role: 'system', text: `Voice error: ${e.error}` });
    };
    recognition.onend = () => {
      if (status === 'listening') setStatus('idle');
    };
    recognition.onresult = (e: SpeechRecognitionEvent) => {
      const text = e.results[0]?.[0]?.transcript || '';
      handleUserInput(text);
    };

    recognitionRef.current = recognition;
    recognition.start();
  }, [append, handleUserInput, status]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setStatus('idle');
  }, []);

  const sendText = useCallback(
    (text: string) => {
      handleUserInput(text);
    },
    [handleUserInput],
  );

  // Listen for the global hotkey summon event
  useEffect(() => {
    if (typeof window === 'undefined' || !window.jarvis) return;
    const unsub = window.jarvis.onSummon(() => {
      startListening();
    });
    return unsub;
  }, [startListening]);

  return {
    status,
    transcript,
    error,
    startListening,
    stopListening,
    sendText,
    clearError: () => setError(null),
  };
}
