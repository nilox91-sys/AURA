/* Real Cubism model: local textures, rig, physics, motions and audio-driven lips. */
(() => {
    'use strict';
    const stage = document.getElementById('avatar-stage');
    if (!stage) return;
    const canvas = document.getElementById('live2d-canvas');
    const loading = document.getElementById('avatar-loading');
    const status = document.getElementById('avatar-status');
    const motionButton = document.getElementById('avatar-motion');
    const frameButton = document.getElementById('avatar-frame');
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    const profile = window.AURA_AVATAR, settings = window.AURA_SETTINGS || {};
    let app, model, observer;
    const savedPause = localStorage.getItem('jarvis.avatar.paused');
    let paused = reducedMotion.matches || (savedPause === null ? settings.avatar_motion === false : savedPause === 'true');
    let closeUp = localStorage.getItem('jarvis.avatar.closeup') === null ? settings.avatar_framing !== 'full' : localStorage.getItem('jarvis.avatar.closeup') !== 'false';
    let level = 0;
    let targetLevel = 0;
    let speaking = false;
    let state = 'idle';
    let expressionTimer;

    function fit() {
        if (!app || !model) return;
        const width = stage.clientWidth;
        const height = stage.clientHeight;
        app.renderer.resize(width, height);
        const bounds = model.getLocalBounds();
        const factor = closeUp ? 1.6 : 1.02;
        const scale = closeUp && profile.portrait_height ? height * profile.portrait_height / bounds.height
            : Math.min(width / (bounds.width * 0.88), height * factor / bounds.height);
        model.scale.set(scale);
        model.position.set(width / 2, height * (closeUp ? 0.035 : 0.02));
        frameButton.textContent = closeUp ? 'Figura intera' : 'Primo piano';
        if (paused) app.renderer.render(app.stage);
    }

    function applyPlayback() {
        if (!app || !model) return;
        const active = !document.hidden && (!paused || speaking);
        model.autoUpdate = false;
        if (active) app.start();
        else {
            app.stop();
            app.renderer.render(app.stage);
        }
        motionButton.textContent = paused ? 'Riprendi movimenti' : 'Pausa movimenti';
        motionButton.setAttribute('aria-pressed', String(paused));
    }

    function changeState(next) {
        state = next || 'idle';
        stage.dataset.state = state;
        const labels = {idle: 'Sono qui, dimmi tutto.', thinking: 'Metto insieme i pezzi…', preparing_voice: 'Preparo la voce…',
            listening: 'Ti ascolto.', speaking: 'Ti rispondo.', offline: 'Connessione non disponibile'};
        status.textContent = labels[state] || labels.idle;
    }

    async function expression(emotion) {
        if (!model) return;
        const expressions = profile.expressions;
        clearTimeout(expressionTimer);
        const manager = model.internalModel.motionManager.expressionManager;
        try {
            if (expressions[emotion]) await model.expression(expressions[emotion]);
            else manager?.resetExpression();
            expressionTimer = setTimeout(() => manager?.resetExpression(), 6000);
        } catch (error) {
            console.warn('Espressione non disponibile:', error.name);
        }
    }

    async function init() {
        try {
            if (!window.PIXI?.live2d || !window.Live2DCubismCore) throw new Error('Runtime Live2D non disponibile');
            app = new PIXI.Application({view: canvas, backgroundAlpha: 0, antialias: true,
                autoDensity: true, resolution: Math.min(devicePixelRatio || 1, settings.avatar_quality === 'light' ? 1 : 2),
                width: stage.clientWidth, height: stage.clientHeight});
            app.ticker.maxFPS = {light:20,balanced:30,fluid:60}[settings.avatar_quality] || 30;
            model = await PIXI.live2d.Live2DModel.from(profile.path, {
                autoInteract: false, autoUpdate: false, motionPreload: 'ALL'
            });
            model.anchor.set(0.5, 0);
            app.stage.addChild(model);
            // Cubism fires this after motion, expressions and physics, before drawing.
            model.internalModel.on('beforeModelUpdate', () => {
                level += (targetLevel - level) * 0.5;
                model.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', speaking && settings.avatar_lipsync !== false ? level : 0);
            });
            // Settle pose crossfades before the first frame, including paused mode.
            model.update(0);
            model.update(1000);
            app.ticker.add(() => model.update(Math.min(app.ticker.elapsedMS, 50)));
            observer = new ResizeObserver(fit);
            observer.observe(stage);
            fit();
            loading.hidden = true;
            canvas.hidden = false;
            stage.dataset.loaded = 'true';
            applyPlayback();
            changeState(state);
            window.auraAvatar = {get model() { return model; }, get app() { return app; }};
        } catch (error) {
            console.error('Caricamento Live2D:', error);
            if (app) { app.destroy(false); app = null; }
            status.textContent = 'Avatar non disponibile';
            loading.replaceChildren();
            const text = document.createElement('p');
            text.textContent = 'Non riesco a caricare il personaggio. Esegui PREPARA_AVATAR.bat nella cartella di AURA e controlla che il browser supporti WebGL.';
            const retry = document.createElement('button');
            retry.type = 'button';
            retry.textContent = 'Riprova';
            retry.addEventListener('click', () => location.reload());
            loading.append(text, retry);
            motionButton.disabled = frameButton.disabled = true;
        }
    }

    motionButton.addEventListener('click', () => {
        paused = !paused;
        localStorage.setItem('jarvis.avatar.paused', String(paused));
        applyPlayback();
    });
    frameButton.addEventListener('click', () => {
        closeUp = !closeUp;
        localStorage.setItem('jarvis.avatar.closeup', String(closeUp));
        fit();
    });
    stage.addEventListener('pointermove', (event) => {
        if (!model || paused || reducedMotion.matches || settings.avatar_follow_cursor === false) return;
        const box = stage.getBoundingClientRect();
        model.focus(event.clientX - box.left, event.clientY - box.top);
    });
    stage.addEventListener('pointerleave', () => model?.focus(stage.clientWidth / 2, stage.clientHeight / 3));
    window.addEventListener('jarvis:state', event => changeState(event.detail.state));
    window.addEventListener('jarvis:emotion', event => expression(event.detail.emotion));
    window.addEventListener('jarvis:audio-level', event => {
        targetLevel = Math.max(0, Math.min(1, Number(event.detail.level) || 0));
    });
    window.addEventListener('jarvis:speaking', event => {
        speaking = Boolean(event.detail.state);
        if (!speaking) { targetLevel = level = 0; }
        applyPlayback();
    });
    document.addEventListener('visibilitychange', applyPlayback);
    window.addEventListener('pagehide', () => {
        observer?.disconnect();
        clearTimeout(expressionTimer);
        model?.destroy();
        app?.destroy(false);
    }, {once: true});
    init();
})();
