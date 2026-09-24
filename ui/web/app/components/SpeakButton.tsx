"use client";

import { useEffect, useId, useState } from "react";
import { ApiError, synthesizeSpeech } from "../lib/api";

let activeId = "";
const subscribers = new Set<() => void>();
let keepAlive: number | null = null;
let audio: HTMLAudioElement | null = null;
const objectUrls: string[] = [];

function notify() {
  subscribers.forEach((listener) => listener());
}

function stopSpeech() {
  window.speechSynthesis?.cancel();
  if (audio) {
    audio.pause();
    audio.src = "";
    audio = null;
  }
  while (objectUrls.length > 0) {
    const url = objectUrls.pop();
    if (url) URL.revokeObjectURL(url);
  }
  activeId = "";
  if (keepAlive !== null) {
    window.clearInterval(keepAlive);
    keepAlive = null;
  }
  notify();
}

function playBlob(blob: Blob): Promise<void> {
  const url = URL.createObjectURL(blob);
  objectUrls.push(url);
  return new Promise((resolve, reject) => {
    const player = new Audio(url);
    audio = player;
    player.onended = () => resolve();
    player.onerror = () => reject(new Error("could not play speech audio"));
    player.play().catch(reject);
  });
}

function chunks(text: string, size = 2800): string[] {
  const parts: string[] = [];
  let rest = text.trim();
  while (rest.length > size) {
    let cut = rest.lastIndexOf(". ", size);
    if (cut < size / 2) cut = size;
    else cut += 1;
    parts.push(rest.slice(0, cut).trim());
    rest = rest.slice(cut).trim();
  }
  if (rest) parts.push(rest);
  return parts;
}

interface Props {
  label: string;
  text: string;
}

export default function SpeakButton({ label, text }: Props) {
  const id = useId();
  const [active, setActive] = useState(false);
  const [unsupported, setUnsupported] = useState(false);
  const [fallbackNote, setFallbackNote] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => setActive(activeId === id);
    subscribers.add(sync);
    return () => {
      subscribers.delete(sync);
      if (activeId === id) stopSpeech();
    };
  }, [id]);

  const speakWithBrowser = (parts: string[]) => {
    const synth = window.speechSynthesis;
    if (!synth) {
      setUnsupported(true);
      stopSpeech();
      return;
    }
    parts.forEach((part, index) => {
      const utter = new SpeechSynthesisUtterance(part);
      const finish = () => {
        if (index === parts.length - 1 && activeId === id) stopSpeech();
      };
      utter.onend = finish;
      utter.onerror = finish;
      synth.speak(utter);
    });
    if (keepAlive === null) {
      keepAlive = window.setInterval(() => {
        if (!window.speechSynthesis?.speaking) return;
        window.speechSynthesis.pause();
        window.speechSynthesis.resume();
      }, 10000);
    }
  };

  const onClick = () => {
    if (activeId === id) {
      stopSpeech();
      return;
    }
    stopSpeech();
    activeId = id;
    setFallbackNote(null);
    notify();
    const parts = chunks(text);
    void (async () => {
      try {
        for (const part of parts) {
          if (activeId !== id) return;
          const blob = await synthesizeSpeech(part);
          if (activeId !== id) return;
          await playBlob(blob);
        }
        if (activeId === id) stopSpeech();
      } catch (err) {
        if (activeId !== id) return;
        const missingKey = err instanceof ApiError && err.status === 503;
        setFallbackNote(
          missingKey
            ? "Using the browser voice. Add OPENAI_API_KEY in Settings for a more natural voice."
            : "Natural voice failed. Using the browser voice.",
        );
        window.speechSynthesis?.cancel();
        speakWithBrowser(parts);
      }
    })();
  };

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={onClick}
        disabled={!text.trim()}
        aria-pressed={active}
        className={
          "rounded-md border px-2 py-1 text-xs font-medium " +
          (active
            ? "border-accent bg-accent text-white"
            : "border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-50")
        }
      >
        {active ? `Stop ${label.toLowerCase()}` : label}
      </button>
      {unsupported && (
        <span className="text-xs text-rose-700">
          Text to speech is not available in this browser.
        </span>
      )}
      {fallbackNote && (
        <span className="max-w-xs text-xs text-neutral-500">{fallbackNote}</span>
      )}
    </span>
  );
}
