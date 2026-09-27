"""Explicit TXT/CSV input. No files, learned dictionaries or persistent caches."""
import csv
import io
import json
import re
import unicodedata
from run_resources import within_run


def _decode(data):
    try:
        text=data.decode('utf-16') if data.startswith((b'\xff\xfe',b'\xfe\xff')) else data.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('Save the file as UTF-8 (or UTF-16 with a BOM).') from exc
    if '\x00' in text:raise ValueError('The file contains null characters; check its encoding.')
    return text


def parse_term_list(data):
    return list(dict.fromkeys(line.strip() for line in _decode(data).splitlines() if line.strip()))


def _key(value):
    return ''.join(c for c in unicodedata.normalize('NFD',value.strip().lower()) if not unicodedata.combining(c))


def regex_template():
    out=io.StringIO();w=csv.writer(out,delimiter=';')
    w.writerow(['Type','Source regex','Target regex','Description'])
    w.writerow(['Forbidden','',r'\bplacebo\b','Example: forbidden term'])
    w.writerow(['Required',r'\bpatient\b',r'\bpaciente\b','Example: translate patient as paciente'])
    return out.getvalue().encode('utf-8-sig')


def parse_regex_csv(data,case_sensitive=False):
    text=_decode(data)
    expected=(['type','source regex','target regex','description'],
              ['tipo','regex origen','regex destino','descripcion'])
    chosen=None
    for delimiter in (';',',','\t'):
        reader=csv.reader(io.StringIO(text),delimiter=delimiter,strict=True)
        try:header=next(reader,[])
        except csv.Error:continue
        if [_key(c) for c in header] in expected:chosen=delimiter;break
    if chosen is None:
        raise ValueError('Required header: Type, Source regex, Target regex, Description. Download the template.')
    reader=csv.reader(io.StringIO(text),delimiter=chosen,strict=True);next(reader)
    rules=[]
    try:
        for row in reader:
            if not any(c.strip() for c in row):continue
            line=reader.line_num
            if len(row)!=4:raise ValueError(f'Row {line}: exactly four columns are required; quote cells containing the separator.')
            kind,source,target,description=[x.strip() for x in row]
            kind=_key(kind)
            aliases={'forbidden':'prohibido','required':'obligatorio'};kind=aliases.get(kind,kind)
            if kind not in {'prohibido','obligatorio'}:raise ValueError(f'Row {line}: Type must be Forbidden or Required.')
            if not target or (kind=='obligatorio' and not source):raise ValueError(f'Row {line}: a required regex is missing.')
            if not description:raise ValueError(f'Row {line}: add a Description to identify the finding.')
            for name,pattern in [('source',source),('target',target)]:
                if not pattern:continue
                try:
                    re.compile(pattern,0 if case_sensitive else re.I)
                    import regex
                    regex.compile(pattern,0 if case_sensitive else regex.I)
                except (re.error,ValueError) as exc:raise ValueError(f'Row {line}, {name} regex: {exc}') from exc
            rules.append(dict(type=kind,source=source,target=target,description=description,line=line))
    except csv.Error as exc:raise ValueError(f'Invalid CSV near row {reader.line_num}: {exc}') from exc
    return rules


@within_run
def _compile_rules(serialized,case_sensitive):
    import regex
    flags=0 if case_sensitive else regex.I
    return [(r,regex.compile(r['source'],flags) if r['source'] else None,
             regex.compile(r['target'],flags)) for r in json.loads(serialized)]


def check_csv_rules(seg,cfg,ctx,kind):
    rules=cfg.get('custom_regex_rules') or []
    if not rules:return []
    from qa_checker import _make_issue
    compiled=_compile_rules(json.dumps(rules,ensure_ascii=False,sort_keys=True),bool(cfg.get('custom_regex_case_sensitive')))
    budget=float(cfg.get('custom_regex_timeout_seconds') or .25)
    issues=[];source=seg.get('source_text') or '';target=seg.get('target_text') or ''
    for rule,src,tgt in compiled:
        if rule['type']!=kind:continue
        try:
            sm=list(src.finditer(source,timeout=budget)) if src else []
            if src and not sm:continue
            tm=list(tgt.finditer(target,timeout=budget))
        except TimeoutError:
            ctx.setdefault('_custom_regex_timeout_segs',set()).add(seg['id']);continue
        if (kind=='prohibido' and not tm) or (kind=='obligatorio' and len(sm)==len(tm)):continue
        cid='custom_forbidden_regex' if kind=='prohibido' else 'custom_required_regex'
        detail=f"Forbidden: {len(tm)} match(es) in target." if kind=='prohibido' else f"Required: {len(sm)} match(es) in source and {len(tm)} in target."
        issue=_make_issue(cid,seg,rule['description']+' — '+detail,
            span_source=[m.group() for m in sm if m.group()],span_target=[m.group() for m in tm if m.group()])
        label='Forbidden' if kind=='prohibido' else 'Required'
        issue['note']=f"CSV · {label} · row {rule['line']}: {rule['description']}"
        issues.append(issue)
    return issues
