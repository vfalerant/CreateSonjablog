<?php
/**
 * CreateSonjaBlog — WordPress-oldali kiegészítés
 *
 * EZT A FÁJLT egy mu-plugin fájlként érdemes elhelyezni:
 *   wp-content/mu-plugins/createsonjablog.php
 * (a "mu-plugins" mappát ha még nem létezik, létre kell hoznod —
 * ezekbe a fájlokba tett kód mindig aktív, nem lehet véletlenül
 * kikapcsolni a Bővítmények oldalon, ami ennek a kódnak fontos,
 * mivel a program működése FÜGGZ tőle).
 *
 * Ha inkább a téma functions.php-jébe tennéd: a "<?php" sort NE
 * másold be még egyszer, ha már van a functions.php tetején.
 *
 * MIT CSINÁL EZ A KÓD:
 *   1. REST-re nyitja a RankMath SEO meta mezőket (enélkül a
 *      WordPress REST API csendben KIHAGYJA őket).
 *   2. Két egyéni REST végpontot regisztrál a Polylang INGYENES
 *      verziójának vezérléséhez (nyelv beállítása, fordítások
 *      összekapcsolása) — mert a Polylang Free ezt nem támogatja
 *      natívan a szabványos REST API-n keresztül.
 *   3. "Bekapcsolja" a REST API "lang" paraméterét kategória-/
 *      egyéb taxonómia-lekérdezésekhez — ez a hivatalos Polylang
 *      dokumentáció szerint ALAPBÓL CSAK a Polylang PRO verzióban
 *      működik; ingyenes verzióban ez a pár soros kód pótolja.
 */

if (!defined('ABSPATH')) {
    exit; // közvetlen elérés tiltva
}


// ============================================================
// 1. RankMath SEO meta mezők REST-re nyitása
// ============================================================

add_action('init', function () {

    $meta_fields = [
        'rank_math_title',
        'rank_math_description',
        'rank_math_focus_keyword',
        'rank_math_primary_category',
    ];

    foreach ($meta_fields as $key) {

        register_post_meta('', $key, [
            'show_in_rest' => true,
            'single'       => true,
            'type'         => 'string',
            'auth_callback' => function () {
                return current_user_can('edit_posts');
            },
        ]);
    }
});


// ============================================================
// 1b. Polylang Free — REST API "lang" paraméter engedélyezése
// ============================================================
//
// HÁTTÉR: a hivatalos Polylang dokumentáció szerint a REST API
// "lang" paramétere (pl. GET /wp/v2/categories?lang=en) ALAPBÓL
// CSAK a Polylang PRO verzióban működik. Ingyenes verzióban a
// WordPress REST API egyszerűen figyelmen kívül hagyja ezt a
// paramétert — emiatt egy kategória-keresés MINDIG a WordPress
// "aktuális nyelvére" (jellemzően az alapértelmezett nyelvre, azaz
// magyarra) szűkül, függetlenül attól, hogy a kérésben mit küldünk.
//
// EZ A KÓD pótolja ezt: a beérkező "lang" GET-paramétert beállítja
// a Polylang belső "aktuális nyelv" állapotába (PLL()->curlang),
// MIELŐTT a WordPress a tényleges lekérdezést lefuttatná — ettől
// kezdve a Polylang saját, meglévő szűrő-logikája (ami egyébként
// is minden lekérdezést az "aktuális nyelvre" szűkít) már a
// HELYES nyelvet fogja használni.
//
// Ez egy jól ismert, a Polylang fejlesztői körben dokumentált
// megoldás (lásd: github.com/polylang/polylang/issues/160).

add_action('rest_api_init', function () {

    if (
        !function_exists('pll_languages_list')
        || !function_exists('pll_default_language')
        || !function_exists('PLL')
    ) {
        // a Polylang nincs aktiválva -> nincs mit tenni
        return;
    }

    $requested_lang = isset($_GET['lang'])
        ? sanitize_text_field(wp_unslash($_GET['lang']))
        : '';

    $available_languages = pll_languages_list();

    // ha a kérésben megadott nyelv NEM egy ismert nyelvkód (pl.
    // elgépelés, vagy a paraméter teljesen hiányzik), biztonságos
    // alapértelmezésként az oldal alapértelmezett nyelvére esünk
    // vissza — ez a korábbi, "lang" paraméter nélküli
    // viselkedéssel egyezik meg, tehát nem ront semmin
    $lang = in_array($requested_lang, $available_languages, true)
        ? $requested_lang
        : pll_default_language();

    $language_object = PLL()->model->get_language($lang);

    if ($language_object) {
        PLL()->curlang = $language_object;
    }
}, 0);
// a "0" prioritás azt jelenti, hogy ez a hook a lehető
// legkorábban fusson le a "rest_api_init" horgon belül, MIELŐTT
// bármelyik REST végpont ténylegesen lekérdezné az adatbázist


// ============================================================
// 2. Polylang integráció — egyéni REST végpontok
// ============================================================

