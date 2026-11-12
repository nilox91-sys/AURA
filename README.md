# AURA · La tua compagna di idee

[![Checks](https://github.com/nilox91-sys/AURA/actions/workflows/checks.yml/badge.svg)](https://github.com/nilox91-sys/AURA/actions/workflows/checks.yml)

[Repository pubblico](https://github.com/nilox91-sys/AURA)

Assistente personale in italiano, con avatar Live2D, personalità configurabile, napoletano e conversazione vocale. Funziona sul PC; puoi scegliere un servizio AI online oppure un modello locale.

## Avvio su Windows

1. Installa [Python 3.10 o successivo](https://www.python.org/downloads/), scarica il repository ed estrailo.
2. Esegui **PREPARA_AVATAR.bat** per scaricare gli asset ufficiali già scelti. Fonti, impronte e dimensioni sono in `asset-manifest.json`; consulta [termini e crediti](licenses/THIRD_PARTY.md).
3. Esegui **start_aura.bat**. Al primo avvio prepara l’ambiente e installa le dipendenze bloccate alle versioni verificate.
4. Apri http://127.0.0.1:5001/settings e filtra le **13 connessioni** per quota gratuita/prova, consumo o esecuzione sul PC. Scegli servizio, chiave e modello. **Salva e verifica** legge il catalogo; **Prova una risposta** genera una frase fissa senza inviare la cronologia. [Guida alla scelta](docs/AI-SERVICES.md).

Su altri sistemi: `python tools/prepare_avatar.py`, poi `python run.py`. Le funzioni vocali opzionali e i BAT sono verificati su Windows; gli altri sistemi non sono stati collaudati.

## Il tuo spazio

- **Connessione:** OpenRouter, Groq, Gemini, Hugging Face, OpenAI, Claude, Mistral, DeepSeek, Cerebras, xAI/Grok, Ollama, LM Studio e un endpoint compatibile con Chat Completions. Filtri per tipo di piano, collegamenti alle condizioni e cataloghi del proprio account.
- **Identità:** nome, frase personale, genere grammaticale, personalità, tono, ironia, emoji, interessi e istruzioni. Le preferenze vengono incluse nelle richieste AI; il dialetto scelto viene ribadito dopo la cronologia.
- **Lingua e voce:** italiano, napoletano e altri registri sperimentali. Qwen, Kokoro, Irodori ed Edge restano selezionabili.
- **Avatar e spazio:** Hiyori/Haru, tre atmosfere, qualità, inquadratura, movimenti, sguardo e labbra.
- **Conversazioni:** profondità, creatività quando supportata, attesa, budget e cronologia. Disattivando la cronologia, i nuovi turni sono indipendenti e non vengono salvati; i precedenti rimangono finché li cancelli.
- **Account e dati:** accesso GitHub facoltativo, esportazione/importazione delle preferenze, ripristino e cache audio.

I provider a consumo aggiunti non sono fallback automatici. Le alternative possono usare solo i servizi già previsti (Groq, Gemini, OpenRouter, Hugging Face, Ollama); disponibilità e tariffe dipendono dai modelli. Ollama e LM Studio selezionati esplicitamente, e gli endpoint compatibili locali, non passano al cloud. GitHub sign-in non fornisce chiavi AI.

### Selezione essenziale dei modelli

Il profilo locale può mostrare soltanto i modelli mantenuti dopo le prove di risposta. La preferenza `ai_model_allowlist` in `settings.json` contiene gli identificativi completi, ad esempio `["gemini:gemini-3.1-flash-lite"]`; un elenco vuoto mantiene il catalogo completo. Il modello principale deve appartenere alla selezione. Quando la selezione è attiva, menu, catalogo e richieste sono limitati a quei modelli e i fallback rimangono disattivati. Le chiavi degli altri servizi vengono conservate.

Chi scarica una nuova copia vede il catalogo completo. Dopo una prova riuscita può scegliere **Mantieni solo questo modello**; con **Mostra tutte le connessioni** può riaprire il catalogo senza cancellare modello o chiavi. Questa selezione resta locale e non viene modificata da importazione o ripristino delle preferenze. Le voci rimangono separate: il token Hugging Face per Irodori è ancora modificabile in Lingua e voce anche quando Hugging Face non compare fra le connessioni AI. La disponibilità effettiva continua a dipendere dall’account e dal servizio.

## Se una chiave è salvata ma l’AI non risponde

**Salva e verifica** controlla l’accesso al catalogo; **Prova una risposta** verifica la generazione effettiva. Un catalogo raggiungibile non garantisce credito, quota o permessi sul modello. La verifica del catalogo non cancella un precedente errore di generazione.

| Errore | Significato e prossimo passo |
| --- | --- |
| 401 | Chiave non accettata: verifica servizio e chiave. |
| 402 | Credito esaurito o non attivato: verifica il saldo oppure scegli un altro servizio. Generare un’altra chiave dello stesso account non aggiunge credito. |
| 403 | Accesso negato: controlla permessi e restrizioni di account/rete. |
| 404 | Modello non disponibile: seleziona un modello attuale; quando possibile AURA mostra il suggerimento del servizio. |
| 429 | Quota o frequenza superata: attendi il ripristino. La quota giornaliera OpenRouter gratuita riguarda l’account, quindi cambiare modello gratuito non la ripristina. |
| 503 | Servizio sovraccarico: attendi o prova un altro modello. |

Per Gemini la scelta iniziale è **gemini-3.1-flash-lite**; alcuni modelli 2.5 ancora elencati nel catalogo non sono accessibili ai nuovi account. Le varianti Lite attuali usano un livello di ragionamento minimo nei profili rapidi/bilanciati, con un’attesa compatibile con il budget della richiesta.

Fonti: [errori DeepSeek](https://api-docs.deepseek.com/quick_start/error_codes/), [credito Hugging Face](https://huggingface.co/docs/inference-providers/main/pricing), [limiti OpenRouter](https://openrouter.ai/collections/free-models), [errori Gemini](https://ai.google.dev/gemini-api/docs/generate-content/api-errors).

## Voci e stanza vocale

La voce di base usa Edge online. Le voci sul PC sono opzionali: **PREPARA_QWEN_TTS.bat** e **PREPARA_VOCE_LOCALE.bat** scaricano modelli e ambienti separati in `%LOCALAPPDATA%/AURA/voices`. Non sono inclusi nel repository. Qwen usa il modello **0.6B Base** e riferimenti sintetici Irodori; non installa i modelli 1.7B.

Apri `/voice`, premi **Avvia voce** e consenti il microfono. Dopo la risposta l’ascolto può ripartire automaticamente; puoi disattivarlo nelle impostazioni. Chrome/Edge possono usare un servizio online per il riconoscimento. L’audio del microfono non viene registrato da AURA; le trascrizioni seguono l’impostazione della cronologia. Pronuncia e dialetti restano sperimentali.

In chat e nella stanza vocale il testo arriva progressivamente: la sintesi della prima frase può partire mentre l’AI continua a generare il resto. Le frasi vengono lette in ordine con la voce selezionata, senza leggere i blocchi di codice. **Interrompi** ferma anche i segmenti vocali in attesa. Se la connessione cade dopo l’inizio della risposta, AURA segnala che il testo è parziale e non lo rigenera automaticamente. Solo gli scambi completati vengono salvati nella cronologia. Il tempo effettivo dipende dal servizio AI, dalla voce e dal caricamento iniziale del modello locale. [Dettagli e verifiche](docs/STREAMING.md).

## GitHub

Il repository è separato dal collegamento del profilo dentro AURA. Per quest’ultimo segui [la guida GitHub](docs/GITHUB.md). Serve una OAuth App personale con Device Flow abilitato; non serve un client secret. Il codice di accesso rimane sul server, il token viene usato per verificare il profilo e non viene salvato. La sessione locale scade dopo otto ore di inattività.

## Dati e sicurezza

Chiavi in `settings.json` o `.env`, conversazioni SQLite, sessioni, audio e modelli sono esclusi da Git. Le chiavi sono conservate in chiaro nei file locali: proteggi il tuo account Windows e non condividere questi file. Il browser riceve solo l’indicazione che una chiave è presente.

Le richieste AI inviano al servizio selezionato il messaggio, l’identità personalizzata e il contesto consentito. Le voci online inviano il testo da leggere. L’esportazione delle preferenze esclude credenziali, account e chat; può contenere le tue istruzioni e informazioni personali inserite nell’identità. AURA ascolta solo su `127.0.0.1`: l’accesso GitHub facoltativo non trasforma l’app in un servizio pubblico sicuro.

Per separare i dati dal codice, imposta `JARVIS_DATA_DIR` nel tuo `.env`. Non mettere questa cartella dentro il repository. Ulteriori dettagli in [SECURITY.md](SECURITY.md).

## Sviluppo e verifiche

```text
python -m unittest discover -s tests -v
node --test tests/test_speech_player.cjs tests/test_voice_room.cjs tests/test_wakeword.cjs tests/test_chat_stream.cjs
python tools/prepare_avatar.py --check
python run.py --check
```

I test usano risposte simulate e non consumano credito API. I controlli che richiedono gli asset Live2D vengono saltati nel checkout pubblico finché non li prepari. Non vengono scaricati modelli vocali durante i test. La CI verifica Python 3.11/3.14 su Windows e i flussi JavaScript.

## Licenze e limiti

Il codice originale di AURA è distribuito sotto licenza MIT; [LICENSE](LICENSE). Le librerie e gli asset di terzi mantengono le loro licenze. I modelli Live2D e Cubism Core non sono distribuiti nel repository: il programma di preparazione li scarica dalle fonti ufficiali e verifica le impronte. Vedi [THIRD_PARTY.md](licenses/THIRD_PARTY.md).

AURA genera testo: non naviga sul web, non esegue codice e non controlla il PC. Le risposte dei modelli possono contenere errori. Questo progetto non è affiliato ai provider o a Live2D.
