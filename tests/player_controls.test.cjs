// Exercise the actual transport handlers with a deterministic media element.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const app = fs.readFileSync('static/app.js', 'utf8');
const controls = fs.readFileSync('static/clip-controls.js', 'utf8');
const elements = {};
const sample = {dataset:{playSpeaker:'s1'}, attrs:{}, querySelector(){return {getAttribute:()=>this.href,setAttribute:(_,v)=>this.href=v};},setAttribute(k,v){this.attrs[k]=v;}};
const ctx = vm.createContext({inlineEditorHost:null,console,document:{querySelectorAll:()=>[sample]},
  $:id=>elements[id]??=( {} ), recording:{duration:100},
  activeSampleSpeaker:null,activePlaybackSpeaker:null,sampleEnd:null,
  speakerById:()=>({id:'s1',name:'Alice',sample_start:5,sample_end:8}),
  audio:{currentTime:0,paused:true,play(){this.paused=false;return Promise.resolve();},pause(){this.paused=true;}},
  ensureAudioGraph(){},renderSpectrum(){},handleError(e){throw e;},updatePlayback(){ctx.updateSamplePlayIcons();}});
vm.runInContext(controls,ctx);
vm.runInContext(fs.readFileSync('static/separation-controls.js','utf8'),ctx);
vm.runInContext(app.split('\n').find(l=>l.startsWith('function seekTo(')),ctx);
// Avoid WebAudio in this deterministic state test.
vm.runInContext('ensureAudioGraph=()=>{};',ctx);
const sampleClick = app.split('\n').find(l=>l.includes("if(button.matches('[data-play-speaker]'))"));
ctx.button={matches:()=>true,dataset:{playSpeaker:'s1'}};
vm.runInContext(sampleClick,ctx);
assert.equal(ctx.audio.paused,false);assert.equal(sample.href,'#i-stop');assert.equal(ctx.sampleEnd,8);
vm.runInContext(sampleClick,ctx);
assert.equal(ctx.audio.paused,true);assert.equal(sample.href,'#i-play');assert.equal(ctx.audio.currentTime,5);
for (const id of ['play-button','stop-button','rewind-button','forward-button','playback-speed']) {
  vm.runInContext(app.split('\n').find(l=>l.startsWith(`$('${id}').on`)),ctx);
}
elements['play-button'].onclick();assert.equal(ctx.audio.paused,false);
ctx.audio.currentTime=95;elements['forward-button'].onclick();assert.equal(ctx.audio.currentTime,100);
elements['rewind-button'].onclick();assert.equal(ctx.audio.currentTime,90);
elements['play-button'].onclick();assert.equal(ctx.audio.paused,true);
ctx.audio.currentTime=3;elements['rewind-button'].onclick();assert.equal(ctx.audio.currentTime,0);assert.equal(ctx.audio.paused,true);
ctx.audio.currentTime=45;elements['stop-button'].onclick();assert.equal(ctx.audio.currentTime,0);assert.equal(ctx.sampleEnd,null);
elements['playback-speed'].value='2';elements['playback-speed'].onchange();assert.equal(ctx.audio.playbackRate,2);
console.log('PASS: sample Play/Stop, play/pause, stop, bounded skips, paused seeking, 2x speed');
ctx.recording={duration:20,turns:[{speaker_id:'a',start:0,end:10},{speaker_id:'b',start:2,end:4}],overlap_regions:[{start:6,end:7}],silenced_ranges:[{start:8,end:9}]};
const solo=ctx.speakerSoloTurns('a');
assert.equal(solo.length,4);
for(const r of solo)for(const [start,end] of [[2,4],[6,7],[8,9]])assert.ok(r.end<=start||r.start>=end,'Solo playback must exclude other voices, overlaps and muted ranges');
assert.equal(ctx.recording.turns[0].start,0,'Original turn must be retained');
ctx.activePlaybackSpeaker='a';ctx.audio.currentTime=3;ctx.audio.paused=false;
ctx.scheduleMutes=()=>{};ctx.updateLanePlayIcons=()=>{};
ctx.advanceSpeakerPlayback();assert.equal(ctx.audio.currentTime,3,'Overlapping turns must remain playable');
console.log('PASS: solo review excludes overlap, other speakers and silence edits; lane playback retains overlaps');
ctx.recording={duration:10,turns:[{speaker_id:'a',start:0,end:5},{speaker_id:'b',start:2,end:4}],separations:[{id:'draft',start:2,end:3,speakers:['a','b'],confirmed:false}]};
assert.equal(ctx.speakerReviewTurns('a').some(r=>r.start<=2.5&&r.end>2.5),true,'Original overlapping mix must remain playable');
assert.equal(ctx.speakerOriginalTurns('a').some(r=>r.start<=2.5&&r.end>2.5),true,'Draft sources must not suppress the original mix');
ctx.recording={...ctx.recording,separations:[{id:'confirmed',start:2,end:3,speakers:['a','b'],confirmed:true}]};
assert.equal(ctx.speakerReviewTurns('a').some(r=>r.start<=2.5&&r.end>2.5),true);
assert.equal(ctx.speakerReviewTurns('other').length,0,'Assigned clip must not enter another speaker lane');
console.log('PASS: only human-confirmed separated clips enter the assigned speaker lanes');

