from run_resources import analysis_scope, RunDictionary
"""Exhaustive block traversal and streaming checks. No memoized comparison results."""
from collections import Counter
import difflib
import json
import qa_checker as q


def prepare_resources(cfg, source, target, fmt):
    ctx={'format':fmt,'source_lang':source,'target_lang':target,'dictionaries':{}}
    enabled=cfg['enabled_checks'];notices=[]
    if cfg.get('glossary_inflected_forms') and 'glossary_violation' in enabled:
        import spellcheck as sp
        for lang in dict.fromkeys([source,target]):
            norm=sp.normalize_lang_code(lang)
            try:ctx['dictionaries'][lang]=sp.get_dictionary(norm,allow_download=cfg.get('allow_dictionary_download',True)) if norm else None
            except Exception as exc:
                notices.append(f'Inflected glossary dictionary could not be loaded ({lang}): {exc}')
            if not ctx['dictionaries'].get(lang):notices.append(f'Inflected glossary matching unavailable for {lang}; literal matching only.')
    if 'spellcheck' in enabled:
        try:
            if ctx['dictionaries'].get(target) is not None:
                ctx['_spellcheck_dict']=ctx['dictionaries'][target]
                ctx['_spellcheck_ignore']=set(cfg.get('spellcheck_ignore',[]))
            else:
                note=q._prepare_spellcheck_context(target,cfg,ctx)
                if note:notices.append(note)
        except Exception as exc:notices.append(f'Spelling could not start: {exc}')
    if ctx.get('_spellcheck_dict') is not None:ctx['_spellcheck_dict']=RunDictionary(ctx['_spellcheck_dict'])
    return ctx,notices


def pair_issue(a,b,kind,n=2):
    axis={'exact-target':'target','exact-source':'source','fuzzy-target':'target','fuzzy-source':'source','fuzzy-both':'both'}[kind]
    message=(f'Consistency ({kind}): compare with segment {a["id"]}; group size {n}.')
    issue=q._make_issue('inconsistent_translation',b,message)
    issue.update(mismatch_axis=axis,reference_segment_id=a['id'],reference_source=a['source_text'].strip(),
                 reference_target=a['target_text'].strip(),diff_against=a['target_text'].strip(),sibling_segment_ids=[a['id'],b['id']])
    return issue


def consistency(store,cfg,pulse):
    threshold=max(.5,min(1.,float(cfg.get('inconsistent_translation_threshold',1))))
    minchars=max(0,int(cfg.get('inconsistent_translation_min_chars',8)))
    db=store.db
    # The same first-reference grouping as the existing exact checks, across every file.
    for col,other,length,kind in [('sn','tn','sl','exact-target'),('tn','sn','tl','exact-source')]:
        groups=db.execute(f"SELECT {col},min(id),count(*) FROM segments WHERE sn<>'' AND tn<>'' AND {length}>=? GROUP BY {col} HAVING count(*)>1",(minchars,))
        done=0
        for value,first,n in groups:
            a=store.get(first)
            other_value=a['_tn' if other=='tn' else '_sn']
            for (raw,) in db.execute(f'SELECT payload FROM segments WHERE {col}=? AND id>? AND {other}<>? ORDER BY id',(value,first,other_value)):
                b=json.loads(raw)
                cur=db.execute('INSERT OR IGNORE INTO pairs VALUES(?,?,?,?)',(first,b['id'],kind,n))
                if cur.rowcount:
                    yield pair_issue(a,b,kind,n)
                    if b['id']%100==0:store.commit()
                pulse('Exact consistency',done,None)
            done+=1
            pulse('Exact consistency',done,None)
    if threshold>=1:return
    total=db.execute("SELECT count(*) FROM segments WHERE sn<>'' AND tn<>''").fetchone()[0]
    comparisons=total*(total-1)//2;done=0
    pulse('Fuzzy consistency: pairs',0,comparisons)
    blocksize=max(1,min(1024,int(cfg.get('comparison_block_size',128))))
    def similar(a,b):
        if not a or not b:return False
        if 2*min(len(a),len(b))/(len(a)+len(b))<threshold:return False
        sm=difflib.SequenceMatcher(None,a,b,autojunk=False)
        return sm.quick_ratio()>=threshold and sm.ratio()>=threshold
    for left in store.blocks(blocksize,candidates=True):
        # Includes the diagonal block and EVERY later block, preserving cross-block/file pairs.
        for right in store.blocks(blocksize,after=left[0]['id']-1,candidates=True):
            for a in left:
                for b in right:
                    if b['id']<=a['id']:continue
                    done+=1
                    if done%128==0:pulse('Fuzzy consistency: pairs',done,comparisons)
                    ss=a['_sn']==b['_sn'];ts=a['_tn']==b['_tn']
                    if ss and ts:continue
                    ssim=not ss and a['_sl']>=minchars and b['_sl']>=minchars and similar(a['_sn'],b['_sn'])
                    tsim=not ts and a['_tl']>=minchars and b['_tl']>=minchars and similar(a['_tn'],b['_tn'])
                    kind='fuzzy-both' if ssim and tsim else ('fuzzy-target' if ssim and not ts else ('fuzzy-source' if tsim and not ss else None))
                    if kind:
                        # Exact groups take precedence; remaining pairs are emitted exactly once.
                        if not db.execute('SELECT 1 FROM pairs WHERE a=? AND b=?',(a['id'],b['id'])).fetchone():
                            yield pair_issue(a,b,kind)
            store.commit();pulse('Fuzzy consistency: pairs',done,comparisons)
    pulse('Fuzzy consistency: pairs',done,comparisons)


