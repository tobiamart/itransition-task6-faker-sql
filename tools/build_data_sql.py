"""Build sql/03_data.sql: lookup data for every locale.

Names, cities and street words come from the Faker package (MIT licence); formats, titles,
physical norms and other vocabularies are defined below. Run: python tools/build_data_sql.py
"""
import importlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'sql' / '03_data.sql'


def provider(kind, locale):
    return importlib.import_module(f'faker.providers.{kind}.{locale}').Provider


def weighted(items):
    """Faker lists are tuples (equal weight) or OrderedDicts {value: frequency}."""
    if isinstance(items, dict):
        return [(k, float(v)) for k, v in items.items()]
    return [(k, 1.0) for k in items]


def unique(pairs):
    seen, out = set(), []
    for v, w in pairs:
        if v not in seen:
            seen.add(v)
            out.append((v, w))
    return out


def q(v):
    return 'NULL' if v is None else "'" + str(v).replace("'", "''") + "'"


LOCALES = [
    # code, name, language, country, units
    ('en_US', 'English (United States)', 'en', 'US', 'imperial'),
    ('de_DE', 'Deutsch (Deutschland)', 'de', 'DE', 'metric'),
    ('pl_PL', 'Polski (Polska)', 'pl', 'PL', 'metric'),
]

names = []      # (locale, kind, gender, value, weight)
words = []      # (locale, category, value, weight)
formats = []    # (locale, category, pattern, weight)
regions = []    # (locale, name, abbr, postal_min, postal_max, weight)


def add_words(locale, category, items):
    words.extend((locale, category, v, w) for v, w in unique(items))


def add_formats(locale, category, items):
    formats.extend((locale, category, p, w) for p, w in items)


# ------------------------------------------------------------------ en_US
p = provider('person', 'en_US')
names += [('en_US', 'first', 'M', v, w) for v, w in weighted(p.first_names_male)]
names += [('en_US', 'first', 'F', v, w) for v, w in weighted(p.first_names_female)]
names += [('en_US', 'last', None, v, w) for v, w in weighted(p.last_names)]
add_words('en_US', 'title:M', [('Mr.', 85), ('Dr.', 10), ('Prof.', 2), ('Rev.', 3)])
add_words('en_US', 'title:F', [('Mrs.', 40), ('Ms.', 38), ('Miss', 10), ('Dr.', 10), ('Prof.', 2)])
add_words('en_US', 'suffix:M', [('Jr.', 40), ('Sr.', 20), ('II', 10), ('III', 10), ('IV', 2), ('MD', 8), ('PhD', 10)])
add_words('en_US', 'suffix:F', [('MD', 40), ('PhD', 45), ('DDS', 15)])
a = provider('address', 'en_US')
us_streets = ['Main', 'Oak', 'Pine', 'Maple', 'Cedar', 'Elm', 'Washington', 'Lake', 'Hill', 'Park', 'Church', 'Walnut',
              'Spring', 'North', 'South', 'Ridge', 'Sunset', 'Highland', 'Mill', 'River', 'Jackson', 'Lincoln', 'Madison',
              'Franklin', 'Jefferson', 'Adams', 'Center', 'Chestnut', 'Willow', 'Dogwood', 'Meadow', 'Forest', 'Cherry',
              'Hickory', 'Birch', 'Spruce', 'Railroad', 'Valley', 'Prospect', 'School', 'Union', 'Market', 'Water', 'Front',
              'Bridge', 'Broad', 'High', 'King', 'Grove', 'Locust', 'Poplar', 'Laurel', 'Magnolia', 'Sycamore', 'Aspen',
              'Hillcrest', 'Lakeview', 'Riverside', 'Woodland', 'Fairview', 'Pleasant', 'Green', 'Rose', 'Liberty',
              'Independence', 'Monroe', 'Hamilton', 'Wilson', 'Jefferson Davis', 'Peachtree', 'Bay', 'Harbor', 'Canyon',
              'Mesa', 'Prairie', 'Summit', 'Heritage', 'Orchard', 'Vineyard', 'Mountain View', 'Country Club', 'College',
              'University', 'Airport', 'Industrial', 'Commerce', 'Mission', 'Ocean', 'Beach', 'Shore', 'Cypress', 'Palm']