ctx.selectedId='test';
vm.runInContext("separatedBuffers.set(bufferKey(recording.separations[0],0),{});",ctx);
assert.equal(ctx.speakerOriginalTurns('a').some(r=>r.start<=2.5&&r.end>2.5),false,'Ready confirmed source replaces the mix without doubling it');
assert.equal(ctx.speakerOriginalTurns('b').some(r=>r.start<=2.5&&r.end>2.5),true,'Unavailable source falls back to the mix');
ctx.recording={duration:10,turns:[{speaker_id:'a',start:2,end:4},{speaker_id:'b',start:2,end:4}],speaker_silences:{a:[{start:3,end:3.5}]}};
assert.equal(ctx.speakerReviewTurns('a').length,2,'Explicit lane silence remains honored');
assert.equal(ctx.speakerOriginalTurns('a').some(r=>r.start<=2.5&&r.end>2.5),true,'Overlap-only speaker must have audible original audio');
console.log('PASS: overlap-only lanes play; confirmed sources replace the mix; missing sources fall back; silence edits remain');

const gainEvents=[];
ctx.audioGraph={context:{currentTime:0},gain:{gain:{cancelScheduledValues(){},setValueAtTime(value,when){gainEvents.push({value,when});}}}};
ctx.audio.currentTime=2.5;ctx.audio.paused=false;ctx.activePlaybackSpeaker='a';
vm.runInContext('scheduleSeparatedPlayback=()=>{};',ctx);
vm.runInContext(controls.slice(controls.indexOf('function scheduleMutes(){'),controls.indexOf('function updateLanePlayIcons')),ctx);
ctx.scheduleMutes();assert.equal(gainEvents[0].value,1,'Original gain must be audible inside unseparated overlap');
console.log('PASS: overlap original-mix gain remains audible');

vm.runInContext(app.split('\n').find(l=>l.startsWith('function seekTranscript(')),ctx);
vm.runInContext(app.split('\n').find(l=>l.startsWith("$('transcript-content').onclick=")),ctx);
let clickedSeek=null;ctx.seekTo=(seconds,play)=>{clickedSeek={seconds,play};};
elements['transcript-content'].onclick({target:{closest:selector=>selector==='.transcript-row'?{dataset:{start:'6.25'}}:null}});
assert.deepEqual(clickedSeek,{seconds:6.25,play:false});assert.equal(ctx.audio.paused,true);
clickedSeek=null;
elements['transcript-content'].onclick({target:{closest:selector=>selector==='.transcript-row'?{dataset:{start:'6.25'}}:{}}});
assert.equal(clickedSeek,null,'Timestamp buttons must not trigger a second seek');
ctx.audio.paused=false;
elements['transcript-content'].onclick({target:{closest:selector=>selector==='.transcript-row'?{dataset:{start:'6.25'}}:selector==='[data-part-start]'?{dataset:{partStart:'7.5'}}:null}});
assert.deepEqual(clickedSeek,{seconds:7.5,play:false});assert.equal(ctx.audio.paused,true,'Transcript navigation pauses existing playback');
const timestampClick=app.split('\n').find(l=>l.includes("if(button.matches('[data-seek]'))"));
ctx.button={matches:()=>true,dataset:{seek:'4'},closest:()=>({})};vm.runInContext(timestampClick,ctx);
assert.deepEqual(clickedSeek,{seconds:4,play:false},'Transcript timestamps seek without autoplay');
ctx.button.closest=()=>null;vm.runInContext(timestampClick,ctx);
assert.deepEqual(clickedSeek,{seconds:4,play:true},'Explicit reference/listen controls retain playback');
console.log('PASS: transcript text, fragments and timestamps seek without autoplay; explicit listen controls still play');

