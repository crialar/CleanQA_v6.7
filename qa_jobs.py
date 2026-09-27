"""Analysis processes with RAM-only records and IPC. Nothing is persisted to disk."""
from pathlib import Path
import atexit, copy, io, json, multiprocessing as mp, os, threading, time, uuid
from collections import Counter
os.environ['PYTHONDONTWRITEBYTECODE']='1'
TERMINAL={'completed','incomplete','failed','cancelled','interrupted'}
_JOBS={}
_LOCK=threading.RLock()


def serialize_config(config):
    out=dict(config);out['enabled_checks']=sorted(out.get('enabled_checks',[]))
    for key in ('custom_forbidden_regex_patterns','custom_required_regex_patterns'):
        out[key]=[(e['raw'] if 'raw' in e else e['pattern'].pattern) if isinstance(e,dict) else (e if isinstance(e,str) else e.pattern) for e in out.get(key,[])]
    out['custom_regex_rules']=[dict(rule) for rule in out.get('custom_regex_rules',[])]
    return out


def deserialize_config(config):
    import qa_checker as q
    out=q._normalize_config(config)
    unknown=out['enabled_checks']-set(q.ALL_CHECK_IDS)
    if unknown:raise ValueError('Unknown QA checks: '+', '.join(sorted(unknown)))
    for key in ('custom_forbidden_regex_patterns','custom_required_regex_patterns'):
        patterns,errors=q.parse_custom_regex_patterns('\n'.join(out.get(key,[])),case_sensitive=out.get('custom_regex_case_sensitive',False))
        if errors:raise ValueError('Invalid custom expressions: '+str(errors))
        out[key]=patterns
    out['custom_regex_rules']=[dict(rule) for rule in out.get('custom_regex_rules',[])]
    return out


def record(job_id):
    if job_id not in _JOBS:raise ValueError('This job is no longer available. Start a new analysis.')
    return _JOBS[job_id]


def status(job_id):
    with _LOCK:
        s=dict(record(job_id)['state'])
        if s['state'] not in TERMINAL:s['elapsed']=time.time()-s['created']
        return s


def list_jobs():
    with _LOCK:return sorted([status(j) for j in _JOBS],key=lambda s:s['created'],reverse=True)


def _collect(jid,conn,proc):
    try:
        while True:
            msg=conn.recv()
            with _LOCK:
                if jid not in _JOBS:break
                job=_JOBS[jid]
                if job['state']['state']=='cancelled':continue
                if msg['type']=='issues':
                    for issue in msg['value']:
                        issue['_issue_id']=len(job['issues'])+1;job['issues'].append(issue)
                elif msg['type']=='segments':job['segments'].extend(msg['value'])
                elif msg['type']=='output':job['output']=msg['value']
                else:job['state'].update(msg['value'])
    except EOFError:pass
    except Exception as exc:
        with _LOCK:
            if jid in _JOBS and _JOBS[jid]['state']['state'] not in TERMINAL:_JOBS[jid]['state'].update(state='failed',complete=False,error=str(exc))
    finally:
        conn.close();proc.join()
        with _LOCK:
            if jid in _JOBS:
                state=_JOBS[jid]['state']
                if state['state'] not in TERMINAL:state.update(state='failed',complete=False,error=f'The process exited ({proc.exitcode}); partial results may be available.')
                state['elapsed']=time.time()-state['created']
                _JOBS[jid]['process']=None


