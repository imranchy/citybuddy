export type Language = "en" | "it" | "pt" | "de" | "bn";

export const LANGUAGE_OPTIONS: ReadonlyArray<{ value: Language; label: string; flag: string }> = [
  { value: "en", label: "English", flag: "🇬🇧" },
  { value: "it", label: "Italiano", flag: "🇮🇹" },
  { value: "pt", label: "Português", flag: "🇵🇹" },
  { value: "de", label: "Deutsch", flag: "🇩🇪" },
  { value: "bn", label: "বাংলা", flag: "🇧🇩" },
];
