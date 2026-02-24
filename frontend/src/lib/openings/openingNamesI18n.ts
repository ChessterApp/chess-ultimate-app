const OPENING_NAMES: Record<string, Record<string, string>> = {
  ru: {
    "Sicilian Defense": "Сицилианская защита",
    "French Defense": "Французская защита",
    "Caro-Kann Defense": "Защита Каро-Канн",
    "Italian Game": "Итальянская партия",
    "Ruy Lopez": "Испанская партия",
    "King's Pawn Game": "Дебют королевской пешки",
    "Queen's Pawn Game": "Дебют ферзевой пешки",
    "Queen's Gambit": "Ферзевый гамбит",
    "King's Indian Defense": "Староиндийская защита",
    "Scotch Game": "Шотландская партия",
    "English Opening": "Английское начало",
    "Pirc Defense": "Защита Пирца",
    "Modern Defense": "Современная защита",
    "Scandinavian Defense": "Скандинавская защита",
    "Dutch Defense": "Голландская защита",
    "Nimzo-Indian Defense": "Защита Нимцовича",
    "Slav Defense": "Славянская защита",
    "Grünfeld Defense": "Защита Грюнфельда",
    "Benoni Defense": "Защита Бенони",
    "Catalan Opening": "Каталонское начало",
    "London System": "Лондонская система",
    "King's Gambit": "Королевский гамбит",
    "Philidor Defense": "Защита Филидора",
    "Petrov Defense": "Русская партия",
    "Vienna Game": "Венская партия",
    "Alekhine Defense": "Защита Алехина",
    "Bird's Opening": "Дебют Берда",
    "Réti Opening": "Дебют Рети",
    "Nimzowitsch-Larsen Attack": "Дебют Нимцовича-Ларсена",
    "Uncommon Opening": "Необычный дебют",
    "Ponziani Opening": "Дебют Понциани",
    "Four Knights Game": "Дебют четырёх коней",
    "Three Knights Opening": "Дебют трёх коней",
    "Bishop's Opening": "Дебют слона",
    "Giuoco Piano": "Тихая итальянская",
    "Evans Gambit": "Гамбит Эванса",
    "Sicilian: Najdorf": "Сицилианская: Найдорф",
    "Sicilian: Dragon": "Сицилианская: Дракон",
    "Sicilian: Alapin": "Сицилианская: Алапин",
    "Sicilian: Scheveningen": "Сицилианская: Шевенинген",
    "Sicilian: Closed": "Сицилианская: Закрытый вариант",
    "Queen's Gambit Declined": "Отказанный ферзевый гамбит",
    "Queen's Gambit Accepted": "Принятый ферзевый гамбит",
    "Trompowsky Attack": "Атака Тромповского",
    "Bogo-Indian Defense": "Защита Боголюбова",
    "Old Indian Defense": "Старо-индийская защита",
    "Budapest Gambit": "Будапештский гамбит",
    "Tarrasch Defense": "Защита Тарраша",
    "Semi-Slav Defense": "Полуславянская защита",
    "Zukertort Opening": "Дебют Цукерторта",
  },
  kz: {
    "Sicilian Defense": "Сицилиялық қорғаныс",
    "French Defense": "Француз қорғанысы",
    "Caro-Kann Defense": "Каро-Канн қорғанысы",
    "Italian Game": "Итальян партиясы",
    "Ruy Lopez": "Испан партиясы",
    "King's Pawn Game": "Король пешкасының дебюті",
    "Queen's Pawn Game": "Ферзь пешкасының дебюті",
    "Queen's Gambit": "Ферзь гамбиті",
    "King's Indian Defense": "Патша үнді қорғанысы",
    "Scotch Game": "Шотланд партиясы",
    "English Opening": "Ағылшын дебюті",
    "Pirc Defense": "Пирц қорғанысы",
    "Modern Defense": "Қазіргі қорғаныс",
    "Scandinavian Defense": "Скандинав қорғанысы",
    "Dutch Defense": "Голланд қорғанысы",
    "Nimzo-Indian Defense": "Нимцович қорғанысы",
    "Slav Defense": "Славян қорғанысы",
    "Grünfeld Defense": "Грюнфельд қорғанысы",
    "Benoni Defense": "Бенони қорғанысы",
    "Catalan Opening": "Каталон дебюті",
    "London System": "Лондон жүйесі",
    "King's Gambit": "Король гамбиті",
    "Philidor Defense": "Филидор қорғанысы",
    "Petrov Defense": "Орыс партиясы",
    "Vienna Game": "Вена партиясы",
    "Alekhine Defense": "Алехин қорғанысы",
    "Bird's Opening": "Бёрд дебюті",
    "Réti Opening": "Рети дебюті",
    "Nimzowitsch-Larsen Attack": "Нимцович-Ларсен шабуылы",
    "Uncommon Opening": "Сирек дебют",
    "Four Knights Game": "Төрт ат дебюті",
    "Sicilian: Najdorf": "Сицилиялық: Найдорф",
    "Sicilian: Dragon": "Сицилиялық: Айдаһар",
    "Sicilian: Alapin": "Сицилиялық: Алапин",
    "Queen's Gambit Declined": "Қабылданбаған ферзь гамбиті",
    "Queen's Gambit Accepted": "Қабылданған ферзь гамбиті",
    "Trompowsky Attack": "Тромповский шабуылы",
    "Semi-Slav Defense": "Жартылай славян қорғанысы",
  }
};

export function translateOpeningName(name: string, locale: string): string {
  if (locale === 'en') return name;
  const map = OPENING_NAMES[locale];
  if (!map) return name;

  if (map[name]) return map[name];

  const baseName = name.split(/[,:]/)[0].trim();
  if (map[baseName]) {
    const suffix = name.slice(baseName.length);
    return map[baseName] + suffix;
  }

  for (const [en, translated] of Object.entries(map)) {
    if (name.startsWith(en)) {
      return translated + name.slice(en.length);
    }
  }

  return name;
}