def submit(files,config,*,overrides=None,kind='qa',parent=None,expected_fingerprints=None):
    with _LOCK:
        if any(s['state'] not in TERMINAL for s in list_jobs()):raise RuntimeError('A job is already running. Wait for it or cancel it.')
        if kind=='qa' and not files:raise ValueError('No input files.')
        entries=[];names=set()
        for name,data in files:
            name=Path(name.replace('\\','/')).name
            if name in names:raise ValueError('File names must be unique.')
            names.add(name)
            if isinstance(data,Path):
                data=data.resolve();fingerprint=(data.stat().st_size,data.stat().st_mtime_ns)
                if expected_fingerprints is not None and fingerprint != expected_fingerprints.get(name):
                    raise ValueError('The original file has changed. Start a new analysis without the previous edits.')
            else:data=bytes(data);fingerprint=None
            entries.append({'name':name,'data':data,'fingerprint':fingerprint})
        jid=uuid.uuid4().hex;now=time.time()
        state=dict(id=jid,kind=kind,created=now,state='queued',phase='Preparing analysis',done=0,total=None,elapsed=0,complete=False,files=[],notices=[])
        payload={'config':serialize_config(config),'files':entries,'overrides':overrides or {},'kind':kind}
        if parent:
            p=record(parent)
            if p['state']['state'] not in TERMINAL:raise ValueError('Wait for QA to finish.')
            payload['parent']=copy.deepcopy({k:p[k] for k in ('state','files','config','overrides','edits','issues','ignored','segments')})
        ctx=mp.get_context('spawn');receive,send=ctx.Pipe(duplex=False)
        proc=ctx.Process(target=_worker,args=(send,payload),daemon=True)
        _JOBS[jid]={'state':state,'files':entries,'config':payload['config'],'overrides':dict(overrides or {}),'edits':{},'segments':[],'issues':[],'ignored':set(),'output':None,'process':proc,'parent':parent}
        try:proc.start()
        except Exception:
            del _JOBS[jid];receive.close();send.close();raise
        # Replace only after the new process starts successfully. Exports of
        # the old QA (and their downloaded bytes) must not remain reachable.
        for old_id in list(_JOBS):
            if old_id == jid:continue
            old=_JOBS[old_id]
            if kind=='qa' or (old.get('parent')==parent and old['state']['kind']==kind):
                del _JOBS[old_id]
        send.close();threading.Thread(target=_collect,args=(jid,receive,proc),daemon=True).start()
        return jid


def cancel(job_id):
    with _LOCK:
        j=record(job_id)
        if j['state']['state'] in TERMINAL:return
        j['state'].update(state='cancelled',complete=False,error='Cancelled. Only findings received so far are available.',elapsed=time.time()-j['state']['created'])
        proc=j['process']
        if proc is not None and proc.is_alive():proc.terminate()


def delete(job_id):
    with _LOCK:
        if status(job_id)['state'] not in TERMINAL:raise ValueError('Cancel the job before deleting it.')
        if any(j.get('parent')==job_id and j['state']['state'] not in TERMINAL for j in _JOBS.values()):raise ValueError('Wait for the export to finish.')
        del _JOBS[job_id]


def clear_all():
    with _LOCK:
        for jid in list(_JOBS):cancel(jid)
        _JOBS.clear()
atexit.register(clear_all)


def restart(job_id):
    with _LOCK:
        j=record(job_id);edits=dict(j['overrides']);edits.update({str(k):v for k,v in j['edits'].items()})
        for entry in j['files']:
            if isinstance(entry['data'],Path):
                _source(entry)
        expected={f['name']:f['fingerprint'] for f in j['files']}
        return submit([(f['name'],f['data']) for f in j['files']],deserialize_config(j['config']),overrides=edits,expected_fingerprints=expected)


def request_report(job_id):return submit([],{},kind='html',parent=job_id)
def output(job_id):
    with _LOCK:return record(job_id)['output']
def edits(job_id):
    with _LOCK:return dict(record(job_id)['edits'])
def discard_exports(job_id):
    """Invalidate every child snapshot before another tab can consume it."""
    with _LOCK:
        record(job_id)
        for jid in list(_JOBS):
            child=_JOBS[jid]
            if child.get('parent')==job_id:
                cancel(jid)
                del _JOBS[jid]

def set_ignored(job_id,issue_id,value):
    with _LOCK:
        ignored=record(job_id)['ignored']
        if (issue_id in ignored)!=bool(value):
            discard_exports(job_id)
            if value:ignored.add(issue_id)
            else:ignored.discard(issue_id)


def issue_page(job_id,category=None,page=1,size=50,show_ignored=True):
    j=record(job_id);items=j['issues'];counts=dict(Counter(i['category_id'] for i in items))
    result=[];total=0;start=max(0,page-1)*size
    for issue in items:
        if category and issue['category_id']!=category:continue
        if not show_ignored and issue['_issue_id'] in j['ignored']:continue
        if start<=total<start+size:result.append(issue)
        total+=1
    return result,total,counts


