"use client";

import { useEffect, useState, useCallback, useRef } from "react";

interface SegmentMicInputProps {
  onResult: (text: string) => void;
  disabled?: boolean;
  language?: string;
}

export default function SegmentMicInput({
  onResult,
  disabled = false,
  language = "te-IN",
}: SegmentMicInputProps) {
  const [listening, setListening] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<any>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  // cleanup on unmount
  useEffect(() => {
    return () => {
      try { recRef.current?.stop(); } catch {}
    };
  }, []);

  const handleClick = useCallback(() => {
    if (listening) {
      try { recRef.current?.stop(); } catch {}
      setListening(false);
      return;
    }

    const SpeechRecognitionAPI =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognitionAPI) {
      setError("Speech recognition not supported");
      setTimeout(() => setError(null), 2000);
      return;
    }

    // stop any other instance that might be running
    if (recRef.current) {
      try { recRef.current.stop(); } catch {}
    }

    const recognition = new SpeechRecognitionAPI();
    recognition.lang = language;
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: any) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim();
      if (transcript) onResult(transcript);
      setListening(false);
      recRef.current = null;
    };

    recognition.onerror = (event: any) => {
      if (event.error !== "aborted") {
        setError(event.error === "not-allowed" ? "Microphone permission denied" : event.error);
        setTimeout(() => setError(null), 2000);
      }
      setListening(false);
      recRef.current = null;
    };

    recognition.onend = () => {
      setListening(false);
      recRef.current = null;
    };

    recRef.current = recognition;

    try {
      recognition.start();
      setListening(true);
    } catch {
      setError("Failed to start microphone");
      setTimeout(() => setError(null), 2000);
      setListening(false);
      recRef.current = null;
    }
  }, [listening, language, onResult]);

  if (!mounted) {
    return (
      <button
        disabled
        style={{
          width: 28, height: 28, borderRadius: 6,
          border: "1px solid var(--gray-200)", background: "var(--white)",
          color: "var(--gray-500)", cursor: "not-allowed", fontSize: 12,
          display: "flex", alignItems: "center", justifyContent: "center", opacity: 0.5,
        }}
        aria-label="Loading microphone"
      >
        🎤
      </button>
    );
  }

  return (
    <>
      {listening && (
        <style>{`
          @keyframes mic-pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(244, 63, 94, 0.4); }
            50% { box-shadow: 0 0 0 6px rgba(244, 63, 94, 0); }
          }
        `}</style>
      )}
      <button
        onClick={handleClick}
        disabled={disabled}
        title={
          error
            ? error
            : listening
              ? "Stop listening"
              : "Speak correction"
        }
        style={{
          width: 28, height: 28, borderRadius: 6,
          border: "1px solid var(--gray-200)",
          background: listening ? "var(--rose)" : "var(--white)",
          color: listening ? "#fff" : "var(--gray-500)",
          cursor: disabled ? "not-allowed" : "pointer",
          fontSize: 12,
          display: "flex", alignItems: "center", justifyContent: "center",
          opacity: disabled && !listening ? 0.5 : 1,
          animation: listening ? "mic-pulse 1.5s ease-in-out infinite" : "none",
          transition: "background 0.15s, color 0.15s",
        }}
        aria-label={listening ? "Stop listening" : "Speak correction"}
      >
        {listening ? "⏹" : "🎤"}
      </button>
    </>
  );
}
