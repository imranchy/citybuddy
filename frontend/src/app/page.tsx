"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";
import AssistantChat from "@/components/AssistantChat";
import PlacesSection from "@/components/PlacesSection";
import { PAGE_COPY } from "@/lib/i18n";
import { LANGUAGE_OPTIONS, type Language } from "@/types/language";

export default function Home() {
  const [isApiConnected, setIsApiConnected] = useState(false);
  const [language, setLanguage] = useState<Language>("en");
  const t = PAGE_COPY[language];

  useEffect(() => {
    const controller = new AbortController();

    async function loadHealth() {
      try {
        await getHealth(controller.signal);
        setIsApiConnected(true);
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }

        setIsApiConnected(false);
      }
    }

    loadHealth();

    return () => controller.abort();
  }, []);

  useEffect(() => {
    const saved = window.localStorage.getItem("citybuddy-language") as Language | null;
    if (saved && LANGUAGE_OPTIONS.some((option) => option.value === saved)) {
      setLanguage(saved);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem("citybuddy-language", language);
    document.documentElement.lang = language;
  }, [language]);

  return (
    <main className="min-h-screen bg-[#070B24] text-[#FFF8E7]">
      <nav className="border-b border-white/10">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6 sm:py-5">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <Image
              src="/citybuddy-city-badge-logo.png"
              alt="CityBuddy city guide"
              width={96}
              height={64}
              preload
              className="h-11 w-auto object-contain sm:h-14"
            />

            <div>
              <p className="text-lg font-bold tracking-tight text-[#FFF8E7] sm:text-xl">
                CityBuddy
              </p>

              <p className="text-xs font-medium text-[#FF6846]">
                {t.city}
              </p>
            </div>
          </div>

          <label className="flex items-center gap-2 rounded-full border border-white/10 bg-[#0B112B] px-3 py-2 text-sm text-[#FFF8E7]">
            <span aria-hidden="true" className="text-base">🌐</span>
            <span className="hidden text-xs font-semibold uppercase tracking-wider text-[#A9B1D6] sm:inline">{t.language}</span>
            <select
              aria-label={t.language}
              value={language}
              onChange={(event) => setLanguage(event.target.value as Language)}
              className="bg-transparent text-sm font-medium outline-none"
            >
              {LANGUAGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value} className="bg-[#0B112B]">
                  {option.flag} {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </nav>

      <section
        aria-labelledby="hero-heading"
        className="relative overflow-hidden px-4 py-16 sm:px-6 sm:py-20 md:py-28"
      >
        <div
          aria-hidden="true"
          className="absolute left-1/2 top-20 h-72 w-72 -translate-x-1/2 rounded-full bg-[#FF6846]/15 blur-3xl"
        />

        <div className="relative mx-auto max-w-4xl text-center">
          <p className="mb-5 text-xs font-semibold uppercase tracking-[0.25em] text-[#FFC83D] sm:text-sm sm:tracking-[0.3em]">
            {t.eyebrow}
          </p>

          <h1
            id="hero-heading"
            className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl md:text-7xl"
          >
            {t.titleA}
            <span className="block text-[#FF6846]">
              {t.titleB}
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-[#A9B1D6] sm:mt-7 sm:text-lg sm:leading-8">
            {t.description}
          </p>

          <AssistantChat
            suggestions={t.suggestions}
            isApiConnected={isApiConnected}
            language={language}
          />
        </div>
      </section>

      <PlacesSection language={language} />

      <section
        aria-labelledby="features-heading"
        className="border-t border-white/10 bg-[#070B24] px-4 py-14 sm:px-6 sm:py-16"
      >
        <div className="mx-auto max-w-6xl">
          <h2 id="features-heading" className="sr-only">
            CityBuddy features
          </h2>

          <div className="grid gap-5 md:grid-cols-3">
            {t.features.map((feature) => (
              <article
                key={feature.title}
                className="rounded-3xl border border-white/10 bg-[#121936] p-6 transition duration-200 hover:-translate-y-1 hover:border-[#FF6846]/40 sm:p-7"
              >
                <div
                  aria-hidden="true"
                  className="mb-5 flex h-11 w-11 items-center justify-center rounded-2xl bg-[#FF6846]/15 text-xl font-bold text-[#FF6846]"
                >
                  {feature.icon}
                </div>

                <h3 className="text-xl font-semibold text-[#FFF8E7]">
                  {feature.title}
                </h3>

                <p className="mt-3 leading-7 text-[#A9B1D6]">
                  {feature.description}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-white/10 px-4 py-8 text-center text-sm text-[#A9B1D6] sm:px-6">
        {t.footer}
      </footer>
    </main>
  );
}