ordinals = []
for n in range(1, 100):
    suf = 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    ordinals.append((f'{n}{suf}', 100.0 / n))   # low numbers are more common
add_words('en_US', 'street_word', [(s, 1) for s in us_streets])
add_words('en_US', 'street_ordinal', ordinals)
us_suffix_weights = {'Street': 30, 'Avenue': 18, 'Road': 12, 'Drive': 10, 'Lane': 8, 'Court': 6, 'Boulevard': 4, 'Way': 5,
                     'Place': 4, 'Circle': 3, 'Trail': 2, 'Parkway': 2}
add_words('en_US', 'street_suffix', [(s, us_suffix_weights.get(s, 0.2)) for s in a.street_suffixes])
add_words('en_US', 'city_prefix', [(c, 1) for c in a.city_prefixes])
add_words('en_US', 'city_suffix', [(c, 1) for c in a.city_suffixes])
state_names = dict(zip([s for s in a.states_abbr if s != 'DC'], a.states)) | {'DC': 'District of Columbia'}
population = {'CA': 39.5, 'TX': 29.1, 'FL': 21.5, 'NY': 20.2, 'PA': 13.0, 'IL': 12.8, 'OH': 11.8, 'GA': 10.7, 'NC': 10.4,
              'MI': 10.1, 'NJ': 9.3, 'VA': 8.6, 'WA': 7.7, 'AZ': 7.2, 'MA': 7.0, 'TN': 6.9, 'IN': 6.8, 'MD': 6.2, 'MO': 6.2,
              'WI': 5.9, 'CO': 5.8, 'MN': 5.7, 'SC': 5.1, 'AL': 5.0, 'LA': 4.7, 'KY': 4.5, 'OR': 4.2, 'OK': 4.0, 'CT': 3.6,
              'UT': 3.3, 'IA': 3.2, 'NV': 3.1, 'AR': 3.0, 'MS': 3.0, 'KS': 2.9, 'NM': 2.1, 'NE': 2.0, 'ID': 1.8, 'WV': 1.8,
              'HI': 1.5, 'NH': 1.4, 'ME': 1.4, 'RI': 1.1, 'MT': 1.1, 'DE': 1.0, 'SD': 0.9, 'ND': 0.8, 'AK': 0.7, 'DC': 0.7,
              'VT': 0.6, 'WY': 0.6}
for abbr, w in population.items():
    lo, hi = a.states_postcode[abbr]
    regions.append(('en_US', state_names[abbr], abbr, lo, hi, w))
add_formats('en_US', 'name:M', [('{first} {last}', 45), ('{first} {middle_initial}. {last}', 15), ('{first} {middle} {last}', 8),
                                ('{title} {first} {last}', 12), ('{title} {first} {middle_initial}. {last}', 5),
                                ('{first} {last} {suffix}', 6), ('{first} {middle_initial}. {last} {suffix}', 3)])
add_formats('en_US', 'name:F', [('{first} {last}', 45), ('{first} {middle_initial}. {last}', 15), ('{first} {middle} {last}', 8),
                                ('{title} {first} {last}', 14), ('{title} {first} {middle_initial}. {last}', 5),
                                ('{first} {last}, {suffix}', 3), ('{first} {last}-{last2}', 4)])
add_formats('en_US', 'street', [('{street_word} {street_suffix}', 55), ('{any_last} {street_suffix}', 25),
                                ('{street_ordinal} {street_suffix}', 15), ('{direction} {street_word} {street_suffix}', 5)])
add_words('en_US', 'direction', [('N', 1), ('S', 1), ('E', 1), ('W', 1)])
add_formats('en_US', 'city', [('{any_first}{city_suffix}', 35), ('{any_last}{city_suffix}', 30),
                              ('{city_prefix} {any_first}{city_suffix}', 15), ('{city_prefix} {any_last}', 10),
                              ('{any_last}', 10)])
