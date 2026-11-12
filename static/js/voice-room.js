(() => {
    'use strict';
    const settings = window.AURA_SETTINGS || {};
    const room = document.querySelector('.voice-room');
    const status = document.getElementById('room-status');
    const hint = document.getElementById('room-hint');
    const start = document.getElementById('room-start');
    const interrupt = document.getElementById('room-interrupt');
    const retry = document.getElementById('room-retry');
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let active = false, phase = 'idle', recognition, restart, run = 0, controller, lastReply;
    const emit = (name, detail) => window.dispatchEvent(new CustomEvent(`jarvis:${name}`, {detail}));
    function state(next, message, detail = '') {
        phase = next; room.dataset.phase = next; status.textContent = message; hint.textContent = detail;
        interrupt.hidden = !active || !['thinking','preparing_voice','speaking'].includes(next);
        emit('state', {state:next});
    }
    const player = new window.AuraSpeech.SpeechPlayer(settings, next => {
        if (!active || next === 'idle') return;
        if (next === 'speaking') state(next, 'Ti rispondo.', 'Puoi interrompermi per riprendere la parola.');
        else state(next, 'Preparo la voce…', settings.tts_engine === 'qwen' ? 'Al primo avvio preparo il modello, poi la voce arriva progressivamente.' : 'Tra un momento ti rispondo.');
    });
    player.warm();
    function stopRecognition() {
        clearTimeout(restart);
        const old = recognition; recognition = null;
        if (old) { old.onend = old.onresult = old.onerror = null; try { old.abort(); } catch (_) {} }
    }
    function stop(message = 'Ci sono, quando vuoi.') {
        active = false; run++; controller?.abort(); controller = null;
        stopRecognition(); player.stop();
        start.textContent = 'Avvia voce ♪'; start.disabled = false;
        state('idle', message, 'Il microfono è spento.');
    }
    function fail(message) { stop(message); if (lastReply) retry.hidden = false; }
    function listen() {
        if (!active || document.hidden) return;
        stopRecognition();
        state('listening', 'Ti ascolto.', 'Parla normalmente. Non serve dire “Aura” a ogni turno.');
        const current = run; const rec = new Recognition(); recognition = rec;
        // Italian recognition understands much Neapolitan, but is not a native dialect model.
        rec.lang = settings.dialect === 'giapponese' ? 'ja-JP' : settings.dialect === 'coreano' ? 'ko-KR' : 'it-IT';
        rec.continuous = false; rec.interimResults = false; rec.maxAlternatives = 1;
        rec.onresult = event => {
            if (!active || current !== run || recognition !== rec) return;
            const text = Array.from(event.results).filter(result => result.isFinal).map(result => result[0].transcript).join(' ').trim();
            if (text) { stopRecognition(); answer(text, current); }
        };
        rec.onerror = event => {
            if (!active || current !== run) return;
            if (['no-speech','aborted'].includes(event.error)) return;
            const messages = {'not-allowed':'Consenti il microfono nel browser e riavvia la voce.',
                'service-not-allowed':'Il servizio vocale del browser non è disponibile.',
                'audio-capture':'Non trovo un microfono. Controlla il collegamento.',
                network:'Il riconoscimento vocale non è disponibile. Controlla la connessione o prova Chrome/Edge.'};
            fail(messages[event.error] || 'Non riesco ad ascoltare. Riavvia la voce.');
        };
        rec.onend = () => {
            if (recognition === rec) recognition = null;
            if (active && current === run && phase === 'listening') restart = setTimeout(listen, 450);
        };
        try { rec.start(); } catch (_) { fail('Il microfono non è pronto. Riavvia la voce.'); }
    }
    async function say(reply, current) {
        retry.hidden = true; lastReply = reply;
        try {
            await player.speak(reply.text, reply.emotion);
            if (active && current === run) { if (settings.voice_auto_listen === false) stop('Quando vuoi, avvia di nuovo la voce.'); else listen(); }
        } catch (error) {
            if (current !== run || error.name === 'AbortError') return;
            fail(error.message || 'La voce non è partita. Puoi riascoltare la risposta.');
        }
    }
    async function answer(text, current) {
        lastReply = null;
        state('thinking', 'Ci penso…', 'Metto insieme le idee.');
        const requestController = new AbortController(); controller = requestController;
        const timeout = setTimeout(() => requestController.abort(), ((settings.ai_timeout_seconds || 65) + 20) * 1000);
        const signal = requestController.signal;
        let liveSpeech = null, speechFailure = null;
        try {
            const response = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({message:text,mode:'voice',stream:true}), signal});
            const data = await window.AuraChat.readAnswer(response, event => {
                if (!active || current !== run || event.event !== 'delta' || speechFailure) return;
                if (!liveSpeech) {
                    liveSpeech = player.startStream(event.emozione || 'normale');
                    liveSpeech.done.catch(error => { speechFailure = error; });
                }
                try { liveSpeech.append(event.text, event.emozione || 'normale'); }
                catch (error) { speechFailure = error; }
            }, signal);
            if (!active || current !== run) return;
            // AI timeout covers generation only; playback has its own per-segment deadline.
            clearTimeout(timeout);
            lastReply = {text:data.response, emotion:data.emozione || 'normale'};
            retry.hidden = true;
            if (speechFailure) throw speechFailure;
            if (!liveSpeech) throw new Error('Non ho ricevuto testo da leggere. Riprova.');
            await liveSpeech.finish();
            if (active && current === run) {
                if (settings.voice_auto_listen === false) stop('Quando vuoi, avvia di nuovo la voce.'); else listen();
            }
        } catch (error) {
            liveSpeech?.cancel();
            if (active && current === run) fail(error.name === 'AbortError' ? 'La risposta ha impiegato troppo tempo. Riprova.' : error.message);
        } finally { clearTimeout(timeout); }
    }
    async function begin(replay = false) {
        if (active) { stop(); return; }
        if (!Recognition) { fail('Questo browser non supporta la conversazione vocale. Apri AURA in Chrome o Edge.'); return; }
        active = true; const current = ++run;
        start.textContent = 'Annulla avvio';
        state('starting', 'Attivo il microfono…', 'Se il browser lo chiede, consenti l’accesso al microfono.');
        try {
            await player.unlock();
            if (!active || current !== run) return;
            const stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
            stream.getTracks().forEach(track => track.stop());
            if (!active || current !== run) return;
            start.disabled = false; start.textContent = 'Termina voce';
            if (replay && lastReply) await say(lastReply,current); else if (settings.voice_greeting) { await say({text:settings.welcome_message || 'Ciao, sono '+settings.assistant_name+'. Da dove iniziamo?',emotion:'normale'},current); } else { retry.hidden = true; listen(); }
        } catch (_) { if (current === run) fail('Non posso usare il microfono. Consenti l’accesso nel browser e riprova.'); }
    }
    start.addEventListener('click', () => begin());
    retry.addEventListener('click', () => begin(true));
    interrupt.addEventListener('click', async () => {
        if (!active) return;
        run++; controller?.abort(); stopRecognition(); player.stop();
        try { await player.unlock(); listen(); } catch (_) { fail('Riattiva la voce con un clic.'); }
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') stop(); });
    document.addEventListener('visibilitychange', () => { if (document.hidden && active) stop('Conversazione in pausa.'); });
    window.addEventListener('pagehide', () => stop(), {once:true});
    if (!Recognition) { state('idle','Apri questa stanza in Chrome o Edge.','Il tuo browser non offre il riconoscimento vocale necessario.'); start.disabled = true; }
})();
