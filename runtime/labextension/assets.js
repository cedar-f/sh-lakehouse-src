import { Widget } from '@lumino/widgets';
import { showDialog, Dialog } from '@jupyterlab/apputils';

export const node=(tag,cls='',text='')=>{const n=document.createElement(tag);n.className=cls;n.textContent=text;return n;};
export const missing='Not reported';

export function formatDate(value,zone='UTC'){
  if(value===undefined||value===null||value==='')return missing;
  const date=new Date(value);if(Number.isNaN(date.getTime()))return missing;
  try{return new Intl.DateTimeFormat(undefined,{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date)+' '+zone;}
  catch{return date.toISOString();}
}

export function properties(parent,entries){
  const dl=node('dl','lh-asset-properties');
  for(const [label,value] of entries){dl.append(node('dt','',label),node('dd','',value===undefined||value===null||value===''?missing:String(value)));}
  parent.append(dl);return dl;
}

export function rawMetadata(parent,value){
  const details=node('details'),label=node('summary','','Raw metadata');details.append(label,node('pre','lh-code',JSON.stringify(value,null,2)));parent.append(details);
}

export async function copyText(root,text,status){
  const done=()=>{if(status)status.textContent='Copied: '+text;};
  try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);done();return;}}catch{}
  const input=node('textarea');input.value=text;input.style.position='fixed';input.style.opacity='0';root.append(input);input.focus();input.select();
  let copied=false;try{copied=document.execCommand('copy');}finally{input.remove();}
  if(copied){done();return;}
  const value=node('textarea');value.value=text;value.readOnly=true;
  await showDialog({title:'Copy (Ctrl+C)',body:new Widget({node:value}),buttons:[Dialog.okButton()]});
}

export function audit(parent,value,zone='UTC'){
  properties(parent,[['Object ID',value.table_id||value.function_id||value.volume_id||value.schema_id||value.id||missing],
    ['Created',formatDate(value.created_at,zone)],['Updated',formatDate(value.updated_at,zone)],
    ['Owner',value.owner],['Created by',value.created_by],['Updated by',value.updated_by]]);
}
