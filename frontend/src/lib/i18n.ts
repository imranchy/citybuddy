import type { Language } from "@/types/language";

export const PAGE_COPY: Record<Language, {
  city: string;
  eyebrow: string;
  titleA: string;
  titleB: string;
  description: string;
  language: string;
  footer: string;
  suggestions: Array<{ label: string; query: string }>;
  features: Array<{ icon: string; title: string; description: string }>;
}> = {
  en: {
    city: "Turin", eyebrow: "Your local discovery assistant", titleA: "What would you like", titleB: "to discover today?",
    description: "Discover food, culture, nature, nightlife, markets, community spaces, places of worship and more around your city.",
    language: "Language", footer: "CityBuddy Turin · Local discovery",
    suggestions: [
      { label: "Near me", query: "Interesting places near me" },
      { label: "Food & drink", query: "Good local food and drink" },
      { label: "Culture", query: "Museums, monuments and cultural attractions" },
      { label: "Outdoors", query: "Parks, gardens and viewpoints" },
      { label: "Places of worship", query: "Churches, mosques, temples and other places of worship" },
    ],
    features: [
      { icon: "⌖", title: "Location aware", description: "Find places based on your current location, neighbourhood or preferred search radius." },
      { icon: "✦", title: "Personalised search", description: "Search naturally using your interests, location, budget, accessibility needs and preferred atmosphere." },
      { icon: "✓", title: "Clear recommendations", description: "Get concise suggestions with useful reasons that match what you asked for." },
    ],
  },
  it: {
    city: "Torino", eyebrow: "Il tuo assistente locale", titleA: "Cosa vorresti", titleB: "scoprire oggi?",
    description: "Scopri cibo, cultura, natura, vita notturna, mercati, spazi di comunità, luoghi di culto e molto altro in città.",
    language: "Lingua", footer: "CityBuddy Torino · Scoperta locale",
    suggestions: [
      { label: "Vicino a me", query: "Luoghi interessanti vicino a me" },
      { label: "Cibo e bevande", query: "Buon cibo e bevande locali" },
      { label: "Cultura", query: "Musei, monumenti e attrazioni culturali" },
      { label: "All'aperto", query: "Parchi, giardini e punti panoramici" },
      { label: "Luoghi di culto", query: "Chiese, moschee, templi e altri luoghi di culto" },
    ],
    features: [
      { icon: "⌖", title: "Attento alla posizione", description: "Trova luoghi in base alla tua posizione, al quartiere o al raggio di ricerca." },
      { icon: "✦", title: "Ricerca personalizzata", description: "Cerca in modo naturale usando interessi, budget, accessibilità e atmosfera preferita." },
      { icon: "✓", title: "Consigli chiari", description: "Ricevi suggerimenti concisi con motivazioni utili e pertinenti." },
    ],
  },
  pt: {
    city: "Turim", eyebrow: "O seu assistente local", titleA: "O que gostaria", titleB: "de descobrir hoje?",
    description: "Descubra comida, cultura, natureza, vida noturna, mercados, espaços comunitários, locais de culto e muito mais pela cidade.",
    language: "Idioma", footer: "CityBuddy Turim · Descoberta local",
    suggestions: [
      { label: "Perto de mim", query: "Lugares interessantes perto de mim" },
      { label: "Comida e bebida", query: "Boa comida e bebida local" },
      { label: "Cultura", query: "Museus, monumentos e atrações culturais" },
      { label: "Ao ar livre", query: "Parques, jardins e miradouros" },
      { label: "Locais de culto", query: "Igrejas, mesquitas, templos e outros locais de culto" },
    ],
    features: [
      { icon: "⌖", title: "Sensível à localização", description: "Encontre lugares com base na sua localização, bairro ou raio de pesquisa." },
      { icon: "✦", title: "Pesquisa personalizada", description: "Pesquise naturalmente por interesses, orçamento, acessibilidade e ambiente preferido." },
      { icon: "✓", title: "Recomendações claras", description: "Receba sugestões concisas com razões úteis que correspondem ao pedido." },
    ],
  },
  de: {
    city: "Turin", eyebrow: "Dein lokaler Entdeckungsassistent", titleA: "Was möchtest du", titleB: "heute entdecken?",
    description: "Entdecke Essen, Kultur, Natur, Nachtleben, Märkte, Gemeinschaftsorte, Gotteshäuser und mehr in deiner Stadt.",
    language: "Sprache", footer: "CityBuddy Turin · Lokale Entdeckungen",
    suggestions: [
      { label: "In meiner Nähe", query: "Interessante Orte in meiner Nähe" },
      { label: "Essen & Trinken", query: "Gutes lokales Essen und Trinken" },
      { label: "Kultur", query: "Museen, Denkmäler und kulturelle Sehenswürdigkeiten" },
      { label: "Draußen", query: "Parks, Gärten und Aussichtspunkte" },
      { label: "Gotteshäuser", query: "Kirchen, Moscheen, Tempel und andere Gotteshäuser" },
    ],
    features: [
      { icon: "⌖", title: "Standortbezogen", description: "Finde Orte anhand deines Standorts, Viertels oder gewünschten Suchradius." },
      { icon: "✦", title: "Persönliche Suche", description: "Suche natürlich nach Interessen, Budget, Barrierefreiheit und gewünschter Atmosphäre." },
      { icon: "✓", title: "Klare Empfehlungen", description: "Erhalte kurze Vorschläge mit hilfreichen, passenden Begründungen." },
    ],
  },
  bn: {
    city: "তুরিন", eyebrow: "আপনার স্থানীয় ভ্রমণ সহকারী", titleA: "আজ আপনি কী", titleB: "আবিষ্কার করতে চান?",
    description: "আপনার শহরে খাবার, সংস্কৃতি, প্রকৃতি, নাইটলাইফ, বাজার, কমিউনিটি স্পেস, উপাসনালয় এবং আরও অনেক কিছু খুঁজুন।",
    language: "ভাষা", footer: "CityBuddy তুরিন · স্থানীয় আবিষ্কার",
    suggestions: [
      { label: "আমার কাছে", query: "আমার কাছাকাছি আকর্ষণীয় জায়গা" },
      { label: "খাবার ও পানীয়", query: "ভালো স্থানীয় খাবার ও পানীয়" },
      { label: "সংস্কৃতি", query: "জাদুঘর, স্মৃতিস্তম্ভ ও সাংস্কৃতিক আকর্ষণ" },
      { label: "খোলা জায়গা", query: "পার্ক, বাগান ও সুন্দর দৃশ্যের জায়গা" },
      { label: "উপাসনালয়", query: "গির্জা, মসজিদ, মন্দির এবং অন্যান্য উপাসনালয়" },
    ],
    features: [
      { icon: "⌖", title: "অবস্থানভিত্তিক", description: "আপনার বর্তমান অবস্থান, এলাকা বা পছন্দের দূরত্ব অনুযায়ী জায়গা খুঁজুন।" },
      { icon: "✦", title: "ব্যক্তিগত অনুসন্ধান", description: "আগ্রহ, বাজেট, প্রবেশযোগ্যতা ও পছন্দের পরিবেশ অনুযায়ী স্বাভাবিক ভাষায় খুঁজুন।" },
      { icon: "✓", title: "স্পষ্ট পরামর্শ", description: "আপনার অনুরোধের সঙ্গে মানানসই সংক্ষিপ্ত ও উপযোগী পরামর্শ পান।" },
    ],
  },
};

