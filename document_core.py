"""Shared, bounded document IO and structure-preserving text operations."""
from __future__ import annotations
import io
import re
import zipfile
import difflib
from lxml import etree

VERSION = '6.6'
XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'
W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XLIFF_URI = 'urn:oasis:names:tc:xliff:document:1.2'
CODE_TAGS = {'ph', 'x', 'bpt', 'ept', 'it', 'bx', 'ex', 'ut'}
MAX_XML_BYTES = 100 * 1024 * 1024
MAX_ZIP_BYTES = 300 * 1024 * 1024
MAX_SEGMENTS = 200000

def local_name(el):
    return etree.QName(el).localname if isinstance(el.tag, str) else ''

def safe_parser():
    return etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True,
                           remove_blank_text=False, strip_cdata=False, recover=False,
                           huge_tree=False, remove_comments=False)

def normalize_xml(data):
    if len(data) > MAX_XML_BYTES:
        raise ValueError('XML exceeds the 100 MiB processing limit. Split the file first.')
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        text = data.decode('utf-16')
        text = re.sub(r'encoding=["\'][^"\']*["\']', 'encoding="UTF-8"', text, count=1)
        return text.encode('utf-8')
    return data[3:] if data.startswith(b'\xef\xbb\xbf') else data

def parse_xml(data, expected=None):
    data = normalize_xml(data)
    # Doctype declarations in ordinary TMX may reference its public DTD.
    # Custom entities are never necessary for supported bilingual files.
    if re.search(br'<!ENTITY\s', data, re.I):
        raise ValueError('Custom XML entities are not supported.')
    tree = etree.fromstring(data, parser=safe_parser())
    if any(isinstance(n, etree._Entity) for n in tree.iter()):
        raise ValueError('Unresolved XML entities are not supported.')
    if expected == 'tmx' and local_name(tree) != 'tmx':
        raise ValueError('Expected a TMX document.')
    if expected == 'mqxliff' and (local_name(tree) != 'xliff' or etree.QName(tree).namespace != XLIFF_URI or tree.get('version', '1.2') != '1.2'):
        raise ValueError('Only namespace-qualified XLIFF 1.2 / MQXLIFF is supported; this file was not checked.')
    return tree

def normalize_lang(code):
    parts = (code or '').strip().replace('_', '-').split('-')
    return '-'.join([parts[0].lower()] + [p.title() if len(p) == 4 else p.upper() for p in parts[1:]])

def tmx_languages(tree):
    header = tree.find('.//header')
    declared = normalize_lang(header.get('srclang', '')) if header is not None else ''
    langs = list(dict.fromkeys(normalize_lang(t.get(XML_LANG) or t.get('lang', '')) for t in tree.xpath('//tu/tuv')))
    langs = [l for l in langs if l]
    src = declared if declared and declared != '*all*' else (langs[0] if langs else '')
    exact = next((l for l in langs if l.lower() == src.lower()), None)
    family = [l for l in langs if l.split('-')[0] == src.split('-')[0]]
    if not exact and len(family) == 1:
        src = family[0]
    if not src or src not in langs:
        raise ValueError('TMX source language cannot be resolved from the header and variants.')
    others = [l for l in langs if l != src]
    if len(others) != 1:
        raise ValueError('Select/export exactly two TMX language variants before processing; found: ' + ', '.join(langs))
    return src, others[0]

def tmx_variant(tu, code):
    code = normalize_lang(code)
    tuvs = list(tu.findall('tuv'))
    exact = [t for t in tuvs if normalize_lang(t.get(XML_LANG) or t.get('lang')) == code]
    fallback = [t for t in tuvs if normalize_lang(t.get(XML_LANG) or t.get('lang')).split('-')[0] == code.split('-')[0]]
    matches = exact or fallback
    if len(matches) > 1:
        raise ValueError('Ambiguous or duplicate TMX language variant: ' + code)
    return matches[0].find('seg') if matches else None

