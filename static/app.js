'use strict';
const $ = id => document.getElementById(id);
let state, selectedBlock = null, busy = false;
const stageText = {
 BEGIN: 'Next: record the transaction start. The original disk is still untouched.',
 LOG: 'Next: write the complete intended data and metadata to the journal.',
 COMMIT: 'Next: flush the commit record. After this, recovery can redo the operation.',
 DATA: 'Next: install data blocks. Metadata may temporarily refer to the old layout.',
 METADATA: 'Next: install filenames, sizes, block pointers and checksums.',
 CHECKPOINT: 'Next: mark disk installation complete. Future recovery can skip this transaction.',
 FINISH: 'Next: finish this unjournaled operation.'
};
function node(tag, text, cls) { const n = document.createElement(tag); if(text !== undefined) n.textContent = text; if(cls) n.className = cls; return n; }
function notify(msg) { $('toast').textContent = msg; $('toast').hidden = false; clearTimeout(notify.timer); notify.timer = setTimeout(() => $('toast').hidden = true, 3500); }
async function request(path, payload) {
 if(busy) return;
 busy = true;
 $('error').hidden = true;
 try {
  const r = await fetch(path, payload === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await r.json();
  if(!r.ok) throw new Error(data.error || 'Request failed.');
  state = data; render();
 } catch(e) { $('error').textContent = e.message.includes('fetch') ? 'Cannot reach the local server. Start app.py, then refresh this page.' : e.message; $('error').hidden = false; }
 finally { busy = false; }
}
function drawBlock() {
 if(selectedBlock === null) return;
 const b = state.blocks[selectedBlock];
 $('blockDetail').textContent = `BLOCK ${String(b.id).padStart(2,'0')} · ${b.allocated ? (b.owner || 'ORPHAN — no metadata owner') : 'FREE'}\n${b.allocated ? 'Data: ' + JSON.stringify(b.text) : 'No data stored.'}`;
}
function render() {
 const s = state, p = s.pending, active = !!p && !s.crashed;
 document.body.classList.toggle('crashed', s.crashed);
 $('space').textContent = `${s.used * s.block_size} / ${s.capacity} B`;
 $('count').textContent = s.files.length;
 $('health').textContent = s.issues.length ? 'Inconsistent' : 'Healthy';
 $('health').classList.toggle('bad', !!s.issues.length);
 $('healthNote').textContent = s.issues.length ? `${s.issues.length} issue(s) detected` : 'Checksums and allocation verified';
 $('recoveries').textContent = s.stats.recoveries;
 $('replayCount').textContent = `${s.stats.replayed} committed transaction(s) replayed`;
 $('mode').checked = s.mode; $('mode').disabled = !!p || s.crashed;
 $('modeTag').textContent = s.mode ? 'Protected' : 'Unprotected';
 $('heroStatus').textContent = s.crashed ? 'An unexpected stop.' : p ? 'Operation in flight.' : 'Ready for takeoff.';
 $('heroHelp').textContent = s.crashed ? 'Recover the disk to see what survived.' : p ? 'Step through the writes, or introduce a crash.' : 'A virtual disk. Real recovery logic.';
 $('txStatus').textContent = s.crashed ? 'Crashed' : p ? `${p.index} / ${p.stages.length} steps` : 'Idle';
 $('txDescription').textContent = p ? `${p.op.toUpperCase()} ${p.name} · Transaction ${p.id}` : 'Stage a file operation to begin. Each step writes to persistent storage.';
 $('stages').replaceChildren();
 const stages = p ? p.stages : s.mode ? ['BEGIN','LOG','COMMIT','DATA','METADATA','CHECKPOINT'] : ['DATA','METADATA','FINISH'];
 stages.forEach((t,i) => {const done = p && i < p.index; const n=node('div',undefined,'stage' + (done?' done':p && i===p.index?' next':'')); n.append(node('span',done?'✓':String(i+1).padStart(2,'0')),node('div',t)); $('stages').append(n);});
 $('stageHelp').textContent = s.crashed ? 'Execution stopped. Recovery reads durable journal records, without using the pending operation plan.' : p ? stageText[p.stages[p.index]] : 'The journal records the intended result before disk changes begin.';
 $('step').disabled = !active; $('run').disabled = !active; $('crash').disabled = !active; $('recover').disabled = !s.crashed;
 for(const id of ['op','filename','content','stage']) $(id).disabled = !!p || s.crashed || !!s.issues.length;
 $('files').replaceChildren();
 if(!s.files.length) $('files').append(node('p','No files yet. Create your first one above.','empty'));
 for(const f of s.files) { const b=node('button',undefined,'file');b.type='button';const text=node('span',f.name);text.append(node('small',`${f.size} bytes · ${f.blocks.length} block(s)`));b.append(node('b','▤'),text,node('span','↗'));b.onclick=()=>{if(p||s.crashed)return; $('op').value='edit';$('filename').value=f.name;$('content').value=f.content;updateForm();notify(`Loaded ${f.name}`);};$('files').append(b); }
 $('blocks').replaceChildren();
 s.blocks.forEach(b=>{const owner=s.files.findIndex(f=>f.name===b.owner);const cls='block'+(b.allocated?' allocated':'')+(b.allocated&&!b.owner?' orphan':'')+(owner>=0?' owner'+owner%4:'')+(selectedBlock===b.id?' selected':'');const n=node('button',String(b.id).padStart(2,'0'),cls);n.title=`Block ${b.id}: ${b.owner || (b.allocated?'Orphan':'Free')}`;n.setAttribute('aria-label',n.title);n.onclick=()=>{selectedBlock=b.id;render();};$('blocks').append(n);});
 $('diskUsage').textContent = `${s.used} / ${s.blocks.length} blocks`;drawBlock();
 $('issues').hidden = !s.issues.length; $('issues').replaceChildren();
 if(s.issues.length){$('issues').append(node('strong','Consistency check'));s.issues.forEach(x=>$('issues').append(node('div',x)));}
 $('journalCount').textContent=`${s.journal.length} records`;$('journal').replaceChildren();
 if(!s.journal.length) $('journal').append(node('p','The journal is empty. Protected operations will appear here.','empty'));
 s.journal.slice().reverse().forEach(e=>{const n=node('div',undefined,'entry');n.append(node('strong',e.type),node('code',e.tx));if(e.type==='LOG')n.append(node('span','Data + metadata after-image saved'));$('journal').append(n);});
 $('events').replaceChildren(); s.events.slice().reverse().forEach(e=>{const n=node('div',undefined,'entry');n.append(node('time',e.time+' UTC'),node('span',e.message));$('events').append(n);});
 updateForm();
}
function updateForm(){const del=$('op').value==='delete';$('contentLabel').hidden=del;$('byteCount').hidden=del;$('byteCount').textContent=`${new TextEncoder().encode($('content').value).length} UTF-8 bytes`;}
$('operationForm').onsubmit=e=>{e.preventDefault();request('/api/start',{op:$('op').value,name:$('filename').value,content:$('content').value});};
$('op').onchange=updateForm;$('content').oninput=updateForm;
for(const id of ['step','run','crash','recover']) $(id).onclick=()=>request('/api/'+id,{});
$('mode').onchange=()=>request('/api/mode',{enabled:$('mode').checked});
$('reset').onclick=()=>{if(confirm('Reset the virtual disk, journal and event history? This only clears Touchdown sandbox data.')){selectedBlock=null;$('blockDetail').textContent='Select any block to inspect its owner and data.';request('/api/reset',{confirm:'RESET'});}};
function sample(edit){if(state.pending||state.crashed){notify('Finish or recover the current operation first.');return;}$('op').value=edit?'edit':'create';$('filename').value='notes.txt';$('content').value=edit?'OS project completed':'OS project';updateForm();$('workspace').scrollIntoView({behavior:'smooth'});notify('Example filled. Select Stage operation.');}
$('sample').onclick=()=>sample(false);$('sampleEdit').onclick=()=>sample(true);
$('export').onclick=()=>{if(!state)return;const blob=new Blob([JSON.stringify({project:'Touchdown',exported_at:new Date().toISOString(),...state},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=node('a');a.href=url;a.download='Touchdown_Experiment.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('Experiment report exported.');};
request('/api/state');
