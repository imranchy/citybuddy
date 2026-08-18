"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import AssistantPlaceCard from "@/components/AssistantPlaceCard";
import { sendAssistantMessage } from "@/lib/api";
import type { AssistantChatResponse, ConversationMessage } from "@/types/assistant";
import { LANGUAGE_OPTIONS, type Language } from "@/types/language";

type SuggestedSearch = { label: string; query: string };
type AssistantTurn = { id: number; question: string; language: Language; response: AssistantChatResponse };
type UserLocation = { latitude: number; longitude: number };
type Props = { suggestions: SuggestedSearch[]; isApiConnected: boolean };

const copy = {
  en: {
    input: "Ask about museums, parks, food, nightlife or places nearby…",
    send: "Send", thinking: "Thinking…", you: "You",
    locate: "Use my location", locating: "Locating…", ready: "Location ready",
    remove: "Remove location", reset: "New conversation", empty: "Tell CityBuddy what you would like to discover.",
    offline: "CityBuddy is offline. Start the backend and try again.", failure: "I could not complete that request. Please try again.",
    locationUsed: "Location is ready for nearby searches.", locationFailed: "Location permission was unavailable.",
  },
  it: {
    input: "Chiedi di musei, parchi, ristoranti, vita notturna o luoghi vicini…",
    send: "Invia", thinking: "Sto cercando…", you: "Tu",
    locate: "Usa la mia posizione", locating: "Localizzazione…", ready: "Posizione pronta",
    remove: "Rimuovi posizione", reset: "Nuova conversazione", empty: "Racconta a CityBuddy cosa vorresti scoprire.",
    offline: "CityBuddy non è disponibile. Avvia il backend e riprova.", failure: "Non sono riuscito a completare la richiesta. Riprova.",
    locationUsed: "La posizione è pronta per le ricerche nelle vicinanze.", locationFailed: "Non è stato possibile accedere alla posizione.",
  },
} as const;

function history(turns: AssistantTurn[]): ConversationMessage[] {
  return turns.flatMap((turn) => [
    { role: "user" as const, content: turn.question },
    { role: "assistant" as const, content: [turn.response.answer, ...turn.response.recommendations.map((item) => `${item.place.name}: ${item.reason}`)].join("\n").slice(0, 2000) },
  ]).slice(-10);
}

