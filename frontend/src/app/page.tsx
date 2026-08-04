"use client";

import Image from "next/image";
import { FormEvent, useEffect, useState } from "react";
import type { Place } from "@/types/place";
import PlaceCard from "@/components/PlaceCard";
import PlaceFilters from "@/components/PlaceFilters";
import {
  getHealth,
  getPlaceCategories,
  getPlaces,
} from "@/lib/api";

const suggestedSearches = [
  {
    label: "Near me",
    query: "Restaurants and cafés near me",
  },
  {
    label: "Under €25",
    query: "Affordable restaurants under €25",
  },
  {
    label: "Vegetarian",
    query: "Restaurants with good vegetarian options",
  },
  {
    label: "Open now",
    query: "Restaurants and cafés open now",
  },
  {
    label: "Quiet",
    query: "A quiet restaurant or café",
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
      "Search naturally using your budget, cuisine, dietary needs and preferred atmosphere.",
  },
  {
    icon: "✓",
    title: "Evidence backed",
    description:
      "Understand why each place is recommended and where the supporting information comes from.",
  },
];

export default function Home() {
  const [query, setQuery] = useState("");
  const [apiStatus, setApiStatus] = useState("Connecting...");
  const [isApiConnected, setIsApiConnected] = useState(false);
  const [message, setMessage] = useState("");
  const [places, setPlaces] = useState<Place[]>([]);
  const [placesStatus, setPlacesStatus] = useState("Loading places...");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [cityInput, setCityInput] = useState("Torino");
  const [city, setCity] = useState("Torino");
  const [limit, setLimit] = useState(10);
  const [offset, setOffset] = useState(0);
  const [isLoadingPlaces, setIsLoadingPlaces] = useState(true);

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

  useEffect(() => {
    const controller = new AbortController();

    async function loadCategories() {
      try {
        const data = await getPlaceCategories(controller.signal);
        setCategories(data);
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }

        setCategories([]);
      }
    }

    loadCategories();

    return () => controller.abort();
  }, []);

  
  useEffect(() => {
  const controller = new AbortController();

  async function loadPlaces() {
    setIsLoadingPlaces(true);
    setPlacesStatus("Loading places...");

    const parameters = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });

    if (category) {
      parameters.set("category", category);
    }

    if (city.trim()) {
      parameters.set("city", city.trim());
    }

    try {
      const data = await getPlaces(
    {
      category,
      city,
      limit,
      offset,
    },
    controller.signal,
  );

  setPlaces(data);
  setPlacesStatus(
    data.length === 1
      ? "1 place loaded"
      : `${data.length} places loaded`,
  );
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }

      setPlaces([]);
      setPlacesStatus("Places are temporarily unavailable");
    } finally {
      if (!controller.signal.aborted) {
        setIsLoadingPlaces(false);
      }
    }
  }

  loadPlaces();

  return () => controller.abort();
}, [category, city, limit, offset]);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!query.trim()) {
      setMessage("Describe what kind of place you are looking for.");
      return;
    }

    setMessage(
      `Search received: “${query}”. Personalised recommendation and filtering will be added in the next development phase.`,
    );
  }

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
              priority
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
            Where do you want
            <span className="block text-[#FF6846]">
              to go today?
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-[#A9B1D6] sm:mt-7 sm:text-lg sm:leading-8">
            Discover restaurants and cafés based on your location, budget,
            dietary needs and preferred atmosphere.
          </p>

          <form
            onSubmit={handleSearch}
            className="mx-auto mt-10 max-w-3xl rounded-3xl border border-white/10 bg-[#121936] p-3 shadow-2xl sm:mt-12"
          >
            <div className="flex flex-col gap-3 md:flex-row">
              <label htmlFor="city-search" className="sr-only">
                Describe the place you are looking for
              </label>

              <input
                id="city-search"
                name="query"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="A quiet vegetarian restaurant near Porta Nuova under €25..."
                autoComplete="off"
                className="min-h-14 min-w-0 flex-1 rounded-2xl border border-white/10 bg-[#0B112B] px-5 text-base text-[#FFF8E7] outline-none placeholder:text-[#A9B1D6]/60 focus:border-[#FF6846] focus:ring-2 focus:ring-[#FF6846]/30"
              />

              <button
                type="submit"
                className="min-h-14 rounded-2xl bg-[#FF6846] px-7 font-semibold text-[#070B24] transition hover:bg-[#FF826B] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FFC83D] focus-visible:ring-offset-2 focus-visible:ring-offset-[#121936] active:scale-[0.98]"
              >
                Find places
              </button>
            </div>

            <div
              aria-label="Suggested searches"
              className="mt-3 flex gap-2 overflow-x-auto px-2 pb-2"
            >
              {suggestedSearches.map((suggestion) => (
                <button
                  key={suggestion.label}
                  type="button"
                  onClick={() => {
                    setQuery(suggestion.query);
                    setMessage("");
                  }}
                  className="min-h-9 shrink-0 rounded-full border border-white/10 px-3 py-1 text-xs text-[#A9B1D6] transition hover:border-[#FF6846]/50 hover:text-[#FFF8E7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FFC83D]"
                >
                  {suggestion.label}
                </button>
              ))}
            </div>
          </form>

          {message && (
            <p
              role="status"
              aria-live="polite"
              className="mx-auto mt-5 max-w-2xl rounded-2xl border border-[#FF6846]/25 bg-[#FF6846]/10 px-5 py-4 text-sm leading-6 text-[#FFF8E7]"
            >
              {message}
            </p>
          )}
        </div>
      </section>

      <section
        aria-labelledby="places-heading"
        className="border-t border-white/10 bg-[#0B112B] px-4 py-14 sm:px-6 sm:py-16"
      >
        <div className="mx-auto max-w-6xl">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.25em] text-[#FFC83D]">
                Live database
              </p>

              <h2
                id="places-heading"
                className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl"
              >
                Places in Turin
              </h2>
            </div>

            <p
              role="status"
              aria-live="polite"
              className="text-sm text-[#A9B1D6]"
            >
              {placesStatus}
            </p>
          </div>

         <PlaceFilters
            categories={categories}
            category={category}
            cityInput={cityInput}
            limit={limit}
            onCategoryChange={(newCategory) => {
              setCategory(newCategory);
              setOffset(0);
            }}
            onCityInputChange={setCityInput}
            onLimitChange={(newLimit) => {
              setLimit(newLimit);
              setOffset(0);
            }}
            onApply={() => {
              setCity(cityInput.trim());
              setOffset(0);
            }}
            onClear={() => {
              setCategory("");
              setCityInput("Torino");
              setCity("Torino");
              setLimit(10);
              setOffset(0);
            }}
          />

          {isLoadingPlaces ? (
            <div className="mt-8 rounded-3xl border border-white/10 bg-[#121936] p-8 text-center text-[#A9B1D6]">
              Loading places...
            </div>
          ) : places.length > 0 ? (
            <div className="mt-8 grid gap-5 md:grid-cols-2">
              {places.map((place) => (
                <PlaceCard key={place.id} place={place} />
              ))}
            </div>
          ) : (
            <div className="mt-8 rounded-3xl border border-white/10 bg-[#121936] p-8 text-center text-[#A9B1D6]">
              {placesStatus}
            </div>
          )}

          {!isLoadingPlaces && places.length > 0 && (
            <div className="mt-8 flex items-center justify-between gap-4">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => {
                  setOffset((currentOffset) =>
                    Math.max(0, currentOffset - limit),
                  );
                }}
                className="min-h-11 rounded-xl border border-white/10 px-5 font-medium text-[#FFF8E7] transition hover:border-[#FF6846]/50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>

              <p className="text-sm text-[#A9B1D6]">
                Page {Math.floor(offset / limit) + 1}
              </p>

              <button
                type="button"
                disabled={places.length < limit}
                onClick={() => {
                  setOffset((currentOffset) => currentOffset + limit);
                }}
                className="min-h-11 rounded-xl bg-[#FF6846] px-5 font-semibold text-[#070B24] transition hover:bg-[#FF826B] disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </section>

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
        CityBuddy Turin · Initial development version
      </footer>
    </main>
  );
}