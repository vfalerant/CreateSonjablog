"""
tests/test_navigation_paths.py

A sorozat-navigációs linkek NYELVI URL-ELŐTAGJÁNAK tesztjei
(2026.09.26-i javítás, lásd converter/navigation.py build_post_path).

Futtatás a projekt gyökeréből:

    python -m unittest discover -s tests -t . -v

SEMMILYEN hálózati hívás nincs: a converter/ modul tiszta
string-építés, a wordpress/ modul itt egyáltalán nem szerepel.
"""

import re
import unittest

from converter.navigation import (
    build_navigation_html,
    build_next_part_button_html,
    build_next_part_marker,
    build_post_path,
    build_series_start_html,
    load_series_config,
)


def _hrefs(html):
    return re.findall(r'href="([^"]*)"', html)


class BuildPostPathTests(unittest.TestCase):

    def test_hu_valtozatlan(self):
        self.assertEqual(
            build_post_path("hu", "/emily-naploja-1-bejegyzes/"),
            "/emily-naploja-1-bejegyzes/",
        )

    def test_en_es_elotagot_kap(self):
        self.assertEqual(
            build_post_path("en", "/emilys-diary-entry-1/"),
            "/en/emilys-diary-entry-1/",
        )
        self.assertEqual(
            build_post_path("es", "/el-diario-de-emily-entrada-1/"),
            "/es/el-diario-de-emily-entrada-1/",
        )

    def test_nincs_dupla_elotag(self):
        self.assertEqual(
            build_post_path("en", "/en/emilys-diary-entry-1/"),
            "/en/emilys-diary-entry-1/",
        )
        self.assertEqual(
            build_post_path("es", "/es/el-salon-parte-7/"),
            "/es/el-salon-parte-7/",
        )
        # kétszeri hívás sem toldja meg (idempotens)
        once = build_post_path("en", "/x/")
        self.assertEqual(build_post_path("en", once), once)

    def test_hasonlo_kezdetu_slug_nem_elotag(self):
        # "entry-1" nem "en/" előtag, "espresso" nem "es/" előtag
        self.assertEqual(
            build_post_path("en", "/entry-1/"), "/en/entry-1/"
        )
        self.assertEqual(
            build_post_path("es", "/espresso-parte-1/"),
            "/es/espresso-parte-1/",
        )

    def test_perjel_normalizalas(self):
        for raw in ("slug", "/slug", "slug/", "/slug/"):
            self.assertEqual(build_post_path("en", raw), "/en/slug/")
            self.assertEqual(build_post_path("hu", raw), "/slug/")

    def test_ures_utvonal(self):
        self.assertEqual(build_post_path("hu", "/"), "/")
        self.assertEqual(build_post_path("en", "/"), "/en/")

    def test_abszolut_url_erintetlen(self):
        url = "https://sonjablog.com/en/emilys-diary-entry-1/"
        self.assertEqual(build_post_path("en", url), url)

    def test_ismeretlen_nyelv(self):
        with self.assertRaises(ValueError):
            build_post_path("de", "/x/")


class NavigationLinkTests(unittest.TestCase):
    """A VALÓDI config/sorozatok.json-nal, mindhárom nyelvre."""

    @classmethod
    def setUpClass(cls):
        cls.config = load_series_config()

    def test_sorozat_eleje_emily(self):
        expected = {
            "hu": "/emily-naploja-1-bejegyzes/",
            "en": "/en/emilys-diary-entry-1/",
            "es": "/es/el-diario-de-emily-entrada-1/",
        }
        for nyelv, href in expected.items():
            html = build_series_start_html(
                "Emily naplója", nyelv, self.config
            )
            self.assertEqual(_hrefs(html), [href], nyelv)

    def test_sorozat_eleje_szalon(self):
        expected = {
            "hu": "/a-szalon-1-resz/",
            "en": "/en/the-salon-part-1/",
            "es": "/es/el-salon-parte-1/",
        }
        for nyelv, href in expected.items():
            html = build_series_start_html("A szalon", nyelv, self.config)
            self.assertEqual(_hrefs(html), [href], nyelv)

    def test_kovetkezo_resz_gomb(self):
        cases = [
            ("Emily naplója", "hu", 27, "/emily-naploja-27-bejegyzes/"),
            ("Emily naplója", "en", 27, "/en/emilys-diary-entry-27/"),
            ("Emily naplója", "es", 27,
             "/es/el-diario-de-emily-entrada-27/"),
            ("A szalon", "hu", 7, "/a-szalon-7-resz/"),
            ("A szalon", "en", 7, "/en/the-salon-part-7/"),
            ("A szalon", "es", 7, "/es/el-salon-parte-7/"),
        ]
        for sorozat, nyelv, n, href in cases:
            html = build_next_part_button_html(
                sorozat, nyelv, n, self.config
            )
            self.assertEqual(_hrefs(html), [href], (sorozat, nyelv))

    def test_jelolo_elozetes_gombja_is_elotagos(self):
        # a placeholder-jelölőbe ágyazott (kikommentezett) gomb ugyanazt
        # a linket kapja, mint az éles gomb
        marker = build_next_part_marker(
            "Emily naplója", 26, "en", self.config
        )
        self.assertIn('href="/en/emilys-diary-entry-27/"', marker)
        self.assertNotIn('href="/emilys-diary-entry-27/"', marker)

    def test_teljes_navigacio_en_es(self):
        for nyelv, first, nxt in (
            ("en", "/en/emilys-diary-entry-1/",
             "/en/emilys-diary-entry-27/"),
            ("es", "/es/el-diario-de-emily-entrada-1/",
             "/es/el-diario-de-emily-entrada-27/"),
        ):
            metadata = {
                "sorozat_nev": "Emily naplója",
                "resz_szam": 26,
                "nyelv": nyelv,
            }
            html = build_navigation_html(metadata, self.config)
            self.assertEqual(_hrefs(html), [first, nxt], nyelv)
            # nincs dupla előtag és nincs előtag nélküli link
            self.assertNotIn(f"/{nyelv}/{nyelv}/", html)

    def test_hu_navigacio_nem_valtozik(self):
        metadata = {
            "sorozat_nev": "Emily naplója",
            "resz_szam": 26,
            "nyelv": "hu",
        }
        html = build_navigation_html(metadata, self.config)
        self.assertEqual(
            _hrefs(html),
            ["/emily-naploja-1-bejegyzes/",
             "/emily-naploja-27-bejegyzes/"],
        )

    def test_config_mar_elotagosan_megadva(self):
        config = {
            "Teszt": {
                "en": {
                    "megjelenitett_nev": "Test",
                    "elso_resz_url": "/en/test-1/",
                    "elso_resz_cim": "Test 1",
                    "resz_url_sablon": "/en/test-{resz}/",
                }
            }
        }
        self.assertEqual(
            _hrefs(build_series_start_html("Teszt", "en", config)),
            ["/en/test-1/"],
        )
        self.assertEqual(
            _hrefs(build_next_part_button_html("Teszt", "en", 5, config)),
            ["/en/test-5/"],
        )


if __name__ == "__main__":
    unittest.main()