add_formats('en_US', 'building', [('%##', 35), ('%###', 30), ('%#', 15), ('%####', 20)])
add_formats('en_US', 'apartment', [('%', 20), ('%#', 40), ('%##', 25), ('%?', 15)])
add_formats('en_US', 'postcode', [('{zip}', 80), ('{zip}-####', 20)])
add_formats('en_US', 'address', [
    ('{building} {street}, {city}, {region_abbr} {postcode}', 50),
    ('{building} {street} Apt. {apartment}, {city}, {region_abbr} {postcode}', 15),
    ('{building} {street}, Suite {apartment}, {city}, {region_abbr} {postcode}', 7),
    ('{building} {street} #{apartment}, {city}, {region_abbr} {postcode}', 6),
    ('{building} {street}, {city}, {region} {postcode}', 17),
    ('PO Box %###, {city}, {region_abbr} {postcode}', 5)])
add_formats('en_US', 'phone', [('(!##) !##-####', 30), ('!##-!##-####', 25), ('!##.!##.####', 10), ('+1 !## !## ####', 12),
                               ('1-!##-!##-####', 10), ('(!##) !##-#### x###', 5), ('+1 (!##) !##-####', 8)])
add_words('en_US', 'email_domain', [('gmail.com', 40), ('yahoo.com', 15), ('outlook.com', 12), ('hotmail.com', 10),
                                    ('aol.com', 5), ('icloud.com', 8), ('comcast.net', 4), ('protonmail.com', 3), ('mail.com', 3)])
add_words('en_US', 'eye_color', [('Brown', 45), ('Blue', 27), ('Hazel', 18), ('Green', 9), ('Gray', 1)])
add_words('en_US', 'hair_color', [('Brown', 40), ('Black', 30), ('Blond', 15), ('Red', 4), ('Gray', 9), ('Auburn', 2)])

# ------------------------------------------------------------------ de_DE
pd = provider('person', 'de_DE')
names += [('de_DE', 'first', 'M', v, w) for v, w in weighted(pd.first_names_male)]
names += [('de_DE', 'first', 'F', v, w) for v, w in weighted(pd.first_names_female)]
de_last = unique(weighted(pd.last_names) + weighted(provider('person', 'de_AT').last_names)
                 + weighted(provider('person', 'de_CH').last_names))
names += [('de_DE', 'last', None, v, w) for v, w in de_last]
add_words('de_DE', 'title:M', [('Herr', 1)])
add_words('de_DE', 'title:F', [('Frau', 1)])
add_words('de_DE', 'academic', [('Dr.', 60), ('Prof. Dr.', 10), ('Dipl.-Ing.', 15), ('Dr. med.', 10), ('Dr.-Ing.', 5)])
ad = provider('address', 'de_DE')
add_words('de_DE', 'city', [(c, 1) for c in ad.cities])
de_roots = ['Haupt', 'Bahnhof', 'Schul', 'Garten', 'Berg', 'Kirch', 'Linden', 'Birken', 'Ahorn', 'Eichen', 'Buchen', 'Tannen',
            'Wald', 'Feld', 'Wiesen', 'Mühlen', 'Rosen', 'Tulpen', 'Nelken', 'Schiller', 'Goethe', 'Mozart', 'Beethoven',
            'Bach', 'Luther', 'Kant', 'Heine', 'Lessing', 'Uhland', 'Bismarck', 'Friedrich', 'Wilhelm', 'Kaiser', 'König',
            'Markt', 'Post', 'Kloster', 'Burg', 'Schloss', 'Brunnen', 'Quell', 'Bach', 'Sonnen', 'Mond', 'Stern', 'Hof',
            'Dorf', 'Stadt', 'Park', 'Hafen', 'Kanal', 'Fluss', 'See', 'Teich', 'Weiden', 'Erlen', 'Kastanien', 'Holunder',
            'Flieder', 'Lerchen', 'Finken', 'Amsel', 'Drossel', 'Meisen', 'Falken', 'Adler', 'Industrie', 'Gewerbe', 'Handwerker',
            'Rathaus', 'Kirchhof', 'Friedhof', 'Turm', 'Tor', 'Brücken', 'Mühlbach', 'Sand', 'Stein', 'Heide', 'Moor', 'Acker',
            'Obst', 'Wein', 'Hopfen', 'Gersten', 'Weizen', 'Korn', 'Raiffeisen', 'Bürger', 'Frieden', 'Freiheits', 'Einheits']
