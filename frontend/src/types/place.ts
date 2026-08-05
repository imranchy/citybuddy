export type PlaceImage = {
  source: string;
  image_url: string;
  thumbnail_url: string | null;
  source_page_url: string;
  attribution: string;
  license: string;
  license_url: string | null;
};

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
  primary_image: PlaceImage | null;
  distance_km?: number;
};