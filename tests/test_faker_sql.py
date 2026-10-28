"""Tests of the faker SQL library. Run: python -m unittest discover tests
Uses $DATABASE_URL, or a local pgserver instance (pip install pgserver) prepared by tools/setup_db.py.
"""
import math
import os
import unittest
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent


def connect():
    url = os.environ.get('DATABASE_URL')
    if not url:
        import pgserver
        url = pgserver.get_server(str(ROOT / '.pgdata'), cleanup_mode=None).get_uri()
    return psycopg.connect(url, autocommit=True)


class FakerSqlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = connect()
        cls.locales = [r[0] for r in cls.db.execute('SELECT code FROM faker.list_locales()')]

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def one(self, sql, *params):
        return self.db.execute(sql, params).fetchone()

    def users(self, locale, seed, batch, size):
        return self.db.execute('SELECT * FROM faker.generate_users(%s, %s, %s, %s)', (locale, seed, batch, size)).fetchall()

    def test_at_least_two_locales(self):
        self.assertGreaterEqual(len(self.locales), 2)

    def test_same_arguments_same_users(self):
        for loc in self.locales:
            self.assertEqual(self.users(loc, 42, 3, 10), self.users(loc, 42, 3, 10))

    def test_user_depends_on_position_not_batch_size(self):
        a = self.users('en_US', 7, 2, 10)[5][3:]   # skip seq, batch, idx
        b = self.users('en_US', 7, 2, 6)[5][3:]
        self.assertEqual(a, b)

    def test_seed_locale_batch_and_index_all_matter(self):
        base = self.users('en_US', 1, 0, 2)
        self.assertNotEqual(base[0][3:], base[1][3:])
        self.assertNotEqual(base[0][3:], self.users('en_US', 2, 0, 2)[0][3:])
        self.assertNotEqual(base[0][3:], self.users('en_US', 1, 1, 2)[0][3:])
        self.assertNotEqual(base[0][3:], self.users('de_DE', 1, 0, 2)[0][3:])

    def test_no_missing_fields(self):
        for loc in self.locales:
            n = self.one("""SELECT count(*) FROM faker.generate_users(%s, 5, 0, 2000)
                            WHERE full_name IS NULL OR address IS NULL OR city IS NULL OR postcode IS NULL
                               OR phone IS NULL OR email IS NULL OR eye_color IS NULL OR hair_color IS NULL
                               OR email !~ '^[a-z0-9._]+@[a-z0-9.-]+\\.[a-z]+$'""", loc)[0]
            self.assertEqual(n, 0, loc)

    def test_geolocation_uniform_on_sphere(self):
        mean_sin, band, north, lon_ok = self.one("""
            SELECT avg(sin(radians(latitude))), avg((abs(latitude) < 30)::int),
                   avg((latitude > 0)::int), bool_and(longitude BETWEEN -180 AND 180)
            FROM faker.generate_users('de_DE', 99, 0, 20000)""")
        # sin(latitude) is uniform on [-1, 1]: mean 0; the band |lat| < 30 deg holds half the area.
        se = 1 / math.sqrt(3 * 20000)
        self.assertLess(abs(mean_sin), 4 * se)
        self.assertAlmostEqual(float(band), 0.5, delta=0.02)
        self.assertAlmostEqual(float(north), 0.5, delta=0.02)
        self.assertTrue(lon_ok)

    def test_height_is_normal_with_configured_parameters(self):
        rows = self.db.execute("""
            SELECT u.gender, avg(u.height_cm), stddev(u.height_cm), n.height_mean, n.height_sd
            FROM faker.generate_users('en_US', 3, 0, 20000) u
            JOIN faker.physical_norms n ON n.locale = 'en_US' AND n.gender = u.gender
            GROUP BY u.gender, n.height_mean, n.height_sd""").fetchall()
        for gender, mean, sd, mu, sigma in rows:
            self.assertAlmostEqual(float(mean), mu, delta=0.25, msg=gender)
            self.assertAlmostEqual(float(sd), sigma, delta=0.25, msg=gender)

    def test_rand_normal_moments(self):
        mean, sd = self.one("""SELECT avg(z), stddev(z) FROM
            (SELECT faker.rand_normal(faker.user_key('en_US', 1, 0, i), 1, 0, 1) AS z FROM generate_series(0, 49999) i) t""")
        self.assertLess(abs(mean), 0.02)
        self.assertAlmostEqual(sd, 1, delta=0.02)

    def test_pick_follows_weights(self):
        share = self.one("""SELECT avg((faker.pick('en_US', 'eye_color', faker.rand(i, 9)) = 'Brown')::int)
                            FROM generate_series(1, 20000) i""")[0]
        self.assertAlmostEqual(float(share), 0.45, delta=0.015)

    def test_us_zip_matches_state(self):
        bad = self.one("""SELECT count(*) FROM faker.generate_users('en_US', 11, 0, 3000) u
                          JOIN faker.regions r ON r.locale = 'en_US' AND r.name = u.region
                          WHERE left(u.postcode, 5)::int NOT BETWEEN r.postal_min AND r.postal_max""")[0]
        self.assertEqual(bad, 0)

    def test_enough_variety_for_100k_users(self):
        names, emails, rows = self.one("""SELECT count(DISTINCT full_name), count(DISTINCT email), count(*)
                                          FROM faker.generate_users('pl_PL', 8, 0, 100000)""")
        self.assertEqual(rows, 100000)
        self.assertGreater(names / rows, 0.8)
        self.assertGreater(emails / rows, 0.85)

    def test_bad_arguments_raise(self):
        with self.assertRaises(psycopg.errors.RaiseException):
            self.users('xx_XX', 1, 0, 10)
        with self.assertRaises(psycopg.errors.RaiseException):
            self.users('en_US', 1, -1, 10)


if __name__ == '__main__':
    unittest.main()
