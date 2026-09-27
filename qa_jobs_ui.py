"""Review the current analysis and its exports with escaped highlights."""
import html,math,re
import streamlit as st
import qa_jobs as jobs
import qa_checker as q


def highlight(text,spans):
    text=text or '';parts=[spans] if isinstance(spans,str) else list(spans or [])
    if not parts:return html.escape(text)
    pattern=re.compile('|'.join(re.escape(p) for p in sorted(set(parts),key=len,reverse=True) if p),re.I)
    result=[];last=0
    for m in pattern.finditer(text):
        result.extend([html.escape(text[last:m.start()]),'<mark>'+html.escape(m.group())+'</mark>']);last=m.end()
    return ''.join(result)+html.escape(text[last:])


def _start_export(kind,jid):
    try:st.session_state['qa_job_requested']=jobs.submit([],{},kind=kind,parent=jid)
    except (ValueError,RuntimeError) as exc:st.session_state['qa_job_error']=str(exc)


def use_current(jid):
    """Drop review widget state only after a replacement QA has started."""
    for key in list(st.session_state):
        if key.startswith(('qa_job','job_','qa_summary','qa_results','edit_text_','ignore_')):
            st.session_state.pop(key,None)
    st.session_state['qa_job_requested']=jid


def _restart(jid):
    try:use_current(jobs.restart(jid))
    except (ValueError,RuntimeError) as exc:st.session_state['qa_job_error']=str(exc)


def render_jobs():
    if st.session_state.get('qa_job_error'):st.error(st.session_state.pop('qa_job_error'))
    st.session_state.pop('qa_job_requested',None)
    rows=jobs.list_jobs()
    analyses=[row for row in rows if row['kind']=='qa']
    if not analyses:return
    state=analyses[0];selected=state['id']
    exports=[row for row in rows if jobs.record(row['id']).get('parent')==selected]
    qa_running=state['state'] not in jobs.TERMINAL
    export_running=any(row['state'] not in jobs.TERMINAL for row in exports)
    st.markdown('### Current QA result')
    st.caption('Only the current QA is kept. Starting a new analysis replaces the previous result and its exports.')
    if qa_running:
        _progress(selected)
        if st.button('Cancel',key='cancel_'+selected):jobs.cancel(selected);st.rerun()
        if st.button('Refresh partial results',key='refresh_'+selected):st.rerun()
    else:_status(state)
    _findings(selected,state,qa_running or export_running)
    for item in exports:
        eid=item['id']
        if item['state'] not in jobs.TERMINAL:
            _progress(eid)
            if st.button('Cancel export',key='cancel_'+eid):jobs.cancel(eid);st.rerun()
        elif item['state']=='completed':
            st.download_button('Download '+item['output'],data=jobs.output(eid),
                file_name=item['output'],key='output_'+eid,on_click='ignore')
        else:_status(item)
    if not qa_running and not export_running and st.button('Clear current result',key='clear_current_qa'):
        jobs.clear_all()
        for key in list(st.session_state):
            if key.startswith(('qa_job','job_','qa_summary','qa_results','edit_text_','ignore_')):
                st.session_state.pop(key,None)
        st.rerun()


def _status(s):
    names={'queued':'Queued','running':'Running','completed':'Completed','incomplete':'Incomplete','cancelled':'Cancelled: partial results','failed':'Failed: partial results','interrupted':'Interrupted: partial results'}
    st.write('**'+names.get(s['state'],s['state'])+'**')
    st.caption(f"{s.get('phase','')} · {s.get('done',0):,}"+(f" / {s['total']:,}" if s.get('total') is not None else '')+f" · {s.get('elapsed',0):.1f} s")
    if s.get('total'):st.progress(min(1.,s.get('done',0)/s['total']))
    if s.get('error'):st.error(s['error'])
    for note in s.get('notices',[]):st.warning(note)


@st.fragment(run_every='1s')
def _progress(job_id):
    s=jobs.status(job_id)
    if s['state'] in jobs.TERMINAL:st.rerun()
    _status(s)


