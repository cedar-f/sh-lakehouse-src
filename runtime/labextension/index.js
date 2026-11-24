import { Widget } from '@lumino/widgets';
import { ServerConnection } from '@jupyterlab/services';
import { showDialog, Dialog } from '@jupyterlab/apputils';
import { FileTree } from './filetree';
import { createCompute } from './compute';
import { createHistory } from './history';
import { createWorkflow } from './workflow';
import { createGitHub } from './github';
import { createCatalog } from './catalog';
import { copyText, formatDate, properties, rawMetadata } from './assets';
import './style.css';

const el=(tag,cls='',text='')=>{const n=document.createElement(tag);n.className=cls;n.textContent=text;return n;};
function button(text,fn,primary=false){const b=el('button',primary?'lh-primary':'',text);b.onclick=()=>Promise.resolve().then(fn).catch(e=>showDialog({title:'Lakehouse',body:String(e.message||e),buttons:[Dialog.okButton()]}));return b;}
let fieldCounter=0;
function field(parent,label,value='',type='input'){const l=el('label','',label),n=el(type);n.id='lh-field-'+(++fieldCounter);l.htmlFor=n.id;n.value=value;parent.append(l,n);return n;}
function table(parent,columns,rows){const wrap=el('div','lh-table-wrap'),t=el('table'),head=el('tr');columns.forEach(c=>head.append(el('th','',c)));const th=el('thead');th.append(head);t.append(th);const body=el('tbody');rows.forEach(r=>{const tr=el('tr');r.forEach(v=>tr.append(el('td','',v===null?'NULL':typeof v==='object'?JSON.stringify(v):v)));body.append(tr);});t.append(body);wrap.append(t);parent.append(wrap);}
async function api(path,data){const settings=ServerConnection.makeSettings();const url=settings.baseUrl+'lakehouse/api/'+path;const r=await ServerConnection.makeRequest(url,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{body:JSON.stringify(data),headers:{'Content-Type':'application/json'}})},settings);const v=await r.json();if(!r.ok)throw Error(v.error||v.detail||JSON.stringify(v));return v;}
async function ask(title,label){const input=el('input');input.placeholder=label;const r=await showDialog({title,body:new Widget({node:input}),buttons:[Dialog.cancelButton(),Dialog.okButton()]});return r.button.accept?input.value.trim():null;}

