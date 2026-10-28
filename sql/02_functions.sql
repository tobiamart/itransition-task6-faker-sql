-- Faker SQL: stored procedures and functions.
-- Layers (each one only uses the layers above it):
--   1. random numbers   hash32, locale_salt, user_key, rand, rand_int, rand_normal
--   2. sampling         pick, pick_ref, rebuild_picks (procedure)
--   3. text             fill_pattern, render, slugify
--   4. fields           person, address, geo, physical, phone, email
--   5. entry points     generate_users, benchmark, list_locales

-- ======================================================================= 1. random numbers

-- 32-bit integer hash "lowbias32" (C. Wellons). Bijective on [0, 2^32), good avalanche.
-- Multiplication by the 32-bit constant is split in two 16-bit halves so it never
-- overflows bigint.
CREATE FUNCTION faker.hash32(x bigint) RETURNS bigint
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    h bigint := x & 4294967295;
BEGIN
    h := h # (h >> 16);
    h := (h * 2146121005) & 4294967295;                                    -- 0x7feb352d
    h := h # (h >> 15);
    h := ((h * 42635) + (((h * 33900) & 65535) << 16)) & 4294967295;       -- 0x846ca68b = 33900 * 2^16 + 42635
    RETURN h # (h >> 16);
END $$;

-- Stable 32-bit hash of a text (FNV-style fold of character codes through hash32).
CREATE FUNCTION faker.locale_salt(p_text text) RETURNS bigint
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    h bigint := 2166136261;
    i integer;
