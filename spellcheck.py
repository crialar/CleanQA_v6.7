"""Explicit local Hunspell dictionaries. Automatic missing-dictionary installation; no word learning or application memoization."""
from __future__ import annotations
import re, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DICTIONARY_SOURCES: Dict[str, Dict[str, str]] = {
    # -- English variants
    "en_US": {"folder": "en",     "aff": "en_US.aff",       "dic": "en_US.dic"},
    "en_GB": {"folder": "en",     "aff": "en_GB.aff",       "dic": "en_GB.dic"},
    "en_AU": {"folder": "en",     "aff": "en_AU.aff",       "dic": "en_AU.dic"},
    "en_CA": {"folder": "en",     "aff": "en_CA.aff",       "dic": "en_CA.dic"},
    # -- Spanish variants
    "es_ES": {"folder": "es",     "aff": "es_ES.aff",       "dic": "es_ES.dic"},
    "es_MX": {"folder": "es",     "aff": "es_MX.aff",       "dic": "es_MX.dic"},
    "es_AR": {"folder": "es",     "aff": "es_AR.aff",       "dic": "es_AR.dic"},
    # -- French
    "fr_FR": {"folder": "fr_FR/dictionaries",  "aff": "fr.aff", "dic": "fr.dic"},
    # -- German variants (frami flavour shipped by LibreOffice)
    "de_DE": {"folder": "de",     "aff": "de_DE_frami.aff", "dic": "de_DE_frami.dic"},
    "de_AT": {"folder": "de",     "aff": "de_AT_frami.aff", "dic": "de_AT_frami.dic"},
    "de_CH": {"folder": "de",     "aff": "de_CH_frami.aff", "dic": "de_CH_frami.dic"},
    # -- Italian
    "it_IT": {"folder": "it_IT",  "aff": "it_IT.aff",       "dic": "it_IT.dic"},
    # -- Portuguese (BR and PT are linguistically distinct, both kept)
    "pt_BR": {"folder": "pt_BR",  "aff": "pt_BR.aff",       "dic": "pt_BR.dic"},
    "pt_PT": {"folder": "pt_PT",  "aff": "pt_PT.aff",       "dic": "pt_PT.dic"},
    # -- Dutch
    "nl_NL": {"folder": "nl_NL",  "aff": "nl_NL.aff",       "dic": "nl_NL.dic"},
    # -- Slavic
    "pl_PL": {"folder": "pl_PL",  "aff": "pl_PL.aff",       "dic": "pl_PL.dic"},
    "ru_RU": {"folder": "ru_RU",  "aff": "ru_RU.aff",       "dic": "ru_RU.dic"},
    "cs_CZ": {"folder": "cs_CZ",  "aff": "cs_CZ.aff",       "dic": "cs_CZ.dic"},
    "sk_SK": {"folder": "sk_SK",  "aff": "sk_SK.aff",       "dic": "sk_SK.dic"},
    "uk_UA": {"folder": "uk_UA",  "aff": "uk_UA.aff",       "dic": "uk_UA.dic"},
    "bg_BG": {"folder": "bg_BG",  "aff": "bg_BG.aff",       "dic": "bg_BG.dic"},
    "hr_HR": {"folder": "hr_HR",  "aff": "hr_HR.aff",       "dic": "hr_HR.dic"},
    "sl_SI": {"folder": "sl_SI",  "aff": "sl_SI.aff",       "dic": "sl_SI.dic"},
    "sr":    {"folder": "sr",     "aff": "sr.aff",          "dic": "sr.dic"},
    "sr_Latn":{"folder": "sr",    "aff": "sr-Latn.aff",     "dic": "sr-Latn.dic"},
    # -- Nordic
    "sv_SE": {"folder": "sv_SE/dictionaries",  "aff": "sv_SE.aff", "dic": "sv_SE.dic"},
    "da_DK": {"folder": "da_DK",  "aff": "da_DK.aff",       "dic": "da_DK.dic"},
    "nb_NO": {"folder": "no",     "aff": "nb_NO.aff",       "dic": "nb_NO.dic"},
    "nn_NO": {"folder": "no",     "aff": "nn_NO.aff",       "dic": "nn_NO.dic"},
    # -- Other European
    "hu_HU": {"folder": "hu_HU",  "aff": "hu_HU.aff",       "dic": "hu_HU.dic"},
    "el_GR": {"folder": "el_GR",  "aff": "el_GR.aff",       "dic": "el_GR.dic"},
    "ro_RO": {"folder": "ro",     "aff": "ro_RO.aff",       "dic": "ro_RO.dic"},
    "tr_TR": {"folder": "tr_TR",  "aff": "tr_TR.aff",       "dic": "tr_TR.dic"},
    "lt_LT": {"folder": "lt_LT",  "aff": "lt.aff",          "dic": "lt.dic"},
    "lv_LV": {"folder": "lv_LV",  "aff": "lv_LV.aff",       "dic": "lv_LV.dic"},
    "et_EE": {"folder": "et_EE",  "aff": "et_EE.aff",       "dic": "et_EE.dic"},
    # -- Semitic
    "he_IL": {"folder": "he_IL",  "aff": "he_IL.aff",       "dic": "he_IL.dic"},
    "ar":    {"folder": "ar",     "aff": "ar.aff",          "dic": "ar.dic"},
}