add_action('rest_api_init', function () {

    // --- 2a0. Kategória ID lekérdezése NÉV + NYELV alapján ---
    //
    // Használat: GET /wp-json/sonjablog/v1/category-id?name=The%20Salon&lang=en
    //
    // HÁTTÉR (2026.07.27-i kiegészítés): a szabványos
    // /wp/v2/categories REST végpont "lang" paramétere csak
    // Polylang PRO verzióban működik (lásd a fájl elején lévő
    // megjegyzést). A PLL()->curlang kézi átállítása (lásd fentebb,
    // 1b. blokk) elméletileg pótolná ezt, de gyakorlatban nem
    // minden Polylang verzióval megbízható (nem hivatalos, belső
    // API-ra épül).
    //
    // EHELYETT ez a végpont közvetlenül a PHP-szintű get_terms()
    // függvényt hívja meg, a Polylang saját "lang" query-
    // paraméterével — EZ a Polylang legalapvetőbb, Free verzióban
    // is régóta stabil funkciója (nem REST-specifikus, nem
    // Pro-only), mert maga a Polylang is ezt használja belül
    // mindenhol (pl. az archívum-oldalak, widgetek nyelvi
    // szűréséhez).

    register_rest_route('sonjablog/v1', '/category-id', [
        'methods'  => 'GET',
        'permission_callback' => function () {
            return current_user_can('edit_posts');
        },
        'callback' => function (WP_REST_Request $request) {

            $name = sanitize_text_field(
                (string) $request->get_param('name')
            );
            $lang = sanitize_text_field(
                (string) $request->get_param('lang')
            );

            if (!$name || !$lang) {
                return new WP_Error(
                    'missing_params',
                    'A "name" és "lang" paraméterek megadása '
                    . 'kötelező.',
                    ['status' => 400]
                );
            }

            $args = [
                'taxonomy'   => 'category',
                'hide_empty' => false,
            ];

            // ha a Polylang aktív, a saját "lang" query-paraméterét
            // is átadjuk a get_terms()-nek — ez szűri a
            // kategóriákat a megadott nyelvre
            if (function_exists('pll_languages_list')) {
                $args['lang'] = $lang;
            }

            $terms = get_terms($args);

            if (is_wp_error($terms)) {
                return new WP_Error(
                    'term_query_failed',
                    $terms->get_error_message(),
                    ['status' => 500]
                );
            }

            foreach ($terms as $term) {

                if (
                    mb_strtolower(trim($term->name))
                    === mb_strtolower(trim($name))
                ) {
                    return ['id' => (int) $term->term_id];
                }
            }

            return new WP_Error(
                'category_not_found',
                "Nincs '{$name}' nevű kategória '{$lang}' nyelven.",
                ['status' => 404]
            );
        },
    ]);


    // --- 2a. Nyelv beállítása egy poszthoz ---
    //
    // Használat: POST /wp-json/sonjablog/v1/set-language
    // Body: {"post_id": 11234, "lang": "hu"}

    register_rest_route('sonjablog/v1', '/set-language', [
        'methods'  => 'POST',
        'permission_callback' => function () {
            return current_user_can('edit_posts');
        },
        'callback' => function (WP_REST_Request $request) {

            if (!function_exists('pll_set_post_language')) {
                return new WP_Error(
                    'polylang_missing',
                    'A Polylang plugin nincs aktiválva ezen az oldalon.',
                    ['status' => 500]
                );
            }

            $post_id = (int) $request->get_param('post_id');
            $lang = sanitize_text_field(
                (string) $request->get_param('lang')
            );

            if (!$post_id || !$lang) {
                return new WP_Error(
                    'missing_params',
                    'A "post_id" és "lang" mezők megadása kötelező.',
                    ['status' => 400]
                );
            }

            if (!get_post($post_id)) {
                return new WP_Error(
                    'post_not_found',
                    "Nincs ilyen ID-jű poszt: {$post_id}.",
                    ['status' => 404]
                );
            }

            pll_set_post_language($post_id, $lang);

            return [
                'success' => true,
                'post_id' => $post_id,
                'lang'    => $lang,
            ];
        },
    ]);


    // --- 2b. Posztok összekötése fordításként ---
    //
    // Használat: POST /wp-json/sonjablog/v1/link-translations
    // Body: {"translations": {"hu": 11234, "en": 11267, "es": 11268}}
    //
    // FONTOS: minden itt megadott posztnak MÁR rendelkeznie kell
    // nyelvvel (lásd 2a) — a Polylang ezt várja el a
    // pll_save_post_translations() hívás előtt.

    register_rest_route('sonjablog/v1', '/link-translations', [
        'methods'  => 'POST',
        'permission_callback' => function () {
            return current_user_can('edit_posts');
        },
        'callback' => function (WP_REST_Request $request) {

            if (!function_exists('pll_save_post_translations')) {
                return new WP_Error(
                    'polylang_missing',
                    'A Polylang plugin nincs aktiválva ezen az oldalon.',
                    ['status' => 500]
                );
            }

            $translations = $request->get_param('translations');

            if (!is_array($translations) || empty($translations)) {
                return new WP_Error(
                    'missing_params',
                    'A "translations" mező megadása kötelező, pl. '
                    . '{"hu": 123, "en": 456}.',
                    ['status' => 400]
                );
            }

            // biztonsági tisztítás: csak ismert nyelvkódokat és
            // egész szám poszt ID-kat fogadunk el
            $clean = [];

            foreach ($translations as $lang => $post_id) {

                $lang = sanitize_text_field((string) $lang);
                $post_id = (int) $post_id;

                if (!$lang || !$post_id) {
                    continue;
                }

                if (!get_post($post_id)) {
                    return new WP_Error(
                        'post_not_found',
                        "Nincs ilyen ID-jű poszt: {$post_id}.",
                        ['status' => 404]
                    );
                }

                $clean[$lang] = $post_id;
            }

            if (empty($clean)) {
                return new WP_Error(
                    'missing_params',
                    'Nem maradt érvényes fordítás a tisztítás után.',
                    ['status' => 400]
                );
            }

            pll_save_post_translations($clean);

            return [
                'success'      => true,
                'translations' => $clean,
            ];
        },
    ]);
});