add_words('de_DE', 'street_root', [(r, 1) for r in dict.fromkeys(de_roots)])
add_words('de_DE', 'street_suffix', [('straße', 40), ('weg', 22), ('str.', 6), ('allee', 6), ('gasse', 6), ('platz', 6),
                                     ('ring', 6), ('damm', 3), ('steig', 2), ('pfad', 3)])
add_words('de_DE', 'street_suffix_long', [('Straße', 60), ('Weg', 20), ('Allee', 8), ('Platz', 6), ('Ring', 6)])
add_words('de_DE', 'street_fixed', [(s, 1) for s in ['Am Markt', 'Am Bahnhof', 'An der Kirche', 'Im Winkel', 'Am Anger',
                                                      'Im Wiesengrund', 'Auf dem Berg', 'Am Mühlbach', 'Zur Linde', 'Am Sportplatz',
                                                      'Hinter den Gärten', 'In der Aue', 'Am Waldrand', 'Unter den Linden',
                                                      'Am Schlossgarten', 'An der Mühle', 'Im Grund', 'Am Hang', 'Am Teich',
                                                      'Neuer Weg', 'Alte Dorfstraße', 'Lange Reihe', 'Kurze Straße']])
de_states = [('Nordrhein-Westfalen', 'NW', 17.9), ('Bayern', 'BY', 13.1), ('Baden-Württemberg', 'BW', 11.1),
             ('Niedersachsen', 'NI', 8.0), ('Hessen', 'HE', 6.3), ('Sachsen', 'SN', 4.1), ('Rheinland-Pfalz', 'RP', 4.1),
             ('Berlin', 'BE', 3.7), ('Schleswig-Holstein', 'SH', 2.9), ('Brandenburg', 'BB', 2.5), ('Sachsen-Anhalt', 'ST', 2.2),
             ('Thüringen', 'TH', 2.1), ('Hamburg', 'HH', 1.9), ('Mecklenburg-Vorpommern', 'MV', 1.6), ('Saarland', 'SL', 1.0),
             ('Bremen', 'HB', 0.7)]
regions += [('de_DE', n, ab, None, None, w) for n, ab, w in de_states]
add_formats('de_DE', 'name:M', [('{first} {last}', 50), ('{first} {middle} {last}', 10), ('{first}-{middle} {last}', 8),
                                ('{title} {first} {last}', 15), ('{academic} {first} {last}', 9),
                                ('{title} {academic} {first} {last}', 5), ('{last}, {first}', 3)])
add_formats('de_DE', 'name:F', [('{first} {last}', 48), ('{first} {middle} {last}', 10), ('{first}-{middle} {last}', 6),
                                ('{title} {first} {last}', 15), ('{academic} {first} {last}', 8),
                                ('{title} {academic} {first} {last}', 5), ('{first} {last}-{last2}', 5), ('{last}, {first}', 3)])
add_formats('de_DE', 'street', [('{street_root}{street_suffix}', 45), ('{any_last}{street_suffix}', 20),
                                ('{any_first}-{any_last}-{street_suffix_long}', 10), ('{street_fixed}', 15),
                                ('{city_any}er {street_suffix_long}', 10)])
add_formats('de_DE', 'building', [('%', 28), ('%#', 50), ('%##', 6), ('%?', 10), ('%#?', 6)])
add_formats('de_DE', 'apartment', [('%', 60), ('%#', 40)])
add_formats('de_DE', 'postcode', [('%####', 1)])
add_formats('de_DE', 'city', [('{city}', 1)])
add_formats('de_DE', 'address', [('{street} {building}, {postcode} {city}', 65),
                                 ('{street} {building}, Whg. {apartment}, {postcode} {city}', 10),
                                 ('{street} {building}, {postcode} {city}, {region}', 12),
                                 ('{street} {building}, D-{postcode} {city}', 8),
                                 ('Postfach %####, {postcode} {city}', 5)])
