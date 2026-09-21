import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE } from './config';

// ---------------------------------------------------------------------------
// Dictation: Web Speech recognition when the runtime offers it, polished
// through POST /api/voice/polish before insertion. Final transcripts are
// delivered via onFinalText; interim results surface for live feedback.
// Unsupported runtimes report supported:false so callers render nothing.
// ---------------------------------------------------------------------------

export interface DictationState {
  supported: boolean;
  listening: boolean;
  interim: string;
  error: string | null;
}

interface RecognitionInstance {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

function getRecognitionConstructor(): (new () => RecognitionInstance) | null {
  if (typeof window === 'undefined') return null;
  const w = window as any;
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function isDictationSupported(): boolean {
  return getRecognitionConstructor() !== null;
}

export async function polishDictation(text: string, context?: string): Promise<string> {
  try {
    const res = await fetch(`${API_BASE}/voice/polish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, context: context || undefined }),
    });
    if (!res.ok) return text;
    const data = await res.json().catch(() => ({}));
    return typeof data?.text === 'string' && data.text ? data.text : text;
  } catch {
    return text;
  }
}

export function useDictation(onFinalText: (text: string) => void): DictationState & {
  start: () => void;
  stop: () => void;
} {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<RecognitionInstance | null>(null);
  const callbackRef = useRef(onFinalText);
  callbackRef.current = onFinalText;

  const stop = useCallback(() => {
    try {
      recognitionRef.current?.stop();
    } catch {
      // Already stopped.
    }
  }, []);

  const start = useCallback(() => {
    const Ctor = getRecognitionConstructor();
    if (!Ctor) {
      setError('Voice input is not supported in this runtime.');
      return;
    }
    try {
      recognitionRef.current?.abort();
    } catch {
      // Nothing live.
    }
    setError(null);
    setInterim('');
    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    recognition.onresult = (event: any) => {
      let interimText = '';
      const finals: string[] = [];
      for (let i = event.resultIndex ?? 0; i < (event.results?.length ?? 0); i += 1) {
        const result = event.results[i];
        const transcript = result?.[0]?.transcript ?? '';
        if (result?.isFinal) finals.push(transcript);
        else interimText += transcript;
      }
      setInterim(interimText);
      finals.forEach((text) => {
        if (text.trim()) callbackRef.current(text);
      });
    };
    recognition.onerror = (event: any) => {
      const kind = event?.error;
      if (kind === 'not-allowed' || kind === 'service-not-allowed') {
        setError('Microphone access was denied.');
      } else if (kind !== 'aborted' && kind !== 'no-speech') {
        setError('Voice input hit an error. Try again.');
      }
      setListening(false);
    };
    recognition.onend = () => {
      setListening(false);
      setInterim('');
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
      setListening(true);
    } catch {
      setError('Could not start voice input.');
      setListening(false);
    }
  }, []);

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.abort();
      } catch {
        // Unmounting anyway.
      }
      recognitionRef.current = null;
    };
  }, []);

  return { supported: isDictationSupported(), listening, interim, error, start, stop };
}
