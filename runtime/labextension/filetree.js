const element=(tag,className='',text='')=>{
  const node=document.createElement(tag);node.className=className;node.textContent=text;return node;
};

function bytes(size){
  if(size<1024)return `${size} B`;
  const units=['KiB','MiB','GiB','TiB'];let value=size/1024,index=0;
  while(value>=1024&&index<units.length-1){value/=1024;index++;}
  return `${value.toFixed(1)} ${units[index]}`;
}

/** Lazy R2 prefix tree. Lists expanded folders only, with pagination per folder. */
export class FileTree{
  constructor({list,downloadUrl,onSelect}){
    this.list=list;this.downloadUrl=downloadUrl;this.onSelect=onSelect;
    this.folders=new Map();this.selected='incoming/';
    this.node=element('div','lh-file-tree');this.node.setAttribute('role','tree');
    this.node.setAttribute('aria-label','R2 file tree');
    this.root=this.folder('','R2',null);this.root.expanded=true;
    this.node.append(this.root.element);this.update(this.root);
  }

  folder(prefix,name,parent){
    if(this.folders.has(prefix))return this.folders.get(prefix);
    const item={prefix,name,parent,expanded:prefix==='incoming/'||!!(prefix&&this.selected.startsWith(prefix)),
      loaded:false,pending:null,nextToken:null,entries:new Map()};
    item.element=element('div','lh-tree-item lh-tree-folder');item.element.dataset.prefix=prefix;
    item.element.setAttribute('role','treeitem');item.element.tabIndex=0;
    item.element.setAttribute('aria-level',String(parent?Number(parent.element.getAttribute('aria-level'))+1:1));
    item.row=element('div','lh-tree-row');item.arrow=element('span','lh-tree-arrow');
    item.arrow.setAttribute('aria-hidden','true');item.label=element('span','lh-tree-name',name);
    item.row.title=prefix||'Bucket root';item.row.append(item.arrow,item.label);
    item.group=element('div','lh-tree-children');item.group.setAttribute('role','group');
    item.status=element('div','lh-tree-status lh-muted');item.status.setAttribute('role','status');
    item.children=element('div');item.group.append(item.children,item.status);
    item.element.append(item.row,item.group);
    item.row.onclick=()=>{this.select(prefix);this.expand(item,!item.expanded);};
    item.element.onkeydown=event=>{
      if(event.target!==item.element)return;
      if(event.key==='ArrowRight'){event.preventDefault();if(!item.expanded)this.expand(item,true);else this.visible(item.element,1);}
      else if(event.key==='ArrowLeft'){event.preventDefault();if(item.expanded)this.expand(item,false);else if(parent)parent.element.focus();}
      else if(event.key==='Enter'||event.key===' '){event.preventDefault();item.row.click();}
      else if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();this.visible(item.element,event.key==='ArrowDown'?1:-1);}
    };
    this.folders.set(prefix,item);this.update(item);return item;
  }

  update(item){
    item.element.setAttribute('aria-expanded',String(item.expanded));
    item.element.setAttribute('aria-label',item.name);
    item.element.setAttribute('aria-selected',String(item.prefix===this.selected));
    item.row.classList.toggle('selected',item.prefix===this.selected);
    item.arrow.textContent=item.expanded?'▾':'▸';item.group.hidden=!item.expanded;
  }

  select(prefix){
    this.selected=prefix;
    for(const item of this.folders.values())this.update(item);
    this.onSelect(prefix);
  }

  visible(current,offset){
    const items=[...this.node.querySelectorAll('[role="treeitem"]')].filter(node=>node.getClientRects().length);
    const index=items.indexOf(current);items[index+offset]?.focus();
  }

  async expand(item,expanded){
    item.expanded=expanded;this.update(item);
    if(expanded&&!item.loaded)await this.load(item,true);
  }

  file(file,parent){
    const item=element('div','lh-tree-item lh-tree-file');item.dataset.key=file.key;
    item.setAttribute('role','treeitem');item.setAttribute('aria-label',file.key.slice(parent.prefix.length));
    item.setAttribute('aria-level',String(Number(parent.element.getAttribute('aria-level'))+1));item.tabIndex=0;
    const row=element('div','lh-tree-row');row.append(element('span','lh-tree-arrow','·'));
    const link=element('a','lh-tree-name',file.key.slice(parent.prefix.length));
    link.href=this.downloadUrl(file.key);link.target='_blank';link.rel='noopener';link.title=file.key;link.tabIndex=-1;
    row.append(link,element('span','lh-tree-size lh-muted',bytes(file.size)));item.append(row);
    item.onkeydown=event=>{
      if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();this.visible(item,event.key==='ArrowDown'?1:-1);}
      else if(event.key==='ArrowLeft'){event.preventDefault();parent.element.focus();}
      else if(event.key==='Enter'){event.preventDefault();link.click();}
    };
    return item;
  }

  render(item){
    item.children.replaceChildren();
    const folders=[...item.entries.values()].filter(entry=>entry.folder).sort((a,b)=>a.folder.name.localeCompare(b.folder.name));
    const files=[...item.entries.values()].filter(entry=>entry.file).sort((a,b)=>a.file.key.localeCompare(b.file.key));
    for(const entry of folders)item.children.append(entry.folder.element);
    for(const entry of files)item.children.append(this.file(entry.file,item));
    if(!item.entries.size&&!item.nextToken)item.children.append(element('div','lh-tree-empty lh-muted','Empty folder'));
    if(item.nextToken){
      const more=element('button','lh-tree-more','Load more');more.type='button';
      more.setAttribute('aria-label','Load more in '+item.name);more.onclick=()=>this.load(item,false);
      item.children.append(more);
    }
  }

  async load(item,reset){
    if(item.pending){await item.pending;if(!reset)return;}
    item.pending=(async()=>{
      item.element.setAttribute('aria-busy','true');item.status.replaceChildren(element('span','','Loading…'));
      for(const button of item.children.querySelectorAll(':scope > .lh-tree-more'))button.disabled=true;
      try{
        const page=await this.list(item.prefix,reset?'':item.nextToken);
        if(reset)item.entries.clear();
        if(item===this.root&&page.bucket){item.name=`r2://${page.bucket}`;item.label.textContent=item.name;this.update(item);}
        const prefixes=new Set(page.folders||[]);
        // Keep the platform's upload landing folder selectable even when empty.
        if(item===this.root&&reset)prefixes.add('incoming/');
        for(const prefix of prefixes){
          if(prefix===item.prefix)continue;
          const name=prefix.slice(item.prefix.length).replace(/\/$/,'');
          item.entries.set('folder:'+prefix,{folder:this.folder(prefix,name,item)});
        }
        for(const file of page.files||[]){
          if(file.key===item.prefix||file.key.endsWith('/'))continue;
          item.entries.set('file:'+file.key,{file});
        }
        item.nextToken=page.next_page_token||null;item.loaded=true;this.render(item);item.status.replaceChildren();
        const expanded=[...item.entries.values()].filter(entry=>entry.folder?.expanded).map(entry=>entry.folder);
        await Promise.all(expanded.map(child=>reset?this.load(child,true):child.loaded?Promise.resolve():this.load(child,true)));
      }catch(error){
        item.status.replaceChildren(element('span','lh-error',error.message+' '));
        const retry=element('button','','Retry');retry.type='button';retry.onclick=()=>this.load(item,reset);item.status.append(retry);
        for(const button of item.children.querySelectorAll(':scope > .lh-tree-more'))button.disabled=false;
      }finally{item.element.setAttribute('aria-busy','false');}
    })();
    try{await item.pending;}finally{item.pending=null;}
  }

  async initialize(){await this.load(this.root,true);}

  async refresh(prefix){
    const item=prefix&&this.folders.get(prefix);
    await this.load(item&&this.node.contains(item.element)?item:this.root,true);
  }

  collapseAll(){
    for(const item of this.folders.values()){if(item!==this.root)item.expanded=false;this.update(item);}
  }
}