add_formats('de_DE', 'phone', [('0%## #######', 20), ('+49 %## #######', 15), ('(0%##) ### ####', 12), ('0%##/######', 12),
                               ('+49 (0)%## ### ###', 8), ('015# ########', 10), ('+49 17# #######', 13), ('0049 %## #######', 10)])
add_words('de_DE', 'email_domain', [('gmail.com', 25), ('web.de', 20), ('gmx.de', 20), ('t-online.de', 12), ('outlook.de', 8),
                                    ('yahoo.de', 5), ('freenet.de', 4), ('posteo.de', 3), ('mail.de', 3)])
add_words('de_DE', 'eye_color', [('Blau', 35), ('Braun', 30), ('Grün', 15), ('Grau', 10), ('Haselnuss', 10)])
add_words('de_DE', 'hair_color', [('Braun', 40), ('Blond', 25), ('Schwarz', 15), ('Rot', 4), ('Grau', 14), ('Dunkelblond', 2)])

# ------------------------------------------------------------------ pl_PL
pp = provider('person', 'pl_PL')
names += [('pl_PL', 'first', 'M', v, w) for v, w in weighted(pp.first_names_male)]
names += [('pl_PL', 'first', 'F', v, w) for v, w in weighted(pp.first_names_female)]
names += [('pl_PL', 'last', None, v, w) for v, w in weighted(pp.unisex_last_names)]


def feminine(surname):
    for m, f in (('cki', 'cka'), ('dzki', 'dzka'), ('ski', 'ska'), ('zki', 'zka'), ('ny', 'na'), ('y', 'a'), ('i', 'a')):
        if surname.endswith(m):
            return surname[: -len(m)] + f
    return surname


names += [('pl_PL', 'last', 'M', v, w) for v, w in weighted(pp.male_last_names)]
names += [('pl_PL', 'last', 'F', feminine(v), w) for v, w in weighted(pp.male_last_names)]
add_words('pl_PL', 'title:M', [('Pan', 1)])
add_words('pl_PL', 'title:F', [('Pani', 1)])
add_words('pl_PL', 'academic', [('dr', 40), ('mgr', 25), ('inż.', 12), ('mgr inż.', 12), ('dr hab.', 7), ('prof.', 4)])
apl = provider('address', 'pl_PL')
add_words('pl_PL', 'city', [(c, 1) for c in apl.cities])
pl_dates = {'Lipca': '22 Lipca', 'Stycznia': '17 Stycznia', 'Maja': '3 Maja', 'Listopada': '11 Listopada'}
add_words('pl_PL', 'street_name', [(pl_dates.get(s, s), 1) for s in apl.streets])
add_words('pl_PL', 'street_prefix', [('ul.', 80), ('al.', 10), ('pl.', 5), ('os.', 5)])
pl_regions = [('mazowieckie', 5.4), ('śląskie', 4.5), ('wielkopolskie', 3.5), ('małopolskie', 3.4), ('dolnośląskie', 2.9),
              ('łódzkie', 2.4), ('pomorskie', 2.3), ('lubelskie', 2.1), ('podkarpackie', 2.1), ('kujawsko-pomorskie', 2.0),
              ('zachodniopomorskie', 1.7), ('warmińsko-mazurskie', 1.4), ('świętokrzyskie', 1.2), ('podlaskie', 1.2),
              ('lubuskie', 1.0), ('opolskie', 1.0)]
regions += [('pl_PL', n, None, None, None, w) for n, w in pl_regions]
add_formats('pl_PL', 'name:M', [('{first} {last}', 55), ('{first} {middle} {last}', 15), ('{title} {first} {last}', 12),
                                ('{academic} {first} {last}', 10), ('{title} {academic} {first} {last}', 3),
                                ('{last} {first}', 5)])
add_formats('pl_PL', 'name:F', [('{first} {last}', 50), ('{first} {middle} {last}', 14), ('{title} {first} {last}', 12),
                                ('{academic} {first} {last}', 9), ('{first} {last}-{last2}', 10),
                                ('{title} {academic} {first} {last}', 2), ('{last} {first}', 3)])