let followCalls=[];
const followedRow={dataset:{start:'2',end:'4'},classList:{toggle(){}},getBoundingClientRect:()=>({top:800,bottom:850})};
ctx.document.querySelectorAll=()=>[followedRow];ctx.modalVisible=()=>false;ctx.autoScroll=true;ctx.lastFollowedRow=null;ctx.selectedId='follow-test';ctx.window={matchMedia:()=>({matches:true})};
ctx.transcriptRowIndex=[];ctx.transcriptMaxEnds=[];ctx.highlightedRows=new Set();ctx.manualScrollUntil=0;ctx.performance={now:()=>100};
ctx.audio.currentTime=3;ctx.audio.paused=false;
elements['transcript-content']={scrollTop:0,getBoundingClientRect:()=>({top:200,bottom:500,height:300}),scrollTo:value=>followCalls.push(value)};
vm.runInContext(app.slice(app.indexOf('function indexTranscriptRows()'),app.indexOf('function updatePlayback()')),ctx);
ctx.indexTranscriptRows();ctx.markCurrentRow();assert.equal(followCalls.length,1);assert.ok(followCalls[0].top>0);
ctx.markCurrentRow();assert.equal(followCalls.length,1,'Repeated media updates must not keep scrolling the same answer');
ctx.autoScroll=false;ctx.lastFollowedRow=null;ctx.markCurrentRow();assert.equal(followCalls.length,1,'Auto-scroll off must leave the reader in control');
console.log('PASS: auto-scroll follows the active answer once and respects the off toggle');
ctx.recording={turns:[{speaker_id:'cached',start:0,end:5}]};
const cachedReview=ctx.speakerReviewTurns('cached');
assert.equal(ctx.speakerReviewTurns('cached'),cachedReview,'Repeated playback ticks reuse intervals');
ctx.recording={...ctx.recording,speaker_silences:{cached:[{start:1,end:2}]}};
assert.notEqual(ctx.speakerReviewTurns('cached'),cachedReview,'Saved edits invalidate cached review');
assert.equal(ctx.speakerReviewTurns('cached').length,2);
console.log('PASS: speaker review caches intervals and refreshes after recording edits');
// Repeated media ticks should not touch thousands of off-screen row classes.
let rowWrites=0;
const manyRows=Array.from({length:10000},(_,i)=>({dataset:{start:String(i*2),end:String(i*2+1)},classList:{toggle(){rowWrites++;}}}));
ctx.document.querySelectorAll=()=>manyRows;ctx.autoScroll=false;ctx.audio.currentTime=10000.5;ctx.highlightedRows=new Set();
ctx.indexTranscriptRows();ctx.markCurrentRow();
for(let i=0;i<100;i++)ctx.markCurrentRow();
assert.equal(rowWrites,1,'Stable playback ticks must update only the changed active row');
ctx.audio.currentTime=10002.5;ctx.markCurrentRow();assert.equal(rowWrites,3,'Only the previous/new row should change');
const nested=[{dataset:{start:'1',end:'10'},classList:{toggle(){}}},{dataset:{start:'2',end:'3'},classList:{toggle(){}}}];
ctx.document.querySelectorAll=()=>nested;ctx.indexTranscriptRows();ctx.audio.currentTime=2.5;ctx.markCurrentRow();assert.equal(ctx.highlightedRows.size,2,'Overlapping answers remain highlighted');
ctx.audio.currentTime=5;ctx.markCurrentRow();assert.equal(ctx.highlightedRows.size,1,'Nested intervals retain the longer active answer');
ctx.document.querySelectorAll=()=>[followedRow];ctx.indexTranscriptRows();ctx.highlightedRows=new Set();ctx.autoScroll=true;ctx.audio.currentTime=3;ctx.lastFollowedRow=null;
vm.runInContext(app.slice(app.indexOf('function pauseFollowForReading()'),app.indexOf("$('transcript-content').addEventListener('wheel'")),ctx);
const beforeManualFollow=followCalls.length;ctx.pauseFollowForReading();ctx.markCurrentRow();assert.equal(followCalls.length,beforeManualFollow,'Manual scrolling suspends auto-follow');
ctx.performance.now=()=>6000;ctx.markCurrentRow();assert.equal(followCalls.length,beforeManualFollow+1,'Follow resumes after the reading pause');
console.log('PASS: 10,000-row playback touches changed rows only, retains overlaps and respects manual scrolling');
// Speaker/text editor payload keeps assignment and name in one save.
const editNodes={
 'edit-overlap-texts':{innerHTML:'',querySelectorAll:()=>[]},'edit-text-label':{textContent:''},
 'edit-speaker':{value:'b'},'edit-speaker-name':{value:'Old name',disabled:false},
 'edit-overlap-fields':{classList:{toggle(){}}},'edit-overlap-speakers':{selectedOptions:[]},'edit-text':{value:'Reviewed text'}
};
const editorCtx=vm.createContext({$:id=>editNodes[id]||(editNodes[id]={}),speakerById:sid=>({a:{name:'Ana'},b:{name:'Ben'}}[sid]),editAnswer:{fingerprint:'f'.repeat(64),speaker_id:'a'},Array});
vm.runInContext(app.slice(app.indexOf('function updateEditorSpeaker(){'),app.indexOf('function openEditor(')),editorCtx);
editorCtx.updateEditorSpeaker();assert.equal(editNodes['edit-speaker-name'].value,'Ben','Choosing a different speaker loads that person’s name');
let editorPayload=JSON.parse(JSON.stringify(editorCtx.answerEditPayload()));
assert.equal(editorPayload.speaker_id,'b');assert.equal(editorPayload.speaker_name,'Ben');assert.equal(editorPayload.text,'Reviewed text');
editNodes['edit-speaker'].value='unknown';editorCtx.updateEditorSpeaker();assert.equal(editorCtx.answerEditPayload().speaker_name,null);
editNodes['edit-speaker'].value='__new__';editorCtx.updateEditorSpeaker();assert.equal(editNodes['edit-speaker-name'].disabled,false);
editNodes['edit-speaker-name'].value='Clara';assert.equal(editorCtx.answerEditPayload().speaker_name,'Clara');
editNodes['edit-speaker'].value='overlap';editorCtx.updateEditorSpeaker();editNodes['edit-overlap-speakers'].selectedOptions=[{value:'a'},{value:'b'}];
assert.deepEqual(JSON.parse(JSON.stringify(editorCtx.answerEditPayload().speaker_ids)),['a','b']);
console.log('PASS: grouped editor saves name, content, new-speaker and overlap selections atomically');

