const {test} = require('node:test');
const assert = require('node:assert/strict');
const {SpeechPlayer, split, clean} = require('../static/js/speech-player.js');
global.CustomEvent = class {constructor(type, data) {this.type=type;this.detail=data.detail;}};
global.dispatchEvent = () => {};
global.requestAnimationFrame = () => 1;global.cancelAnimationFrame = () => {};
class Context {
    constructor() {this.state='suspended';this.currentTime=0;this.destination={};this.played=0;}
    async resume() {this.state='running';}
    async decodeAudioData(bytes) {assert.ok(bytes.byteLength);return {duration:.002};}
    createAnalyser() {return {connect(){},getByteTimeDomainData(a){a.fill(128);}};}
    createBufferSource() {
        const ctx=this;
        return {connect(){},disconnect(){},start(){ctx.played++;setImmediate(()=>this.onended?.());},stop(){this.onended?.();}};
    }
}
global.AudioContext=Context;
function streamed(events) {
    const bytes=new TextEncoder().encode(events.map(e=>JSON.stringify(e)+'\n').join(''));
    // Deliberately split through the JSON and UTF-8 boundaries.
    return {ok:true,body:new ReadableStream({start(c){for(let i=0;i<bytes.length;i+=7)c.enqueue(bytes.slice(i,i+7));c.close();}})};
}
const audio={event:'audio',audio:Buffer.from('wave data').toString('base64')};
test('long replies are segmented without dropping dialect or the tail',()=>{
    const text="Aggio capito. ".repeat(300)+"Chesta è l'urdema frase.";
    const chunks=split(text,180);
    assert.ok(chunks.every(c=>c.length<=180));assert.equal(chunks.join(' '),clean(text));
    assert.ok(chunks.at(-1).endsWith("Chesta è l'urdema frase."));
});
test('code and links are not spelled out; labels remain',()=>{
    assert.equal(clean('Guarda [il sito](https://example.com) e `API`.\n```py\na=1\n```'), 'Guarda il sito e API. Blocco di codice omesso.');
});
test('streamed audio plays through one unlocked context in order',async()=>{
    const states=[];const player=new SpeechPlayer({tts_engine:'qwen'},s=>states.push(s));
    await player.unlock();
    global.fetch=async()=>{assert.equal(player.context.state,'running');return streamed([audio,audio,{event:'done'}]);};
    await player.speak('Jamme.');
    assert.equal(player.context.played,2);assert.equal(player.active,false);
    assert.ok(states.includes('speaking'));assert.equal(states.at(-1),'idle');
});
test('cancel prevents late audio from an abandoned response',async()=>{
    const player=new SpeechPlayer({tts_engine:'qwen'});
    let deliver;
    global.fetch=()=>new Promise(resolve=>{deliver=resolve;});
    const pending=player.speak('Prima frase.');await new Promise(r=>setImmediate(r));
    player.stop();deliver(streamed([audio,{event:'done'}]));
    await assert.rejects(pending,{name:'AbortError'});assert.equal(player.context.played,0);
});
test('a truncated stream fails explicitly and leaves playback retryable',async()=>{
    const player=new SpeechPlayer({tts_engine:'qwen'});
    global.fetch=async()=>streamed([audio]);
    await assert.rejects(player.speak('Prima frase.'),/Audio interrotto/);
    assert.equal(player.active,false);
    global.fetch=async()=>streamed([audio,{event:'done'}]);
    await player.speak('Seconda frase.');assert.equal(player.active,false);
});
test('provider failures do not silently change the selected voice',async()=>{
    const player=new SpeechPlayer({tts_engine:'qwen'});const paths=[];
    global.fetch=async path=>{paths.push(path);return streamed([{event:'error',error:'Riprova'}]);};
    await assert.rejects(player.speak('Jamme.'),/Riprova/);assert.deepEqual(paths,['/api/tts/stream']);
});