export const CHAT_COPY: Record<Language, {
  input: string; send: string; thinking: string; you: string; locate: string; locating: string;
  ready: string; remove: string; reset: string; empty: string; offline: string; failure: string;
  locationUsed: string; locationFailed: string;
}> = {
  en: { input: "Ask about museums, parks, food, nightlife or places nearby…", send: "Send", thinking: "Thinking…", you: "You", locate: "Use my location", locating: "Locating…", ready: "Location ready", remove: "Remove location", reset: "New conversation", empty: "Tell CityBuddy what you would like to discover.", offline: "CityBuddy is offline. Start the backend and try again.", failure: "I could not complete that request. Please try again.", locationUsed: "Location is ready for nearby searches.", locationFailed: "Location permission was unavailable." },
  it: { input: "Chiedi di musei, parchi, ristoranti, vita notturna o luoghi vicini…", send: "Invia", thinking: "Sto pensando…", you: "Tu", locate: "Usa la mia posizione", locating: "Localizzazione…", ready: "Posizione pronta", remove: "Rimuovi posizione", reset: "Nuova conversazione", empty: "Racconta a CityBuddy cosa vorresti scoprire.", offline: "CityBuddy non è disponibile. Avvia il backend e riprova.", failure: "Non sono riuscito a completare la richiesta. Riprova.", locationUsed: "La posizione è pronta per le ricerche nelle vicinanze.", locationFailed: "Non è stato possibile accedere alla posizione." },
  pt: { input: "Pergunte sobre museus, parques, comida, vida noturna ou lugares próximos…", send: "Enviar", thinking: "A pensar…", you: "Você", locate: "Usar a minha localização", locating: "A localizar…", ready: "Localização pronta", remove: "Remover localização", reset: "Nova conversa", empty: "Diga ao CityBuddy o que gostaria de descobrir.", offline: "O CityBuddy está offline. Inicie o backend e tente novamente.", failure: "Não consegui concluir o pedido. Tente novamente.", locationUsed: "A localização está pronta para pesquisas próximas.", locationFailed: "Não foi possível obter permissão de localização." },
  de: { input: "Frage nach Museen, Parks, Essen, Nachtleben oder Orten in der Nähe…", send: "Senden", thinking: "Ich denke nach…", you: "Du", locate: "Meinen Standort verwenden", locating: "Standort wird ermittelt…", ready: "Standort bereit", remove: "Standort entfernen", reset: "Neue Unterhaltung", empty: "Sag CityBuddy, was du entdecken möchtest.", offline: "CityBuddy ist offline. Starte das Backend und versuche es erneut.", failure: "Die Anfrage konnte nicht abgeschlossen werden. Bitte versuche es erneut.", locationUsed: "Der Standort ist für Suchen in der Nähe bereit.", locationFailed: "Standortfreigabe war nicht verfügbar." },
  bn: { input: "জাদুঘর, পার্ক, খাবার, নাইটলাইফ বা কাছাকাছি জায়গা সম্পর্কে জিজ্ঞাসা করুন…", send: "পাঠান", thinking: "ভাবছি…", you: "আপনি", locate: "আমার অবস্থান ব্যবহার করুন", locating: "অবস্থান খোঁজা হচ্ছে…", ready: "অবস্থান প্রস্তুত", remove: "অবস্থান সরান", reset: "নতুন কথোপকথন", empty: "CityBuddy-কে বলুন আপনি কী আবিষ্কার করতে চান।", offline: "CityBuddy অফলাইন। ব্যাকএন্ড চালু করে আবার চেষ্টা করুন।", failure: "অনুরোধটি সম্পন্ন করা যায়নি। আবার চেষ্টা করুন।", locationUsed: "কাছাকাছি অনুসন্ধানের জন্য অবস্থান প্রস্তুত।", locationFailed: "অবস্থান ব্যবহারের অনুমতি পাওয়া যায়নি।" },
};

