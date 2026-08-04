export type Place = {
  id: number;
  name: string;
  category: string;
  description: string | null;
  address: string;
  city: string;
  country_code: string;
  latitude: number;
  longitude: number;
  price_level: number | null;
  rating: number | null;
  dietary_options: string[];
  distance_km?: number;
};