/* Shared history and detail UI. All user strings are DOM text, never HTML. */
export function createHistory(root,{api,el,button,baseUrl,workflow=false}){
  let page=1,zone='Asia/Ho_Chi_Minh',selected=null,generation=0,requestVersion=0;
  root.addEventListener('lh-dispose',()=>generation++);
  const title=workflow?'Workflow Run History':'Runs';
  root.append(el('h2','',title));
  const notice=el('div','lh-muted','Loading timezone…'),filters=el('div','lh-filters lh-history-filters');root.append(notice,filters);
  const field=(label,type,placeholder='')=>{const wrap=el('label','lh-filter',label),n=el(type);n.setAttribute('aria-label',label);n.placeholder=placeholder;wrap.append(n);filters.append(wrap);return n;};
  const search=field('Search name or ID','input','Name or execution ID'),kind=field('Type','select'),status=field('Status','select'),from=field('From date/time','input'),to=field('To date/time','input'),size=field('Items per page','select');
  from.type=to.type='datetime-local';from.step=to.step='1';
  function options(select,items){for(const [value,label] of items){const o=el('option','',label);o.value=value;select.append(o);}}
  options(kind,[['','All types'],...['notebook','dbt','sql',...(workflow?['condition','loop','variable','workflow']:['cluster_restart','artifact_archive'])].map(v=>[v,v])]);
  options(status,[['','All statuses'],...['QUEUED','CREATED','RUNNING','PAUSED','RESTARTED','SUCCESS','WARNING','FAILED','KILLED','CANCELLED','TIMED_OUT','INTERRUPTED','SKIPPED','ARCHIVED'].map(v=>[v,v])]);
  options(size,[10,25,50,100,200].map(v=>[v,String(v)]));size.value='25';
  const controls=el('div','lh-toolbar'),message=el('div','lh-status'),list=el('div'),pager=el('div','lh-toolbar'),detail=el('section','lh-run-detail');
  controls.append(button('Apply filters',()=>{page=1;return load();},true),button('Reset',()=>{search.value=kind.value=status.value=from.value=to.value='';page=1;return load();}),button('Refresh',load));
  root.append(controls,message,list,pager,detail);
  for(const n of [search,from,to])n.onkeydown=e=>{if(e.key==='Enter'){page=1;load();}};
  for(const n of [kind,status,size])n.onchange=()=>{page=1;load();};
  function format(value){if(!value)return '—';const date=typeof value==='number'?new Date(value*1000):new Date(value);return Number.isNaN(date.getTime())?'—':new Intl.DateTimeFormat('en-GB',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(date);}
  const duration=n=>n==null?'—':Number(n).toFixed(2)+' s';
  function badge(value){return el('span','lh-state lh-state-'+String(value).toLowerCase(),value||'UNKNOWN');}
  function table(parent,columns,rows){const wrap=el('div','lh-table-wrap'),t=el('table'),head=el('thead'),tr=el('tr');columns.forEach(c=>tr.append(el('th','',c)));head.append(tr);const body=el('tbody');for(const row of rows){const tr=el('tr');for(const value of row){const td=el('td');if(value instanceof Node)td.append(value);else td.textContent=value==null?'—':String(value);tr.append(td);}body.append(tr);}t.append(head,body);wrap.append(t);parent.append(wrap);return body;}
  function kv(parent,object){table(parent,['Field','Value'],Object.entries(object||{}).map(([k,v])=>[k,typeof v==='object'?jsonTree(v):v]));}
  function jsonTree(value){if(value===null||typeof value!=='object')return el('span','',String(value));const out=el('div','lh-json');for(const [k,v] of Object.entries(value)){const line=el('div');line.append(el('strong','',k+': '));if(v!==null&&typeof v==='object'){const d=el('details'),s=el('summary','',Array.isArray(v)?'Array ('+v.length+')':'Object');d.append(s,jsonTree(v));line.append(d);}else line.append(el('span','',String(v)));out.append(line);}return out;}
  async function load(){
    const version=++requestVersion;
    try{message.textContent='Loading…';const query=new URLSearchParams({search:search.value,kind:kind.value,status:status.value,from_time:from.value,to_time:to.value,page:String(page),page_size:size.value});
      const data=await api('history/'+(workflow?'workflows':'runs')+'?'+query);if(version!==requestVersion)return;zone=data.timezone;
      notice.textContent='Dates, logs and time filters use '+zone+'. History is filtered by start time.'+(data.warning?' '+data.warning:'');
      list.replaceChildren();table(list,['Name','ID','Type','Status','Started ('+zone+')','Duration','Details'],data.items.map(r=>[r.name,r.id,workflow?(r.types||[]).join(', '):r.kind,badge(r.status),format(r.started),duration(r.duration),button('View',()=>show(r.id))]));
      if(!data.items.length)list.append(el('p','lh-muted','No runs match these filters.'));
      pager.replaceChildren();const previous=button('Previous',()=>{page--;return load();}),next=button('Next',()=>{page++;return load();});previous.disabled=page<=1;next.disabled=page>=data.pages;pager.append(previous,el('span','',`Page ${page} of ${data.pages} · ${data.total} items`),next);message.textContent='';
    }catch(e){if(version===requestVersion){message.textContent=e.message;message.classList.add('lh-error');}}
  }
  async function show(id){selected=id;generation++;detail.replaceChildren(el('h3','','Loading details…'));try{workflow?await showWorkflow(id):await showRun(id,detail,generation);}catch(e){detail.replaceChildren(el('p','lh-error',e.message));}detail.scrollIntoView({block:'nearest'});}
  function sections(parent,labels){const bar=el('div','lh-detail-tabs'),content=el('div');parent.append(bar,content);const panels={};for(const label of labels){const panel=el('div');panel.hidden=true;panels[label]=panel;content.append(panel);const b=button(label,()=>{for(const p of Object.values(panels))p.hidden=true;panel.hidden=false;for(const x of bar.children)x.classList.remove('active');b.classList.add('active');});bar.append(b);}if(bar.firstChild)bar.firstChild.click();return panels;}
  function overview(parent,data){const head=el('div','lh-toolbar');head.append(el('h3','',data.name||data.id),badge(data.status));parent.append(head);kv(parent,{ID:data.id,Type:data.kind||'workflow',Started:format(data.started),Ended:format(data.ended),Duration:duration(data.duration),Timezone:zone,...(data.stage?{Stage:data.stage}:{}),...(data.invocation?{Command:data.invocation.join(' ')}:{})});if(data.error)parent.append(el('div','lh-error lh-card',data.error));}
  async function showRun(id,parent,token){
    const data=await api('runs/'+id);if(token!==generation)return;parent.replaceChildren();overview(parent,data);
    if(data.artifacts_expired){parent.append(el('p','lh-muted','Artifacts and logs expired under the retention policy. History metadata is retained.'));return;}
    const labels=['Parameters','Code','Logs',...(data.kind==='dbt'?['Models']:[]),...(data.kind==='notebook'?['Cells']:[]),'Outputs','Artifacts'];const tabs=sections(parent,labels);
    kv(tabs.Parameters,data.parameters||{});if(!Object.keys(data.parameters||{}).length)tabs.Parameters.append(el('p','lh-muted','No parameters.'));
    if(data.workflow_execution_id)tabs.Parameters.append(button('View parent workflow',()=>{generation++;detail.replaceChildren();return showWorkflow(data.workflow_execution_id);}));
    const files=data.source?.files||[];
    if(files.length){const select=el('select');select.setAttribute('aria-label','Source file');for(const f of files){const o=el('option','',f.path);select.append(o);}const code=el('pre','lh-code',files[0].code);select.onchange=()=>code.textContent=files[select.selectedIndex].code;tabs.Code.append(select,code);}else tabs.Code.append(el('p','lh-muted','Source snapshots are available for runs created after this update.'));
    logView(tabs.Logs,id,token);
    if(tabs.Models){const rows=await api('runs/'+id+'/models');table(tabs.Models,['Model / test','Type','Status','Duration','Message','SQL'],rows.map(r=>{const d=el('details');d.append(el('summary','','View SQL'),el('pre','lh-code',r.sql||'Not compiled yet'));return [r.name,r.type,badge(r.status),duration(r.duration),r.message,d];}));if(!rows.length)tabs.Models.append(el('p','lh-muted','No dbt models yet. Refresh while the run progresses.'));}
    if(tabs.Cells)cellView(tabs.Cells,id,token);
    tabs.Outputs.append(jsonTree(data.outputs||{}));
    table(tabs.Artifacts,['Artifact','Size','Download'],(data.artifacts||[]).map(a=>{const link=el('a','','Download');link.href=baseUrl+'lakehouse/artifacts/'+id+'?path='+encodeURIComponent(a.path);link.target='_blank';link.rel='noopener';return [a.path,(a.size/1024).toFixed(1)+' KB',link];}));
    const tools=el('div','lh-toolbar');tools.append(button('Refresh detail',()=>showRun(id,parent,++generation)));if(data.kind==='dbt'&&(data.artifacts||[]).some(a=>a.path==='target/index.html'))tools.append(button('Open dbt Docs',()=>window.open(baseUrl+'lakehouse/docs/'+id+'/index.html','_blank','noopener')));parent.append(tools);
  }
  function logView(parent,id,token){
    let cursor='',busy=false,stop=false,count=0,timer=null;
    const filters=el('div','lh-toolbar'),level=el('select'),source=el('select'),search=el('input'),state=el('span','lh-muted'),live=el('input');live.type='checkbox';live.checked=true;live.setAttribute('aria-label','Live logs');search.placeholder='Search log messages';search.setAttribute('aria-label','Search log messages');options(level,[['','All levels'],...['DEBUG','INFO','WARN','ERROR'].map(v=>[v,v])]);level.setAttribute('aria-label','Log level');options(source,[['','All sources'],['process','Process / dbt / Spark'],['notebook','Notebook cells'],['legacy','Legacy log']]);source.setAttribute('aria-label','Log source');const lab=el('label','','Live');lab.append(live);filters.append(level,source,search,button('Filter logs',()=>reset()),lab,state);parent.append(filters);
    const logs=el('div');parent.append(logs);let body=table(logs,['Time ('+zone+')','Level','Source / cell / model','Message'],[]);
    const more=button('Load more logs',()=>fetchLogs());parent.append(more);
    function reset(){cursor='';count=0;body.replaceChildren();return fetchLogs();}
    async function fetchLogs(){if(busy)return;busy=true;try{const result=await api('runs/'+id+'/logs?'+new URLSearchParams({cursor,limit:'100',level:level.value,source:source.value,search:search.value}));cursor=result.cursor;
      for(const e of result.items){const tr=el('tr');tr.append(el('td','',format(e.timestamp)));const td=el('td');td.append(badge(e.level));tr.append(td,el('td','',[e.source,e.cell!=null?'cell '+e.cell:'',e.model||''].filter(Boolean).join(' · ')));const msg=el('td','lh-log-message',e.message);tr.append(msg);body.append(tr);count++;}
      while(body.children.length>1000)body.firstChild.remove();state.textContent=count+' events loaded · showing last '+body.children.length;more.disabled=!result.has_more;stop=!result.has_more&&!['RUNNING','QUEUED'].includes((await api('runs/'+id)).status);
    }catch(e){state.textContent=e.message;stop=true;}finally{busy=false;}}
    live.onchange=()=>{if(live.checked){stop=false;schedule();}};
    async function schedule(){clearTimeout(timer);if(token!==generation)return;if(root.isConnected&&root.getClientRects().length&&live.checked&&!stop&&!parent.hidden){await fetchLogs();}timer=setTimeout(schedule,2000);}
    fetchLogs();schedule();
  }
  function cellView(parent,id,token){let page=1;const controls=el('div','lh-toolbar'),body=el('div');parent.append(controls,body);
    async function load(){const r=await api('runs/'+id+'/cells?page='+page);body.replaceChildren();for(const c of r.items){const d=el('details','lh-cell'),s=el('summary');s.append(el('strong','','Cell '+c.number+' '),badge(c.status),el('span','lh-muted',' · '+duration(c.duration)+' · '+format(c.started)));d.append(s,el('pre','lh-code',c.source));for(const o of c.outputs||[])renderOutput(d,o);body.append(d);}controls.replaceChildren();const prev=button('Previous cells',()=>{page--;return load();}),next=button('Next cells',()=>{page++;return load();});prev.disabled=page<=1;next.disabled=page*25>=r.total;controls.append(button('Refresh cells',load),prev,el('span','',r.total+' code cells · page '+page),next);}
    load().catch(e=>body.textContent=e.message);
  }
  function renderOutput(parent,o){const block=el('div','lh-cell-output');block.append(el('div','lh-muted',o.output_type+(o.name?' · '+o.name:'')));
    const data=o.data||{};
    if(data['text/html']){const iframe=el('iframe','lh-output-frame');iframe.title='Notebook table output';iframe.setAttribute('sandbox','');iframe.srcdoc='<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">'+(Array.isArray(data['text/html'])?data['text/html'].join(''):data['text/html']);block.append(iframe);}
    else if(data['image/png']){const img=el('img','lh-output-image');img.alt='Notebook output';img.src='data:image/png;base64,'+data['image/png'];block.append(img);}
    else{const value=o.text||o.traceback||data['text/plain']||o.evalue||'';block.append(el('pre','',Array.isArray(value)?value.join(''):String(value)));}parent.append(block);
  }
  async function showWorkflow(id){
    const version=generation,data=await api('workflow-history/'+id);if(version!==generation)return;detail.replaceChildren();overview(detail,data);
    const panels=sections(detail,['Tasks','Inputs & variables','Outputs','Definition','Kestra logs']);
    const tasks=data.tasks?.length?data.tasks:data.kestra_tasks||[];
    table(panels.Tasks,['Step / iteration','Type','Status','Started','Duration','Error / condition','Task runs'],tasks.map(t=>{const links=el('div','lh-toolbar');for(const runid of t.run_ids||[]){links.append(button(runid.slice(0,10),()=>{generation++;return showRun(runid,child,generation);}));}return [t.id,t.kind||t.task_id,badge(t.status),format(t.started),duration(t.duration??(t.ended&&t.started?t.ended-t.started:null)),t.error||(t.condition!=null?'condition: '+t.condition:''),links];}));
    const child=el('section','lh-run-detail');
    if(data.runs?.length){panels.Tasks.append(el('h3','','Linked notebook / dbt / SQL runs'));table(panels.Tasks,['Name','ID','Status','Details'],data.runs.map(r=>[r.name,r.id,badge(r.status),button('View code and logs',()=>{generation++;return showRun(r.id,child,generation);})]));}
    else panels.Tasks.append(el('p','lh-muted','Older executions may not have linked run IDs. Kestra logs below retain their original error messages.'));
    panels.Tasks.append(child);kv(panels['Inputs & variables'],{Inputs:data.inputs||{},Variables:data.variables||{}});panels.Outputs.append(jsonTree(data.outputs||{}));panels.Definition.append(data.definition?jsonTree(data.definition):el('p','lh-muted','Definition snapshot was not recorded for this legacy/native execution. Task run source snapshots are available in the linked runs.'));
    const logs=Array.isArray(data.logs)?data.logs:data.logs?.results||[];table(panels['Kestra logs'],['Time ('+zone+')','Level','Task','Message'],logs.map(l=>[format(l.timestamp),badge(l.level),l.taskId||'',el('div','lh-log-message',l.message)]));if(data.log_error)panels['Kestra logs'].append(el('p','lh-error',data.log_error));
    detail.append(button('Refresh workflow detail',()=>showWorkflow(id)));
  }
  return load();
}