export const PLACES_COPY: Record<Language, { eyebrow: string; heading: string; loading: string; previous: string; next: string; page: string }> = {
  en: { eyebrow: "Explore places", heading: "Places in", loading: "Loading places…", previous: "Previous", next: "Next", page: "Page" },
  it: { eyebrow: "Esplora i luoghi", heading: "Luoghi a", loading: "Caricamento luoghi…", previous: "Precedente", next: "Successivo", page: "Pagina" },
  pt: { eyebrow: "Explorar lugares", heading: "Lugares em", loading: "A carregar lugares…", previous: "Anterior", next: "Seguinte", page: "Página" },
  de: { eyebrow: "Orte entdecken", heading: "Orte in", loading: "Orte werden geladen…", previous: "Zurück", next: "Weiter", page: "Seite" },
  bn: { eyebrow: "জায়গা ঘুরে দেখুন", heading: "যেসব জায়গা", loading: "জায়গা লোড হচ্ছে…", previous: "আগের", next: "পরের", page: "পৃষ্ঠা" },
};

export const FILTER_COPY: Record<Language, {
  category: string; allCategories: string; city: string; enterCity: string; results: string;
  apply: string; clear: string; radius: string; finding: string; useLocation: string; showAll: string;
}> = {
  en: { category: "Category", allCategories: "All categories", city: "City", enterCity: "Enter a city", results: "Results per page", apply: "Apply", clear: "Clear", radius: "Search radius", finding: "Finding location…", useLocation: "Use my location", showAll: "Show all places" },
  it: { category: "Categoria", allCategories: "Tutte le categorie", city: "Città", enterCity: "Inserisci una città", results: "Risultati per pagina", apply: "Applica", clear: "Cancella", radius: "Raggio di ricerca", finding: "Localizzazione…", useLocation: "Usa la mia posizione", showAll: "Mostra tutti i luoghi" },
  pt: { category: "Categoria", allCategories: "Todas as categorias", city: "Cidade", enterCity: "Introduza uma cidade", results: "Resultados por página", apply: "Aplicar", clear: "Limpar", radius: "Raio de pesquisa", finding: "A localizar…", useLocation: "Usar a minha localização", showAll: "Mostrar todos os lugares" },
  de: { category: "Kategorie", allCategories: "Alle Kategorien", city: "Stadt", enterCity: "Stadt eingeben", results: "Ergebnisse pro Seite", apply: "Anwenden", clear: "Zurücksetzen", radius: "Suchradius", finding: "Standort wird ermittelt…", useLocation: "Meinen Standort verwenden", showAll: "Alle Orte anzeigen" },
  bn: { category: "বিভাগ", allCategories: "সব বিভাগ", city: "শহর", enterCity: "শহরের নাম লিখুন", results: "প্রতি পাতায় ফলাফল", apply: "প্রয়োগ করুন", clear: "মুছুন", radius: "অনুসন্ধানের দূরত্ব", finding: "অবস্থান খোঁজা হচ্ছে…", useLocation: "আমার অবস্থান ব্যবহার করুন", showAll: "সব জায়গা দেখান" },
};