BUNDLED_LANGUAGES: Tuple[str, ...] = ("en_US", "es_ES", "fr_FR", "de_DE", "it_IT")

_LANG_NORMALISATION: Dict[str, str] = {
    # English: route every English region to the closest LibreOffice variant.
    "en":    "en_US",
    "en-us": "en_US", "en_us": "en_US",
    "en-gb": "en_GB", "en_gb": "en_GB",
    "en-uk": "en_GB",
    "en-au": "en_AU", "en_au": "en_AU",
    "en-ca": "en_CA", "en_ca": "en_CA",
    "en-nz": "en_AU", "en-ie": "en_GB", "en-za": "en_GB",
    # Spanish: Latin-American variants route to es_MX when available.
    "es":    "es_ES",
    "es-es": "es_ES", "es_es": "es_ES",
    "es-mx": "es_MX", "es_mx": "es_MX",
    "es-ar": "es_AR", "es_ar": "es_AR",
    "es-co": "es_MX", "es-cl": "es_MX", "es-pe": "es_MX",
    "es-uy": "es_AR", "es-ve": "es_MX", "es-419": "es_MX",
    # French: Belgian/Swiss/Canadian fall back to fr_FR (single LO dict).
    "fr":    "fr_FR",
    "fr-fr": "fr_FR", "fr_fr": "fr_FR",
    "fr-ca": "fr_FR", "fr-be": "fr_FR", "fr-ch": "fr_FR", "fr-lu": "fr_FR",
    # German: Austria + Switzerland have their own frami dictionaries.
    "de":    "de_DE",
    "de-de": "de_DE", "de_de": "de_DE",
    "de-at": "de_AT", "de_at": "de_AT",
    "de-ch": "de_CH", "de_ch": "de_CH", "de-li": "de_CH",
    # Italian
    "it":    "it_IT", "it-it": "it_IT", "it_it": "it_IT", "it-ch": "it_IT",
    # Portuguese: keep BR vs PT distinct (very different orthographies).
    "pt":    "pt_PT",
    "pt-pt": "pt_PT", "pt_pt": "pt_PT",
    "pt-br": "pt_BR", "pt_br": "pt_BR",
    "pt-ao": "pt_PT", "pt-mz": "pt_PT",
    # Dutch (Belgium falls back to NL since LO has no nl_BE dictionary).
    "nl":    "nl_NL", "nl-nl": "nl_NL", "nl_nl": "nl_NL", "nl-be": "nl_NL",
    # Slavic
    "pl":    "pl_PL", "pl-pl": "pl_PL", "pl_pl": "pl_PL",
    "ru":    "ru_RU", "ru-ru": "ru_RU", "ru_ru": "ru_RU",
    "cs":    "cs_CZ", "cs-cz": "cs_CZ", "cs_cz": "cs_CZ",
    "sk":    "sk_SK", "sk-sk": "sk_SK", "sk_sk": "sk_SK",
    "uk":    "uk_UA", "uk-ua": "uk_UA", "uk_ua": "uk_UA",
    "bg":    "bg_BG", "bg-bg": "bg_BG", "bg_bg": "bg_BG",
    "hr":    "hr_HR", "hr-hr": "hr_HR", "hr_hr": "hr_HR",
    "sl":    "sl_SI", "sl-si": "sl_SI", "sl_si": "sl_SI",
    "sr":    "sr",    "sr-rs": "sr",    "sr_rs": "sr",
    "sr-cyrl": "sr",  "sr-latn": "sr_Latn",
    # Nordic — Norwegian Bokmål is the default for `no`.
    "sv":    "sv_SE", "sv-se": "sv_SE", "sv_se": "sv_SE", "sv-fi": "sv_SE",
    "da":    "da_DK", "da-dk": "da_DK", "da_dk": "da_DK",
    "no":    "nb_NO",
    "nb":    "nb_NO", "nb-no": "nb_NO", "nb_no": "nb_NO",
    "nn":    "nn_NO", "nn-no": "nn_NO", "nn_no": "nn_NO",
    # Other European
    "hu":    "hu_HU", "hu-hu": "hu_HU", "hu_hu": "hu_HU",
    "el":    "el_GR", "el-gr": "el_GR", "el_gr": "el_GR", "gr": "el_GR",
    "ro":    "ro_RO", "ro-ro": "ro_RO", "ro_ro": "ro_RO", "ro-md": "ro_RO",
    "tr":    "tr_TR", "tr-tr": "tr_TR", "tr_tr": "tr_TR",
    "lt":    "lt_LT", "lt-lt": "lt_LT", "lt_lt": "lt_LT",
    "lv":    "lv_LV", "lv-lv": "lv_LV", "lv_lv": "lv_LV",
    "et":    "et_EE", "et-ee": "et_EE", "et_ee": "et_EE",
    # Semitic
    "he":    "he_IL", "he-il": "he_IL", "he_il": "he_IL", "iw": "he_IL",
    "ar":    "ar",    "ar-sa": "ar", "ar-eg": "ar", "ar-ae": "ar",
    "ar-ma": "ar", "ar-tn": "ar", "ar-jo": "ar", "ar-lb": "ar",
}

