-- Faker SQL: schema. Every lookup table is shared by all locales and keyed by `locale`,
-- so a new locale is added with INSERTs only (no new tables, no code changes).

DROP SCHEMA IF EXISTS faker CASCADE;
CREATE SCHEMA faker;

CREATE TABLE faker.locales (
    code      text PRIMARY KEY,               -- e.g. 'en_US'
    name      text NOT NULL,                  -- label shown in the UI
    language  text NOT NULL,
    country   text NOT NULL,
    units     text NOT NULL CHECK (units IN ('metric', 'imperial'))
);

-- First and last names. gender NULL = used for both genders.
CREATE TABLE faker.names (
    id      serial PRIMARY KEY,
    locale  text NOT NULL REFERENCES faker.locales ON DELETE CASCADE,
    kind    text NOT NULL CHECK (kind IN ('first', 'last')),
    gender  char(1) CHECK (gender IN ('M', 'F')),
    value   text NOT NULL,
    weight  double precision NOT NULL DEFAULT 1 CHECK (weight > 0)
);

-- Any other localized vocabulary: titles, street words, cities, e-mail domains, eye colours...
CREATE TABLE faker.words (
    id        serial PRIMARY KEY,
    locale    text NOT NULL REFERENCES faker.locales ON DELETE CASCADE,
    category  text NOT NULL,
    value     text NOT NULL,
    weight    double precision NOT NULL DEFAULT 1 CHECK (weight > 0)
);

-- Templates: {placeholder} for values, # digit, % digit 1-9, ! digit 2-9, ? letter A-F.
CREATE TABLE faker.formats (
    id        serial PRIMARY KEY,
    locale    text NOT NULL REFERENCES faker.locales ON DELETE CASCADE,
    category  text NOT NULL,
    pattern   text NOT NULL,
    weight    double precision NOT NULL DEFAULT 1 CHECK (weight > 0)
);

-- States / provinces with optional postal-code range (used when the locale has one).
CREATE TABLE faker.regions (
    id          serial PRIMARY KEY,
    locale      text NOT NULL REFERENCES faker.locales ON DELETE CASCADE,
    name        text NOT NULL,
    abbr        text,
    postal_min  integer,
    postal_max  integer,
    weight      double precision NOT NULL DEFAULT 1 CHECK (weight > 0)
);

-- Parameters of the normal distributions for body measurements.
CREATE TABLE faker.physical_norms (
    locale       text NOT NULL REFERENCES faker.locales ON DELETE CASCADE,
    gender       char(1) NOT NULL CHECK (gender IN ('M', 'F')),
    height_mean  double precision NOT NULL,   -- cm
    height_sd    double precision NOT NULL,
    bmi_mean     double precision NOT NULL,   -- kg/m2
    bmi_sd       double precision NOT NULL,
    PRIMARY KEY (locale, gender)
);

-- Derived index for O(log n) weighted sampling, rebuilt by CALL faker.rebuild_picks().
-- Each (locale, category) is a list of values whose cumulative weight share is cum_hi;
-- a uniform u in [0,1) selects the first row with cum_hi > u.
CREATE TABLE faker.picks (
    locale    text COLLATE "C" NOT NULL,
    category  text COLLATE "C" NOT NULL,
    cum_hi    double precision NOT NULL,
    value     text NOT NULL,
    ref_id    integer,                        -- source row id (regions use it)
    PRIMARY KEY (locale, category, cum_hi)
);

CREATE INDEX ON faker.names (locale, kind, gender);
CREATE INDEX ON faker.words (locale, category);
CREATE INDEX ON faker.formats (locale, category);
