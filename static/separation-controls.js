// Experimental preview and human-confirmed source routing; no automatic identity claims.
const separatedBuffers=new Map();
let separatedNodes=[],separationRenderKey='',separationActiveClip=null;
function confirmedClips(sid){return (recording?.separations||[]).filter(c=>c.confirmed&&c.speakers?.includes(sid));}
function speakerReviewTurns(sid){
  const spans=[...speakerSoloTurns(sid),...confirmedClips(sid).map(c=>({start:c.start,end:c.end}))].sort((a,b)=>a.start-b.start),result=[];
  for(const span of spans){const last=result.at(-1);if(last&&span.start<=last.end)last.end=Math.max(last.end,span.end);else result.push({...span});}
  return result;
}
function bufferKey(clip,index){return `${selectedId}/${clip.id}/${clip.signature}/${index}`;}
async function prepareSeparatedPlayback(sid){
  ensureAudioGraph();
  const rid=selectedId;
  for(const clip of confirmedClips(sid)){
    const index=clip.speakers.indexOf(sid),key=bufferKey(clip,index);if(separatedBuffers.has(key))continue;
    const response=await fetch(`/api/recordings/${rid}/separations/${clip.id}/audio/${index}`,{cache:'no-store'});
    if(!response.ok)throw new Error('A separated clip is stale or missing. Remove or regenerate it before playing this lane.');
    const buffer=await audioGraph.context.decodeAudioData(await response.arrayBuffer());
    if(rid!==selectedId)throw new Error('Recording changed. Start speaker playback again.');
    separatedBuffers.set(key,buffer);
  }
}
function stopSeparatedNodes(){for(const node of separatedNodes){try{node.stop();}catch{}node.disconnect();}separatedNodes=[];}
function scheduleSeparatedPlayback(){
  stopSeparatedNodes();if(!audioGraph||audio.paused||!activePlaybackSpeaker)return;
  const now=audioGraph.context.currentTime,pos=audio.currentTime,rate=audio.playbackRate||1;
  for(const clip of confirmedClips(activePlaybackSpeaker)){
    if(clip.end<=pos)continue;
    const index=clip.speakers.indexOf(activePlaybackSpeaker),buffer=separatedBuffers.get(bufferKey(clip,index));if(!buffer)continue;
    const offset=Math.max(0,pos-clip.start),duration=Math.min(clip.end-Math.max(pos,clip.start),buffer.duration-offset);if(duration<=0)continue;
    const node=audioGraph.context.createBufferSource();node.buffer=buffer;node.playbackRate.value=rate;
    const gain=audioGraph.context.createGain();gain.gain.value=audio.muted?0:1;node.connect(gain);gain.connect(audioGraph.context.destination);
    node.onended=()=>{node.disconnect();gain.disconnect();};node.start(now+Math.max(0,clip.start-pos)/rate,offset,duration);separatedNodes.push(node);
  }
}
function renderSeparationReview(){
  if($('separation-backdrop').classList.contains('hidden'))return;
  const clips=recording?.separations||[],key=JSON.stringify([selectedId,clips,separationActiveClip]);if(key===separationRenderKey)return;separationRenderKey=key;
  const clip=clips.find(c=>c.id===separationActiveClip);
  $('separation-saved').innerHTML=clips.map(c=>`<button class="button" data-review-separation="${c.id}">${time(c.start)}–${time(c.end)} · ${c.confirmed?'Assigned':'Needs review'}</button>`).join('')||'<p class="setting-hint">Drag a short overlapping range in a speaker lane, then right-click to separate two voices.</p>';
  if(!clip){$('separation-preview').innerHTML='';return;}
  const options=recording.speakers.filter(s=>s.identity_status!=='unresolved');
  $('separation-preview').innerHTML=`<p>${time(clip.start)}–${time(clip.end)} · two estimated sources. Listen to both before assigning names. Leakage, missing words and distortion are possible.</p>${clip.review_warning?'<p class="alert">The two outputs are highly related. Separation may not have worked well; compare with the original before confirming.</p>':''}<button class="button" data-listen-separation-original="${clip.id}">Listen to original mix</button>${[0,1].map(i=>`<div class="separation-source"><strong>Source ${i===0?'A':'B'}</strong><audio controls preload="metadata" src="/api/recordings/${selectedId}/separations/${clip.id}/audio/${i}"></audio><label>Assign to <select data-separation-source="${i}"><option value="">Choose speaker…</option>${options.map(s=>`<option value="${s.id}" ${clip.speakers?.[i]===s.id?'selected':''}>${esc(s.name)}</option>`).join('')}</select></label></div>`).join('')}<div class="separation-actions"><button class="button primary" data-confirm-separation="${clip.id}" ${busy()?'disabled':''}>Confirm assignments</button><button class="button" data-delete-separation="${clip.id}" ${busy()?'disabled':''}>Remove previews</button></div><p class="setting-hint">Only confirmed clips are included in speaker-lane playback. The original recording and transcript are unchanged.</p>`;
}
async function requestSeparation(selection){
  if(!recording||busy())return;
  audio.pause();closeClipMenu();separationActiveClip=null;separationRenderKey='';openModal('separation-backdrop');renderSeparationReview();
  try{
    const rid=selectedId;
    const result=await api(`/api/recordings/${rid}/separations`,{method:'POST',body:JSON.stringify({start:selection.start,end:selection.end})});
    $('separation-preview').innerHTML='<p><span class="spinner"></span> Separating the selected clip locally…</p><button class="button" data-cancel-separation>Cancel separation</button>';
    await poll();
    while(!result.cached&&state?.job.state==='running'){await new Promise(resolve=>setTimeout(resolve,500));await poll();if(rid!==selectedId)return;}
    if(!result.cached&&state?.job.state==='error')throw new Error(state.job.message);
    if(!result.cached&&state?.job.state==='cancelled'){$('separation-preview').textContent='Separation cancelled. Original audio and transcript are kept.';return;}
    separationActiveClip=result.id;separationRenderKey='';renderSeparationReview();
  }catch(error){$('separation-preview').textContent=error.message;handleError(error);}
}
function initSeparationControls(){
  $('separation-history').onclick=()=>{audio.pause();separationActiveClip=recording?.separations?.at(-1)?.id;separationRenderKey='';openModal('separation-backdrop');renderSeparationReview();};
  document.addEventListener('play',event=>{if(event.target.tagName!=='AUDIO')return;document.querySelectorAll('audio').forEach(el=>{if(el!==event.target)el.pause();});},true);
  document.addEventListener('click',async event=>{
    if(event.target.closest('[data-cancel-separation]')){try{await api('/api/jobs/cancel',{method:'POST'});toast('Cancellation requested. Waiting for this short inference call to return.');}catch(error){handleError(error);}return;}
    const button=event.target.closest('[data-review-separation],[data-confirm-separation],[data-delete-separation],[data-listen-separation-original]');if(!button||button.disabled)return;
    try{
      if(button.dataset.reviewSeparation){separationActiveClip=button.dataset.reviewSeparation;renderSeparationReview();return;}
      if(button.dataset.listenSeparationOriginal){const clip=recording.separations.find(c=>c.id===button.dataset.listenSeparationOriginal);seekTo(clip.start,true,clip.end);return;}
      const cid=button.dataset.confirmSeparation||button.dataset.deleteSeparation;
      if(button.dataset.deleteSeparation&&!confirm('Remove these separated previews? Original audio and transcript are kept.'))return;
      const speakers=[...document.querySelectorAll('[data-separation-source]')].map(el=>el.value);
      recording=await api(`/api/recordings/${selectedId}/separations/${cid}`,{method:button.dataset.deleteSeparation?'DELETE':'PATCH',...(button.dataset.deleteSeparation?{}:{body:JSON.stringify({speakers})})});
      separatedBuffers.clear();separationRenderKey='';
      if(button.dataset.confirmSeparation){closeModal('separation-backdrop');toast('Assigned clips will now play in their speaker lanes. Review the result; identity is not automatically verified.');}else{separationActiveClip=null;renderSeparationReview();}
      renderRecording();
    }catch(error){handleError(error);}
  });
}