def normalize_lang_code(code: Optional[str]) -> Optional[str]:
    """Map an ISO/IETF code to a key in :data:`DICTIONARY_SOURCES`, or None.

    Resolution order (most specific first):
      1. Exact match in :data:`_LANG_NORMALISATION` (e.g. ``es-MX`` -> ``es_MX``).
      2. Exact match against an existing :data:`DICTIONARY_SOURCES` key
         (e.g. the file already labels its target as ``de_AT`` -> kept).
      3. Bare language head in :data:`_LANG_NORMALISATION`
         (e.g. ``zh-Hans`` -> ``zh`` -> not in map -> None).
    Returns ``None`` for genuinely unsupported languages so the caller can
    surface a "spell-check skipped" notice without crashing the QA run.
    """
    if not code:
        return None
    raw = code.strip().lower().replace("_", "-")
    if raw in _LANG_NORMALISATION:
        return _LANG_NORMALISATION[raw]
    # Allow files that already use a DICTIONARY_SOURCES key verbatim
    # (case-insensitive match against the canonical keys).
    raw_underscore = raw.replace("-", "_")
    for canonical in DICTIONARY_SOURCES:
        if canonical.lower() == raw_underscore:
            return canonical
    head = raw.split("-", 1)[0]
    return _LANG_NORMALISATION.get(head)

