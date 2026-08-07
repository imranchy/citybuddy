"use client";

import { useEffect, useState } from "react";

import {
  getNearbyPlaces,
  getPlaceCategories,
  getPlaces,
} from "@/lib/api";
import type { CategoryGroup, Place } from "@/types/place";

export default function usePlacesDiscovery() {
  const [places, setPlaces] = useState<Place[]>([]);
  const [placesStatus, setPlacesStatus] =
    useState("Loading places...");
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
      setPlacesStatus("Loading places...");

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
          data.length === 1
            ? "1 place loaded"
            : `${data.length} places loaded`,
        );
      } catch (error) {
        if (
          error instanceof Error &&
          error.name === "AbortError"
        ) {
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
  }, [
    category,
    city,
    limit,
    offset,
    radiusKm,
    userLocation,
  ]);

  function handleUseLocation() {
    if (!navigator.geolocation) {
      setLocationStatus(
        "Location services are not supported by this browser.",
      );
      return;
    }

    setIsLocating(true);
    setLocationStatus("Requesting your location...");

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
        setOffset(0);
        setIsLocating(false);
        setLocationStatus(
          `Showing places within ${radiusKm} km of you.`,
        );
      },
      () => {
        setIsLocating(false);
        setLocationStatus(
          "Unable to access your location. Check browser permission.",
        );
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