BEGIN
    FOR i IN 1 .. length(p_text) LOOP
        h := faker.hash32(h # ascii(substr(p_text, i, 1)));
    END LOOP;
    RETURN h;
END $$;

-- 62-bit key of one fake user: two independent 32-bit hash chains over
-- (locale salt, seed low word, seed high word, batch, index). Every random value of the user
-- is derived from this key and a stream number, so it never depends on other users.
CREATE FUNCTION faker.user_key_salted(p_salt bigint, p_seed bigint, p_batch integer, p_index integer) RETURNS bigint
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    parts bigint[] := ARRAY[p_seed & 4294967295, (p_seed >> 32) & 4294967295, p_batch::bigint & 4294967295, p_index::bigint & 4294967295];
    h1 bigint := p_salt;
    h2 bigint := faker.hash32(p_salt + 1);
    i integer;
BEGIN
    FOR i IN 1 .. 4 LOOP
        h1 := faker.hash32(h1 # faker.hash32(parts[i] + 1013904223::bigint * i));
        h2 := faker.hash32(h2 # faker.hash32(parts[i] + 1664525::bigint * i + 7));
    END LOOP;
    RETURN (h1 << 30) # h2;
END $$;

-- Convenience form taking the locale code.
CREATE FUNCTION faker.user_key(p_locale text, p_seed bigint, p_batch integer, p_index integer) RETURNS bigint
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT faker.user_key_salted(faker.locale_salt(p_locale), p_seed, p_batch, p_index)
$$;

-- Uniform double in (0, 1) for a user key and a stream number: lowbias32 of
-- (high key word XOR stream * golden ratio), XOR low key word, lowbias32 again.
-- Written out in one function (no nested calls) because it is the hottest code path.
CREATE FUNCTION faker.rand(p_key bigint, p_stream integer) RETURNS double precision
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    h bigint := ((p_key >> 30) # (p_stream::bigint * 2654435769)) & 4294967295;
BEGIN
    h := h # (h >> 16);
    h := (h * 2146121005) & 4294967295;
    h := h # (h >> 15);
    h := ((h * 42635) + (((h * 33900) & 65535) << 16)) & 4294967295;
    h := h # (h >> 16);
    h := h # (p_key & 4294967295);
    h := h # (h >> 16);
    h := (h * 2146121005) & 4294967295;
    h := h # (h >> 15);
    h := ((h * 42635) + (((h * 33900) & 65535) << 16)) & 4294967295;
    h := h # (h >> 16);
    RETURN (h::double precision + 0.5) / 4294967296.0;
END $$;

-- Uniform integer in [p_lo, p_hi].
CREATE FUNCTION faker.rand_int(p_key bigint, p_stream integer, p_lo bigint, p_hi bigint) RETURNS bigint
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT p_lo + floor(faker.rand(p_key, p_stream) * (p_hi - p_lo + 1))::bigint
$$;

-- Normal(p_mean, p_sd) by the Box-Muller transform; uses streams p_stream and p_stream + 1.
CREATE FUNCTION faker.rand_normal(p_key bigint, p_stream integer, p_mean double precision, p_sd double precision)
RETURNS double precision
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT p_mean + p_sd * sqrt(-2 * ln(faker.rand(p_key, p_stream))) * cos(2 * pi() * faker.rand(p_key, p_stream + 1))
$$;

-- ======================================================================= 2. sampling

-- Rebuilds faker.picks (cumulative weight shares) from the lookup tables.
-- Call after inserting or changing names, words, formats or regions.
CREATE PROCEDURE faker.rebuild_picks()
LANGUAGE sql AS $$
    TRUNCATE faker.picks;
    INSERT INTO faker.picks (locale, category, cum_hi, value, ref_id)
    SELECT locale, category,
           CASE WHEN rn = cnt THEN 1.0 ELSE cum / total END,
           value, ref_id
    FROM (
        SELECT locale, category, value, ref_id,
               sum(weight) OVER w AS cum,
               sum(weight) OVER (PARTITION BY locale, category) AS total,
               row_number() OVER w AS rn,
               count(*) OVER (PARTITION BY locale, category) AS cnt
        FROM (
            SELECT n.locale, n.kind || ':' || g.gender AS category, n.value, n.weight, n.id AS ref_id
              FROM faker.names n
              CROSS JOIN (VALUES ('M'), ('F')) AS g(gender)
             WHERE n.gender IS NULL OR n.gender = g.gender
            UNION ALL
            SELECT locale, category, value, weight, id FROM faker.words
            UNION ALL
            SELECT locale, 'fmt:' || category, pattern, weight, id FROM faker.formats
            UNION ALL
            SELECT locale, 'region', name, weight, id FROM faker.regions
        ) src
        WINDOW w AS (PARTITION BY locale, category ORDER BY ref_id ROWS UNBOUNDED PRECEDING)
    ) t;
    ANALYZE faker.picks;
$$;

-- Weighted choice: the value whose cumulative share interval contains p_u (0 <= p_u < 1).
-- An index range scan on faker.picks' primary key, O(log n). PL/pgSQL keeps the plan cached.
CREATE FUNCTION faker.pick(p_locale text, p_category text, p_u double precision) RETURNS text
LANGUAGE plpgsql STABLE STRICT PARALLEL SAFE AS $$
BEGIN
    RETURN (SELECT value FROM faker.picks
             WHERE locale = p_locale AND category = p_category AND cum_hi > p_u
             ORDER BY cum_hi
             LIMIT 1);
END $$;

-- Same as pick, but returns the id of the source row (used for regions).
CREATE FUNCTION faker.pick_ref(p_locale text, p_category text, p_u double precision) RETURNS integer
LANGUAGE plpgsql STABLE STRICT PARALLEL SAFE AS $$
BEGIN
    RETURN (SELECT ref_id FROM faker.picks
             WHERE locale = p_locale AND category = p_category AND cum_hi > p_u
             ORDER BY cum_hi
             LIMIT 1);
END $$;

-- ======================================================================= 3. text

-- Replaces pattern characters with random ones: # digit 0-9, % digit 1-9, ! digit 2-9,
-- ? letter A-F (as in 12B). Everything else is copied. Character i uses stream p_stream * 128 + i.
CREATE FUNCTION faker.fill_pattern(p_pattern text, p_key bigint, p_stream integer) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    result text := '';
    c text;
    u double precision;
    i integer;
BEGIN
    IF p_pattern !~ '[#%!?]' THEN
        RETURN p_pattern;
    END IF;
    FOR i IN 1 .. length(p_pattern) LOOP
        c := substr(p_pattern, i, 1);
        IF c IN ('#', '%', '!', '?') THEN
            u := faker.rand(p_key, p_stream * 128 + i);
            c := CASE c
                     WHEN '#' THEN floor(u * 10)::int::text
                     WHEN '%' THEN (1 + floor(u * 9))::int::text
                     WHEN '!' THEN (2 + floor(u * 8))::int::text
                     ELSE chr(65 + floor(u * 6)::int)
                 END;
        END IF;
        result := result || c;
    END LOOP;
    RETURN result;
END $$;

-- Renders a template: digits via fill_pattern, then every {placeholder}, left to right.
-- A placeholder takes its value from p_values when present; otherwise it is drawn from
-- the locale's word list of the same name ({city} -> words category 'city'), with the
-- aliases {any_first}, {any_last} (random first / last name) and {city_any} (= city).
-- Placeholder number n uses stream p_stream * 128 + 64 + n. Repeated spaces are collapsed.
CREATE FUNCTION faker.render(p_locale text, p_pattern text, p_key bigint, p_stream integer,
                             p_values jsonb DEFAULT '{}'::jsonb) RETURNS text
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    result text := faker.fill_pattern(p_pattern, p_key, p_stream);
    open_at integer := strpos(result, '{');
    close_at integer;
    name text;
    val text;
    n integer := 0;
    u double precision;
BEGIN
    WHILE open_at > 0 LOOP
        close_at := strpos(substr(result, open_at), '}');
        EXIT WHEN close_at = 0;
        name := substr(result, open_at + 1, close_at - 2);
        n := n + 1;
        IF p_values ? name THEN
            val := p_values ->> name;
        ELSE
            u := faker.rand(p_key, p_stream * 128 + 64 + n);
            val := CASE name
                       WHEN 'any_first' THEN faker.pick(p_locale, CASE WHEN u < 0.5 THEN 'first:F' ELSE 'first:M' END,
                                                        (u * 2) - floor(u * 2))
                       WHEN 'any_last' THEN faker.pick(p_locale, 'last:M', u)
                       WHEN 'city_any' THEN faker.pick(p_locale, 'city', u)
                       ELSE faker.pick(p_locale, name, u)
                   END;
        END IF;
        result := replace(result, '{' || name || '}', coalesce(val, ''));
        open_at := strpos(result, '{');
    END LOOP;
    IF strpos(result, '  ') > 0 THEN
        result := regexp_replace(result, '\s{2,}', ' ', 'g');
    END IF;
    RETURN btrim(result, ' ,');
END $$;

-- Lower-case ASCII form of a name for e-mail addresses (ü -> ue, ł -> l, spaces dropped).
CREATE FUNCTION faker.slugify(p_text text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT regexp_replace(
               translate(replace(replace(replace(replace(lower(p_text), 'ä', 'ae'), 'ö', 'oe'), 'ü', 'ue'), 'ß', 'ss'),
                         'àáâãåāăąçćčďđèéêëēėęěìíîïīįłñńňòóôõøōőřśšşťùúûůūűųýÿźżž',
                         'aaaaaaaacccddeeeeeeeeiiiiiilnnnooooooorsssstuuuuuuuyyzzz'),
               '[^a-z0-9]', '', 'g')
$$;

-- ======================================================================= 4. fields

CREATE TYPE faker.person_t AS (
    gender char(1), title text, first_name text, middle_name text, last_name text, full_name text);

-- Name with variations chosen by the locale's 'name:M' / 'name:F' formats
-- (title, academic degree, middle name or initial, suffix, double surname...). Streams 100-119.
CREATE FUNCTION faker.person(p_locale text, p_key bigint) RETURNS faker.person_t
LANGUAGE plpgsql STABLE STRICT PARALLEL SAFE AS $$
DECLARE
    g char(1) := CASE WHEN faker.rand(p_key, 100) < 0.5 THEN 'F' ELSE 'M' END;
    fmt text := faker.pick(p_locale, 'fmt:name:' || g, faker.rand(p_key, 101));
    first text := faker.pick(p_locale, 'first:' || g, faker.rand(p_key, 102));
    middle text;
    last text := faker.pick(p_locale, 'last:' || g, faker.rand(p_key, 104));
    vals jsonb := jsonb_build_object('first', first, 'last', last);
    r faker.person_t;
BEGIN
    IF fmt LIKE '%{middle%' THEN
        middle := faker.pick(p_locale, 'first:' || g, faker.rand(p_key, 103));
        IF middle = first THEN   -- never "John John Smith"
            middle := faker.pick(p_locale, 'first:' || g, (faker.rand(p_key, 103) + 0.5) - floor(faker.rand(p_key, 103) + 0.5));
        END IF;
        vals := vals || jsonb_build_object('middle', middle, 'middle_initial', left(middle, 1));
    END IF;
    IF fmt LIKE '%{last2}%' THEN
        vals := vals || jsonb_build_object('last2', faker.pick(p_locale, 'last:' || g, faker.rand(p_key, 105)));
    END IF;
    IF fmt LIKE '%{title}%' THEN
        r.title := faker.pick(p_locale, 'title:' || g, faker.rand(p_key, 106));
        vals := vals || jsonb_build_object('title', r.title);
    END IF;
    IF fmt LIKE '%{suffix}%' THEN
        vals := vals || jsonb_build_object('suffix', faker.pick(p_locale, 'suffix:' || g, faker.rand(p_key, 107)));
    END IF;
    IF fmt LIKE '%{academic}%' THEN
        vals := vals || jsonb_build_object('academic', faker.pick(p_locale, 'academic', faker.rand(p_key, 108)));
    END IF;
    r.gender := g;
    r.first_name := first;
    r.middle_name := middle;
    r.last_name := CASE WHEN vals ? 'last2' THEN last || '-' || (vals ->> 'last2') ELSE last END;
    r.full_name := faker.render(p_locale, fmt, p_key, 110, vals);
    RETURN r;
END $$;

CREATE TYPE faker.address_t AS (
    street text, building text, apartment text, city text, region text, region_abbr text, postcode text, full_address text);

-- Address from the locale's 'street', 'city', 'building', 'apartment', 'postcode' and
-- 'address' formats; the region is drawn by population weight and, when it has a
-- postal-code range (US states), the ZIP code comes from that range. Streams 200-279.
CREATE FUNCTION faker.address(p_locale text, p_key bigint) RETURNS faker.address_t
LANGUAGE plpgsql STABLE STRICT PARALLEL SAFE AS $$
DECLARE
    fmt text := faker.pick(p_locale, 'fmt:address', faker.rand(p_key, 200));
    reg faker.regions;
    zip text;
    r faker.address_t;
BEGIN
    SELECT * INTO reg FROM faker.regions WHERE id = faker.pick_ref(p_locale, 'region', faker.rand(p_key, 201));
    IF reg.postal_min IS NOT NULL THEN
        zip := lpad(faker.rand_int(p_key, 202, reg.postal_min, reg.postal_max)::text, 5, '0');
    END IF;
    r.street := faker.render(p_locale, faker.pick(p_locale, 'fmt:street', faker.rand(p_key, 203)), p_key, 210);
    r.city := faker.render(p_locale, faker.pick(p_locale, 'fmt:city', faker.rand(p_key, 204)), p_key, 220);
    r.building := faker.render(p_locale, faker.pick(p_locale, 'fmt:building', faker.rand(p_key, 205)), p_key, 230);
    IF fmt LIKE '%{apartment}%' THEN
        r.apartment := faker.render(p_locale, faker.pick(p_locale, 'fmt:apartment', faker.rand(p_key, 206)), p_key, 240);
    END IF;
    r.postcode := faker.render(p_locale, faker.pick(p_locale, 'fmt:postcode', faker.rand(p_key, 207)), p_key, 250,
                               jsonb_build_object('zip', zip));
    r.region := reg.name;
    r.region_abbr := reg.abbr;
    r.full_address := faker.render(p_locale, fmt, p_key, 260,
        jsonb_build_object('street', r.street, 'building', r.building, 'apartment', r.apartment, 'city', r.city,
                           'region', r.region, 'region_abbr', coalesce(r.region_abbr, r.region), 'postcode', r.postcode));
    RETURN r;
END $$;

-- Point uniformly distributed on the sphere (equal-area): longitude is uniform, while
-- latitude = asin(2v - 1), because the area of a band between latitudes is proportional
-- to the difference of their sines. Streams 300-301. Rounded to 1e-6 degree (about 0.1 m) so the
-- result does not depend on the last bit of the platform's asin().
CREATE FUNCTION faker.geo(p_key bigint, OUT latitude double precision, OUT longitude double precision)
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT round(degrees(asin(2 * faker.rand(p_key, 300) - 1))::numeric, 6)::double precision,
           round((360 * faker.rand(p_key, 301) - 180)::numeric, 6)::double precision
$$;

CREATE TYPE faker.physical_t AS (
    height_cm numeric, weight_kg numeric, height text, weight text, eye_color text, hair_color text);

-- Height ~ Normal(mean, sd) and body-mass index ~ Normal(mean, sd) from faker.physical_norms
-- (weight = BMI * height^2, so tall people are heavier); eye and hair colour are weighted
-- discrete choices. Text uses feet/inches and pounds for imperial locales. Streams 400-405.
CREATE FUNCTION faker.physical(p_locale text, p_key bigint, p_gender char) RETURNS faker.physical_t
LANGUAGE plpgsql STABLE STRICT PARALLEL SAFE AS $$
DECLARE
    norm faker.physical_norms;
    imperial boolean := (SELECT units = 'imperial' FROM faker.locales WHERE code = p_locale);
    h double precision;
    bmi double precision;
    inches integer;
    r faker.physical_t;
BEGIN
    SELECT * INTO norm FROM faker.physical_norms WHERE locale = p_locale AND gender = p_gender;
    h := faker.rand_normal(p_key, 400, norm.height_mean, norm.height_sd);
    bmi := greatest(16.5, faker.rand_normal(p_key, 402, norm.bmi_mean, norm.bmi_sd));
    r.height_cm := round(h::numeric, 1);
    r.weight_kg := round((bmi * (h / 100) ^ 2)::numeric, 1);
    IF imperial THEN
        inches := round(h / 2.54);
        r.height := format('%s′ %s″', inches / 12, inches % 12);
        r.weight := format('%s lb', round(r.weight_kg * 2.20462));
    ELSE
        r.height := format('%s cm', round(h));
        r.weight := format('%s kg', round(r.weight_kg));
    END IF;
    r.eye_color := faker.pick(p_locale, 'eye_color', faker.rand(p_key, 404));
    r.hair_color := faker.pick(p_locale, 'hair_color', faker.rand(p_key, 405));
    RETURN r;
END $$;

-- Phone number in one of the locale's 'phone' formats. Streams 500-501.
CREATE FUNCTION faker.phone(p_locale text, p_key bigint) RETURNS text
LANGUAGE sql STABLE STRICT PARALLEL SAFE AS $$
    SELECT faker.render(p_locale, faker.pick(p_locale, 'fmt:phone', faker.rand(p_key, 500)), p_key, 501)
$$;

-- E-mail built from the person's names with the locale's 'email' formats and domains. Streams 600-602.
CREATE FUNCTION faker.email(p_locale text, p_key bigint, p_first text, p_last text) RETURNS text
LANGUAGE plpgsql STABLE STRICT PARALLEL SAFE AS $$
DECLARE
    first text := faker.slugify(p_first);
BEGIN
    RETURN faker.render(p_locale, faker.pick(p_locale, 'fmt:email', faker.rand(p_key, 600)), p_key, 602,
                        jsonb_build_object('first', first, 'last', faker.slugify(p_last), 'f', left(first, 1),
                                           'domain', faker.pick(p_locale, 'email_domain', faker.rand(p_key, 601))));
END $$;

-- ======================================================================= 5. entry points

-- Batch of fake users. The user at (locale, seed, batch, index) is always the same,
-- whatever the batch size. seq = batch * size + index (0-based) is for display.
CREATE FUNCTION faker.generate_users(p_locale text, p_seed bigint, p_batch integer DEFAULT 0, p_size integer DEFAULT 10)
RETURNS TABLE (
    seq bigint, batch integer, idx integer,
    full_name text, gender char(1), title text, first_name text, middle_name text, last_name text,
    address text, street text, building text, apartment text, city text, region text, postcode text,
    latitude double precision, longitude double precision,
    height_cm numeric, weight_kg numeric, height text, weight text, eye_color text, hair_color text,
    phone text, email text)
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
#variable_conflict use_variable
DECLARE
    salt bigint := faker.locale_salt(p_locale);
    k bigint;
    i integer;
    p faker.person_t;
    a faker.address_t;
    ph faker.physical_t;
    g record;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM faker.locales WHERE code = p_locale) THEN
        RAISE EXCEPTION 'Unknown locale %', p_locale USING HINT = 'SELECT * FROM faker.list_locales()';
    END IF;
    IF p_seed IS NULL OR p_batch IS NULL OR p_batch < 0 OR p_size IS NULL OR p_size < 1 OR p_size > 1000000 THEN
        RAISE EXCEPTION 'Invalid arguments: seed must be set, batch >= 0, 1 <= size <= 1000000';
    END IF;
    FOR i IN 0 .. p_size - 1 LOOP
        k := faker.user_key_salted(salt, p_seed, p_batch, i);
        p := faker.person(p_locale, k);
        a := faker.address(p_locale, k);
        ph := faker.physical(p_locale, k, p.gender);
        g := faker.geo(k);
        seq := p_batch::bigint * p_size + i;
        batch := p_batch;
        idx := i;
        full_name := p.full_name; gender := p.gender; title := p.title;
        first_name := p.first_name; middle_name := p.middle_name; last_name := p.last_name;
        address := a.full_address; street := a.street; building := a.building; apartment := a.apartment;
        city := a.city; region := a.region; postcode := a.postcode;
        latitude := g.latitude; longitude := g.longitude;
        height_cm := ph.height_cm; weight_kg := ph.weight_kg; height := ph.height; weight := ph.weight;
        eye_color := ph.eye_color; hair_color := ph.hair_color;
        phone := faker.phone(p_locale, k);
        email := faker.email(p_locale, k, p.first_name, p.last_name);
        RETURN NEXT;
    END LOOP;
END $$;

-- Generates p_users users in one call and reports the speed measured inside the database.
CREATE FUNCTION faker.benchmark(p_locale text DEFAULT 'en_US', p_users integer DEFAULT 10000, p_seed bigint DEFAULT 1)
RETURNS TABLE (locale text, users integer, seconds numeric, users_per_second numeric)
LANGUAGE plpgsql VOLATILE AS $$
#variable_conflict use_variable
DECLARE
    t0 timestamptz := clock_timestamp();
    n integer;
BEGIN
    SELECT count(*) INTO n FROM faker.generate_users(p_locale, p_seed, 0, p_users);
    seconds := round(extract(epoch FROM clock_timestamp() - t0)::numeric, 3);
    locale := p_locale;
    users := n;
    users_per_second := round(n / greatest(seconds, 0.001));
    RETURN NEXT;
END $$;

CREATE FUNCTION faker.list_locales() RETURNS TABLE (code text, name text)
LANGUAGE sql STABLE AS $$
    SELECT code, name FROM faker.locales ORDER BY code
$$;