def bundled_dir() -> Path:
    """Directory where build_exe pre-downloads the 5 default dictionaries.

    Resolution depends on whether the app is running frozen (PyInstaller
    one-file .exe) or as plain source:

    * **Frozen** — PyInstaller's ``--add-data dictionaries;dictionaries``
      extracts the folder under ``sys._MEIPASS`` at startup. The previous
      ``Path(__file__).resolve().parent`` resolved to PyInstaller's
      bootloader temp dir for the *script* — NOT ``_MEIPASS`` — so the
      bundled dictionaries were never found and every language fell
      through to the lazy-download path (including IT, which was supposed
      to ship offline). We now prefer ``sys._MEIPASS`` (where ``--add-data``
      actually lands) and fall back to ``sys.executable.parent`` so users
      who keep a manual ``dictionaries/`` folder beside the .exe also
      work.
    * **Source / dev** — same as before: the ``dictionaries/`` folder
      sitting next to ``spellcheck.py``.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = Path(meipass) / "dictionaries"
            if candidate.exists():
                return candidate
        # Fallback: dictionaries/ folder next to the .exe (user-managed).
        exe_dir = Path(sys.executable).resolve().parent / "dictionaries"
        if exe_dir.exists():
            return exe_dir
        # Last resort — return the _MEIPASS path even if missing so the
        # downstream candidate-check logs a sensible "not found" path.
        if meipass:
            return Path(meipass) / "dictionaries"
    return Path(__file__).resolve().parent / "dictionaries"

_TOKEN_RE = re.compile(
    r"\b[^\W\d_]+(?:['\u2019\u2018\u02bc\-][^\W\d_]+)*\b",
    re.UNICODE,
)

def _tokenize_for_spellcheck(text: str) -> List[str]:
    if not text:
        return []
    return [t for t in _TOKEN_RE.findall(text) if len(t) > 1]

def spell_check_text(text: str, dictionary: Any,
                     ignore_words: Optional[set] = None) -> List[str]:
    """Return a deduplicated, ordered list of misspelled tokens in ``text``.

    Uses the dictionary's case-insensitive lookup heuristic: a token is
    considered correct if either the original or its lowercased form passes.
    Single-character tokens, pure numbers, and tokens in ``ignore_words``
    (case-insensitive) are skipped.
    """
    if not text or dictionary is None:
        return []
    ignore = {w.lower() for w in (ignore_words or set())}
    seen: set = set()
    out: List[str] = []
    for tok in _tokenize_for_spellcheck(text):
        key = tok.lower()
        if key in seen or key in ignore:
            continue
        seen.add(key)
        # Hunspell .aff files typically encode elisions (dell', l', d', etc.)
        # with the straight ASCII apostrophe. Word/InDesign/LibreOffice/Mac
        # may output curly U+2019, left-curly U+2018, or modifier letter
        # apostrophe U+02BC — all of which would otherwise miss those affixes.
        variants = [tok, tok.lower()]
        if any(ch in tok for ch in ("\u2019", "\u2018", "\u02bc")):
            straight = (tok.replace("\u2019", "'")
                          .replace("\u2018", "'")
                          .replace("\u02bc", "'"))
            variants.extend([straight, straight.lower()])
        try:
            if any(dictionary.lookup(v) for v in variants):
                continue
        except Exception as exc:
            raise ValueError('Spell-check lookup failed; this segment was not fully checked.') from exc
        out.append(tok)
    return out

_BASE_URL = "https://raw.githubusercontent.com/LibreOffice/dictionaries/master"
_MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024


def installed_dir():
    """Visible persistent resources beside the application, never a hidden cache."""
    root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    return root / 'dictionaries'


def _read_dictionary(lang, base):
    info = DICTIONARY_SOURCES[lang]
    aff, dic = base / info['aff'], base / info['dic']
    raw=dic.read_bytes()
    if lang=='it_IT':raw=b''.join(l for l in raw.splitlines(keepends=True) if not l.startswith(b'/ ') and l.strip()!=b'/')
    return _load_bytes(aff.read_bytes(),raw)


def _fetch_dictionary_file(url, dest):
    import urllib.request
    request = urllib.request.Request(url, headers={'User-Agent': 'CleanQA/6.6'})
    size = 0
    with urllib.request.urlopen(request, timeout=15) as response, dest.open('wb') as out:
        while True:
            chunk = response.read(65536)
            if not chunk: break
            size += len(chunk)
            if size > _MAX_DOWNLOAD_BYTES: raise ValueError('Dictionary download exceeds 64 MiB per file.')
            out.write(chunk)
    if not size: raise ValueError('Downloaded dictionary file is empty.')


def _install_dictionary(lang):
    import tempfile, os
    info = DICTIONARY_SOURCES[lang]
    root = installed_dir();root.mkdir(parents=True, exist_ok=True)
    # The app serializes QA workers. Publish only a complete, parseable pair.
    with tempfile.TemporaryDirectory(prefix='download-'+lang+'-', dir=root) as tmp:
        stage = Path(tmp)
        for key in ('aff', 'dic'):
            _fetch_dictionary_file(f"{_BASE_URL}/{info['folder']}/{info[key]}", stage / info[key])
        aff = (stage / info['aff']).read_bytes().removeprefix(b'\xef\xbb\xbf')
        first = (stage / info['dic']).read_bytes().removeprefix(b'\xef\xbb\xbf').splitlines()[0].strip()
        if not re.search(rb'^SET\s+\S+', aff, re.MULTILINE) or not first.isdigit():
            raise ValueError('Downloaded files are not a valid Hunspell pair.')
        dictionary = _read_dictionary(lang, stage)
        dest = root / lang
        if not dest.exists(): os.replace(stage, dest)
        else:
            # Repair an incomplete installation, without replacing a complete pair.
            if all((dest/info[k]).is_file() for k in ('aff','dic')): return _read_dictionary(lang, dest)
            for key in ('aff','dic'): os.replace(stage/info[key], dest/info[key])
        return dictionary


def get_dictionary(lang, *, allow_download=True):
    if not lang or lang not in DICTIONARY_SOURCES: return None
    info = DICTIONARY_SOURCES[lang]
    for root in dict.fromkeys([installed_dir(), bundled_dir()]):
        base = root / lang
        if all((base / info[k]).is_file() for k in ('aff', 'dic')):
            return _read_dictionary(lang, base)
    if not allow_download: return None
    try: return _install_dictionary(lang)
    except Exception as exc:
        raise RuntimeError(f"Cannot install dictionary {lang} in {installed_dir()}: {exc}") from exc


def get_negative_reason(lang):
    return 'Dictionary unavailable in dictionaries/' + str(lang)

def _load_pair(stem):
    from spylls.hunspell import Dictionary, readers
    from spylls.hunspell.readers.file_reader import FileReader
    class ClosingReader(FileReader):
        def reset_io(self, obj):
            old=getattr(self, 'io', None)
            if old is not None: old.close()
            super().reset_io(obj)
    aff_reader=ClosingReader(stem+'.aff')
    try: aff, context=readers.read_aff(aff_reader)
    finally: aff_reader.io.close()
    dic_reader=ClosingReader(stem+'.dic',encoding=context.encoding)
    try: dic=readers.read_dic(dic_reader,aff=aff,context=context)
    finally: dic_reader.io.close()
    return Dictionary(aff,dic)


def _load_bytes(aff_bytes,dic_bytes):
    # Remove only an initial UTF-8 signature, before interpreting SET/word count.
    # Keep the encoding declared by SET; BOM-free legacy dictionaries are unchanged.
    aff_bytes = aff_bytes.removeprefix(b'\xef\xbb\xbf')
    dic_bytes = dic_bytes.removeprefix(b'\xef\xbb\xbf')
    import io
    from spylls.hunspell import Dictionary, readers
    from spylls.hunspell.readers.file_reader import BaseReader
    class MemoryReader(BaseReader):
        def __init__(self,raw,encoding='Windows-1252'):
            self.raw=raw;super().__init__(io.StringIO(raw.decode(encoding,errors='surrogateescape')))
        def reset_encoding(self,encoding):
            self.io.close();self.reset_io(io.StringIO(self.raw.decode(encoding,errors='surrogateescape')))
    ar=MemoryReader(aff_bytes)
    try:aff,context=readers.read_aff(ar)
    finally:ar.io.close()
    dr=MemoryReader(dic_bytes,context.encoding)
    try:dic=readers.read_dic(dr,aff=aff,context=context)
    finally:dr.io.close()
    return Dictionary(aff,dic)
