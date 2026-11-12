document.addEventListener('DOMContentLoaded', () => {
    'use strict';

    const settings = window.AURA_SETTINGS || window.NEXUS_SETTINGS || {};
    const toastStack = document.getElementById('toast-stack');
    const voiceToggle = document.getElementById('voice-enable');

    window.showToast = (message, type = 'info') => {
        if (!toastStack) return;
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        toastStack.appendChild(toast);
        window.setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(12px)';
            window.setTimeout(() => toast.remove(), 180);
        }, 3200);
    };

    let voiceEnabled = (localStorage.getItem('aura.voice') ?? localStorage.getItem('nexus.voice')) !== 'off';
    if (voiceToggle) {
        voiceToggle.checked = voiceEnabled;
        voiceToggle.addEventListener('change', () => {
            voiceEnabled = voiceToggle.checked;
            localStorage.setItem('aura.voice', voiceEnabled ? 'on' : 'off');
            const voiceState = document.getElementById('voice-state');
            if (voiceState) voiceState.textContent = voiceEnabled ? 'Voce attiva' : 'Voce disattivata';
            if (!voiceEnabled && chatMessages) stopCurrentAudio();
        });
    }

    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;

    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-btn');
    const micButton = document.getElementById('mic-btn');
    const micVisualizer = document.getElementById('mic-visualizer');
    const clearButton = document.getElementById('clear-chat');
    const exportButton = document.getElementById('export-chat');
    const wakeIndicator = document.getElementById('wake-indicator');
    const coreStage = document.getElementById('core-stage');
    const coreState = document.getElementById('core-state');
    const memoryCount = document.getElementById('memory-count');
    const modelStatus = document.getElementById('model-status');
    const voiceModule = document.getElementById('voice-module');
    const wakeStatus = document.getElementById('wake-status');
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const isSecureContextForMic = window.isSecureContext || ['localhost', '127.0.0.1'].includes(location.hostname);

    let chatHistory = [];
    let requestInFlight = false;
    let audioContext = null;
    let isSpeaking = false;
    let isManualListening = false;
    let wakeRecognition = null;
    let commandRecognition = null;
    let wakeRestartTimer = null;
    let microphoneStream = null;
    let visualizerFrame = null;
    let microphoneContext = null;
    let microphoneSession = 0;
    let microphoneDenied = false;
    const stopAudioButton = document.getElementById('stop-audio');
    const emit = (name, detail) => window.dispatchEvent(new CustomEvent(`jarvis:${name}`, {detail}));

    const assistantName = settings.assistant_name || 'AURA';
    const userName = settings.user_name || 'Utente';
    const wakeWord = String(settings.wake_word || 'ehi aura').trim().toLowerCase();

    const escapeHTML = (value) => String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');

    const inlineMarkup = (value) => value
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    const renderRichText = (text) => {
        const safe = escapeHTML(text).replace(/\r\n/g, '\n').trim();
        if (!safe) return '<p></p>';

        const blocks = safe.split(/\n{2,}/);
        return blocks.map((block) => {
            const trimmed = block.trim();
            const codeMatch = trimmed.match(/^```[a-zA-Z0-9_-]*\n?([\s\S]*?)```$/);
            if (codeMatch) return `<pre><code>${codeMatch[1].trim()}</code></pre>`;

            const lines = trimmed.split('\n');
            if (lines.every((line) => /^\s*[-*]\s+/.test(line))) {
                return `<ul>${lines.map((line) => `<li>${inlineMarkup(line.replace(/^\s*[-*]\s+/, ''))}</li>`).join('')}</ul>`;
            }
            if (lines.every((line) => /^\s*\d+[.)]\s+/.test(line))) {
                return `<ol>${lines.map((line) => `<li>${inlineMarkup(line.replace(/^\s*\d+[.)]\s+/, ''))}</li>`).join('')}</ol>`;
            }
            return `<p>${inlineMarkup(lines.join('<br>'))}</p>`;
        }).join('');
    };

    const nowTime = () => new Intl.DateTimeFormat('it-IT', {
        hour: '2-digit',
        minute: '2-digit'
    }).format(new Date());

    const updateClock = () => {
        const timeNode = document.getElementById('live-time');
        const dateNode = document.getElementById('live-date');
        const now = new Date();
        if (timeNode) {
            timeNode.textContent = new Intl.DateTimeFormat('it-IT', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            }).format(now);
        }
        if (dateNode) {
            dateNode.textContent = new Intl.DateTimeFormat('it-IT', {
                weekday: 'short',
                day: '2-digit',
                month: 'short'
            }).format(now).toUpperCase();
        }
    };

    updateClock();
    window.setInterval(updateClock, 1000);

    const setCoreState = (state, label) => {
        coreStage?.classList.remove('thinking', 'speaking', 'listening', 'preparing_voice');
        if (state) coreStage?.classList.add(state);
        if (coreState) coreState.textContent = label || 'IN ATTESA';
        emit('state', {state: state || 'idle'});
    };

    const scrollToLatest = (smooth = true) => {
        chatMessages.scrollTo({
            top: chatMessages.scrollHeight,
            behavior: smooth ? 'smooth' : 'auto'
        });
    };

    const addMessage = (role, text, options = {}) => {
        const isUser = role === 'user';
        const wrapper = document.createElement('article');
        wrapper.className = `message ${isUser ? 'user-msg' : 'nexus-msg'}`;

        const meta = document.createElement('div');
        meta.className = 'message-meta';
        const source = document.createElement('span');
        source.className = 'message-source';
        source.textContent = isUser ? 'USR' : 'AU';
        const name = document.createElement('span');
        name.textContent = isUser ? userName : assistantName;
        const time = document.createElement('time');
        time.textContent = options.time || nowTime();
        meta.append(source, name, time);

        const content = document.createElement('div');
        content.className = 'msg-content';
        content.innerHTML = renderRichText(text);
        wrapper.append(meta, content);

        if (!isUser && !options.isError) {
            const actions = document.createElement('div');
            actions.className = 'message-actions';
            const replay = document.createElement('button');
            replay.type = 'button';
            replay.textContent = 'Ascolta';
            replay.setAttribute('aria-label', 'Ascolta questa risposta');
            replay.addEventListener('click', () => { player.unlock().catch(() => {}); speak(text, options.emotion || 'normale', true); });
            const copy = document.createElement('button');
            copy.type = 'button';
            copy.textContent = 'Copia';
            copy.setAttribute('aria-label', 'Copia questa risposta');
            copy.addEventListener('click', async () => {
                try { await navigator.clipboard.writeText(text); window.showToast('Risposta copiata'); }
                catch (_) { window.showToast('Copia non disponibile in questo browser', 'error'); }
            });
            actions.append(replay, copy);
            wrapper.appendChild(actions);
        }

        if (options.latency || options.provider) {
            const stats = document.createElement('div');
            stats.className = 'message-stats';
            const parts = [];
            if (options.provider) parts.push(String(options.provider).toUpperCase());
            if (options.model) parts.push(String(options.model));
            if (options.latency) parts.push(`${options.latency} MS`);
            stats.textContent = parts.join(' · ');
            wrapper.appendChild(stats);
        }

        chatMessages.appendChild(wrapper);
        if (options.track !== false) chatHistory.push({role, content: text});
        scrollToLatest(options.smooth !== false);

        if (!isUser && options.speak !== false) {
            emit('emotion', {emotion: options.emotion || 'normale'});
            speak(text, options.emotion || 'normale');
        }
        return wrapper;
    };

    const addTypingIndicator = () => {
        const wrapper = document.createElement('article');
        wrapper.className = 'message nexus-msg typing-message';
        wrapper.innerHTML = `
            <div class="message-meta">
                <span class="message-source">JV</span>
                <span>${escapeHTML(assistantName)}</span>
                <span>ELABORAZIONE</span>
            </div>
            <div class="msg-content"><div class="typing-dots"><i></i><i></i><i></i></div></div>
        `;
        chatMessages.appendChild(wrapper);
        scrollToLatest();
        return wrapper;
    };

    const setBusy = (busy) => {
        requestInFlight = busy;
        sendButton.disabled = busy;
        userInput.disabled = busy;
        if (clearButton) clearButton.disabled = busy;
        if (micButton && SpeechRecognition && isSecureContextForMic) micButton.disabled = busy;
        if (busy) stopWakeListener();
        if (busy || !isSpeaking) setCoreState(busy ? 'thinking' : '', busy ? 'ELABORAZIONE' : 'IN ATTESA');
        if (!busy && !isSpeaking) scheduleWakeRestart();
    };

    const resizeComposer = () => {
        userInput.style.height = 'auto';
        userInput.style.height = `${Math.min(userInput.scrollHeight, 128)}px`;
    };

    userInput.addEventListener('input', resizeComposer);
    userInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
        if (event.key === 'Escape') {
            stopCurrentAudio();
            stopManualListening();
        }
    });

    const sendMessage = async (presetText = null) => {
        const text = String(presetText ?? userInput.value).trim();
        if (!text || requestInFlight) return;
        setBusy(true);
        stopCurrentAudio();
        stopManualListening();
        if (voiceEnabled) player.unlock().catch(() => {});
        userInput.value = '';
        resizeComposer();
        addMessage('user', text, {speak: false});
        const typing = addTypingIndicator();

        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), ((settings.ai_timeout_seconds || 65) + 20) * 1000);

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: text}),
                signal: controller.signal
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.status !== 'success') {
                throw new Error(data.error || `Errore del sistema (${response.status})`);
            }

            addMessage('bot', data.response, {
                emotion: data.emozione,
                latency: data.latency_ms,
                provider: data.provider,
                model: data.model
            });
            if (data.provider === 'offline') window.showToast('I servizi AI non sono disponibili. Controlla le impostazioni.', 'error');
            if (modelStatus) modelStatus.textContent = data.provider === 'offline' ? 'AI non disponibile' : `${String(data.provider).toUpperCase()} · ${data.model}`;
            if (memoryCount && Number.isFinite(data.memory_count)) {
                memoryCount.textContent = data.memory_count;
            }
        } catch (error) {
            const message = error.name === 'AbortError'
                ? 'La risposta sta impiegando troppo tempo. Riprova tra poco.'
                : error.message;
            addMessage('bot', message, {emotion: 'allerta', speak: false, isError: true});
            if (!userInput.value) { userInput.value = text; resizeComposer(); }
            window.showToast(message, 'error');
        } finally {
            window.clearTimeout(timeout);
            typing.remove();
            setBusy(false);
            userInput.focus();
        }
    };

    sendButton.addEventListener('click', () => sendMessage());

    document.querySelectorAll('[data-prompt]').forEach((button) => {
        button.addEventListener('click', () => {
            const prompt = button.dataset.prompt || '';
            if (!prompt) return;
            userInput.value = prompt;
            resizeComposer();
            userInput.focus();
        });
    });

    const loadHistory = async () => {
        try {
            const response = await fetch('/api/history?limit=40');
            const data = await response.json();
            if (!response.ok || data.status !== 'success') return;
            if (memoryCount) memoryCount.textContent = data.count || 0;
            if (!Array.isArray(data.messages) || data.messages.length === 0) return;

            chatMessages.replaceChildren();
            data.messages.forEach((message) => {
                addMessage(message.role === 'user' ? 'user' : 'bot', message.content, {
                    track: true,
                    speak: false,
                    smooth: false
                });
            });
            scrollToLatest(false);
        } catch (error) {
            console.warn('Memoria non disponibile:', error);
        }
    };

    const loadStatus = async () => {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            if (modelStatus) {
                const provider = String(data.provider || 'AI').toUpperCase();
                if (provider === 'AUTO') {
                    const count = Array.isArray(data.configured_providers) ? data.configured_providers.length : 0;
                    modelStatus.textContent = `AUTO · ${count} provider configurati`;
                } else {
                    modelStatus.textContent = data.provider_configured === false && provider !== 'OLLAMA'
                        ? `${provider} · chiave assente`
                        : `${provider} · pronto`;
                }
            }
            if (memoryCount) memoryCount.textContent = data.memory_count || 0;
            const ready = Boolean(data.provider_configured);
            const label = document.getElementById('connection-label');
            const title = document.getElementById('connection-title');
            const detail = document.getElementById('connection-detail');
            if (label) label.textContent = ready ? 'AI' : '—';
            if (title) title.textContent = ready ? 'CONFIGURATA' : 'DA CONFIGURARE';
            if (detail) detail.textContent = ready ? 'Provider configurato · disponibilità verificata a ogni risposta' : 'Aggiungi una chiave API o avvia Ollama';
            if (voiceModule) voiceModule.textContent = data.voice_enabled ? 'Sintesi pronta' : 'Non configurata';
            if (wakeStatus) {
                wakeStatus.textContent = data.wake_enabled ? `Pronuncia “${data.wake_word}”` : 'Disattivata';
            }
        } catch (error) {
            if (modelStatus) modelStatus.textContent = 'Stato non disponibile';
        }
    };

    clearButton?.addEventListener('click', async () => {
        if (!window.confirm('Cancellare definitivamente la memoria della conversazione?')) return;
        try {
            const response = await fetch('/api/clear_chat', {method: 'POST'});
            if (!response.ok) throw new Error('Operazione non riuscita');
            chatHistory = [];
            chatMessages.replaceChildren();
            addMessage('bot', `Memoria conversazionale azzerata. Sono pronto, ${userName}.`, {
                track: false,
                speak: false
            });
            if (memoryCount) memoryCount.textContent = '0';
            window.showToast('Memoria conversazionale azzerata', 'success');
        } catch (error) {
            window.showToast(error.message, 'error');
        }
    });

    exportButton?.addEventListener('click', () => {
        const header = `${assistantName} // Conversazione\nEsportato: ${new Date().toLocaleString('it-IT')}\n${'='.repeat(48)}\n\n`;
        const log = chatHistory.map((message) => {
            const label = message.role === 'user' ? userName : assistantName;
            return `[${label}]\n${message.content}`;
        }).join('\n\n');
        const blob = new Blob([header + log], {type: 'text/plain;charset=utf-8'});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `aura_log_${new Date().toISOString().slice(0, 10)}.txt`;
        link.click();
        URL.revokeObjectURL(url);
    });

    const player = new window.AuraSpeech.SpeechPlayer(settings, state => {
        isSpeaking = player.active;
        if (stopAudioButton) stopAudioButton.hidden = !player.active;
        setCoreState(state === 'idle' ? (requestInFlight ? 'thinking' : '') : state,
            state === 'speaking' ? 'TI RISPONDO' : state === 'preparing_voice' ? 'PREPARO LA VOCE' : requestInFlight ? 'ELABORAZIONE' : 'IN ATTESA');
        if (state === 'idle') scheduleWakeRestart(500);
    });
    player.warm();
    function stopCurrentAudio() { player.stop(); }
    const speak = async (text, emotion = 'normale', force = false) => {
        if (!voiceEnabled && !force) return;
        stopWakeListener();
        try { await player.speak(text, emotion); }
        catch (error) {
            if (error.name !== 'AbortError') window.showToast(error.message || 'Voce non disponibile. Riprova.', 'error');
        }
    };
    stopAudioButton?.addEventListener('click', stopCurrentAudio);
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') { stopCurrentAudio(); stopManualListening(); }
    });

    const playSignal = (frequency = 720) => {
        try {
            audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gain = audioContext.createGain();
            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(frequency, audioContext.currentTime);
            gain.gain.setValueAtTime(0.0001, audioContext.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.055, audioContext.currentTime + 0.015);
            gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.13);
            oscillator.connect(gain).connect(audioContext.destination);
            oscillator.start();
            oscillator.stop(audioContext.currentTime + 0.14);
        } catch (_) {}
    };

    const startVisualizer = async () => {
        if (!micVisualizer || !navigator.mediaDevices?.getUserMedia) return;
        const session = ++microphoneSession;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({audio: true});
            if (!isManualListening || session !== microphoneSession) {
                stream.getTracks().forEach(track => track.stop());
                return;
            }
            microphoneStream = stream;
            micVisualizer.style.display = 'block';
            const context = new (window.AudioContext || window.webkitAudioContext)();
            microphoneContext = context;
            const analyser = context.createAnalyser();
            analyser.fftSize = 64;
            context.createMediaStreamSource(microphoneStream).connect(analyser);
            const data = new Uint8Array(analyser.frequencyBinCount);
            const canvasContext = micVisualizer.getContext('2d');

            const draw = () => {
                analyser.getByteFrequencyData(data);
                canvasContext.clearRect(0, 0, micVisualizer.width, micVisualizer.height);
                const barWidth = 2;
                const gap = 2;
                data.slice(0, 18).forEach((value, index) => {
                    const height = Math.max(2, (value / 255) * 22);
                    canvasContext.fillStyle = `rgba(101, 217, 232, ${0.28 + value / 420})`;
                    canvasContext.fillRect(index * (barWidth + gap), (micVisualizer.height - height) / 2, barWidth, height);
                });
                visualizerFrame = requestAnimationFrame(draw);
            };
            draw();
        } catch (_) {}
    };

    const stopVisualizer = () => {
        microphoneSession += 1;
        if (visualizerFrame) cancelAnimationFrame(visualizerFrame);
        visualizerFrame = null;
        if (microphoneStream) microphoneStream.getTracks().forEach((track) => track.stop());
        microphoneStream = null;
        microphoneContext?.close().catch(() => {});
        microphoneContext = null;
        if (micVisualizer) {
            micVisualizer.style.display = 'none';
            micVisualizer.getContext('2d')?.clearRect(0, 0, micVisualizer.width, micVisualizer.height);
        }
    };

    const scheduleWakeRestart = (delay = 1000) => {
        window.clearTimeout(wakeRestartTimer);
        if (!settings.wake_enabled || microphoneDenied || document.hidden || requestInFlight || isSpeaking || isManualListening || !SpeechRecognition) return;
        wakeRestartTimer = window.setTimeout(startWakeListener, delay);
    };

    function stopWakeListener() {
        window.clearTimeout(wakeRestartTimer);
        if (!wakeRecognition) return;
        wakeRecognition.onend = null;
        try { wakeRecognition.abort(); } catch (_) {}
        wakeRecognition = null;
    }

    const handleRecognitionDenied = () => {
        microphoneDenied = true;
        stopWakeListener();
        if (wakeStatus) wakeStatus.textContent = 'Permesso microfono richiesto';
        if (micButton) {
            micButton.title = 'Autorizza il microfono nelle impostazioni del browser';
        }
    };

    function startWakeListener() {
        if (!settings.wake_enabled || microphoneDenied || document.hidden || requestInFlight || !SpeechRecognition || !isSecureContextForMic || isSpeaking || isManualListening || wakeRecognition) return;

        const recognition = new SpeechRecognition();
        wakeRecognition = recognition;
        recognition.lang = 'it-IT';
        recognition.continuous = true;
        recognition.interimResults = true;

        recognition.onresult = (event) => {
            for (const result of Array.from(event.results).slice(event.resultIndex)) {
                if (!result.isFinal) continue;
                const transcript = result[0].transcript.trim();
                const command = window.AuraWake.extractCommand(transcript, wakeWord);
                if (command === null) continue;
                stopWakeListener();
                if (command) sendMessage(command);
                else activateWakeCommand();
                break;
            }
        };
        recognition.onerror = (event) => {
            if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                handleRecognitionDenied();
                stopWakeListener();
                return;
            }
            wakeRecognition = null;
            scheduleWakeRestart(event.error === 'no-speech' ? 450 : 1800);
        };
        recognition.onend = () => {
            if (wakeRecognition === recognition) wakeRecognition = null;
            scheduleWakeRestart(700);
        };

        try {
            recognition.start();
            if (wakeStatus) wakeStatus.textContent = `Pronuncia “${wakeWord}”`;
        } catch (_) {
            wakeRecognition = null;
            scheduleWakeRestart(1500);
        }
    }

    const activateWakeCommand = () => {
        if (!SpeechRecognition || requestInFlight || isManualListening) return;
        playSignal(860);
        wakeIndicator?.classList.add('active');
        window.setTimeout(() => wakeIndicator?.classList.remove('active'), 2200);
        beginCommandRecognition(true);
    };

    const beginCommandRecognition = (fromWake = false) => {
        if (!SpeechRecognition || requestInFlight || isManualListening) return;
        stopCurrentAudio();
        stopWakeListener();
        isManualListening = true;
        micButton?.classList.add('mic-active');
        setCoreState('listening', 'ASCOLTO');
        startVisualizer();

        const recognition = new SpeechRecognition();
        commandRecognition = recognition;
        recognition.lang = 'it-IT';
        recognition.interimResults = true;
        recognition.continuous = false;

        recognition.onresult = (event) => {
            const transcript = Array.from(event.results)
                .map((result) => result[0].transcript)
                .join(' ')
                .trim();
            userInput.value = transcript;
            resizeComposer();
            if (event.results[event.results.length - 1].isFinal) {
                window.setTimeout(() => sendMessage(), 120);
            }
        };
        recognition.onerror = (event) => {
            if (event.error === 'not-allowed') handleRecognitionDenied();
            if (event.error !== 'aborted' && event.error !== 'no-speech') {
                window.showToast(`Riconoscimento vocale: ${event.error}`, 'error');
            }
        };
        recognition.onend = () => {
            isManualListening = false;
            commandRecognition = null;
            micButton?.classList.remove('mic-active');
            stopVisualizer();
            if (!requestInFlight && !isSpeaking) setCoreState('', 'IN ATTESA');
            scheduleWakeRestart(fromWake ? 1000 : 650);
        };

        try {
            recognition.start();
            playSignal(fromWake ? 960 : 720);
        } catch (error) {
            isManualListening = false;
            commandRecognition = null;
            stopVisualizer();
            scheduleWakeRestart();
        }
    };

    function stopManualListening() {
        if (!commandRecognition) return;
        try { commandRecognition.abort(); } catch (_) {}
        commandRecognition = null;
        isManualListening = false;
        micButton?.classList.remove('mic-active');
        stopVisualizer();
        setCoreState('', 'IN ATTESA');
    }

    if (micButton) {
        if (!SpeechRecognition || !isSecureContextForMic) {
            micButton.disabled = true;
            micButton.title = 'Riconoscimento vocale non supportato in questo browser';
            if (wakeStatus) wakeStatus.textContent = 'Browser non compatibile';
        } else {
            micButton.addEventListener('click', () => {
                player.unlock().catch(() => {});
                microphoneDenied = false;
                if (isManualListening) {
                    stopManualListening();
                } else {
                    beginCommandRecognition(false);
                }
            });
            scheduleWakeRestart(1200);
        }
    }

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stopWakeListener();
            stopManualListening();
        } else {
            scheduleWakeRestart(1000);
        }
    });

    window.addEventListener('beforeunload', () => {
        stopWakeListener();
        stopManualListening();
        stopCurrentAudio();
    });

    const initialVoiceState = document.getElementById('voice-state');
    if (initialVoiceState) initialVoiceState.textContent = voiceEnabled ? 'Voce attiva' : 'Voce disattivata';
    sendButton.disabled = userInput.disabled = true;
    Promise.allSettled([loadHistory(), loadStatus()]).then(() => {
        sendButton.disabled = userInput.disabled = false;
        userInput.focus();
    });
});
