"use client";

import { useEffect, useState } from "react";

import {
  getNearbyPlaces,
  getPlaceCategories,
  getPlaces,
} from "@/lib/api";
import type { CategoryGroup, Place } from "@/types/place";
import type { Language } from "@/types/language";
import { DISCOVERY_STATUS_COPY } from "@/lib/i18n";

export default function usePlacesDiscovery(language: Language) {
  const t = DISCOVERY_STATUS_COPY[language];
  const [places, setPlaces] = useState<Place[]>([]);
  const [placesStatus, setPlacesStatus] =
    useState(DISCOVERY_STATUS_COPY.en.loading);
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<CategoryGroup[]>([]);
  const [cityInput, setCityInput] = useState("Torino");
  const [city, setCity] = useState("Torino");
  const [limit, setLimit] = useState(5);
  const [offset, setOffset] = useState(0);
  const [isLoadingPlaces, setIsLoadingPlaces] = useState(true);
  const [userLocation, setUserLocation] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);
  const [radiusKm, setRadiusKm] = useState(2);
  const [isLocating, setIsLocating] = useState(false);
  const [locationStatus, setLocationStatus] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function loadCategories() {
      try {
        const data = await getPlaceCategories(controller.signal);
        setCategories(data);
      } catch (error) {
        if (
          error instanceof Error &&
          error.name === "AbortError"
        ) {
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
      setPlacesStatus(t.loading);

      try {
        const data = userLocation
          ? await getNearbyPlaces(
              {
                latitude: userLocation.latitude,
                longitude: userLocation.longitude,
                radiusKm,
                category,
                limit,
              },
              controller.signal,
            )
          : await getPlaces(
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
          data.length === 1 ? t.one : t.many(data.length),
        );
      } catch (error) {
        if (
          error instanceof Error &&
          error.name === "AbortError"
        ) {
          return;
        }

        setPlaces([]);
        setPlacesStatus(t.unavailable);
      } finally {
        if (!controller.signal.aborted) {
          setIsLoadingPlaces(false);
        }
      }
    }

    loadPlaces();

    return () => controller.abort();
  }, [
    category,
    city,
    limit,
    offset,
    radiusKm,
    userLocation,
    language,
    t,
  ]);

  function handleUseLocation() {
    if (!navigator.geolocation) {
      setLocationStatus(t.unsupportedLocation);
      return;
    }

    setIsLocating(true);
    setLocationStatus(t.requestingLocation);

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
        setOffset(0);
        setIsLocating(false);
        setLocationStatus(t.within(radiusKm));
      },
      () => {
        setIsLocating(false);
        setLocationStatus(t.locationDenied);
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 300000,
      },
    );
  }

  return {
    places,
    placesStatus,
    category,
    categories,
    cityInput,
    city,
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
  };
}
