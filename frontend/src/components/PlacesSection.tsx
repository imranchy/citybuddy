"use client";

import LocationControls from "@/components/LocationControls";
import PlaceCard from "@/components/PlaceCard";
import PlaceFilters from "@/components/PlaceFilters";
import usePlacesDiscovery from "@/hooks/usePlacesDiscovery";

export default function PlacesSection() {
  const {
    places,
    placesStatus,
    category,
    categories,
    cityInput,
    limit,
    offset,
    isLoadingPlaces,
    userLocation,
    radiusKm,
    isLocating,
    locationStatus,
    setCategory,
    setCityInput,
    setCity,
    setLimit,
    setOffset,
    setUserLocation,
    setRadiusKm,
    setLocationStatus,
    handleUseLocation,
  } = usePlacesDiscovery();

  return (
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

        <LocationControls
          radiusKm={radiusKm}
          isLocating={isLocating}
          locationStatus={locationStatus}
          isNearbyMode={userLocation !== null}
          onRadiusChange={(newRadius) => {
            setRadiusKm(newRadius);

            if (userLocation) {
              setLocationStatus(
                `Showing places within ${newRadius} km of you.`,
              );
            }
          }}
          onUseLocation={handleUseLocation}
          onExitNearbyMode={() => {
            setUserLocation(null);
            setLocationStatus("");
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

        {!isLoadingPlaces &&
          places.length > 0 &&
          !userLocation && (
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
                  setOffset(
                    (currentOffset) => currentOffset + limit,
                  );
                }}
                className="min-h-11 rounded-xl bg-[#FF6846] px-5 font-semibold text-[#070B24] transition hover:bg-[#FF826B] disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
      </div>
    </section>
  );
}