add_formats('pl_PL', 'street', [('{street_prefix} {street_name}', 85), ('{street_name}', 15)])
add_formats('pl_PL', 'building', [('%', 30), ('%#', 52), ('%##', 6), ('%?', 12)])
add_formats('pl_PL', 'apartment', [('%', 38), ('%#', 59), ('%##', 3)])
add_formats('pl_PL', 'postcode', [('%#-###', 1)])
add_formats('pl_PL', 'city', [('{city}', 1)])
add_formats('pl_PL', 'address', [('{street} {building}, {postcode} {city}', 50),
                                 ('{street} {building}/{apartment}, {postcode} {city}', 35),
                                 ('{street} {building} m. {apartment}, {postcode} {city}', 5),
                                 ('{street} {building}, {postcode} {city}, woj. {region}', 10)])
add_formats('pl_PL', 'phone', [('+48 %## ### ###', 30), ('%## ### ###', 25), ('%##-###-###', 15), ('(%#) ### ## ##', 10),
                               ('+48 (%#) ### ## ##', 8), ('0048 %## ### ###', 7), ('%########', 5)])
add_words('pl_PL', 'email_domain', [('gmail.com', 35), ('wp.pl', 18), ('onet.pl', 15), ('interia.pl', 12), ('o2.pl', 10),
                                    ('outlook.com', 5), ('poczta.fm', 3), ('tlen.pl', 2)])
add_words('pl_PL', 'eye_color', [('niebieskie', 35), ('piwne', 25), ('brązowe', 20), ('zielone', 12), ('szare', 8)])
add_words('pl_PL', 'hair_color', [('ciemny blond', 30), ('brązowe', 25), ('blond', 15), ('czarne', 10), ('rude', 4), ('siwe', 16)])

# ------------------------------------------------------------------ shared formats (same rules, every locale)
for loc, *_ in LOCALES:
    add_formats(loc, 'email', [('{first}.{last}@{domain}', 30), ('{first}{last}@{domain}', 12), ('{f}{last}@{domain}', 15),
                               ('{first}_{last}##@{domain}', 8), ('{last}.{first}@{domain}', 8), ('{first}##@{domain}', 7),
                               ('{f}.{last}###@{domain}', 6), ('{first}.{last}####@{domain}', 6), ('{last}{f}@{domain}', 8)])

# height in cm (mean, sd) and body-mass index (mean, sd) by locale and gender
NORMS = [('en_US', 'M', 175.4, 7.4, 29.0, 5.5), ('en_US', 'F', 161.7, 7.0, 29.5, 6.5),
         ('de_DE', 'M', 179.9, 7.2, 27.0, 4.5), ('de_DE', 'F', 166.2, 6.6, 25.5, 5.0),
         ('pl_PL', 'M', 178.7, 7.0, 27.2, 4.5), ('pl_PL', 'F', 165.1, 6.4, 25.4, 5.0)]


def rows(table, cols, data):
    out = [f'INSERT INTO faker.{table} ({", ".join(cols)}) VALUES']
    out.append(',\n'.join('(' + ', '.join(q(v) for v in r) + ')' for r in data) + ';')
    return '\n'.join(out)


sql = ['-- Generated by tools/build_data_sql.py. Do not edit by hand.', 'BEGIN;',
       'TRUNCATE faker.names, faker.words, faker.formats, faker.regions, faker.physical_norms, faker.locales CASCADE;',
       rows('locales', ['code', 'name', 'language', 'country', 'units'], LOCALES),
       rows('names', ['locale', 'kind', 'gender', 'value', 'weight'], names),
       rows('words', ['locale', 'category', 'value', 'weight'], words),
       rows('formats', ['locale', 'category', 'pattern', 'weight'], formats),
       rows('regions', ['locale', 'name', 'abbr', 'postal_min', 'postal_max', 'weight'], regions),
       rows('physical_norms', ['locale', 'gender', 'height_mean', 'height_sd', 'bmi_mean', 'bmi_sd'], NORMS),
       'CALL faker.rebuild_picks();', 'COMMIT;', '']
OUT.parent.mkdir(exist_ok=True)
OUT.write_text('\n\n'.join(sql), encoding='utf-8')
print(f'{OUT.name}: {len(names)} names, {len(words)} words, {len(formats)} formats, {len(regions)} regions')
