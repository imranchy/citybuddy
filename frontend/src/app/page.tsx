"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";
import AssistantChat from "@/components/AssistantChat";
import PlacesSection from "@/components/PlacesSection";

const suggestedSearches = [
  {
    label: "Near me",
    query: "Interesting places near me",
  },
  {
    label: "Food & drink",
    query: "Good local food and drink",
  },
  {
    label: "Culture",
    query: "Museums, monuments and cultural attractions",
  },
  {
    label: "Outdoors",
    query: "Parks, gardens and viewpoints",
  },
  {
    label: "Places of worship",
    query: "Churches, mosques, temples and other places of worship",
  },
];

const features = [
  {
    icon: "⌖",
    title: "Location aware",
    description:
      "Find places based on your current location, neighbourhood or preferred search radius.",
  },
  {
    icon: "✦",
    title: "Personalised search",
    description:
      "Search naturally using your interests, location, budget, accessibility needs and preferred atmosphere.",
  },
  {
    icon: "✓",
    title: "Evidence backed",
    description:
      "Understand why each place is recommended and where the supporting information comes from.",
  },
];

export default function Home() {
  const [apiStatus, setApiStatus] = useState("Connecting...");
  const [isApiConnected, setIsApiConnected] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    async function loadHealth() {
      try {
        const data = await getHealth(controller.signal);
        setApiStatus(`${data.application} is ready`);
        setIsApiConnected(true);
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }

        setApiStatus("Connection unavailable");
        setIsApiConnected(false);
      }
    }

    loadHealth();

    return () => controller.abort();
  }, []);

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
                Turin
              </p>
            </div>
          </div>

          <div
            role="status"
            aria-live="polite"
            className={`flex shrink-0 items-center gap-2 rounded-full border px-2.5 py-2 text-[11px] sm:px-3 sm:text-xs ${
              isApiConnected
                ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                : "border-amber-400/30 bg-amber-400/10 text-amber-300"
            }`}
          >
            <span
              aria-hidden="true"
              className={`h-2 w-2 rounded-full ${
                isApiConnected ? "bg-emerald-400" : "bg-amber-400"
              }`}
            />

            <span className="hidden sm:inline">{apiStatus}</span>

            <span className="sm:hidden">
              {isApiConnected ? "Ready" : "Offline"}
            </span>
          </div>
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
            Your local discovery assistant
          </p>

          <h1
            id="hero-heading"
            className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl md:text-7xl"
          >
            What would you like
            <span className="block text-[#FF6846]">
              to discover today?
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-[#A9B1D6] sm:mt-7 sm:text-lg sm:leading-8">
            Discover food, culture, nature, nightlife, markets, community
            spaces, places of worship and more around your city.
          </p>

          <AssistantChat
            suggestions={suggestedSearches}
            isApiConnected={isApiConnected}
          />
        </div>
      </section>

      <PlacesSection />

      <section
        aria-labelledby="features-heading"
        className="border-t border-white/10 bg-[#070B24] px-4 py-14 sm:px-6 sm:py-16"
      >
        <div className="mx-auto max-w-6xl">
          <h2 id="features-heading" className="sr-only">
            CityBuddy features
          </h2>

          <div className="grid gap-5 md:grid-cols-3">
            {features.map((feature) => (
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
        CityBuddy Turin · Local discovery MVP
      </footer>
    </main>
  );
}
