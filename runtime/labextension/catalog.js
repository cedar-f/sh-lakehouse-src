import { Widget } from '@lumino/widgets';
import { showDialog, Dialog } from '@jupyterlab/apputils';
import { audit, copyText, formatDate, properties, rawMetadata, missing } from './assets';

export async function createCatalog(root,{api,el,field,button,table,notebook,open,ask}){
  root.append(el('h2','','Catalog'),el('p','lh-muted','Browse persistent tables, SQL views, functions and volumes. Inspect schemas, definitions, ownership and audit metadata.'));
  const bar=el('div','lh-toolbar'),catalog=el('select'),schema=el('select'),kind=el('select'),search=el('input');
  catalog.setAttribute('aria-label','Catalog');schema.setAttribute('aria-label','Schema');kind.setAttribute('aria-label','Asset type');search.setAttribute('aria-label','Search catalog assets');search.placeholder='Search name';
  for(const [value,label] of [['all','All assets'],['tables','Tables'],['views','Views'],['functions','Functions'],['volumes','Volumes']]){const option=el('option','',label);option.value=value;kind.append(option);}
  bar.append(catalog,schema,kind,search);root.append(bar);
  const status=el('div','lh-status'),actions=el('div','lh-toolbar'),body=el('div'),detail=el('div','lh-run-detail');root.append(status,actions,body,detail);
  const summary=el('div','lh-asset-summary');summary.setAttribute('aria-label','Catalog asset counts');root.insertBefore(summary,status);
  let generation=0,data={tables:[],views:[],functions:[],volumes:[]},selected=new Set(),viewSelected=new Set(),active=null,busy=false;
  const timezone=(await api('preferences')).timezone||'UTC';
  const isView=t=>['VIEW','METRIC_VIEW','MATERIALIZED_VIEW'].includes(t.table_type);
  const controls=[];
  const setBusy=value=>{busy=value;for(const c of controls)c.disabled=value;draw();};
  function choose(select,items,previous){select.replaceChildren();for(const item of items){const option=el('option','',item.name);option.value=item.name;select.append(option);}if(items.some(i=>i.name===previous))select.value=previous;}
  async function listing(resource,query){const rows=[];let token='';const seen=new Set();do{const r=await api(resource+query+(token?'&page_token='+encodeURIComponent(token):''));rows.push(...(r[resource]||[]));token=r.next_page_token||'';if(token&&seen.has(token))throw Error('Repeated catalog pagination token');seen.add(token);}while(token);return rows;}
  async function loadAssets(ticket){
    if(!schema.value){data={tables:[],views:[],functions:[],volumes:[]};selected.clear();viewSelected.clear();draw();return;}
    const cat=catalog.value,sch=schema.value,q='?catalog='+encodeURIComponent(cat)+'&schema='+encodeURIComponent(sch);
    const [tables,functions,volumes]=await Promise.all(['tables','functions','volumes'].map(resource=>listing(resource,q)));
    if(ticket!==generation)return;
    const full=r=>({...r,full_name:r.full_name||cat+'.'+sch+'.'+r.name});
    data={tables:tables.filter(t=>!isView(t)).map(full),views:tables.filter(isView).map(full),functions:functions.map(full),volumes:volumes.map(full)};
    const available=new Set([...data.tables,...data.views].map(t=>t.full_name));selected=new Set([...selected].filter(n=>data.tables.some(t=>t.full_name===n)));viewSelected=new Set([...viewSelected].filter(n=>data.views.some(v=>v.full_name===n)));
    draw();if(active?.kind==='table'&&available.has(active.name))await showTable(active.name);else if(active?.kind==='function'&&data.functions.some(f=>f.full_name===active.name))await showFunction(active.name);else if(active?.kind==='volume'&&data.volumes.some(v=>v.full_name===active.name))await showVolume(active.name);else if(active?.kind==='namespace')await showNamespace(active.resource,active.name);else if(active?.kind!=='create'){active=null;detail.replaceChildren();}
  }
  async function refresh(){
    if(busy)return;const ticket=++generation,oldCat=catalog.value,oldSchema=schema.value;
    const cats=(await api('catalogs')).catalogs||[];if(ticket!==generation)return;
    choose(catalog,cats,oldCat);
    if(!catalog.value){schema.replaceChildren();data={tables:[],views:[],functions:[],volumes:[]};selected.clear();viewSelected.clear();detail.replaceChildren();draw();return;}
    const result=await listing('schemas','?catalog='+encodeURIComponent(catalog.value));if(ticket!==generation)return;
    choose(schema,result,catalog.value===oldCat?oldSchema:'');
    if(catalog.value!==oldCat||schema.value!==oldSchema){selected.clear();viewSelected.clear();active=null;detail.replaceChildren();}
    await loadAssets(ticket);
  }
  catalog.onchange=async()=>{const ticket=++generation;selected.clear();viewSelected.clear();active=null;detail.replaceChildren();try{const rows=await listing('schemas','?catalog='+encodeURIComponent(catalog.value));if(ticket!==generation)return;choose(schema,rows,'');await loadAssets(ticket);}catch(e){if(ticket===generation)status.textContent=e.message;}};
  schema.onchange=()=>{selected.clear();viewSelected.clear();active=null;detail.replaceChildren();void loadAssets(++generation).catch(e=>status.textContent=e.message);};
  kind.onchange=draw;search.oninput=draw;
  controls.push(catalog,schema,kind,search);
  const copy=text=>copyText(root,text,status);
  const refreshButton=button('Refresh',refresh),newCat=button('+ Catalog',async()=>{const n=await ask('Create catalog','sales');if(n){await api('catalogs',{name:n});await refresh();catalog.value=n;await catalog.onchange();}}),newSchema=button('+ Schema',async()=>{if(!catalog.value)throw Error('Choose a catalog');const n=await ask('Create schema','raw');if(n){await api('schemas',{name:n,catalog_name:catalog.value});await refresh();schema.value=n;schema.onchange();}});
  bar.append(refreshButton,newCat,newSchema);controls.push(refreshButton,newCat,newSchema);
  bar.append(button('Catalog details',()=>showNamespace('catalog',catalog.value)),button('Schema details',()=>showNamespace('schema',catalog.value+'.'+schema.value)));
  const selectionCount=el('span','lh-muted');
  const deleteSelected=button('Delete selected tables',async()=>{
    const names=[...selected].sort();if(!names.length)return;
    const box=el('div');box.append(el('p','','Drop the exact tables below through Spark. Managed table data may be removed; external data files remain. This batch is not atomic.'));
    box.append(el('pre','lh-code',names.join('\n')));const confirm=field(box,'Type DELETE to confirm','');
    const response=await showDialog({title:'Delete '+names.length+' selected tables',body:new Widget({node:box}),buttons:[Dialog.cancelButton(),Dialog.okButton({label:'Delete selected'})]});
    if(!response.button.accept)return;if(confirm.value!=='DELETE')throw Error('Type DELETE to confirm');
    setBusy(true);
    try{
      const result=await api('tables/delete',{names,confirmation:'DELETE',confirmed_names:names});
      for(const r of result.results)if(['DELETED','MISSING'].includes(r.status))selected.delete(r.name);
      status.replaceChildren();table(status,['Table','Result','Details'],result.results.map(r=>[r.name,r.status,(r.error||'')+(r.note?' '+r.note:'')]));
    }catch(error){status.textContent=error.message+' Refresh Catalog and check registry status before retrying.';}
    finally{setBusy(false);await refresh();}
  });
  const deleteViewSelected=button('Delete selected views',async()=>{
    const names=[...viewSelected].sort();if(!names.length)return;
    const box=el('div');box.append(el('p','','Drop these SQL view definitions. Their source tables and data are retained. This batch is not atomic.'),el('pre','lh-code',names.join('\n')));
    const confirm=field(box,'Type DELETE to confirm','');
    const response=await showDialog({title:'Delete '+names.length+' selected views',body:new Widget({node:box}),buttons:[Dialog.cancelButton(),Dialog.okButton({label:'Delete views'})]});
    if(!response.button.accept)return;if(confirm.value!=='DELETE')throw Error('Type DELETE to confirm');
    setBusy(true);try{const result=await api('views/delete',{names,confirmed_names:names,confirmation:'DELETE'});for(const r of result.results)if(['DELETED','MISSING'].includes(r.status))viewSelected.delete(r.name);status.replaceChildren();table(status,['View','Result','Details'],result.results.map(r=>[r.name,r.status,r.error||'']));}finally{setBusy(false);await refresh();}
  });
  actions.append(deleteSelected,selectionCount,deleteViewSelected,button('Clear selection',()=>{selected.clear();viewSelected.clear();draw();}));
  function updateSelection(){deleteSelected.disabled=busy||selected.size===0||selected.size>100;selectionCount.textContent=selected.size+' tables selected (max 100)';deleteViewSelected.disabled=busy||viewSelected.size===0||viewSelected.size>100;deleteViewSelected.title=viewSelected.size+' views selected (max 100)';}
  function visible(resource){return (kind.value==='all'||kind.value===resource)?data[resource].filter(r=>r.full_name.toLowerCase().includes(search.value.toLowerCase())):[];}
  function actionRow(items){const node=el('div','lh-toolbar');node.append(...items);return node;}
  function draw(){
    body.replaceChildren();summary.replaceChildren();updateSelection();
    for(const label of ['tables','views','functions','volumes']){const card=el('div','lh-card');card.append(el('strong','',data[label].length),el('div','lh-muted',label));summary.append(card);}
    const tables=visible('tables');if(tables.length){body.append(el('h3','','Tables'));const selectAll=el('input');selectAll.type='checkbox';selectAll.setAttribute('aria-label','Select all visible tables');selectAll.checked=tables.every(t=>selected.has(t.full_name));selectAll.indeterminate=!selectAll.checked&&tables.some(t=>selected.has(t.full_name));selectAll.disabled=busy;selectAll.onchange=()=>{for(const t of tables)selectAll.checked?selected.add(t.full_name):selected.delete(t.full_name);draw();};
      const rows=tables.map(t=>{const cb=el('input');cb.type='checkbox';cb.checked=selected.has(t.full_name);cb.disabled=busy;cb.setAttribute('aria-label','Select '+t.full_name);cb.onchange=()=>{cb.checked?selected.add(t.full_name):selected.delete(t.full_name);draw();};return [cb,button(t.name,()=>showTable(t.full_name)),t.table_type+' · '+t.data_source_format,formatDate(t.created_at,timezone),formatDate(t.updated_at,timezone),t.table_id||missing,button('Copy full name',()=>copy(t.full_name))];});
      nodeTable(body,[selectAll,'Name','Type / format','Created','Updated','Object ID','Actions'],rows);
    }
    const views=visible('views');if(views.length){body.append(el('h3','','Views'));nodeTable(body,['Select','Name','Type','Created','Updated','Object ID','Actions'],views.map(v=>{const cb=el('input');cb.type='checkbox';cb.checked=viewSelected.has(v.full_name);cb.disabled=busy||v.table_type!=='VIEW';cb.setAttribute('aria-label','Select view '+v.full_name);cb.onchange=()=>{cb.checked?viewSelected.add(v.full_name):viewSelected.delete(v.full_name);draw();};return [cb,button(v.name,()=>showTable(v.full_name)),v.table_type,formatDate(v.created_at,timezone),formatDate(v.updated_at,timezone),v.table_id||missing,button('Copy full name',()=>copy(v.full_name))];}));}
    const functions=visible('functions');if(functions.length){body.append(el('h3','','Functions'));nodeTable(body,['Name','Language','Returns','Created','Updated','Object ID','Actions'],functions.map(f=>[button(f.name,()=>showFunction(f.full_name)),f.external_language||f.routine_body,f.full_data_type||f.data_type,formatDate(f.created_at,timezone),formatDate(f.updated_at,timezone),f.function_id||missing,actionRow([button('Copy full name',()=>copy(f.full_name)),button('Delete function',()=>deleteFunction(f.full_name))]) ]));}
    const volumes=visible('volumes');if(volumes.length){body.append(el('h3','','Volumes / files'));nodeTable(body,['Name','Location','Created','Updated','Object ID'],volumes.map(v=>[button(v.name,()=>showVolume(v.full_name)),v.storage_location,formatDate(v.created_at,timezone),formatDate(v.updated_at,timezone),v.volume_id||missing]));}
    if(!tables.length&&!views.length&&!functions.length&&!volumes.length)body.append(el('p','lh-muted','No matching assets.'));
  }
  function nodeTable(parent,columns,rows){const wrap=el('div','lh-table-wrap'),t=el('table'),head=el('tr'),tbody=el('tbody');for(const c of columns){const th=el('th');th.append(c instanceof Node?c:document.createTextNode(String(c)));head.append(th);}const thead=el('thead');thead.append(head);t.append(thead);for(const row of rows){const tr=el('tr');for(const value of row){const td=el('td');td.append(value instanceof Node?value:document.createTextNode(String(value??'')));tr.append(td);}tbody.append(tr);}t.append(tbody);wrap.append(t);parent.append(wrap);}
  async function showTable(name){
    active={kind:'table',name};const value=await api('table?name='+encodeURIComponent(name));if(active?.name!==name||active.kind!=='table')return;
    const query='SELECT * FROM '+name+' LIMIT 100';
    detail.replaceChildren(el('h3','',name),el('p','lh-muted',value.comment||''),actionRow([button('Copy full name',()=>copy(name)),...(value.table_id?[button('Copy object ID',()=>copy(value.table_id))]:[]),button('Copy SELECT',()=>copy(query+';')),button('Preview',async()=>{const r=await api('sql',{sql:query});if(active?.name!==name)return;const out=el('section','lh-card');out.append(el('h3','','Preview (up to 100 rows)'));detail.append(out);table(out,r.columns,r.rows);}),button('Open SQL notebook',()=>notebook(query+';'))]));
    properties(detail,[['Type',value.table_type],['Format',value.data_source_format],['Location',value.storage_location||(isView(value)?'Logical view; no table data directory':missing)]]);audit(detail,value,timezone);
    detail.append(el('h3','','Columns'));table(detail,['Position','Column','Type','Nullable','Partition index','Comment'],(value.columns||[]).map(c=>[c.position,c.name,c.type_text,c.nullable===undefined?missing:String(c.nullable),c.partition_index??'',c.comment||'']));
    if(isView(value)){
      detail.append(el('h3','','View definition'),el('pre','lh-code',value.view_definition||'Definition not reported'),button('Copy definition',()=>copy(value.view_definition||'')));
      const dependencies=value.view_dependencies?.dependencies||[];detail.append(el('h3','','Dependencies'));
      table(detail,['Kind','Full name'],dependencies.map(d=>[d.table?'Table / view':'Function',d.table?.table_full_name||d.function?.function_full_name||missing]));
      detail.append(el('p','lh-muted','Native SQL views execute in Spark. UC 0.7 does not support replacing an existing view in place; create a new version or explicitly drop/create.'));
    }
    if(value.properties&&Object.keys(value.properties).length){detail.append(el('h3','','Properties'));table(detail,['Property','Value'],Object.entries(value.properties));}
    detail.append(el('p','lh-muted',value.authorization?.note||'Shared trusted workspace; UC authorization is disabled.'));rawMetadata(detail,value);
  }
  async function showNamespace(resource,name){
    if(!catalog.value||(resource==='schema'&&!schema.value))throw Error('Choose a catalog and schema');
    active={kind:'namespace',resource,name};const value=await api(resource+'?name='+encodeURIComponent(name));if(active?.name!==name||active.kind!=='namespace')return;
    detail.replaceChildren(el('h3','',name),el('p','lh-muted',value.comment||''),actionRow([button('Copy full name',()=>copy(name))]));audit(detail,value,timezone);
    properties(detail,[['Type',resource],['Storage root',value.storage_root],['Storage location',value.storage_location]]);
    if(value.properties)table(detail,['Property','Value'],Object.entries(value.properties));rawMetadata(detail,value);
  }
  async function showVolume(name){
    active={kind:'volume',name};const value=await api('volume?name='+encodeURIComponent(name));if(active?.name!==name||active.kind!=='volume')return;
    detail.replaceChildren(el('h3','',name),el('p','lh-muted',value.comment||''),actionRow([button('Copy full name',()=>copy(name)),button('Copy path',()=>copy((value.storage_location||'').replace(/^s3:\/\//,'s3a://'))),button('Open Files',()=>open('Files'))]));
    audit(detail,value,timezone);properties(detail,[['Volume type',value.volume_type],['Location',value.storage_location]]);rawMetadata(detail,value);
  }
  async function showFunction(name){
    active={kind:'function',name};const f=await api('function?name='+encodeURIComponent(name));if(active?.name!==name||active.kind!=='function')return;
    detail.replaceChildren(el('h3','',name),el('p','lh-muted',f.comment||''),el('p','lh-muted',f.routine_body==='SQL'?'Supported SQL scalar expressions can run by full name in notebooks, SQL editor and workflow SQL tasks.':'Python/external definition only; an execution runtime is not configured.'),actionRow([button('Copy full name',()=>copy(name)),button('Delete function',()=>deleteFunction(name))]));
    table(detail,['Language','Returns','SQL access','Deterministic'],[[f.external_language||f.routine_body,f.full_data_type||f.data_type,f.sql_data_access||'Unspecified',f.is_deterministic===undefined?'Unspecified':String(f.is_deterministic)]]);
    audit(detail,f,timezone);table(detail,['Parameter','Type','Default','Comment'],(f.input_params?.parameters||[]).map(p=>[p.name,p.type_text,p.parameter_default??'',p.comment||'']));detail.append(el('pre','lh-code',f.routine_definition||''),actionRow([button('Copy definition',()=>copy(f.routine_definition||'')),...(f.function_id?[button('Copy object ID',()=>copy(f.function_id))]:[])]));rawMetadata(detail,f);
  }
  async function deleteFunction(name){if(busy)return;const confirmation=await ask('Delete function '+name,'Type '+name);if(confirmation===null)return;if(confirmation!==name)throw Error('Confirm the full function name');await api('functions/delete',{name,confirmation});status.textContent='Deleted function: '+name;active=null;detail.replaceChildren();await refresh();}
  const createFunction=button('+ Function',()=>{
    if(!schema.value)throw Error('Choose a catalog and schema');active={kind:'create'};detail.replaceChildren(el('h3','','Register function in '+catalog.value+'.'+schema.value));
    const cat=catalog.value,sch=schema.value,name=field(detail,'Function name',''),language=field(detail,'Language','','select');for(const label of ['PYTHON','SQL'])language.append(el('option','',label));
    const result=field(detail,'Return type','INT'),params=field(detail,'Input parameters (JSON array)','[{"name":"value","type":"INT"}]','textarea'),comment=field(detail,'Description',''),definition=field(detail,'Function body','return value + 1','textarea');
    detail.append(el('p','lh-muted','Python: write the body without def. SQL: write the SQL expression. Registering stores the definition; it does not execute code. Existing names are never replaced.'));
    detail.append(button('Register function',async()=>{const f=await api('functions',{name:name.value,catalog_name:cat,schema_name:sch,language:language.value,return_type:result.value,parameters:JSON.parse(params.value),comment:comment.value,body:definition.value});active={kind:'function',name:f.full_name||cat+'.'+sch+'.'+name.value};status.textContent='Registered function. Check Compute for R2 synchronization status.';await refresh();},true));
  });bar.append(createFunction);controls.push(createFunction);
  const createView=button('+ View',()=>{
    if(!schema.value)throw Error('Choose a catalog and schema');const cat=catalog.value,sch=schema.value;active={kind:'create'};
    detail.replaceChildren(el('h3','','Create SQL view in '+cat+'.'+sch));
    const name=field(detail,'View name',''),comment=field(detail,'View description',''),query=field(detail,'View SELECT query','SELECT 1 AS example','textarea');
    detail.append(el('p','lh-muted','Enter one SELECT/WITH query. Source tables/views should use full catalog.schema.name references. The view stores SQL and output columns in UC; it does not copy table data.'));
    detail.append(button('Create view',async()=>{const value=await api('views',{name:cat+'.'+sch+'.'+name.value,sql:query.value,comment:comment.value});active={kind:'table',name:value.full_name||cat+'.'+sch+'.'+name.value};status.textContent='Created SQL view. View definitions are synchronized to the R2 registry.';await refresh();},true));
  });bar.append(createView);controls.push(createView);
  await refresh();
}