export const DISCOVERY_STATUS_COPY: Record<Language, {
  loading: string; one: string; many: (count: number) => string; unavailable: string;
  unsupportedLocation: string; requestingLocation: string; within: (radius: number) => string; locationDenied: string;
}> = {
  en: { loading: "Loading places…", one: "1 place loaded", many: (count) => `${count} places loaded`, unavailable: "Places are temporarily unavailable", unsupportedLocation: "Location services are not supported by this browser.", requestingLocation: "Requesting your location…", within: (radius) => `Showing places within ${radius} km of you.`, locationDenied: "Unable to access your location. Check browser permission." },
  it: { loading: "Caricamento luoghi…", one: "1 luogo caricato", many: (count) => `${count} luoghi caricati`, unavailable: "I luoghi non sono temporaneamente disponibili", unsupportedLocation: "I servizi di localizzazione non sono supportati da questo browser.", requestingLocation: "Richiesta della posizione…", within: (radius) => `Luoghi entro ${radius} km dalla tua posizione.`, locationDenied: "Impossibile accedere alla posizione. Controlla i permessi del browser." },
  pt: { loading: "A carregar lugares…", one: "1 lugar carregado", many: (count) => `${count} lugares carregados`, unavailable: "Os lugares estão temporariamente indisponíveis", unsupportedLocation: "Os serviços de localização não são suportados por este navegador.", requestingLocation: "A solicitar a sua localização…", within: (radius) => `A mostrar lugares num raio de ${radius} km.`, locationDenied: "Não foi possível aceder à localização. Verifique as permissões do navegador." },
  de: { loading: "Orte werden geladen…", one: "1 Ort geladen", many: (count) => `${count} Orte geladen`, unavailable: "Orte sind vorübergehend nicht verfügbar", unsupportedLocation: "Standortdienste werden von diesem Browser nicht unterstützt.", requestingLocation: "Standort wird angefordert…", within: (radius) => `Orte im Umkreis von ${radius} km.`, locationDenied: "Auf den Standort konnte nicht zugegriffen werden. Prüfe die Browserberechtigung." },
  bn: { loading: "জায়গা লোড হচ্ছে…", one: "১টি জায়গা লোড হয়েছে", many: (count) => `${count}টি জায়গা লোড হয়েছে`, unavailable: "জায়গাগুলো সাময়িকভাবে পাওয়া যাচ্ছে না", unsupportedLocation: "এই ব্রাউজার অবস্থান সেবা সমর্থন করে না।", requestingLocation: "আপনার অবস্থান চাওয়া হচ্ছে…", within: (radius) => `আপনার ${radius} কিমি এলাকার জায়গা দেখানো হচ্ছে।`, locationDenied: "আপনার অবস্থান পাওয়া যায়নি। ব্রাউজারের অনুমতি পরীক্ষা করুন।" },
};
