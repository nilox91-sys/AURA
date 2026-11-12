const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
const code=fs.readFileSync(require.resolve('../static/js/voice-room.js'),'utf8');
const tick=()=>new Promise(r=>setImmediate(r));
function harness({denied=false, unsupported=false, delayed=false}={}) {
    const elements={};const callbacks={};const calls=[];const recognitions=[];
    const element=id=>elements[id]||=( {textContent:'',disabled:false,hidden:false,dataset:{},addEventListener(event,fn){this[event]=fn;}} );
    const media={stopped:0};let deliver;
    class Recognition {constructor(){recognitions.push(this);}start(){this.started=true;}abort(){this.stopped=true;}}
    class Player {constructor(settings,callback){this.callback=callback;}warm(){}async unlock(){}stop(){}async speak(){this.callback('speaking');}}
    const window={AURA_SETTINGS:{dialect:'napoletano'},AuraSpeech:{SpeechPlayer:Player},SpeechRecognition:unsupported?undefined:Recognition,
        dispatchEvent(){},addEventListener(event,fn){callbacks[event]=fn;}};
    const document={hidden:false,querySelector:()=>element('room'),getElementById:element,addEventListener(event,fn){callbacks[event]=fn;}};
    const fetch=async(path,opts)=>{
        calls.push([path,JSON.parse(opts.body)]);
        if(delayed)return new Promise(resolve=>{deliver=resolve;});
        return {ok:true,json:async()=>({status:'success',response:'Jamme.',emozione:'felice'})};
    };
    vm.runInNewContext(code,{window,document,navigator:{mediaDevices:{getUserMedia:async()=>{
        if(denied)throw new Error('denied');return {getTracks:()=>[{stop(){media.stopped++;}}]};
    }}},fetch,CustomEvent:class{},AbortController,setTimeout,clearTimeout});
    return {elements,calls,recognitions,media,callbacks,get deliver(){return deliver;}};
}
test('voice turn resumes listening, sends no history request, and needs no wake word',async()=>{
    const h=harness();await h.elements['room-start'].click();await tick();
    assert.equal(h.media.stopped,1);assert.equal(h.elements.room.dataset.phase,'listening');
    const result=[{transcript:'Spiegami una cache'}];result.isFinal=true;
    h.recognitions[0].onresult({results:[result]});await tick();await tick();
    assert.equal(h.recognitions.length,2);assert.equal(h.elements.room.dataset.phase,'listening');
    assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],'/api/chat');
    assert.equal(h.calls[0][1].mode,'voice');
    await h.elements['room-start'].click();assert.equal(h.elements.room.dataset.phase,'idle');
    assert.equal(h.recognitions.at(-1).stopped,true);
});
test('denied microphone leaves a clear retry and does not call AI',async()=>{
    const h=harness({denied:true});await h.elements['room-start'].click();await tick();
    assert.match(h.elements['room-status'].textContent,/microfono/);assert.equal(h.elements['room-start'].disabled,false);
    assert.equal(h.calls.length,0);
});
test('stopping a pending answer prevents late playback and microphone restart',async()=>{
    const h=harness({delayed:true});await h.elements['room-start'].click();await tick();
    const result=[{transcript:'Ciao'}];result.isFinal=true;
    h.recognitions[0].onresult({results:[result]});await tick();
    await h.elements['room-start'].click();h.deliver({ok:true,json:async()=>({status:'success',response:'Jamme.'})});
    await tick();await tick();assert.equal(h.recognitions.length,1);assert.equal(h.elements.room.dataset.phase,'idle');
});
test('unsupported browsers expose an explanation instead of a broken control',()=>{
    const h=harness({unsupported:true});assert.equal(h.elements['room-start'].disabled,true);
    assert.match(h.elements['room-status'].textContent,/Chrome o Edge/);
});