def hyphenation(store,pulse):
    db=store.db
    db.execute('CREATE TABLE IF NOT EXISTS hyph(norm TEXT, id INTEGER, kind TEXT, token TEXT, PRIMARY KEY(norm,id,kind))')
    db.execute('DELETE FROM hyph')
    for n,seg in enumerate(store,1):
        text=seg.get('target_text','')
        for m in q._HYPHENATED_TOKEN_RE.finditer(text):
            token=m.group();norm=token.replace('-','').lower()
            if len(norm)>=6:db.execute('INSERT OR IGNORE INTO hyph VALUES(?,?,?,?)',(norm,seg['id'],'h',token))
        for m in q._PLAIN_WORD_RE.finditer(text):
            token=m.group()
            if len(token)>=6:db.execute('INSERT OR IGNORE INTO hyph VALUES(?,?,?,?)',(token.lower(),seg['id'],'p',token))
        if n%100==0:store.commit();pulse('Hyphenation consistency',n,len(store))
    for norm,first in db.execute("SELECT norm,min(id) FROM hyph WHERE kind='h' GROUP BY norm"):
        a=store.get(first);at=db.execute("SELECT token FROM hyph WHERE norm=? AND id=? AND kind='h'",(norm,first)).fetchone()[0]
        for sid,bt in db.execute("SELECT p.id,p.token FROM hyph p WHERE p.norm=? AND p.kind='p' AND NOT EXISTS(SELECT 1 FROM hyph h WHERE h.norm=p.norm AND h.id=p.id AND h.kind='h')",(norm,)):
            b=store.get(sid);ref,other=(a,b) if first<sid else (b,a)
            issue=pair_issue(ref,other,'fuzzy-both');issue['mismatch_axis']='hyphenation'
            issue['message']=f"Hyphenation inconsistency: '{at}' vs '{bt}'."
            yield issue
            pulse('Hyphenation consistency',sid,None)
    db.execute('DROP TABLE hyph');store.commit()


def format_tokens(seg,mode):
    text=seg.get('target_text','')
    if mode=='date':return [(m.group(2),m.group()) for m in q._DATE_RE.finditer(text)]
    text=q._DATE_RE.sub(lambda m:' '*len(m.group()),text)
    return [(sep,m.group()) for m in q._NUMBER_RE.finditer(text) if (sep:=q._decimal_separator_of(m.group()))]


def format_consistency(store,mode,pulse):
    counts=Counter()
    for n,seg in enumerate(store,1):
        counts.update(sep for sep,raw in format_tokens(seg,mode))
        if n%100==0:pulse('Batch-wide conventions: '+mode,n,len(store)*2)
    top=counts.most_common(2)
    if len(top)<2 or top[0][1]==top[1][1]:return
    majority=top[0][0]
    for n,seg in enumerate(store,1):
        odd=[raw for sep,raw in format_tokens(seg,mode) if sep!=majority]
        if odd:yield q._make_issue(mode+'_format_mismatch',seg,f"{mode.title()} format differs from the batch majority separator '{majority}'.",span_target=odd)
        if n%100==0:pulse('Batch-wide conventions: '+mode,len(store)+n,len(store)*2)


@analysis_scope
def execute(store,cfg,fmt,src,tgt,pulse):
    enabled=cfg['enabled_checks']
    notices=[]
    if fmt=='docx':
        unavailable=enabled-q.MONOLINGUAL_CHECK_IDS
        if unavailable:notices.append('Not applicable to monolingual Word: '+', '.join(sorted(unavailable)))
        enabled=enabled & q.MONOLINGUAL_CHECK_IDS
        cfg=dict(cfg,enabled_checks=enabled)
        tgt=cfg.get('monolingual_lang') or 'es-ES'
    pulse('Preparing dictionaries (downloading if needed)',0,None)
    ctx,resource_notices=prepare_resources(cfg,src,tgt,fmt);notices.extend(resource_notices)
    total=len(store)
    for n,seg in enumerate(store,1):
        pulse('Checking segments',n-1,total)
        for cid,fn in q._PER_SEGMENT_CHECKS:
            if cid not in enabled:continue
            for issue in fn(seg,cfg,ctx):store.add_issue(issue)
        if n%100==0:store.commit()
    store.commit();pulse('Checking segments',total,total)
    if 'inconsistent_translation' in enabled:
        for issue in consistency(store,cfg,pulse):store.add_issue(issue)
        for issue in hyphenation(store,pulse):store.add_issue(issue)
    for mode in ('date','number'):
        if mode+'_format_mismatch' in enabled:
            for issue in format_consistency(store,mode,pulse):store.add_issue(issue)
    store.commit()
    notices.extend(sorted(ctx.get('_coverage_notices',set())))
    if ctx.get('_custom_regex_timeout_segs'):notices.append('One or more custom expressions exceeded their per-segment safety deadline; coverage is incomplete.')
    if ctx.get('_polarity_unsupported_langs'):notices.append('Polarity rules unavailable for: '+', '.join(sorted(ctx['_polarity_unsupported_langs'])))
    return sorted(enabled),notices