def _findings(jid,state,running):
    _,_,counts=jobs.issue_page(jid,size=0)
    st.write(f"**{sum(counts.values()):,} findings** · {state.get('segment_count','—')} segments")
    category=st.selectbox('Check',['All']+sorted(counts),key='job_category_'+jid)
    show_ignored=st.checkbox('Show ignored',value=True,key='job_ignored_'+jid)
    opts=dict(category=None if category=='All' else category,show_ignored=show_ignored)
    _,total,_=jobs.issue_page(jid,size=0,**opts)
    pages=max(1,math.ceil(total/50));key='job_page_'+jid
    if st.session_state.get(key,1)>pages:st.session_state[key]=1
    page=int(st.number_input('Page (50 findings)',min_value=1,max_value=pages,step=1,key=key))
    issues,_,_=jobs.issue_page(jid,page=page,**opts)
    st.caption(f'Page {page} of {pages}; {total} matching findings. Filters do not limit the analysis.')
    pending=jobs.edits(jid)
    if pending:st.warning(f'{len(pending)} edited segments have not been reanalyzed. Findings still refer to the previous analysis.')
    word=any(f.get('format')=='docx' for f in state.get('files',[]))
    for issue in issues:
        sid=issue['segment_id'];iid=issue['_issue_id']
        with st.expander(f"{issue.get('file','')} · {issue.get('original_segment_id',sid)} · {issue['category_id']}"):
            st.write(issue['message'])
            if issue.get('note'):st.info('Glossary note: '+issue['note'])
            source=highlight(issue.get('source'),issue.get('span_source'));target=highlight(issue.get('target'),issue.get('span_target'))
            if issue.get('reference_segment_id'):
                axis_diff=issue.get('mismatch_axis','target')
                rs=html.escape(issue.get('reference_source',''));rt=html.escape(issue.get('reference_target',''))
                if axis_diff in {'source','both'}:rs,source=q.highlight_diff(issue.get('reference_source',''),issue.get('source',''))
                if axis_diff in {'target','both'}:rt,target=q.highlight_diff(issue.get('reference_target',''),issue.get('target',''))
                st.caption(f"Reference: {issue.get('reference_file','')} · {issue['reference_segment_id']}")
                st.markdown('<div style="white-space:pre-wrap">'+rs+'<br>'+rt+'</div>',unsafe_allow_html=True)
            left,right=st.columns(2)
            left.markdown('<div style="white-space:pre-wrap">'+source+'</div>',unsafe_allow_html=True)
            right.markdown('<div style="white-space:pre-wrap">'+target+'</div>',unsafe_allow_html=True)
            if not running:
                ignored=iid in jobs.record(jid)['ignored']
                if st.button('Restore finding' if ignored else 'Ignore finding',key=f'ignore_{jid}_{iid}'):
                    jobs.set_ignored(jid,iid,not ignored);st.rerun()
            if issue.get('has_tags'):st.caption('Protected tags: edit this target in your CAT tool.')
            elif not word and not running:
                with st.form(f'edit_{jid}_{iid}'):
                    value=st.text_area('Edit target',value=pending.get(sid,issue.get('_target_plain',issue.get('target',''))),key=f'edit_text_{jid}_{iid}')
                    if st.form_submit_button('Save correction'):
                        jobs.save_edit(jid,sid,value)
                        for key in list(st.session_state):
                            if key.startswith('edit_text_'+jid+'_'):st.session_state.pop(key,None)
                        st.rerun()
    if not running:
        st.button('Run QA again with edits',key='restart_'+jid,on_click=_restart,args=(jid,))
        for kind,label,keyprefix in [('html','Generate interactive HTML','report_'),('csv','Generate CSV','csv_')]+([('edited','Generate corrected files','edited_')] if not word and (pending or jobs.record(jid)['overrides']) else []):
            st.button(label,key=keyprefix+jid,on_click=_start_export,args=(kind,jid))
        outputs=st.session_state.get('results',{})
        record=jobs.record(jid)
        matches=bool(outputs) and not record['edits'] and not record['overrides'] and len(outputs)==len(record['files']) and all(isinstance(f['data'],bytes) and outputs.get(f['name'])==f['data'] for f in record['files'])
        if matches and state.get('complete') and st.button('Link QA summary to the TM/Excel report',key='link_tm_'+jid):
            from qa_exports import report_results
            st.session_state['qa_results']=report_results(record);st.session_state['qa_summary_jobid']=jid;st.success('Summary linked to these same files.')
