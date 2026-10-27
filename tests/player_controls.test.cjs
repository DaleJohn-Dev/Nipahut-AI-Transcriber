// Exercise the actual transport handlers with a deterministic media element.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const app = fs.readFileSync('static/app.js', 'utf8');
const controls = fs.readFileSync('static/clip-controls.js', 'utf8');
const elements = {};
const sample = {dataset:{playSpeaker:'s1'}, attrs:{}, querySelector(){return {getAttribute:()=>this.href,setAttribute:(_,v)=>this.href=v};},setAttribute(k,v){this.attrs[k]=v;}};
const ctx = vm.createContext({console,document:{querySelectorAll:()=>[sample]},
  $:id=>elements[id]??=( {} ), recording:{duration:100},
  activeSampleSpeaker:null,activePlaybackSpeaker:null,sampleEnd:null,
  speakerById:()=>({id:'s1',name:'Alice',sample_start:5,sample_end:8}),
  audio:{currentTime:0,paused:true,play(){this.paused=false;return Promise.resolve();},pause(){this.paused=true;}},
  ensureAudioGraph(){},renderSpectrum(){},handleError(e){throw e;},updatePlayback(){ctx.updateSamplePlayIcons();}});
vm.runInContext(controls,ctx);
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
ctx.advanceSpeakerPlayback();assert.ok(ctx.audio.currentTime>4&&ctx.audio.currentTime<6);
console.log('PASS: solo review excludes overlap, other speakers and silence edits; skips to next solo section');