export default {
  id:'@lakehouse/workspace:plugin',autoStart:true,
  activate:app=>{
    const panels=new Map();
    async function notebook(sql){const id='Query_'+Date.now()+'.ipynb';await app.serviceManager.contents.save(id,{type:'notebook',format:'json',content:{nbformat:4,nbformat_minor:5,metadata:{kernelspec:{name:'python3',display_name:'Python 3',language:'python'}},cells:[{cell_type:'code',metadata:{},source:'%%sql\n'+sql,outputs:[],execution_count:null}]}});await app.commands.execute('docmanager:open',{path:id,factory:'Notebook',options:{mode:'tab-after'}});}
    async function open(name){
      const existing=panels.get(name);
      if(existing&&!existing.isDisposed){
        // Closing a plain Lumino Widget hides/detaches it without disposing it.
        // Restore the same widget so edits, uploads and folder state survive.
        existing.show();
        if(!existing.isAttached)app.shell.add(existing,'main',{mode:'tab-after'});
        app.shell.activateById(existing.id);
        return;
      }
      const panel=new Widget();panel.id='lakehouse-'+name.replaceAll(' ','-');panel.title.label=name;panel.title.closable=true;panel.addClass('lh-root');panels.set(name,panel);
      panel.disposed.connect(()=>{panel.node.dispatchEvent(new Event('lh-dispose'));if(panels.get(name)===panel)panels.delete(name);});
      app.shell.add(panel,'main',{mode:'tab-after'});app.shell.activateById(panel.id);
      try{await views[name](panel.node);}catch(e){panel.node.append(el('pre','lh-error',e.message));}
    }
    const views={
      Catalog:root=>createCatalog(root,{api,el,field,button,table,notebook,open,ask}),
      Files:async root=>{
        root.append(el('h2','','Files on R2'),el('div','lh-muted','Upload and delete files or subfolders inside incoming/. Deletion is permanent. Table data under warehouse/ is read only.'));
        const bar=el('div','lh-toolbar'),prefix=el('input');prefix.value='incoming/';prefix.style.flex='1';prefix.setAttribute('aria-label','Upload folder');bar.append(el('span','lh-muted','Upload folder'),prefix,button('Refresh tree',()=>tree.refresh()),button('Collapse all',()=>tree.collapseAll()));root.append(bar);
        const drop=el('div','lh-drop','Drop files here, or click to select multiple files'),input=el('input');input.type='file';input.multiple=true;input.hidden=true;drop.append(input);root.append(drop);const queue=el('div'),listing=el('div');root.append(queue,listing);
        const deletion=el('div','lh-delete-status');deletion.setAttribute('aria-live','polite');root.append(deletion);
        const metadataStatus=el('div','lh-status');metadataStatus.setAttribute('role','status');
        const fileDetail=el('section','lh-run-detail lh-file-detail');fileDetail.hidden=true;root.append(metadataStatus,fileDetail);
        const preferences=await api('preferences');let detailTicket=0;
        let running=Promise.resolve(),pendingUploads=0;
        const enqueue=files=>{
          if(tree.deleting){queue.append(el('div','lh-error','Wait for deletion to finish before uploading.'));return;}
          for(const f of files){pendingUploads++;running=running.then(()=>upload(f)).catch(e=>queue.append(el('div','lh-error',e.message))).finally(()=>pendingUploads--);}
        };
        const tree=new FileTree({
          list:(path,token)=>api('files?prefix='+encodeURIComponent(path)+(token?'&page_token='+encodeURIComponent(token):'')),
          downloadUrl:key=>ServerConnection.makeSettings().baseUrl+'lakehouse/api/download?key='+encodeURIComponent(key),
          onSelect:path=>{prefix.value=path;},
          onDelete:remove,
          timezone:preferences.timezone,
          onError:error=>{metadataStatus.textContent=error.message;},
          onCopy:({key,bucket})=>{if(!bucket)throw Error('Wait for the bucket listing');return copyText(root,'s3a://'+bucket+'/'+key,metadataStatus);},
          onInspect:inspect,
        });
        listing.append(tree.node);
        async function inspect({key,kind}){
          const ticket=++detailTicket;fileDetail.hidden=false;fileDetail.replaceChildren(el('p','lh-muted','Loading metadata…'));
          const value=await api('file?key='+encodeURIComponent(key)+'&kind='+kind).catch(error=>{if(ticket===detailTicket)fileDetail.replaceChildren(el('p','lh-error',error.message));throw error;});if(ticket!==detailTicket)return;
          const actions=el('div','lh-toolbar');actions.append(button('Copy path',()=>copyText(root,value.spark_path,metadataStatus)),button('Copy object ID',()=>copyText(root,value.object_id,metadataStatus)),button('Close details',()=>{detailTicket++;fileDetail.hidden=true;}));
          fileDetail.replaceChildren(el('h3','',key||value.bucket),actions);
          properties(fileDetail,[['Type',value.virtual?'Virtual folder prefix':kind==='folder'?'Folder marker object':'File object'],['Bucket',value.bucket],['Spark path',value.spark_path],['S3 path',value.s3_path],['Object ID (bucket/key)',value.object_id],['ID source',value.object_id_kind],['Created',formatDate(value.created_at,preferences.timezone)],['Creation metadata',value.created_at_source],['Updated (Last-Modified)',formatDate(value.updated_at,preferences.timezone)],['Size',value.size===undefined?'Not calculated / not reported':Number(value.size).toLocaleString()+' bytes'],['Content type',value.content_type],['ETag',value.etag],['Storage class',value.storage_class],['Version ID',value.version_id]]);
          if(value.note)fileDetail.append(el('p','lh-muted',value.note));
          if(kind==='file'){
            const download=el('a','lh-download-link','Download file');download.href=ServerConnection.makeSettings().baseUrl+'lakehouse/api/download?key='+encodeURIComponent(key);download.target='_blank';download.rel='noopener';fileDetail.append(download);
            const extension=key.split('.').pop().toLowerCase();
            if(['csv','json','parquet'].includes(extension)){
              const code='df = spark.read'+(extension==='csv'?'.option("header", True)':'')+'.'+extension+'('+JSON.stringify(value.spark_path)+')\ndisplay(df.limit(20).toPandas())';
              fileDetail.append(el('h3','','Read in notebook'),el('pre','lh-code',code),button('Copy read code',()=>copyText(root,code,metadataStatus)));
            }
          }
          rawMetadata(fileDetail,value);
        }
        prefix.onchange=()=>{prefix.value=prefix.value.trim().replace(/\/?$/,'/');tree.select(prefix.value);};
        input.onchange=()=>{enqueue(input.files);input.value='';};drop.onclick=e=>{if(e.target!==input&&!tree.deleting)input.click();};drop.ondragover=e=>{e.preventDefault();if(!tree.deleting)drop.classList.add('over');};drop.ondragleave=()=>drop.classList.remove('over');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');enqueue(e.dataTransfer.files);};
        async function remove(key,kind){
          if(pendingUploads){await showDialog({title:'Uploads in progress',body:'Finish or cancel queued uploads before deleting.',buttons:[Dialog.okButton()]});return null;}
          const body=el('div');body.append(el('p','',kind==='folder'?'Permanently delete this folder and every object inside it?':'Permanently delete this file?'),el('code','lh-delete-path',key),el('p','lh-muted','There is no recycle bin.'));
          const confirmation=kind==='folder'?field(body,'Type the full folder path to confirm',''):null;
          if(confirmation)confirmation.autocomplete='off';
          const choice=await showDialog({title:'Delete '+kind,body:new Widget({node:body}),buttons:[Dialog.cancelButton(),Dialog.okButton({label:'Delete',displayType:'warn'})]});
          if(!choice.button.accept)return null;
          if(confirmation&&confirmation.value!==key){deletion.replaceChildren(el('div','lh-error','Path did not match. Nothing was deleted.'));return null;}
          let deleted=0,more=true,stopped=false,failed=false;
          const card=el('div','lh-card'),summary=el('div','','Deleting '+key),progress=el('progress','lh-progress'),actions=el('div','lh-toolbar');
          progress.setAttribute('aria-label','Deletion in progress');
          const stop=button('Stop after current batch',()=>{stopped=true;stop.disabled=true;});actions.append(stop);
          card.append(summary,progress,actions);deletion.replaceChildren(card);input.disabled=true;
          try{
            do{
              const result=await api('files/delete',{key,kind,confirmation:key});deleted+=result.deleted;more=result.has_more;
              summary.textContent=`Deleted ${deleted} object(s) from ${key}${more?' — continuing…':''}`;
              if(result.errors?.length){failed=true;summary.classList.add('lh-error');summary.textContent=`Deletion stopped: ${deleted} object(s) deleted; ${result.errors.length} object(s) failed. Remaining objects were kept.`;table(card,['Object','Code','Message'],result.errors.map(error=>[error.key,error.code,error.message]));break;}
            }while(more&&!stopped);
            if(!failed)summary.textContent=more?`Stopped after deleting ${deleted} object(s) from ${key}. Remaining objects were kept.`:`Deleted ${kind} ${key} (${deleted} object(s)).`;
          }catch(error){failed=true;summary.classList.add('lh-error');summary.textContent=`Deletion stopped after ${deleted} confirmed object(s): ${error.message}. Refresh the tree to check remaining objects.`;}
          finally{progress.remove();stop.disabled=true;input.disabled=false;}
          return {complete:!more&&!failed};
        }
        async function upload(file){if(!prefix.value.startsWith('incoming/'))throw Error('Choose an incoming/ destination before uploading');if(!file.size)throw Error('Empty files are not supported by multipart upload');const key=prefix.value.replace(/\/?$/,'/')+file.name;const card=el('div','lh-card'),label=el('div','',file.name),progress=el('progress','lh-progress'),state=el('div','lh-muted','Preparing…');progress.max=file.size;card.append(label,progress,state);queue.append(card);const identity='lh-upload:'+key+':'+file.size+':'+file.lastModified;let id=localStorage.getItem(identity),parts=new Map();if(id){try{const r=await api('upload?id='+id);parts=new Map(r.parts.map(p=>[p.PartNumber,p.Size]));}catch{id=null;}}if(!id){const r=await api('upload/start',{key,size:file.size});id=r.id;localStorage.setItem(identity,id);}let canceled=false;card.append(button('Cancel',async()=>{canceled=true;await api('upload/abort',{id});localStorage.removeItem(identity);state.textContent='Canceled';}));const size=32*1024*1024;let sent=0;try{for(let offset=0,part=1;offset<file.size;offset+=size,part++){if(canceled)return;const blob=file.slice(offset,offset+size);if(parts.get(part)===blob.size){sent+=blob.size;progress.value=sent;continue;}const settings=ServerConnection.makeSettings();state.textContent='Uploading part '+part;const r=await ServerConnection.makeRequest(settings.baseUrl+'lakehouse/api/upload/part?id='+id+'&part='+part,{method:'POST',body:blob,headers:{'Content-Type':'application/octet-stream'}},settings);if(!r.ok)throw Error((await r.json()).error);sent+=blob.size;progress.value=sent;state.textContent=(100*sent/file.size).toFixed(1)+'%';}await api('upload/complete',{id});localStorage.removeItem(identity);state.textContent='Complete';await tree.refresh(key.slice(0,key.lastIndexOf('/')+1));}catch(e){state.textContent='Paused: '+e.message+'. Select the same file again to resume.';}}
        await tree.initialize();
      },
      Compute:root=>createCompute(root,{api,el,field,button}),
      SQL:async root=>{
        root.append(el('h2','','SQL editor'));const query=field(root,'Spark SQL','SELECT current_catalog(), current_schema();','textarea'),out=el('div');root.append(button('Run',async()=>{out.replaceChildren(el('div','lh-muted','Running…'));const r=await api('sql',{sql:query.value});out.replaceChildren();table(out,r.columns,r.rows);if(r.truncated)out.append(el('div','lh-muted','Showing first 1000 rows'));},true),button('Open as notebook',()=>notebook(query.value)),out);
      },
      dbt:async root=>{
        root.append(el('h2','','dbt'),el('div','lh-muted','Models, tests, snapshots and documentation run against the shared Spark SQL endpoint.'));
        const path=field(root,'Project directory in workspace','dbt'),select=field(root,'Selection (optional)','');root.append(el('p','lh-muted','Declare vars.lakehouse_catalog and +schema in dbt_project.yml. Project mode uses exact schema names and rejects models without a schema.'));const legacy=el('details');legacy.append(el('summary','','Legacy project overrides'));root.append(legacy);const catalog=field(legacy,'Legacy target catalog (optional)',''),schema=field(legacy,'Legacy target schema (optional)','');legacy.append(el('p','lh-muted','For projects without vars.lakehouse_catalog only. Clear overrides after migrating.'));const commands=el('div','lh-toolbar');root.append(commands);for(const command of ['debug','seed','build','test','snapshot','docs','deps'])commands.append(button(command,async()=>{const r=await api('jobs',{kind:'dbt',path:path.value,command,select:select.value,catalog:catalog.value,schema:schema.value});await showDialog({title:'dbt queued',body:'Run '+r.id+'. Open Runs to see output.',buttons:[Dialog.okButton()]});}));root.append(button('Open Runs',()=>open('Runs')),button('Open Docs',async()=>{
          const windowRef=window.open('about:blank','_blank');if(windowRef){windowRef.opener=null;windowRef.document.body.textContent='Preparing dbt documentation…';}
          try{let latest=await api('docs/latest?project='+encodeURIComponent(path.value));
            if(!latest.run_id){const job=await api('jobs',{kind:'dbt',path:path.value,command:'docs',catalog:catalog.value,schema:schema.value});
              for(let i=0;i<900;i++){await new Promise(resolve=>setTimeout(resolve,2000));const run=await api('runs/'+job.id);if(!['QUEUED','RUNNING','SUCCESS'].includes(run.status))throw Error(run.error||'Documentation generation failed; open Runs.');if(run.status==='SUCCESS'){latest={run_id:job.id};break;}}
              if(!latest.run_id)throw Error('Documentation is still running. Open Runs and try Open Docs when it completes.');}
            const url=ServerConnection.makeSettings().baseUrl+'lakehouse/docs/'+latest.run_id+'/index.html';if(windowRef&&!windowRef.closed)windowRef.location.href=url;else root.append(el('p','lh-muted','Allow popups, then click Open Docs again.'));
          }catch(error){if(windowRef&&!windowRef.closed)windowRef.document.body.textContent=error.message;throw error;}
        },true));
      },
      Runs:root=>createHistory(root,{api,el,button,baseUrl:ServerConnection.makeSettings().baseUrl}),
      'Workflow Run History':root=>createHistory(root,{api,el,button,baseUrl:ServerConnection.makeSettings().baseUrl,workflow:true}),
      Workflows:root=>createWorkflow(root,{api,el,field,button,open}),
      GitHub:root=>createGitHub(root,{api,el,field,button,app}),
      Notebook:async root=>{root.append(el('h2','','Run saved notebook'));const path=field(root,'Notebook path under workspace',''),params=field(root,'Parameters (JSON)','{}','textarea');path.placeholder='Folder/MyNotebook.ipynb';root.append(button('Run in background',async()=>{if(!path.value.trim())throw Error('Enter the path of a saved notebook.');const r=await api('jobs',{kind:'notebook',path:path.value.trim(),parameters:JSON.parse(params.value)});root.append(el('p','',r.id+' queued. See Runs.'));},true));}
    };
    for(const name of Object.keys(views))app.commands.addCommand('lakehouse:'+name,{label:'Lakehouse: '+name,execute:()=>open(name)});
    app.restored.then(async()=>{
    const side=new Widget();side.id='lakehouse-sidebar';side.title.label='Lakehouse';side.title.caption='Lakehouse V3';side.addClass('lh-root');side.addClass('lh-sidebar');side.node.append(el('h3','','LAKEHOUSE'),el('div','lh-badge','V3 · R2 + Delta'));
    for(const name of Object.keys(views))side.node.append(button(name,()=>open(name)));
    app.shell.add(side,'left',{rank:150});
    app.shell.activateById(side.id);
    await open('Catalog');
    });
  }
};