def save_edit(job_id,sid,value):
    with _LOCK:
        j=record(job_id)
        if j['state']['state'] not in TERMINAL:raise ValueError('Wait for the analysis to finish.')
        issue=next((i for i in j['issues'] if i['segment_id']==sid),None)
        if not issue:raise ValueError('Unknown segment.')
        if issue.get('has_tags'):raise ValueError('Edit tagged segments in the CAT tool.')
        new_value=None if value==issue.get('_target_plain',issue['target']) else value
        if j['edits'].get(sid)!=new_value:
            discard_exports(job_id)
            if new_value is None:j['edits'].pop(sid,None)
            else:j['edits'][sid]=new_value


def _source(entry):
    data=entry['data']
    if isinstance(data,Path):
        if (data.stat().st_size,data.stat().st_mtime_ns)!=entry['fingerprint']:raise ValueError('The original file has changed since it was selected. Start a new QA analysis.')
        return data
    return io.BytesIO(data)


def _worker(conn,payload):
    import sys
    sys.dont_write_bytecode=True
    from qa_store import SegmentStore
    from qa_stream import inspect_file,read_segments
    from qa_analysis import execute
    pending=[];last=0;last_phase=None;finished=threading.Event();send_lock=threading.Lock()
    def send(kind,value):
        with send_lock:conn.send({'type':kind,'value':value})
    def watch_parent():
        while not finished.wait(.5):
            try:send('status',{})
            except (OSError,EOFError):os._exit(0)
    threading.Thread(target=watch_parent,daemon=True).start()
    def flush():
        if pending:send('issues',list(pending));pending.clear()
    def pulse(phase,done=0,total=None):
        nonlocal last,last_phase
        if phase!=last_phase or time.monotonic()-last>.2:
            flush();send('status',dict(phase=phase,done=done,total=total));last=time.monotonic();last_phase=phase
    def issue_callback(issue):
        pending.append(issue)
        if len(pending)>=25:flush()
    store=None
    try:
        send('status',dict(state='running'))
        if payload['kind']!='qa':
            from qa_exports import export_job
            data,name=export_job(payload['kind'],payload['parent'],pulse)
            send('output',data);send('status',dict(state='completed',complete=True,output=name,phase='Export ready',source_state=payload['parent']['state']['state']));return
        cfg=deserialize_config(payload['config']);metadata=[];pairs=set()
        for f in payload['files']:
            fmt,src,tgt=inspect_file(_source(f),f['name'],pulse)
            if fmt=='docx' and len(payload['files'])!=1:raise ValueError('Word must be analyzed separately.')
            if fmt=='docx':
                tgt=cfg.get('monolingual_lang') or 'es-ES'
            metadata.append(dict(name=f['name'],format=fmt,source_lang=src,target_lang=tgt));pairs.add((src,tgt))
        if len(pairs)!=1:raise ValueError('Run each language pair in a separate job.')
        store=SegmentStore(on_issue=issue_callback);count=0;context=[]
        for f,entry in zip(metadata,payload['files']):
            offset=count;local_edits={str(int(s)-offset):v for s,v in payload['overrides'].items() if int(s)>offset}
            local_count=0
            for seg in read_segments(_source(entry),f['format'],f['source_lang'],f['target_lang'],pulse,local_edits):
                count+=1;local_count+=1;seg.update(local_id=seg['id'],id=count,file=f['name']);store.append(seg)
                context.append(dict(id=count,original_id=seg['original_id'],file=f['name'],local_id=local_count,source=seg['source_text'],target=seg['target_text']))
                if len(context)>=100:send('segments',context);context=[]
                if count%100==0:store.commit();pulse('Reading segments',count,None)
            f.update(offset=offset,segment_count=local_count)
        if context:send('segments',context)
        store.commit();send('status',dict(files=metadata,segment_count=count))
        first=metadata[0]
        enabled,notices=execute(store,cfg,first['format'],first['source_lang'],first['target_lang'],pulse)
        flush();send('status',dict(state='incomplete' if notices else 'completed',complete=not notices,notices=notices,enabled=enabled,phase='Finished',done=1,total=1))
    except BaseException as exc:
        flush();send('status',dict(state='failed',complete=False,error=f'{type(exc).__name__}: {exc}'))
    finally:
        finished.set()
        if store:store.close()
        conn.close()