const overlapCtx=vm.createContext({recording:{segments:[],speakers:[{id:'a',name:'Ana'},{id:'b',name:'Ben'}],answer_groups:[{indices:[4],start:10,end:12,speaker_id:'overlap',speaker_ids:['a','b'],overlap:true,text:'Mixed hypothesis',speaker_texts:{a:'Hello.'}}]},speakerById:id=>overlapCtx.recording.speakers.find(s=>s.id===id)});
vm.runInContext(app.slice(app.indexOf('function transcriptDisplayRows(){'),app.indexOf('function renderTranscript(')),overlapCtx);
const simultaneous=JSON.parse(JSON.stringify(overlapCtx.transcriptDisplayRows()));
assert.equal(simultaneous.length,1);
assert.equal(simultaneous[0].seg.text,'Hello.');
assert.equal(simultaneous[0].seg.start,10);
assert.equal(simultaneous[0].seg.speaker_id,'a');
assert.ok(simultaneous.every(r=>r.index===4),'All display rows edit the same source overlap answer');
overlapCtx.recording.answer_groups[0].speaker_texts={};
overlapCtx.recording.answer_groups[0].overlap_sources=[{speaker_id:'a',source:0,text:'First voice.'},{speaker_id:'unknown',source:1,text:'Second voice.'}];
const recovered=JSON.parse(JSON.stringify(overlapCtx.transcriptDisplayRows()));
assert.deepEqual(recovered.map(r=>r.seg.start),[10,10]);
assert.deepEqual(recovered.map(r=>r.seg.text),['First voice.','Second voice.']);
assert.equal(recovered[1].seg.source_label,'Unidentified voice B');
assert.ok(recovered.every(r=>!r.seg.words_pending&&!r.seg.mixed_reference));
console.log('PASS: overlap shows actual source text only, shared timestamps and honest unknown labels');

let attachedHost=null,inlineRenders=0;
const inlineSection={classList:{add(){},remove(){}},setAttribute(){},removeAttribute(){},scrollIntoView(){}};
const inlineHome={querySelector:()=>inlineSection,appendChild(value){assert.equal(value,inlineSection);}};
const inlineControl={dataset:{editAnswer:'4'},closest:()=>({after(host){attachedHost=host;}})};
const inlineContent={querySelectorAll:()=>[inlineControl]};
const inlineCtx=vm.createContext({inlineEditorHost:null,readabilityRequest:0,editAnswer:{},recording:{},
 document:{createElement:()=>({appendChild(value){assert.equal(value,inlineSection);},querySelector:()=>inlineSection,remove(){attachedHost=null;}})},
 $:id=>id==='edit-backdrop'?inlineHome:inlineContent,renderRecording(){inlineRenders++;},indexTranscriptRows(){},Array,Number});
vm.runInContext(app.slice(app.indexOf('function showInlineEditor('),app.indexOf('function openSettings(')),inlineCtx);
assert.equal(inlineCtx.showInlineEditor(4),true);assert.ok(attachedHost);
inlineCtx.closeInlineEditor();assert.equal(attachedHost,null);assert.equal(inlineRenders,1);
assert.equal(inlineCtx.showInlineEditor(999),false);
console.log('PASS: inline editor mounts beside its answer and restores the same controls on close');
