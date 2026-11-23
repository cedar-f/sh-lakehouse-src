export async function createCompute(root,{api,el,field,button}){
  root.append(el('h2','','Compute'),el('div','lh-muted','Save Spark settings and restart SQL/dbt, selected notebooks, or both.'));
  const summary=el('div','lh-card'),status=el('div','lh-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');root.append(summary);
  const config=await api('cluster');
  const threads=field(root,'CPU threads (auto uses available CPUs)',config.threads),memory=field(root,'Driver memory, e.g. 4g',config.driver_memory),shuffle=field(root,'Shuffle partitions',config.shuffle_partitions),catalog=field(root,'Default catalog',config.default_catalog),schema=field(root,'Default schema',config.default_schema),extra=field(root,'Extra Spark config / Maven packages (JSON)',JSON.stringify(config.extra||{},null,2),'textarea');
  const scope=field(root,'Restart scope','','select');
  for(const [value,label] of [['both','SQL/dbt + selected notebooks'],['sql','SQL/dbt only'],['notebooks','Selected notebooks only']]){const option=el('option','',label);option.value=value;scope.append(option);}
  scope.value='both';
  const kernels=el('div','lh-card'),choices=el('div'),warning=el('p','lh-muted');kernels.append(el('h3','','Notebook kernels'),choices);root.append(kernels,warning);
  const selected=new Map(),kernelPaths=new Map();let active=null,monitoring=false,busy=false;
  function updateScope(){kernels.hidden=scope.value==='sql';warning.textContent=scope.value==='sql'?'SQL/dbt waits for running runner jobs to finish before restarting.':'Restarting selected notebooks interrupts their queries and clears Python variables and DataFrames held in memory. SQL/dbt waits for running runner jobs to finish.';}
  scope.onchange=updateScope;updateScope();
  function renderKernels(model,first=false){
    const previous=new Map([...selected].map(([id,input])=>[id,input.checked]));selected.clear();choices.replaceChildren();
    for(const kernel of model.kernels){
      kernelPaths.set(kernel.id,kernel.path);
      const row=el('label','lh-kernel-row'),input=el('input');input.type='checkbox';input.checked=previous.has(kernel.id)?previous.get(kernel.id):first;input.disabled=busy;input.value=kernel.id;
      row.append(input,el('span','',kernel.path+' · '+kernel.state));choices.append(row);selected.set(kernel.id,input);
    }
    if(!model.kernels.length)choices.append(el('div','lh-muted','No running notebook kernels. New kernels will use the saved settings.'));
    summary.textContent='SQL '+model.sql_status+' · '+model.kernels.length+' notebook kernels · '+model.cpu_visible+' visible CPUs';
  }
  function setBusy(value){busy=value;for(const input of [threads,memory,shuffle,catalog,schema,extra,scope,...selected.values()])input.disabled=value;save.disabled=value;refresh.disabled=value;}
  function render(job){
    const lines=[job.state+' · '+job.stage];
    if(job.sql.state!=='SKIPPED')lines.push('SQL/dbt: '+job.sql.state);
    for(const kernel of job.kernels){const label=kernelPaths.get(kernel.id)||kernel.id;lines.push(label+': '+kernel.state+(kernel.error?' · '+kernel.error:''));}
    if(job.error)lines.push(job.error);
    status.classList.toggle('lh-error',job.state==='FAILED');status.textContent=lines.join('\n');
  }
  async function monitor(job){
    if(monitoring)return;monitoring=true;active=job;setBusy(true);check.hidden=true;
    try{
      while(true){
        render(active);
        if(active.state==='READY'||active.state==='FAILED'){setBusy(false);summary.textContent=active.state==='READY'?'Selected Spark services are ready.':'Settings saved. Review the restart error below.';break;}
        await new Promise(resolve=>setTimeout(resolve,1000));
        active=await api('cluster/restarts/'+active.id);
      }
    }catch(error){status.classList.add('lh-error');status.textContent='Could not read restart status: '+error.message+'\nThe restart may still be running. Check its status before saving again.';check.hidden=false;}
    finally{monitoring=false;}
  }
  const refresh=button('Refresh notebook list',async()=>renderKernels(await api('cluster')));
  const save=button('Save & Restart Spark',async()=>{
    setBusy(true);status.classList.remove('lh-error');status.textContent='Saving configuration…';
    try{
      const job=await api('cluster/restart',{scope:scope.value,kernel_ids:[...selected].filter(([,input])=>input.checked).map(([id])=>id),
        config:{threads:threads.value,driver_memory:memory.value,shuffle_partitions:Number(shuffle.value),default_catalog:catalog.value,default_schema:schema.value,extra:JSON.parse(extra.value)}});
      await monitor(job);
    }catch(error){setBusy(false);status.classList.add('lh-error');status.textContent='Could not start restart: '+error.message;}
  },true);
  const check=button('Check restart status',async()=>{if(active)await monitor(await api('cluster/restarts/'+active.id));});check.hidden=true;
  const actions=el('div','lh-toolbar');actions.append(save,refresh,check);root.append(actions,status,el('p','lh-muted','CPU/RAM container limits are set in .env. Notebook, SQL and runner have separate memory budgets.'));
  renderKernels(config,true);
  const maintenance=el('details'),maintenanceSummary=el('summary','','Artifact retention & cleanup'),cleanupStatus=el('div','lh-status');maintenance.append(maintenanceSummary,el('p','lh-muted','Automatic cleanup runs hourly. Table data, catalog metadata, warehouses and active runs are excluded. Configure retention in .env.'));
  function describe(r){cleanupStatus.textContent=`Retention: ${r.retention_days} days · quota: ${r.storage_max_gb} GB · history: ${r.history_retention_days} days\n${r.apply?'Removed':'Eligible'}: ${r.runs.length} runs, ${(r.bytes/1024/1024).toFixed(1)} MB · ${r.temporary.length} temporary directories`;}
  maintenance.append(button('Preview cleanup',async()=>describe(await api('maintenance'))),button('Clean eligible artifacts now',async()=>describe(await api('maintenance',{}))),cleanupStatus);root.append(maintenance);
  const registry=el('section','lh-card'),registryStatus=el('div','lh-status');
  registry.append(el('h3','','Catalog registry on R2'),el('p','lh-muted','Portable catalog/schema definitions, comments, properties, external volumes, function definitions and table inventory. Check synchronization before resetting local metadata.'),registryStatus);
  let registryZone='UTC';
  function showRegistry(r){
    registryStatus.replaceChildren();
    registryStatus.classList.toggle('lh-error',Boolean(r.error)||Boolean(r.unrestored?.length)||Boolean(r.nonportable?.length));
    if(!r.enabled){registryStatus.textContent='Registry disabled. Local UC metadata has no automatic portable recovery.';return;}
    const when=r.last_sync?new Date(r.last_sync*1000).toLocaleString(undefined,{timeZone:registryZone})+' '+registryZone:'Not synchronized in this process';
    registryStatus.append(el('p','',`${r.ready?'Synchronized':'Pending'} · s3://${r.bucket}/${r.key} · ${when}`));
    for(const [kind,count] of Object.entries(r.counts||{}))registryStatus.append(el('div','',`${kind}: ${count}`));
    if(r.error)registryStatus.append(el('p','lh-error',r.error));
    for(const item of r.unrestored||[])registryStatus.append(el('p','lh-error',`${item.kind} ${item.name}: not restored — ${item.reason}`));
    const missing=new Set((r.unrestored||[]).map(item=>item.kind+':'+item.name));
    for(const item of r.nonportable||[])if(!missing.has(item.kind+':'+item.name))registryStatus.append(el('p','lh-error',`${item.kind} ${item.name}: inventory saved, but requires separate recovery after a local reset.`));
  }
  async function refreshRegistry(){try{const [r,p]=await Promise.all([api('catalog-registry'),api('preferences')]);registryZone=p.timezone;showRegistry(r);}catch(e){registryStatus.textContent=e.message;registryStatus.classList.add('lh-error');}}
  registry.append(button('Refresh registry status',refreshRegistry),button('Sync registry now',async()=>{showRegistry(await api('catalog-registry/sync',{}));}));root.append(registry);
  await refreshRegistry();
  if(config.restart){active=config.restart;render(active);if(active.state==='RESTARTING')void monitor(active);}
}
