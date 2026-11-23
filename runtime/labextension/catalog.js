import { Widget } from '@lumino/widgets';
import { showDialog, Dialog } from '@jupyterlab/apputils';

export async function createCatalog(root,{api,el,field,button,table,notebook,open,ask}){
  root.append(el('h2','','Catalog'),el('p','lh-muted','Persistent tables, volumes and registered function definitions. Function code is not executed here.'));
  const bar=el('div','lh-toolbar'),catalog=el('select'),schema=el('select'),kind=el('select'),search=el('input');
  catalog.setAttribute('aria-label','Catalog');schema.setAttribute('aria-label','Schema');kind.setAttribute('aria-label','Asset type');search.setAttribute('aria-label','Search catalog assets');search.placeholder='Search name';
  for(const [value,label] of [['all','All assets'],['tables','Tables'],['functions','Functions'],['volumes','Volumes']]){const option=el('option','',label);option.value=value;kind.append(option);}
  bar.append(catalog,schema,kind,search);root.append(bar);
  const status=el('div','lh-status'),actions=el('div','lh-toolbar'),body=el('div'),detail=el('div','lh-run-detail');root.append(status,actions,body,detail);
  let generation=0,data={tables:[],functions:[],volumes:[]},selected=new Set(),active=null,busy=false;
  const controls=[];
  const setBusy=value=>{busy=value;for(const c of controls)c.disabled=value;draw();};
  function choose(select,items,previous){select.replaceChildren();for(const item of items){const option=el('option','',item.name);option.value=item.name;select.append(option);}if(items.some(i=>i.name===previous))select.value=previous;}
  async function listing(resource,query){const rows=[];let token='';const seen=new Set();do{const r=await api(resource+query+(token?'&page_token='+encodeURIComponent(token):''));rows.push(...(r[resource]||[]));token=r.next_page_token||'';if(token&&seen.has(token))throw Error('Repeated catalog pagination token');seen.add(token);}while(token);return rows;}
  async function loadAssets(ticket){
    if(!schema.value){data={tables:[],functions:[],volumes:[]};selected.clear();draw();return;}
    const cat=catalog.value,sch=schema.value,q='?catalog='+encodeURIComponent(cat)+'&schema='+encodeURIComponent(sch);
    const [tables,functions,volumes]=await Promise.all(['tables','functions','volumes'].map(resource=>listing(resource,q)));
    if(ticket!==generation)return;
    const full=r=>({...r,full_name:r.full_name||cat+'.'+sch+'.'+r.name});
    data={tables:tables.map(full),functions:functions.map(full),volumes:volumes.map(full)};
    const available=new Set(data.tables.map(t=>t.full_name));selected=new Set([...selected].filter(n=>available.has(n)));
    draw();if(active?.kind==='table'&&available.has(active.name))await showTable(active.name);else if(active?.kind==='function'&&data.functions.some(f=>f.full_name===active.name))await showFunction(active.name);else if(active?.kind!=='create'){active=null;detail.replaceChildren();}
  }
  async function refresh(){
    if(busy)return;const ticket=++generation,oldCat=catalog.value,oldSchema=schema.value;
    const cats=(await api('catalogs')).catalogs||[];if(ticket!==generation)return;
    choose(catalog,cats,oldCat);
    if(!catalog.value){schema.replaceChildren();data={tables:[],functions:[],volumes:[]};selected.clear();detail.replaceChildren();draw();return;}
    const result=await listing('schemas','?catalog='+encodeURIComponent(catalog.value));if(ticket!==generation)return;
    choose(schema,result,catalog.value===oldCat?oldSchema:'');
    if(catalog.value!==oldCat||schema.value!==oldSchema){selected.clear();active=null;detail.replaceChildren();}
    await loadAssets(ticket);
  }
  catalog.onchange=async()=>{const ticket=++generation;selected.clear();active=null;detail.replaceChildren();try{const rows=await listing('schemas','?catalog='+encodeURIComponent(catalog.value));if(ticket!==generation)return;choose(schema,rows,'');await loadAssets(ticket);}catch(e){if(ticket===generation)status.textContent=e.message;}};
  schema.onchange=()=>{selected.clear();active=null;detail.replaceChildren();void loadAssets(++generation).catch(e=>status.textContent=e.message);};
  kind.onchange=draw;search.oninput=draw;
  controls.push(catalog,schema,kind,search);
  async function copy(text){
    try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);status.textContent='Copied: '+text;return;}}catch{}
    const input=el('textarea');input.value=text;input.style.position='fixed';input.style.opacity='0';root.append(input);input.focus();input.select();let done=false;try{done=document.execCommand('copy');}finally{input.remove();}
    if(done){status.textContent='Copied: '+text;return;}
    const value=el('input');value.value=text;value.readOnly=true;const w=new Widget({node:value});await showDialog({title:'Copy full name (Ctrl+C)',body:w,buttons:[Dialog.okButton()]});
  }
  const refreshButton=button('Refresh',refresh),newCat=button('+ Catalog',async()=>{const n=await ask('Create catalog','sales');if(n){await api('catalogs',{name:n});await refresh();catalog.value=n;await catalog.onchange();}}),newSchema=button('+ Schema',async()=>{if(!catalog.value)throw Error('Choose a catalog');const n=await ask('Create schema','raw');if(n){await api('schemas',{name:n,catalog_name:catalog.value});await refresh();schema.value=n;schema.onchange();}});
  bar.append(refreshButton,newCat,newSchema);controls.push(refreshButton,newCat,newSchema);
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
  actions.append(deleteSelected,selectionCount,button('Clear selection',()=>{selected.clear();draw();}));
  function updateSelection(){deleteSelected.disabled=busy||selected.size===0||selected.size>100;selectionCount.textContent=selected.size+' tables selected (max 100)';}
  function visible(resource){return (kind.value==='all'||kind.value===resource)?data[resource].filter(r=>r.full_name.toLowerCase().includes(search.value.toLowerCase())):[];}
  function actionRow(items){const node=el('div','lh-toolbar');node.append(...items);return node;}
  function draw(){
    body.replaceChildren();updateSelection();
    const tables=visible('tables');if(tables.length){body.append(el('h3','','Tables'));const selectAll=el('input');selectAll.type='checkbox';selectAll.setAttribute('aria-label','Select all visible tables');selectAll.checked=tables.every(t=>selected.has(t.full_name));selectAll.indeterminate=!selectAll.checked&&tables.some(t=>selected.has(t.full_name));selectAll.disabled=busy;selectAll.onchange=()=>{for(const t of tables)selectAll.checked?selected.add(t.full_name):selected.delete(t.full_name);draw();};
      const rows=tables.map(t=>{const cb=el('input');cb.type='checkbox';cb.checked=selected.has(t.full_name);cb.disabled=busy;cb.setAttribute('aria-label','Select '+t.full_name);cb.onchange=()=>{cb.checked?selected.add(t.full_name):selected.delete(t.full_name);draw();};return [cb,button(t.name,()=>showTable(t.full_name)),t.table_type+' · '+t.data_source_format,button('Copy full name',()=>copy(t.full_name))];});
      nodeTable(body,[selectAll,'Name','Type / format','Actions'],rows);
    }
    const functions=visible('functions');if(functions.length){body.append(el('h3','','Functions'));nodeTable(body,['Name','Language','Returns','Actions'],functions.map(f=>[button(f.name,()=>showFunction(f.full_name)),f.external_language||f.routine_body,f.full_data_type||f.data_type,actionRow([button('Copy full name',()=>copy(f.full_name)),button('Delete function',()=>deleteFunction(f.full_name))]) ]));}
    const volumes=visible('volumes');if(volumes.length){body.append(el('h3','','Volumes / files'));nodeTable(body,['Name','Location'],volumes.map(v=>[button(v.name,()=>open('Files')),v.storage_location]));}
    if(!tables.length&&!functions.length&&!volumes.length)body.append(el('p','lh-muted','No matching assets.'));
  }
  function nodeTable(parent,columns,rows){const wrap=el('div','lh-table-wrap'),t=el('table'),head=el('tr'),tbody=el('tbody');for(const c of columns){const th=el('th');th.append(c instanceof Node?c:document.createTextNode(String(c)));head.append(th);}const thead=el('thead');thead.append(head);t.append(thead);for(const row of rows){const tr=el('tr');for(const value of row){const td=el('td');td.append(value instanceof Node?value:document.createTextNode(String(value??'')));tr.append(td);}tbody.append(tr);}t.append(tbody);wrap.append(t);parent.append(wrap);}
  async function showTable(name){
    active={kind:'table',name};const value=await api('table?name='+encodeURIComponent(name));if(active?.name!==name||active.kind!=='table')return;
    detail.replaceChildren(el('h3','',name),actionRow([button('Copy full name',()=>copy(name)),button('Preview',async()=>{const r=await api('sql',{sql:'SELECT * FROM '+name+' LIMIT 100'});const out=el('div');detail.append(out);table(out,r.columns,r.rows);}),button('Open SQL notebook',()=>notebook('SELECT * FROM '+name+' LIMIT 100;'))]));
    table(detail,['Column','Type','Comment'],(value.columns||[]).map(c=>[c.name,c.type_text,c.comment||'']));detail.append(el('pre','lh-code',JSON.stringify({location:value.storage_location,type:value.table_type,properties:value.properties},null,2)),el('p','lh-muted',value.authorization?.note||'Shared trusted workspace; UC authorization is disabled.'));
  }
  async function showFunction(name){
    active={kind:'function',name};const f=await api('function?name='+encodeURIComponent(name));if(active?.name!==name||active.kind!=='function')return;
    detail.replaceChildren(el('h3','',name),el('p','lh-muted',f.comment||''),el('p','lh-muted','Registered definition only. No execution in Spark/MCP is enabled by this screen.'),actionRow([button('Copy full name',()=>copy(name)),button('Delete function',()=>deleteFunction(name))]));
    table(detail,['Language','Returns','SQL access','Deterministic'],[[f.external_language||f.routine_body,f.full_data_type||f.data_type,f.sql_data_access||'Unspecified',f.is_deterministic===undefined?'Unspecified':String(f.is_deterministic)]]);
    table(detail,['Parameter','Type','Default','Comment'],(f.input_params?.parameters||[]).map(p=>[p.name,p.type_text,p.parameter_default??'',p.comment||'']));detail.append(el('pre','lh-code',f.routine_definition||''));
  }
  async function deleteFunction(name){if(busy)return;const confirmation=await ask('Delete function '+name,'Type '+name);if(confirmation===null)return;if(confirmation!==name)throw Error('Confirm the full function name');await api('functions/delete',{name,confirmation});status.textContent='Deleted function: '+name;active=null;detail.replaceChildren();await refresh();}
  const createFunction=button('+ Function',()=>{
    if(!schema.value)throw Error('Choose a catalog and schema');active={kind:'create'};detail.replaceChildren(el('h3','','Register function in '+catalog.value+'.'+schema.value));
    const cat=catalog.value,sch=schema.value,name=field(detail,'Function name',''),language=field(detail,'Language','','select');for(const label of ['PYTHON','SQL'])language.append(el('option','',label));
    const result=field(detail,'Return type','INT'),params=field(detail,'Input parameters (JSON array)','[{"name":"value","type":"INT"}]','textarea'),comment=field(detail,'Description',''),definition=field(detail,'Function body','return value + 1','textarea');
    detail.append(el('p','lh-muted','Python: write the body without def. SQL: write the SQL expression. Registering stores the definition; it does not execute code. Existing names are never replaced.'));
    detail.append(button('Register function',async()=>{const f=await api('functions',{name:name.value,catalog_name:cat,schema_name:sch,language:language.value,return_type:result.value,parameters:JSON.parse(params.value),comment:comment.value,body:definition.value});active={kind:'function',name:f.full_name||cat+'.'+sch+'.'+name.value};status.textContent='Registered function. Check Compute for R2 synchronization status.';await refresh();},true));
  });bar.append(createFunction);controls.push(createFunction);
  await refresh();
}
