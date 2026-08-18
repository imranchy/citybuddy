export type Language = "en" | "it" | "pt" | "de" | "bn";

export const LANGUAGE_OPTIONS: ReadonlyArray<{ value: Language; label: string }> = [
  { value: "en", label: "English" },
  { value: "it", label: "Italiano" },
  { value: "pt", label: "Português" },
  { value: "de", label: "Deutsch" },
  { value: "bn", label: "বাংলা" },
];
