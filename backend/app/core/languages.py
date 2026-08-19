from __future__ import annotations

from typing import Literal

LanguageCode = Literal["en", "it", "pt", "de", "bn"]

SUPPORTED_LANGUAGE_CODES: tuple[LanguageCode, ...] = ("en", "it", "pt", "de", "bn")
LANGUAGE_NAMES: dict[LanguageCode, str] = {
    "en": "English",
    "it": "Italian",
    "pt": "Portuguese",
    "de": "German",
    "bn": "Bangla",
}

# These strings are used only when the response model is unavailable or when
# deterministic application logic must return a safety/status message without
# asking another model to translate it. They are intentionally centralized so
# multilingual support does not leak into category mappings or orchestration.
_FALLBACK_COPY: dict[LanguageCode, dict[str, str]] = {
    "en": {
        "category": "Category",
        "verified_place": "This is a reviewed CityBuddy place that matches the validated filters.",
        "one_place": "Here is one place that could be a good match.",
        "many_places": "Here are {count} places that could be a good match.",
        "no_places": "I could not find a suitable place for that request.",
        "intent_recovered": "The intent model failed; the response model recovered the request.",
        "intent_retry": "Intent extraction succeeded after one model retry.",
        "model_unavailable": "The local model was unavailable; CityBuddy used verified filters.",
        "unsupported_city": "CityBuddy currently supports Torino only.",
        "location_required": "Share your location to search for nearby places.",
        "semantic_unavailable": "Semantic evidence was unavailable; verified place data was used.",
        "opening_unavailable": "CityBuddy cannot verify whether a place is open right now; check current information before visiting.",
        "rating_unavailable": "CityBuddy cannot verify the requested external rating or award.",
        "context_unverified": "I could not verify a preference between those places.",
        "verified_filters": "CityBuddy used verified filters for these suggestions.",
        "live_tool_unavailable": "I could not verify the requested live information right now.",
        "transit_disclaimer": "Open Google Maps for current public-transport directions. Routes, departure times, disruptions, and availability may change; verify the latest information before travelling.",
    },
    "it": {
        "category": "Categoria",
        "verified_place": "Questo è un luogo verificato da CityBuddy che corrisponde ai filtri convalidati.",
        "one_place": "Ecco un luogo che potrebbe fare al caso tuo.",
        "many_places": "Ecco {count} luoghi che potrebbero fare al caso tuo.",
        "no_places": "Non ho trovato luoghi adatti alla tua richiesta.",
        "intent_recovered": "Il modello di risposta ha recuperato la richiesta dopo un errore del modello di intenti.",
        "intent_retry": "L'estrazione dell'intento è riuscita dopo un nuovo tentativo del modello.",
        "model_unavailable": "Il modello locale non era disponibile; CityBuddy ha usato filtri verificati.",
        "unsupported_city": "Al momento CityBuddy supporta solo Torino.",
        "location_required": "Condividi la tua posizione per cercare luoghi nelle vicinanze.",
        "semantic_unavailable": "La ricerca semantica non era disponibile; sono stati usati dati verificati.",
        "opening_unavailable": "CityBuddy non può verificare se un luogo è aperto in questo momento; controlla le informazioni aggiornate prima della visita.",
        "rating_unavailable": "CityBuddy non può verificare la valutazione o il premio esterno richiesto.",
        "context_unverified": "Non sono riuscito a verificare una preferenza tra questi luoghi.",
        "verified_filters": "CityBuddy ha usato filtri verificati per questi suggerimenti.",
        "live_tool_unavailable": "Non sono riuscito a verificare in questo momento le informazioni aggiornate richieste.",
        "transit_disclaimer": "Apri Google Maps per indicazioni aggiornate con i mezzi pubblici. Percorsi, orari di partenza, interruzioni e disponibilità possono cambiare; verifica le informazioni più recenti prima di partire.",
    },
    "pt": {
        "category": "Categoria",
        "verified_place": "Este é um lugar verificado pelo CityBuddy que corresponde aos filtros validados.",
        "one_place": "Aqui está um lugar que pode ser uma boa opção.",
        "many_places": "Aqui estão {count} lugares que podem ser boas opções.",
        "no_places": "Não encontrei um lugar adequado para esse pedido.",
        "intent_recovered": "O modelo de resposta recuperou o pedido após uma falha do modelo de intenção.",
        "intent_retry": "A extração da intenção foi concluída após uma nova tentativa do modelo.",
        "model_unavailable": "O modelo local não estava disponível; o CityBuddy usou filtros verificados.",
        "unsupported_city": "No momento, o CityBuddy oferece suporte apenas a Torino.",
        "location_required": "Partilhe a sua localização para procurar lugares próximos.",
        "semantic_unavailable": "A evidência semântica não estava disponível; foram usados dados verificados dos lugares.",
        "opening_unavailable": "O CityBuddy não consegue verificar se um lugar está aberto agora; confirme as informações atuais antes da visita.",
        "rating_unavailable": "O CityBuddy não consegue verificar a classificação ou distinção externa solicitada.",
        "context_unverified": "Não consegui verificar uma preferência entre esses lugares.",
        "verified_filters": "O CityBuddy usou filtros verificados para estas sugestões.",
        "live_tool_unavailable": "Não consegui verificar agora as informações atuais solicitadas.",
        "transit_disclaimer": "Abra o Google Maps para obter direções atuais de transporte público. Rotas, horários de partida, interrupções e disponibilidade podem mudar; confirme as informações mais recentes antes de viajar.",
    },
    "de": {
        "category": "Kategorie",
        "verified_place": "Dies ist ein von CityBuddy geprüfter Ort, der den validierten Filtern entspricht.",
        "one_place": "Hier ist ein Ort, der gut passen könnte.",
        "many_places": "Hier sind {count} Orte, die gut passen könnten.",
        "no_places": "Ich konnte keinen passenden Ort für diese Anfrage finden.",
        "intent_recovered": "Das Antwortmodell hat die Anfrage nach einem Fehler des Intent-Modells wiederhergestellt.",
        "intent_retry": "Die Intent-Erkennung war nach einem erneuten Modellversuch erfolgreich.",
        "model_unavailable": "Das lokale Modell war nicht verfügbar; CityBuddy hat geprüfte Filter verwendet.",
        "unsupported_city": "CityBuddy unterstützt derzeit nur Torino.",
        "location_required": "Teile deinen Standort, um nach Orten in der Nähe zu suchen.",
        "semantic_unavailable": "Semantische Evidenz war nicht verfügbar; es wurden geprüfte Ortsdaten verwendet.",
        "opening_unavailable": "CityBuddy kann nicht prüfen, ob ein Ort gerade geöffnet ist; prüfe vor dem Besuch die aktuellen Informationen.",
        "rating_unavailable": "CityBuddy kann die angeforderte externe Bewertung oder Auszeichnung nicht überprüfen.",
        "context_unverified": "Ich konnte keine Präferenz zwischen diesen Orten verifizieren.",
        "verified_filters": "CityBuddy hat für diese Vorschläge geprüfte Filter verwendet.",
        "live_tool_unavailable": "Ich konnte die angeforderten aktuellen Informationen gerade nicht verifizieren.",
        "transit_disclaimer": "Öffne Google Maps für aktuelle Verbindungen mit öffentlichen Verkehrsmitteln. Routen, Abfahrtszeiten, Störungen und Verfügbarkeit können sich ändern; prüfe vor der Fahrt die neuesten Informationen.",
    },
    "bn": {
        "category": "বিভাগ",
        "verified_place": "এটি CityBuddy দ্বারা যাচাই করা একটি স্থান, যা যাচাই করা ফিল্টারের সঙ্গে মেলে।",
        "one_place": "এখানে একটি জায়গা আছে যা আপনার জন্য উপযুক্ত হতে পারে।",
        "many_places": "এখানে {count}টি জায়গা আছে যা আপনার জন্য উপযুক্ত হতে পারে।",
        "no_places": "এই অনুরোধের জন্য উপযুক্ত কোনো জায়গা খুঁজে পাইনি।",
        "intent_recovered": "ইনটেন্ট মডেল ব্যর্থ হওয়ার পর রেসপন্স মডেল অনুরোধটি পুনরুদ্ধার করেছে।",
        "intent_retry": "মডেলটি আরেকবার চেষ্টা করার পর ইনটেন্ট নির্ধারণ সফল হয়েছে।",
        "model_unavailable": "লোকাল মডেলটি উপলভ্য ছিল না; CityBuddy যাচাই করা ফিল্টার ব্যবহার করেছে।",
        "unsupported_city": "CityBuddy বর্তমানে শুধু Torino সমর্থন করে।",
        "location_required": "কাছাকাছি জায়গা খুঁজতে আপনার অবস্থান শেয়ার করুন।",
        "semantic_unavailable": "সেমান্টিক তথ্য পাওয়া যায়নি; যাচাই করা জায়গার তথ্য ব্যবহার করা হয়েছে।",
        "opening_unavailable": "CityBuddy এই মুহূর্তে কোনো জায়গা খোলা আছে কি না যাচাই করতে পারে না; যাওয়ার আগে সর্বশেষ তথ্য দেখে নিন।",
        "rating_unavailable": "CityBuddy অনুরোধ করা বাহ্যিক রেটিং বা পুরস্কার যাচাই করতে পারে না।",
        "context_unverified": "এই জায়গাগুলোর মধ্যে কোনটি বেশি উপযুক্ত তা যাচাই করতে পারিনি।",
        "verified_filters": "CityBuddy এই পরামর্শগুলোর জন্য যাচাই করা ফিল্টার ব্যবহার করেছে।",
        "live_tool_unavailable": "আমি এই মুহূর্তে অনুরোধ করা হালনাগাদ তথ্য যাচাই করতে পারিনি।",
        "transit_disclaimer": "হালনাগাদ গণপরিবহন নির্দেশনার জন্য Google Maps খুলুন। রুট, ছাড়ার সময়, বিঘ্ন এবং প্রাপ্যতা বদলাতে পারে; যাত্রার আগে সর্বশেষ তথ্য যাচাই করুন।",
    },
}


def language_name(code: LanguageCode) -> str:
    return LANGUAGE_NAMES[code]


def fallback_text(code: LanguageCode, key: str, **values: object) -> str:
    template = _FALLBACK_COPY[code][key]
    return template.format(**values)
