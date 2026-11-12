(() => {
    'use strict';
    const form = document.getElementById('settings-form');
    if (!form) return;
    const settings = window.AURA_SETTINGS || {}, profiles = window.AURA_DIALECTS || {}, providers = window.AURA_PROVIDERS;
    const node = id => document.getElementById(id), value = id => node(id).value.trim();
    const state = node('save-state'); let previewRun = 0, saving;
    const previewPlayer = new window.AuraSpeech.SpeechPlayer(settings, status => {
        node('stop-preview').hidden = !previewPlayer.active;
        if (status === 'speaking') node('voice-preview-state').textContent = 'Ascolto della voce selezionata.';
    });
    function saveState(label,kind='') {state.className='save-state '+kind;state.querySelector('span').textContent=label;}
    const fields = [...form.querySelectorAll('input[data-setting],select[data-setting],textarea[data-setting]')];
    const secret = key => key.endsWith('_api_key');
    function fill(preferences) {
        for (const el of fields) {
            const key=el.dataset.setting;
            if (!(key in preferences) || secret(key)) continue;
            if (el.type==='checkbox') el.checked=preferences[key];
            else if (el.tagName==='SELECT' && ![...el.options].some(o=>o.value===String(preferences[key]))) {
                const option=new Option('Personale · '+preferences[key],preferences[key]);el.add(option);el.value=preferences[key];
            } else el.value=preferences[key];
        }
    }
    // Keep the avatar controls already chosen on this browser when migrating.
    if (localStorage.getItem('jarvis.avatar.paused')!==null) node('avatar-motion').checked=localStorage.getItem('jarvis.avatar.paused')!=='true';
    if (localStorage.getItem('jarvis.avatar.closeup')!==null) node('avatar-framing').value=localStorage.getItem('jarvis.avatar.closeup')==='false'?'full':'portrait';
    function tab(id) {
        if (!document.getElementById(id)?.classList.contains('settings-panel')) id='connessione';
        for (const el of document.querySelectorAll('.settings-panel')) el.hidden=el.id!==id;
        for (const el of document.querySelectorAll('[data-tab]')) {el.classList.toggle('active',el.dataset.tab===id);if(el.dataset.tab===id)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');}
    }
    window.addEventListener('hashchange',()=>tab(location.hash.slice(1)));tab(location.hash.slice(1));
    const modelValues={};let selected='';
    function chooseProvider() {
        if (selected) modelValues[selected]=value('model-id');
        selected=value('connection-provider');
        for(const el of document.querySelectorAll('[data-provider]'))el.hidden=el.dataset.provider!==selected;
        node('model-controls').hidden=selected==='auto';
        node('model-id').value=modelValues[selected]??providers[selected]?.default??'';
        node('model-catalog').replaceChildren();node('connection-result').textContent='';
        node('model-note').textContent='Verifica per leggere il catalogo, oppure inserisci un identificativo. Il catalogo non garantisce quote o permessi di generazione.';
    }
    function setModel(model) {
        const pos=model.indexOf(':');let provider=pos<0?'huggingface':model.slice(0,pos);
        if(provider==='hf')provider='huggingface';
        if(!providers[provider])provider='auto';
        selected='';node('connection-provider').value=provider;
        modelValues[provider]=pos<0?model:model.slice(pos+1);chooseProvider();
    }
    setModel(settings.model);node('connection-provider').addEventListener('change',chooseProvider);
    function payload() {
        const result={};
        for (const el of fields) result[el.dataset.setting]=el.type==='checkbox'?el.checked:el.type==='number'?Number(el.value):el.value.trim();
        result.voice_pitch_hz=Number(value('voice-pitch-hz'));result.voice_rate_percent=Number(value('voice-rate-percent'));
        const model=value('model-id')||providers[selected]?.default;
        result.model=selected==='auto'?'auto:free':model?selected+':'+model:settings.model;
        return result;
    }
    async function request(url,data,timeout=40000) {
        const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:AbortSignal.timeout(timeout)});
        const body=await res.json();if(!res.ok)throw new Error(body.error||body.message||'Operazione non riuscita.');return body;
    }
    async function saveForm() {
        if(saving)return saving;
        // Validate hidden panels too, then bring the invalid field into view.
        for(const el of fields) if(!el.checkValidity()) {tab(el.closest('.settings-panel').id);el.reportValidity();return false;}
        saving=(async()=>{
            const button=form.querySelector('[type="submit"]');button.disabled=true;saveState('Salvataggio…');
            try {
                const data=await request('/api/save_settings',payload());Object.assign(settings,data.settings);
                for(const el of fields.filter(el=>secret(el.dataset.setting))) {el.value='';el.placeholder=data.settings.secrets_configured[el.dataset.setting]?'Già configurata · lascia vuoto per conservarla':'Non configurata';}
                localStorage.setItem('jarvis.avatar.paused',String(!settings.avatar_motion));localStorage.setItem('jarvis.avatar.closeup',String(settings.avatar_framing==='portrait'));
                document.body.dataset.theme=settings.theme;saveState('Tutto salvato','saved');return true;
            } catch(error) {saveState(error.message,'error');return false;}
            finally {button.disabled=false;}
        })();try{return await saving;}finally{saving=null;}
    }
    function updatePreview() {
        const dialect=value('selected-dialect'),intensity=value('dialect-intensity');node('dialect-intensity').disabled=dialect==='standard';
        node('dialect-preview-text').textContent=profiles[dialect]?.previews?.[intensity]||(dialect==='standard'?'Ciao, sono Aura. Vediamo da dove iniziare, un passo alla volta.':'Il registro scelto verrà applicato alle prossime risposte.');
    }
    function updatePersonaPreview() {
        const name=value('assistant-name')||'AURA',profile=value('personality-profile');node('nerd-intensity').disabled=profile!=='cozy_nerd';
        node('identity-name').textContent=name;node('identity-initial').textContent=name[0].toUpperCase();node('identity-tagline').textContent=value('assistant-tagline');
        node('persona-preview-text').textContent={cozy_nerd:'Ci sto. Facciamo un po’ di debug dell’idea: qual è il primo pezzo da far funzionare?',neutral:'Vediamo obiettivo e vincoli, poi scegliamo il primo passo utile.',creative:'E se provassimo due strade diverse? Facciamo un piccolo esperimento.',mentor:'Partiamo da un esempio semplice, poi aggiungiamo un passaggio alla volta.'}[profile];
    }
    for(const id of ['selected-dialect','dialect-intensity'])node(id).addEventListener('change',updatePreview);
    for(const id of ['assistant-name','assistant-tagline','personality-profile','nerd-intensity'])node(id).addEventListener('input',updatePersonaPreview);
    node('theme').addEventListener('change',()=>{document.body.dataset.theme=value('theme');});
    updatePreview();updatePersonaPreview();
    const voicePresets = {
        irodori: {'tts-engine':'irodori','irodori-reading':'kana'},
        qwen: {'tts-engine':'qwen','qwen-voice-style':'anime'},
        hiyori: {'tts-engine':'kokoro','local-voice-style':'hiyori','voice-name':'it-IT-ElsaNeural','voice-pitch-hz':'0','voice-rate-percent':'0','voice-character':'soft','voice-effect':'none'},
        hiyori_soft: {'tts-engine':'kokoro','local-voice-style':'hiyori_soft','voice-name':'it-IT-ElsaNeural','voice-pitch-hz':'0','voice-rate-percent':'0','voice-character':'soft','voice-effect':'none'},
        edge: {'tts-engine':'edge','local-voice-style':'hiyori','voice-name':'it-IT-ElsaNeural','voice-pitch-hz':'0','voice-rate-percent':'0','voice-character':'soft','voice-effect':'none'},
        isabella: {'tts-engine':'edge','local-voice-style':'hiyori','voice-name':'it-IT-IsabellaNeural','voice-pitch-hz':'4','voice-rate-percent':'-4','voice-character':'cozy','voice-effect':'none'}
    };
    function updateVoiceControls() {
        const engine = value('tts-engine');
        node('local-voice-style').disabled = engine !== 'kokoro';
        node('qwen-controls').hidden = engine !== 'qwen';
        node('irodori-controls').hidden = engine !== 'irodori';
        node('qwen-voice-style').disabled = engine !== 'qwen';
        node('irodori-reading').disabled = engine !== 'irodori';
        for (const id of ['voice-name','voice-pitch-hz','voice-character','voice-effect']) node(id).disabled = engine !== 'edge';
        node('voice-rate-percent').disabled = engine === 'qwen';
        node('voice-engine-note').textContent = {
            edge:'Le voci italiane precedenti, con tutti i controlli di timbro e intonazione.',
            kokoro:'Voce sul PC, leggera e senza quota online.',
            qwen:'Italiano sul PC con timbro anime e audio progressivo. AURA prepara la voce all’avvio.',
            irodori:'Anime giapponese sperimentale. Richiede il token Hugging Face indicato sotto e una quota disponibile.'
        }[engine];
    }
    function reflectVoicePreset() {
        updateVoiceControls();
        const match = Object.entries(voicePresets).find(([,fields]) =>
            Object.entries(fields).every(([id,setting]) => value(id) === setting));
        node('voice-preset').value = match?.[0] || 'custom';
        node('voice-preset-note').textContent = match
            ? 'Profilo selezionato. Salva e ascolta per provarlo.'
            : 'Regolazione personale. Puoi richiamare un profilo oppure salvare questi valori.';
    }
    node('voice-preset').addEventListener('change', () => {
        const fields = voicePresets[value('voice-preset')];
        if (!fields) {
            node('voice-preset-note').textContent = 'Regola voce, intonazione, velocità e timbro come preferisci, poi salva o ascolta.';
            return;
        }
        for (const [id,setting] of Object.entries(fields)) node(id).value = setting;
        saveState('Profilo pronto · salva o ascolta', 'dirty');
        reflectVoicePreset();
    });
    for (const id of new Set(Object.values(voicePresets).flatMap(fields => Object.keys(fields)))) node(id).addEventListener('change', reflectVoicePreset);
    reflectVoicePreset();


    form.addEventListener('input',()=>saveState('Modifiche da salvare','dirty'));
    form.addEventListener('submit',async event=>{event.preventDefault();await saveForm();});
    async function providerAction(test) {
        const output=node('connection-result'),button=node(test?'test-provider':'verify-provider');button.disabled=true;
        try {
            if(test && !value('model-id'))throw new Error('Scegli prima il modello da provare.');
            if(!await saveForm())return;
            output.dataset.state='loading';output.textContent=test?'Provo una breve risposta…':'Verifico il collegamento…';
            const result=await request(test?'/api/integrations/test':'/api/integrations/check',{provider:selected,model:value('model-id')});
            output.dataset.state=result.state==='not_configured'?'error':'success';output.textContent=result.message+(result.latency_ms?' · '+(result.latency_ms/1000).toFixed(1)+' s':'');
            if(result.models) {
                node('model-catalog').replaceChildren(...result.models.map(model=>new Option(model,model)));
                node('model-note').textContent=result.models.length+' modelli nel catalogo. Digita per cercare; puoi scrivere anche un altro identificativo.';
                if(!value('model-id') && result.models.length){node('model-id').value=result.models[0];saveState('Modello trovato · salva per usarlo','dirty');}
            }
        }catch(error){output.dataset.state='error';output.textContent=error.name==='TimeoutError'?'Il servizio ha impiegato troppo tempo. Riprova.':error.message;}
        finally{button.disabled=false;}
    }
    node('verify-provider').addEventListener('click',()=>providerAction(false));node('test-provider').addEventListener('click',()=>providerAction(true));
    for(const button of document.querySelectorAll('[data-remove-key]'))button.addEventListener('click',async()=>{
        button.disabled=true;try{const provider=button.dataset.removeKey;const data=await request('/api/integrations/remove-key',{provider});const input=node(providers[provider].key.replaceAll('_','-'));input.value='';input.placeholder=data.environment_key_present?'Chiave presente nella configurazione .env':'Non configurata';saveState(data.environment_key_present?'Chiave locale rimossa; resta quella del file .env':'Chiave rimossa','saved');}catch(error){saveState(error.message,'error');}finally{button.disabled=false;}
    });
    node('export-preferences').addEventListener('click',async()=>{if(await saveForm())location.href='/api/preferences/export';});
    const excluded=key=>secret(key)||key.startsWith('github_')||key==='schema_version';
    node('import-preferences').addEventListener('change',async event=>{
        const file=event.target.files[0];if(!file)return;
        try {
            if(file.size>65536)throw new Error('Il file supera 64 KB.');
            const data=JSON.parse(await file.text());if(data.format!=='aura-preferences'||data.version!==1||!data.preferences||Array.isArray(data.preferences))throw new Error('File di preferenze AURA non valido.');
            const accepted={};for(const [key,val]of Object.entries(data.preferences))if(!excluded(key)&&key in window.AURA_DEFAULTS&&typeof val===typeof window.AURA_DEFAULTS[key])accepted[key]=val;
            fill(accepted);if(accepted.model)setModel(accepted.model);updatePreview();updatePersonaPreview();reflectVoicePreset();document.body.dataset.theme=value('theme');saveState('Preferenze importate · controlla e salva','dirty');
        }catch(error){saveState(error.message,'error');}finally{event.target.value='';}
    });
    node('reset-preferences').addEventListener('click',()=>{const defaults=Object.fromEntries(Object.entries(window.AURA_DEFAULTS).filter(([key])=>!excluded(key)));fill(defaults);setModel(defaults.model);updatePreview();updatePersonaPreview();reflectVoicePreset();document.body.dataset.theme=value('theme');saveState('Valori iniziali pronti · salva per applicarli','dirty');});
    async function cacheInfo(clear=false) {
        try {const data=clear?await request('/api/audio-cache',{}):await (await fetch('/api/audio-cache')).json();node('cache-state').textContent=(data.bytes/1048576).toFixed(1)+' MB · '+data.files+' file';}catch(error){node('cache-state').textContent=error.message;}
    }
    node('clear-audio-cache').addEventListener('click',()=>cacheInfo(true));cacheInfo();
    window.AuraAccount?.init(saveForm);
    function stopPreview() {
        previewRun++; previewPlayer.stop();
        node('stop-preview').hidden = true;
    }
    node('stop-preview').addEventListener('click', () => {
        stopPreview(); node('voice-preview-state').textContent = 'Ascolto interrotto.';
    });
    node('preview-voice').addEventListener('click', async event => {
        const button = event.currentTarget;
        button.disabled = true; stopPreview(); const current = previewRun;
        try {
            await previewPlayer.unlock();
            if (!await saveForm() || current !== previewRun) return;
            node('stop-preview').hidden = false;
            node('voice-preview-state').textContent = 'Preparo la voce selezionata…';
            const text = value('selected-dialect') === 'napoletano'
                ? "Uè, so' Aura. Dimme che vuò fa': ce pensammo 'nzieme."
                : 'Ehi, sono Aura! Hai una nuova idea? Raccontamela, sono curiosa.';
            await previewPlayer.speak(text, 'normale');
            if (current === previewRun) node('voice-preview-state').textContent = 'Prova completata.';
        } catch (error) {
            if (current !== previewRun || error.name === 'AbortError') return;
            node('voice-preview-state').textContent = error.message;
            window.showToast?.(error.message, 'error');
        } finally { button.disabled = false; }
    });
    window.addEventListener('pagehide', stopPreview, {once:true});
})();
