"use client";

import type { CategoryGroup } from "@/types/place";
import type { Language } from "@/types/language";
import { FILTER_COPY } from "@/lib/i18n";

type PlaceFiltersProps = {
  language: Language;
  categories: CategoryGroup[];
  category: string;
  cityInput: string;
  limit: number;
  onCategoryChange: (category: string) => void;
  onCityInputChange: (city: string) => void;
  onLimitChange: (limit: number) => void;
  onApply: () => void;
  onClear: () => void;
};

export default function PlaceFilters({
  language,
  categories,
  category,
  cityInput,
  limit,
  onCategoryChange,
  onCityInputChange,
  onLimitChange,
  onApply,
  onClear,
}: PlaceFiltersProps) {
  const t = FILTER_COPY[language];
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onApply();
      }}
      className="mt-8 grid gap-4 rounded-3xl border border-white/10 bg-[#121936] p-5 sm:grid-cols-2 lg:grid-cols-4"
    >
      <div>
        <label
          htmlFor="category-filter"
          className="mb-2 block text-xs font-semibold uppercase tracking-[0.15em] text-[#A9B1D6]"
        >
          {t.category}
        </label>

        <select
          id="category-filter"
          value={category}
          onChange={(event) =>
            onCategoryChange(event.target.value)
          }
          className="min-h-12 w-full rounded-xl border border-white/10 bg-[#0B112B] px-4 text-[#FFF8E7] outline-none focus:border-[#FF6846]"
        >
          <option value="">{t.allCategories}</option>

          {categories.map((group) => (
            <optgroup key={group.key} label={group.label}>
              {group.categories.map((availableCategory) => (
                <option
                  key={availableCategory.key}
                  value={availableCategory.key}
                >
                  {availableCategory.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      <div>
        <label
          htmlFor="city-filter"
          className="mb-2 block text-xs font-semibold uppercase tracking-[0.15em] text-[#A9B1D6]"
        >
          {t.city}
        </label>

        <input
          id="city-filter"
          type="text"
          value={cityInput}
          onChange={(event) =>
            onCityInputChange(event.target.value)
          }
          className="min-h-12 w-full rounded-xl border border-white/10 bg-[#0B112B] px-4 text-[#FFF8E7] outline-none placeholder:text-[#A9B1D6]/60 focus:border-[#FF6846]"
          placeholder={t.enterCity}
        />
      </div>

      <div>
        <label
          htmlFor="limit-filter"
          className="mb-2 block text-xs font-semibold uppercase tracking-[0.15em] text-[#A9B1D6]"
        >
          {t.results}
        </label>

        <select
          id="limit-filter"
          value={limit}
          onChange={(event) =>
            onLimitChange(Number(event.target.value))
          }
          className="min-h-12 w-full rounded-xl border border-white/10 bg-[#0B112B] px-4 text-[#FFF8E7] outline-none focus:border-[#FF6846]"
        >
          <option value={5}>5</option>
          <option value={10}>10</option>
          <option value={20}>20</option>
        </select>
      </div>

      <div className="flex items-end gap-2">
        <button
          type="submit"
          className="min-h-12 flex-1 rounded-xl bg-[#FF6846] px-4 font-semibold text-[#070B24] transition hover:bg-[#FF826B]"
        >
          {t.apply}
        </button>

        <button
          type="button"
          onClick={onClear}
          className="min-h-12 rounded-xl border border-white/10 px-4 text-sm text-[#A9B1D6] transition hover:border-[#FF6846]/50 hover:text-[#FFF8E7]"
        >
          {t.clear}
        </button>
      </div>
    </form>
  );
}