export default function AssistantChat({ suggestions, isApiConnected }: Props) {
  const [language, setLanguage] = useState<Language>("en");
  const [query, setQuery] = useState("");
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [message, setMessage] = useState("");
  const [location, setLocation] = useState<UserLocation | null>(null);
  const [isLocating, setIsLocating] = useState(false);
  const nextId = useRef(1);
  const controller = useRef<AbortController | null>(null);
  const transcript = useRef<HTMLDivElement | null>(null);
  // The selector controls assistant output language. UI chrome stays on the
  // existing English/Italian localization until broader UI localization is added.
  const t = copy[language === "it" ? "it" : "en"];

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (turns.length) transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: "smooth" });
  }, [turns, isSending]);

  async function submitText(text: string) {
    const question = text.trim();
    if (!question) return setMessage(t.empty);
    if (!isApiConnected) return setMessage(t.offline);
    controller.current?.abort();
    const active = new AbortController();
    controller.current = active;
    setIsSending(true); setMessage("");
    try {
      const previousIds = turns.at(-1)?.response.recommendations.map((item) => item.place.id) ?? [];
      const response = await sendAssistantMessage({
        message: question,
        language,
        history: history(turns),
        context_place_ids: previousIds,
        ...(location ? location : {}),
      }, active.signal);
      setTurns((current) => [...current, { id: nextId.current++, question, language, response }]);
      setQuery("");
    } catch (error) {
      if (!(error instanceof Error && error.name === "AbortError")) setMessage(t.failure);
    } finally {
      if (controller.current === active) { controller.current = null; setIsSending(false); }
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void submitText(query); }

  function locate() {
    if (!navigator.geolocation) return setMessage(t.locationFailed);
    setIsLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => { setLocation({ latitude: position.coords.latitude, longitude: position.coords.longitude }); setMessage(t.locationUsed); setIsLocating(false); },
      () => { setMessage(t.locationFailed); setIsLocating(false); },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
    );
  }

  const composer = (
    <form onSubmit={submit} className="border-t border-white/10 bg-[#121936] p-3">
      <div className="flex gap-2">
        <label htmlFor="city-search" className="sr-only">{t.input}</label>
        <textarea id="city-search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder={t.input} rows={1} maxLength={2000} disabled={isSending} className="min-h-12 flex-1 resize-none rounded-xl border border-white/10 bg-[#0B112B] px-4 py-3 text-[#FFF8E7] outline-none placeholder:text-[#A9B1D6]/60 focus:border-[#FF6846]" />
        <button disabled={isSending || !isApiConnected} className="rounded-xl bg-[#FF6846] px-5 font-semibold text-[#070B24] disabled:opacity-50">{isSending ? t.thinking : t.send}</button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select aria-label="Language" value={language} onChange={(event) => setLanguage(event.target.value as Language)} className="rounded-full border border-white/10 bg-[#0B112B] px-3 py-2 text-xs text-[#FFF8E7]">{LANGUAGE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
        <button type="button" onClick={locate} disabled={isLocating} className="rounded-full border border-[#FFC83D]/30 px-3 py-2 text-xs text-[#FFC83D]">{isLocating ? t.locating : location ? t.ready : t.locate}</button>
        {location && <button type="button" onClick={() => setLocation(null)} className="rounded-full border border-white/10 px-3 py-2 text-xs text-[#A9B1D6]">{t.remove}</button>}
        {turns.length > 0 && <button type="button" onClick={() => { setTurns([]); setQuery(""); setMessage(""); }} className="ml-auto rounded-full border border-white/10 px-3 py-2 text-xs text-[#A9B1D6]">{t.reset}</button>}
      </div>
    </form>
  );

  return (
    <div className="mx-auto mt-10 max-w-5xl text-left">
      <section aria-label="CityBuddy conversation" className="overflow-hidden rounded-3xl border border-white/10 bg-[#121936] shadow-2xl">
        {turns.length === 0 ? (
          <div className="p-3">
            <div className="flex gap-2 overflow-x-auto px-2 pb-3">{suggestions.map((item) => <button key={item.label} type="button" onClick={() => setQuery(item.query)} className="shrink-0 rounded-full border border-white/10 px-3 py-2 text-xs text-[#A9B1D6] hover:text-[#FFF8E7]">{item.label}</button>)}</div>
            {composer}
          </div>
        ) : (
          <>
            <div ref={transcript} className="max-h-[68vh] space-y-6 overflow-y-auto p-4 sm:p-6">
              {turns.map((turn) => (
                <article key={turn.id} className="space-y-3">
                  <div className="ml-auto max-w-2xl rounded-2xl rounded-br-md bg-[#FF6846] px-4 py-3 text-[#070B24]"><p className="text-[11px] font-bold uppercase tracking-wider opacity-70">{t.you}</p><p className="mt-1">{turn.question}</p></div>
                  <div className="max-w-3xl rounded-2xl rounded-tl-md border border-white/10 bg-[#0B112B]/60 p-4">
                    <div className="flex items-center"><span className="text-xs font-semibold uppercase tracking-wider text-[#FFC83D]">CityBuddy</span></div>
                    <p className="mt-3 leading-7">{turn.response.answer}</p>
                    {turn.response.transport_disclaimer && <p className="mt-3 rounded-xl border border-[#FFC83D]/20 bg-[#FFC83D]/10 p-3 text-sm leading-6">{turn.response.transport_disclaimer}</p>}
                    {turn.response.warnings.map((warning) => <p key={warning} className="mt-2 text-xs text-amber-200">{warning}</p>)}
                  </div>
                  {turn.response.recommendations.length > 0 && <div className="grid max-w-3xl gap-3 sm:grid-cols-2">{turn.response.recommendations.map((item) => <AssistantPlaceCard key={item.place.id} recommendation={item} language={turn.language} />)}</div>}
                </article>
              ))}
              {isSending && <p role="status" className="text-sm text-[#A9B1D6]">{t.thinking}</p>}
            </div>
            <div className="sticky bottom-0">{composer}</div>
          </>
        )}
      </section>
      {message && <p role="status" className="mt-3 text-sm text-[#A9B1D6]">{message}</p>}
    </div>
  );
}
