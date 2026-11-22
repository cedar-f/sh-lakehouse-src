export async function createGitHub(root,{api,el,field,button,app}){
  root.append(el('h2','','GitHub'),el('p','lh-muted','Create an empty repository on GitHub first. Connect this workspace folder, make the first commit, then use the native Git panel for everyday work.'));
  const link=el('a','','Create repository on GitHub');link.href='https://github.com/new';link.target='_blank';link.rel='noopener noreferrer';root.append(link);
  const feedback=el('div','lh-status');feedback.setAttribute('aria-live','polite');root.append(feedback);
  const setup=el('section','lh-card');setup.append(el('h3','','1. Repository and author'));
  const path=field(setup,'Repository directory inside workspace','.'),remote=field(setup,'Existing GitHub repository URL',''),name=field(setup,'Git author name',''),email=field(setup,'Git author email',''),branch=field(setup,'Branch','main');
  remote.placeholder='git@github.com:OWNER/REPO.git';
  setup.append(el('p','lh-muted','For local code, use . or an existing folder, then Initialize / connect. For a GitHub repository with code, configure SSH and Clone to a new folder below. A managed .gitignore is added automatically. Save notebooks before reviewing files.'));
  const clonePath=field(setup,'Clone destination inside workspace (new or empty directory)','workspace-code');
  const repoState=el('div'),setupActions=el('div','lh-toolbar');setup.append(setupActions,repoState);root.append(setup);
  const ssh=el('section','lh-card');ssh.append(el('h3','','2. SSH authentication'));
  const keyState=el('div'),publicKey=field(ssh,'Public key to add on GitHub','','textarea');publicKey.readOnly=true;
  ssh.append(keyState);
  const keyLink=el('a','','GitHub SSH keys');keyLink.href='https://github.com/settings/keys';keyLink.target='_blank';keyLink.rel='noopener noreferrer';ssh.append(keyLink);
  const phrase=field(ssh,'SSH key passphrase (empty only for an unprotected key)','','input');phrase.type='password';phrase.autocomplete='off';
  ssh.append(el('p','lh-muted','The private key stays on the server. Passphrases are used once and are not saved. An encrypted key needs unlocking again after the container/agent restarts.'));
  const sshActions=el('div','lh-toolbar');ssh.append(sshActions);root.append(ssh);
  const review=el('section','lh-card');review.append(el('h3','','3. Review and initial commit'));
  const reviewActions=el('div','lh-toolbar'),fileList=el('div'),message=field(review,'Initial commit message','Initial workspace commit');review.append(reviewActions,fileList);root.append(review);
  const publish=el('section','lh-card');publish.append(el('h3','','4. First push and native Git panel'));
  const confirmation=field(publish,'Confirm destination SSH URL before first push','');
  const publishActions=el('div','lh-toolbar');publish.append(publishActions,el('p','lh-muted','First push sets the branch upstream. A non-empty remote is refused unless it already points to this exact commit. Later commits/pulls/pushes belong in the native Git panel.'));root.append(publish);
  let info=null,preview=null,busy=false,selection=new Set();
  const controls=[];
  function add(parent,label,fn,primary=false){const control=button(label,async()=>{
    if(busy)return;busy=true;feedback.className='lh-status';feedback.textContent='Working…';update();
    try{await fn();}catch(error){feedback.className='lh-status lh-error';feedback.textContent=error.message||String(error);}
    finally{busy=false;phrase.value='';update();}
  },primary);controls.push(control);parent.append(control);return control;}
  function data(){return{path:path.value.trim()||'.',remote:remote.value.trim(),name:name.value.trim(),email:email.value.trim(),branch:branch.value.trim()};}
  function showState(value){
    info=value;publicKey.value=value.ssh.public_key||'';
    keyState.textContent=value.ssh.key_exists?(value.ssh.key_loaded?'SSH key loaded in the shared agent.':'SSH key exists; unlock it if protected.'):'No SSH key exists for this Jupyter user.';
    repoState.replaceChildren();
    for(const [label,text] of Object.entries({Directory:value.path,Repository:value.initialized?'Initialized':'Not initialized',Branch:value.branch||'—',Origin:value.remote||'—',Commit:value.head||'No commits',Upstream:value.upstream||'Not set'})){
      const row=el('div','lh-git-property');row.append(el('strong','',label+': '),el('span','',text));repoState.append(row);
    }
    if(value.name&&!name.value)name.value=value.name;
    if(value.email&&!email.value)email.value=value.email;
    if(value.remote&&!remote.value)remote.value=value.remote;
    if(value.branch)branch.value=value.branch;
  }
  async function refresh(){showState(await api('git/status?path='+encodeURIComponent(data().path)));update();}
  function update(){
    controls.forEach(control=>{control.disabled=busy;});
    generate.disabled=busy||Boolean(info?.ssh.key_exists);
    unlock.disabled=busy||!info?.ssh.key_exists;
    previewButton.disabled=busy||!info?.initialized||Boolean(info?.head);
    commit.disabled=busy||!preview||!selection.size||Boolean(info?.head);
    push.disabled=busy||!info?.head;
  }
  add(setupActions,'Refresh status',async()=>{preview=null;selection.clear();fileList.replaceChildren();await refresh();feedback.textContent='Status refreshed.';});
  add(setupActions,'Initialize / connect repository',async()=>{
    showState(await api('git/init',data()));preview=null;selection.clear();fileList.replaceChildren();
    feedback.textContent=info.head?'Connected. This repository already has commits; continue in the native Git panel.':'Repository initialized and connected. Configure SSH, then review the first commit.';
  },true);
  add(setupActions,'Clone existing repository',async()=>{
    const result=await api('git/clone',{...data(),path:clonePath.value.trim()});
    path.value=result.path;showState(result);preview=null;selection.clear();fileList.replaceChildren();
    feedback.textContent='Repository cloned with automatic .gitignore. Review that file, then use the native Git panel to commit and push changes.';
  });
  const generate=add(sshActions,'Create SSH key',async()=>{
    await api('git/key',{passphrase:phrase.value});await refresh();feedback.textContent='Key created. Add the public key to GitHub, then test repository access.';
  });
  const unlock=add(sshActions,'Unlock SSH key',async()=>{
    await api('git/unlock',{passphrase:phrase.value});await refresh();feedback.textContent='Key unlocked for the native Git panel and this setup screen.';
  },true);
  add(sshActions,'Copy public key',async()=>{
    if(!publicKey.value)throw Error('Create a key first.');
    try{await navigator.clipboard.writeText(publicKey.value);feedback.textContent='Public key copied.';}
    catch{publicKey.focus();publicKey.select();feedback.textContent='Public key selected. Press Ctrl+C to copy.';}
  });
  add(sshActions,'Test repository access',async()=>{
    const result=await api('git/test',{remote:remote.value.trim()});await refresh();feedback.textContent=result.empty?'SSH read access works; the GitHub repository is empty.':'SSH read access works; the remote already contains branches/tags. Use native Git to reconcile it.';
  });
  const previewButton=add(reviewActions,'Review files',async()=>{
    preview=await api('git/preview?path='+encodeURIComponent(data().path));
    selection=new Set(preview.files.filter(file=>!file.blocked).map(file=>file.path));
    fileList.replaceChildren(el('p','lh-muted',`${preview.files.length} candidate file(s). Only checked files will be committed. Ignored files are omitted. Review notebook outputs and secrets before committing.`));
    const table=el('table'),head=el('tr');['Include','Path','Size','Check'].forEach(value=>head.append(el('th','',value)));const header=el('thead');header.append(head);table.append(header);const body=el('tbody');table.append(body);
    for(const file of preview.files){
      const row=el('tr'),choose=el('input');choose.type='checkbox';choose.checked=!file.blocked;choose.disabled=Boolean(file.blocked);choose.setAttribute('aria-label','Include '+file.path);
      choose.onchange=()=>{if(choose.checked)selection.add(file.path);else selection.delete(file.path);update();};
      const cell=el('td');cell.append(choose);row.append(cell,el('td','',file.path),el('td','',file.size+' B'),el('td',file.blocked?'lh-error':'',file.blocked||'Ready'));body.append(row);
    }
    const wrap=el('div','lh-table-wrap');wrap.append(table);fileList.append(wrap);feedback.textContent='File preview ready. Changes after this preview require a new review.';
  });
  const commit=add(reviewActions,'Create initial commit',async()=>{
    const result=await api('git/commit',{path:data().path,token:preview.token,files:[...selection],message:message.value});
    preview=null;selection.clear();await refresh();fileList.replaceChildren(el('p','lh-muted',result.committed+' file(s) committed.'));feedback.textContent='Initial commit created: '+result.head+'. It has not been pushed yet.';
  },true);
  const push=add(publishActions,'Push first commit',async()=>{
    const result=await api('git/push',{path:data().path,confirmation:confirmation.value.trim()});
    await refresh();feedback.textContent='Pushed '+result.branch+' and set its upstream. Open the native Git panel for subsequent changes.';
  },true);
  add(publishActions,'Open native Git panel',async()=>{
    const directory=data().path==='.'?'':data().path.replace(/\/$/,'');
    if(app.commands.hasCommand('filebrowser:go-to-path'))await app.commands.execute('filebrowser:go-to-path',{path:directory});
    app.shell.activateById('jp-git-sessions');feedback.textContent='Native Git panel opened. Use the same repository folder to stage, commit, pull and push.';
  });
  add(publishActions,'Open terminal',()=>app.commands.execute('terminal:create-new'));
  for(const input of [path,remote,name,email,branch])input.addEventListener('change',()=>{preview=null;selection.clear();fileList.replaceChildren();if(input===path)info=null;update();});
  await refresh();
}