def text_slots(element):
    """Visible text slots, excluding encoded native codes. Includes all tails."""
    slots = []
    def visit(el):
        if not isinstance(el.tag, str):
            return
        if local_name(el) not in CODE_TAGS:
            if el.text is not None:
                slots.append((el, 'text'))
            for child in el:
                visit(child)
                if child.tail is not None:
                    slots.append((child, 'tail'))
    if element is not None:
        visit(element)
    return slots

def visible_text(element):
    return ''.join(getattr(e, a) or '' for e, a in text_slots(element))

def rewrite_slots(slots, old, new):
    """Map equal spans and replacements to original slots; never move XML nodes."""
    if old == new or not slots:
        return
    if len(old) > 200000 or len(new) > 200000:
        raise ValueError('A text segment exceeds 200,000 characters. Split it before editing.')
    import bisect
    starts, pos = [], 0
    for el, attr in slots:
        starts.append(pos)
        pos += len(getattr(el, attr) or '')
    result = [''] * len(slots)
    def bucket(i):
        return min(len(slots)-1, max(0, bisect.bisect_right(starts, i)-1))
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == 'equal':
            for k in range(bucket(i1), len(slots)):
                a, b = max(i1, starts[k]), min(i2, starts[k+1] if k+1<len(slots) else len(old))
                if a < b:
                    result[k] += new[j1+a-i1:j1+b-i1]
                if b >= i2:
                    break
        elif tag in ('replace', 'insert'):
            result[bucket(i1)] += new[j1:j2]
    if ''.join(result) != new:
        raise ValueError('Text reconstruction failed; the file was not exported.')
    for (el, attr), value in zip(slots, result):
        setattr(el, attr, value)
        if attr == 'text' and el.tag == '{'+W_NS+'}t' and value != value.strip():
            el.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

def rewrite_element(element, transform):
    slots = text_slots(element)
    old = ''.join(getattr(e, a) or '' for e, a in slots)
    new = transform(old) if old else old
    rewrite_slots(slots, old, new)
    return old, new

def checked_zip(data):
    if len(data) > MAX_XML_BYTES:
        raise ValueError('Office file exceeds the 100 MiB input limit.')
    z = zipfile.ZipFile(io.BytesIO(data))
    infos = z.infolist()
    if len(infos) > 20000 or sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
        z.close()
        raise ValueError('Office package exceeds the processing size/member limits.')
    if len({i.filename for i in infos}) != len(infos):
        z.close()
        raise ValueError('Office package contains duplicate members.')
    return z

def word_parts(data):
    with checked_zip(data) as z:
        for n in z.namelist():
            if n.startswith('word/') and n.endswith('.xml'):
                yield n, parse_xml(z.read(n))

def word_paragraphs(tree):
    for p in tree.iter('{'+W_NS+'}p'):
        slots = []
        for el in p.iter():
            if not isinstance(el.tag, str) or etree.QName(el).namespace != W_NS:
                continue
            parent = el.getparent()
            while parent is not None and parent.tag != '{'+W_NS+'}p':
                parent = parent.getparent()
            if parent is not p:
                continue
            kind = local_name(el)
            if kind in {'tab','br','cr'}:
                if slots:
                    yield p, slots
                    slots = []
            elif kind in {'t','delText','instrText'}:
                slots.append((el,'text'))
        if slots:
            yield p, slots

def safe_cell(value):
    # CSV text escape. XLSX callers additionally force data_type='s'.
    return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value

class TimedPattern:
    def __init__(self, pattern, flags=0):
        try:
            import regex
        except ImportError as exc:
            raise ValueError('Install the regex dependency to enable regex search.') from exc
        self.pattern = regex.compile(pattern, flags)
        self.timed_out = False
    def search(self, text):
        if self.timed_out: return None
        try: return self.pattern.search(text, timeout=.05)
        except TimeoutError:
            self.timed_out = True
            return None
    def sub(self, repl, text):
        if self.timed_out: return text
        try: return self.pattern.sub(repl, text, timeout=.05)
        except TimeoutError:
            self.timed_out = True
            return text
