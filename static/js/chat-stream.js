/* One conversation stream for chat and voice room; reading never waits for speech. */
(function (root) {
    'use strict';
    async function readAnswer(response, onEvent, signal) {
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || `Risposta non disponibile (${response.status}).`);
        }
        if (!response.body) throw new Error('Il browser non supporta le risposte progressive.');
        const reader = response.body.getReader(), decoder = new TextDecoder();
        let pending = '', complete = false, result;
        async function line(value) {
            if (!value.trim()) return;
            if (complete) throw new Error('Dati ricevuti dopo la fine della risposta.');
            const event = JSON.parse(value);
            if (event.event === 'error') throw new Error(event.error || 'La risposta si è interrotta.');
            if (event.event === 'done') {
                if (event.status !== 'success' || typeof event.response !== 'string') throw new Error('Risposta finale non valida.');
                complete = true; result = event;
            } else if (!['start', 'delta'].includes(event.event)) throw new Error('Sequenza della risposta non valida.');
            if (event.event === 'delta' && typeof event.text !== 'string') throw new Error('Testo ricevuto non valido.');
            await onEvent(event);
        }
        try {
            while (true) {
                const {value, done} = await reader.read();
                if (signal?.aborted) throw new DOMException('Risposta annullata', 'AbortError');
                if (done) break;
                pending += decoder.decode(value, {stream:true});
                if (pending.length > 1024 * 1024) throw new Error('Risposta troppo grande.');
                let newline;
                while ((newline = pending.indexOf('\n')) >= 0) {
                    const value = pending.slice(0, newline); pending = pending.slice(newline + 1);
                    await line(value);
                }
            }
            pending += decoder.decode();
            if (pending.trim()) await line(pending);
            if (!complete) throw new Error('La risposta si è interrotta prima della fine. Riprova.');
            return result;
        } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
    }
    root.AuraChat = {readAnswer};
    if (typeof module !== 'undefined') module.exports = root.AuraChat;
})(typeof window !== 'undefined' ? window : globalThis);
