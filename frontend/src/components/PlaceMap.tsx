"use client";

import L from "leaflet";
import { useEffect, useRef } from "react";

import type { Place } from "@/types/place";

import {
  getGoogleDirectionsUrl,
  getGoogleMapsUrl,
} from "@/lib/maps";

type UserLocation = {
  latitude: number;
  longitude: number;
};

type PlaceMapProps = {
  places: Place[];
  userLocation: UserLocation | null;
};

function createPlacePopup(place: Place): HTMLElement {
  const container = document.createElement("div");

  const name = document.createElement("strong");
  name.textContent = place.name;
  container.appendChild(name);

  const category = document.createElement("p");
  category.textContent =
    place.category.charAt(0).toUpperCase() +
    place.category.slice(1);
  category.style.margin = "4px 0";
  container.appendChild(category);

  const address = document.createElement("p");
  address.textContent = `${place.address}, ${place.city}`;
  address.style.margin = "4px 0";
  container.appendChild(address);

  if (place.distance_km !== undefined) {
    const distance = document.createElement("p");

    distance.textContent =
      place.distance_km < 1
        ? `${Math.round(place.distance_km * 1000)} m away`
        : `${place.distance_km.toFixed(1)} km away`;

    distance.style.margin = "4px 0";
    distance.style.fontWeight = "600";
    container.appendChild(distance);
  }

    const actions = document.createElement("div");
    actions.style.display = "flex";
    actions.style.gap = "8px";
    actions.style.marginTop = "10px";

    const mapsLink = document.createElement("a");
    mapsLink.href = getGoogleMapsUrl(place);
    mapsLink.target = "_blank";
    mapsLink.rel = "noopener noreferrer";
    mapsLink.textContent = "View on Google Maps";
    mapsLink.style.color = "#D94E31";
    mapsLink.style.fontWeight = "600";

    const directionsLink = document.createElement("a");
    directionsLink.href = getGoogleDirectionsUrl(place);
    directionsLink.target = "_blank";
    directionsLink.rel = "noopener noreferrer";
    directionsLink.textContent = "Directions";
    directionsLink.style.color = "#D94E31";
    directionsLink.style.fontWeight = "600";

    actions.appendChild(mapsLink);
    actions.appendChild(directionsLink);
    container.appendChild(actions);

  return container;
}

export default function PlaceMap({
  places,
  userLocation,
}: PlaceMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }

    const map = L.map(containerRef.current, {
      center: [45.0703, 7.6869],
      zoom: 13,
      scrollWheelZoom: true,
      zoomAnimation: false,
      fadeAnimation: false,
      markerZoomAnimation: false,
    });

    L.tileLayer(
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        attribution: "&copy; OpenStreetMap contributors",
      },
    ).addTo(map);

    const markers = L.layerGroup().addTo(map);

    mapRef.current = map;
    markersRef.current = markers;

    const frame = requestAnimationFrame(() => {
      map.invalidateSize();
    });

    return () => {
      cancelAnimationFrame(frame);
      markersRef.current = null;
      map.stop();
      map.off();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const markers = markersRef.current;

    if (!map || !markers) {
      return;
    }

    markers.clearLayers();

    const positions: L.LatLngExpression[] = [];

    places.forEach((place) => {
      const position: L.LatLngExpression = [
        place.latitude,
        place.longitude,
      ];

      positions.push(position);

      L.circleMarker(position, {
        radius: 8,
        color: "#070B24",
        fillColor: "#FF6846",
        fillOpacity: 1,
        weight: 2,
        })
        .bindPopup(createPlacePopup(place))
        .addTo(markers);
    });

    if (userLocation) {
      const userPosition: L.LatLngExpression = [
        userLocation.latitude,
        userLocation.longitude,
      ];

      positions.push(userPosition);

      L.circleMarker(userPosition, {
        radius: 9,
        color: "#070B24",
        fillColor: "#FFC83D",
        fillOpacity: 1,
        weight: 3,
      })
        .bindPopup("Your current location")
        .addTo(markers);
    }

    map.stop();
    map.invalidateSize();

    if (positions.length === 1) {
      map.setView(positions[0], 15, {
        animate: false,
      });
    } else if (positions.length > 1) {
      map.fitBounds(L.latLngBounds(positions), {
        padding: [40, 40],
        maxZoom: 15,
        animate: false,
      });
    }
  }, [places, userLocation]);

  return (
    <div className="mt-8 overflow-hidden rounded-3xl border border-white/10">
      <div
        ref={containerRef}
        aria-label="Map showing CityBuddy places"
        className="h-[28rem] w-full"
      />
    </div>
  );
}
