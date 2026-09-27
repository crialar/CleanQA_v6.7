"""Bounded XML iteration. Large plain XML is not rejected by total file size."""
from pathlib import Path
from lxml import etree as E
import zipfile
import qa_checker as q
from document_core import XML_LANG, XLIFF_URI, W_NS, normalize_lang, local_name, tmx_variant, word_paragraphs

def events(source):
    if isinstance(source,Path):source=str(source)
    elif hasattr(source,'seek'):source.seek(0)
    return E.iterparse(source,events=('start','end'),resolve_entities=False,load_dtd=False,no_network=True,huge_tree=False,recover=False)

def release(el):
    parent=el.getparent()
    el.clear()
    if parent is not None:
        while el.getprevious() is not None:del parent[0]

def validate_entities(el):
    if any(isinstance(n,E._Entity) for n in el.iter()):raise ValueError('XML entities are not supported.')

def inspect_file(path,name,pulse):
    fmt=q._detect_format(b'',name)
    if fmt=='docx':
        with zipfile.ZipFile(path) as z:
            infos=z.infolist()
            if 'word/document.xml' not in z.namelist():raise ValueError('Not a Word document.')
            if len(infos)>20000 or len({i.filename for i in infos})!=len(infos):raise ValueError('Office package has too many or duplicate members.')
            # Reject dangerous compression ratios rather than valid large text by a small absolute cap.
            expanded=sum(i.file_size for i in infos);compressed=sum(i.compress_size for i in infos)
            if (expanded>100*1024*1024 and expanded/max(compressed,1)>500) or any(i.file_size>100*1024*1024 and i.file_size/max(i.compress_size,1)>500 for i in infos):raise ValueError('Office package has an unsafe compression ratio.')
        return fmt,'',''
    if fmt=='doc':raise ValueError('Convert legacy .doc to .docx before QA.')
    root_checked=False;declared='';langs=set();pairs=set();count=0
    for event,el in events(path):
        tag=local_name(el)
        if not root_checked:
            root_checked=True
            if fmt=='tmx' and tag!='tmx':raise ValueError('Expected TMX.')
            if fmt=='mqxliff' and (el.tag!='{'+XLIFF_URI+'}xliff' or el.get('version')!='1.2'):raise ValueError('Only XLIFF 1.2 is supported.')
        if event=='start':
            if tag=='header' and fmt=='tmx':declared=normalize_lang(el.get('srclang'))
            if tag=='file' and fmt=='mqxliff':pairs.add((normalize_lang(el.get('source-language')),normalize_lang(el.get('target-language'))))
            if tag=='tuv' and fmt=='tmx':langs.add(normalize_lang(el.get(XML_LANG) or el.get('lang')))
        elif tag in {'tu','trans-unit'}:
            validate_entities(el);count+=1
            if count%100==0:pulse('Reading and validating',count,None)
            release(el)
    if not count:raise ValueError('No supported segments found.')
    if fmt=='tmx':
        if '' in langs or len(langs)!=2:raise ValueError('Export exactly two explicit TMX language variants.')
        if not declared or declared=='*all*':raise ValueError('TMX must declare its source language; no language is guessed.')
        if declared not in langs:
            matches=[l for l in langs if l.split('-')[0]==declared.split('-')[0]]
            if len(matches)!=1:raise ValueError('Ambiguous TMX source language.')
            declared=matches[0]
        return fmt,declared,next(l for l in langs if l!=declared)
    if len(pairs)!=1 or not all(next(iter(pairs))):raise ValueError('Split files into one explicit language pair each.')
    return fmt,*next(iter(pairs))

def segment(src,tgt,idx,original):
    sr=q._element_text(src);tr=q._element_text(tgt)
    return dict(id=idx,original_id=original,source_text=q._strip_pseudo_tags(sr),target_text=q._strip_pseudo_tags(tr),
        source_text_glossary=q._strip_pseudo_tags(sr),target_text_glossary=q._strip_pseudo_tags(tr),
        source_text_raw=sr,target_text_raw=tr,source_text_display=q._strip_pseudo_tags(q._element_text_with_markers(src)),
        target_text_display=q._strip_pseudo_tags(q._element_text_with_markers(tgt)),
        target_text_edges=q._strip_pseudo_tags(q._element_text_with_markers(tgt,include_formatting_markers=False)),
        source_tags=q._inline_tags(src),target_tags=q._inline_tags(tgt),has_tags=tgt is not None and len(tgt)>0)

def read_segments(path,fmt,source,target,pulse,overrides=None):
    overrides=overrides or {};idx=0
    if fmt=='docx':
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.startswith('word/') or not name.endswith('.xml'):continue
                with z.open(name) as stream:
                    for event,el in events(stream):
                        if event!='end' or el.tag!='{'+W_NS+'}p':continue
                        # Nested textbox paragraphs are emitted separately; outer parents ignore them.
                        for _,slots in word_paragraphs(el):
                            if _ is not el:continue
                            text=''.join(e.text or '' for e,a in slots if local_name(e)=='t')
                            if not text.strip():continue
                            idx+=1;seg=q._make_word_segment(idx,text);seg.update(original_id=f'{name}:{idx}',has_tags=False)
                            yield seg
                            pulse('Reading Word document',idx,None)
                        release(el)
        if not idx:raise ValueError('No supported Word text found.')
        return
    for event,el in events(path):
        if event!='end' or local_name(el)!=('tu' if fmt=='tmx' else 'trans-unit'):continue
        validate_entities(el);idx+=1
        if fmt=='tmx':src,tgt=tmx_variant(el,source),tmx_variant(el,target)
        else:src,tgt=el.find('{'+XLIFF_URI+'}source'),el.find('{'+XLIFF_URI+'}target')
        edit=overrides.get(str(idx))
        if edit is not None:
            if tgt is None:tgt=E.Element('target')
            q._replace_target_with_plain_text(tgt,edit)
        yield segment(src,tgt,idx,el.get('tuid') or el.get('id') or str(idx))
        if idx%100==0:pulse('Reading segments',idx,None)
        release(el)
