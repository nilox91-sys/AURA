/* Shared Web Audio playback: unlock once, stream ordered chunks, cancel stale speech. */
(function (root) {
    'use strict';
    const clean = text => String(text).replace(/```[\s\S]*?```/g, ' Blocco di codice omesso. ')
        .replace(/\[([^\]]+)\]\(https?:\/\/[^)]+\)/g, '$1').replace(/https?:\/\/\S+/g, '')
        .replace(/[*_~`#>|[\]{}]/g, '').replace(/\s+/g, ' ').trim();
    function split(text, limit = 240) {
        const result = [];
        let rest = clean(text);
        if (rest.length > 24000) throw new Error('Risposta troppo lunga da leggere. Chiedi una sintesi.');
        while (rest.length > limit) {
            const head = rest.slice(0, limit);
            const endings = [...head.matchAll(/[.!?;。！？](?:\s|$)/g)];
            let cut = endings.filter(m => m.index >= limit / 3).at(-1)?.index;
            cut = cut === undefined ? head.lastIndexOf(' ', limit) : cut + 1;
            if (cut < 1) cut = limit;
            result.push(rest.slice(0, cut).trim());
            rest = rest.slice(cut).trim();
        }
        if (rest) result.push(rest);
        return result;
    }
    const aborted = () => new DOMException('Lettura interrotta', 'AbortError');
    class SpeechPlayer {
        constructor(settings = {}, onState = () => {}) {
            this.settings = settings; this.onState = onState;
            this.session = 0; this.sources = new Set(); this.waiters = new Set(); this.active = false;
        }
        async unlock() {
            this.context ||= new (root.AudioContext || root.webkitAudioContext)();
            let timer;
            try {
                await Promise.race([this.context.resume(), new Promise((_,reject) => {
                    timer = setTimeout(() => reject(new Error('Il browser non ha attivato l’audio. Riprova con un clic.')), 5000);
                })]);
            } finally { clearTimeout(timer); }
            if (this.context.state !== 'running') throw new Error('Attiva la voce con un clic e riprova.');
        }
        warm() {
            if (this.settings.tts_engine === 'qwen') {
                fetch('/api/voice/warm', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}).catch(() => {});
            }
        }
        emit(name, detail) { root.dispatchEvent(new CustomEvent(`jarvis:${name}`, {detail})); }
        stop() {
            this.session++; this.controller?.abort(); this.controller = null;
            for (const source of this.sources) { try { source.stop(); source.disconnect(); } catch (_) {} }
            this.sources.clear();
            for (const done of this.waiters) done();
            this.waiters.clear(); this.active = false; this.nextTime = 0;
            cancelAnimationFrame(this.frame); this.frame = null;
            this.emit('audio-level', {level:0}); this.emit('speaking', {state:false});
            this.onState('idle');
        }
        check(session) { if (session !== this.session) throw aborted(); }
        async queue(bytes, session, emotion) {
            this.check(session);
            const buffer = await this.context.decodeAudioData(bytes);
            this.check(session);
            // Backpressure keeps at most about six seconds scheduled in the browser.
            while (this.nextTime - this.context.currentTime > 6) {
                await new Promise(resolve => setTimeout(resolve, 80)); this.check(session);
                if (this.context.state !== 'running') throw new Error('Audio sospeso: riattiva la voce con un clic.');
            }
            this.analyser ||= this.context.createAnalyser();
            this.analyser.fftSize = 512;
            if (!this.connected) { this.analyser.connect(this.context.destination); this.connected = true; }
            const source = this.context.createBufferSource(); source.buffer = buffer;
            source.connect(this.analyser); this.sources.add(source);
            source.onended = () => {
                this.sources.delete(source); source.disconnect();
                if (!this.sources.size) { for (const done of this.waiters) done(); this.waiters.clear(); }
            };
            const time = Math.max(this.context.currentTime + .025, this.nextTime || 0);
            source.start(time); this.nextTime = time + buffer.duration;
            if (!this.frame) {
                this.onState('speaking'); this.emit('speaking', {state:true}); this.emit('emotion', {emotion});
                const samples = new Uint8Array(this.analyser.fftSize);
                const draw = () => {
                    if (session !== this.session) return;
                    this.analyser.getByteTimeDomainData(samples);
                    const energy = samples.reduce((sum, x) => sum + ((x - 128) / 128) ** 2, 0);
                    this.emit('audio-level', {level:Math.min(1, Math.sqrt(energy / samples.length) * 5)});
                    this.frame = requestAnimationFrame(draw);
                }; draw();
            }
        }
        async readStream(response, session, emotion) {
            if (!response.body) throw new Error('Il browser non supporta l’audio progressivo.');
            const reader = response.body.getReader(); const decoder = new TextDecoder();
            let pending = '', complete = false, count = 0;
            try {
                while (true) {
                    const {value, done} = await reader.read(); this.check(session);
                    if (done) break;
                    pending += decoder.decode(value, {stream:true});
                    if (pending.length > 4 * 1024 * 1024) throw new Error('Audio ricevuto non valido.');
                    let newline;
                    while ((newline = pending.indexOf('\n')) >= 0) {
                        const line = pending.slice(0, newline); pending = pending.slice(newline + 1);
                        if (!line) continue;
                        const event = JSON.parse(line);
                        if (event.event === 'error') throw new Error(event.error || 'Voce non disponibile.');
                        if (event.event === 'done') complete = true;
                        else if (event.event === 'audio' && !complete && typeof event.audio === 'string') {
                            const raw = atob(event.audio); count += raw.length;
                            if (count > 24 * 1024 * 1024) throw new Error('Audio troppo lungo.');
                            const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
                            await this.queue(bytes.buffer, session, emotion);
                        } else throw new Error('Sequenza audio non valida.');
                    }
                }
                if (!complete || pending.trim()) throw new Error('Audio interrotto. Riprova con il pulsante di lettura.');
            } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
        }
        async speak(text, emotion = 'normale') {
            this.stop(); const session = this.session;
            const engine = this.settings.tts_engine;
            const chunks = split(text, engine === 'irodori' ? 90 : engine === 'kokoro' ? 180 : 240);
            if (!chunks.length) return;
            this.active = true; const controller = new AbortController(); this.controller = controller;
            try {
                this.onState('preparing_voice');
                await this.unlock(); this.check(session);
                for (const chunk of chunks) {
                    this.check(session);
                    const timer = setTimeout(() => controller.abort(), engine === 'qwen' ? 400000 : 180000);
                    try {
                        const response = await fetch(engine === 'qwen' ? '/api/tts/stream' : '/api/tts', {
                            method:'POST', headers:{'Content-Type':'application/json'},
                            body:JSON.stringify({text:chunk, emotion}), signal:controller.signal
                        });
                        if (!response.ok) {
                            const data = await response.json().catch(() => ({}));
                            throw new Error(data.error || 'Voce non disponibile. Riprova.');
                        }
                        if (engine === 'qwen') await this.readStream(response, session, emotion);
                        else await this.queue(await response.arrayBuffer(), session, emotion);
                    } finally { clearTimeout(timer); }
                }
                this.check(session);
                if (this.sources.size) await new Promise(resolve => this.waiters.add(resolve));
                this.check(session);
            } catch (error) {
                if (session === this.session && controller.signal.aborted) throw new Error('La voce ha impiegato troppo tempo. Riprova la lettura.');
                throw error;
            } finally { if (session === this.session) this.stop(); }
        }
    }
    root.AuraSpeech = {SpeechPlayer, split, clean};
    if (typeof module !== 'undefined') module.exports = root.AuraSpeech;
})(typeof window !== 'undefined' ? window : globalThis);
