# Risposte e voce progressive

Il browser invia `POST /api/chat` con `stream: true`. Il server risponde in NDJSON: `start`, uno o più `delta`, quindi `done` oppure `error`. Il formato JSON precedente rimane disponibile omettendo `stream`, anche per le verifiche delle connessioni.

Il testo viene estratto dal campo `testo` dell’involucro JSON mentre arriva, gestendo escape, caratteri Unicode e delimitatori Markdown divisi tra più eventi. Ragionamento interno e metadati del servizio non vengono inviati come testo. La risposta completa viene comunque validata prima di salvare lo scambio in una transazione.

La coda vocale riceve frasi complete senza bloccare la ricezione del testo. Per periodi lunghi usa segmenti limitati; evita di dividere codice, collegamenti e abbreviazioni comuni. Ogni lettura ha una sola sessione: annullarla interrompe richieste audio, riproduzione e frasi ancora in attesa. Qwen conserva il proprio modello già caricato. Kokoro, Irodori ed Edge restano selezionabili e usano la stessa coda, con i rispettivi servizi di sintesi.

Le 13 connessioni usano i protocolli nativi già previsti dal progetto: Gemini SSE, Ollama NDJSON, Claude Messages, OpenAI/xAI Responses e Chat Completions per gli altri servizi compatibili. La disponibilità dello streaming dipende anche dal modello o dall’endpoint personalizzato. Un errore prima del primo testo può usare le alternative consentite dalle impostazioni. Dopo il primo testo non ci sono rigenerazioni o cambi automatici di modello, per evitare di leggere due risposte diverse.

`ai.first_text_ms` nell’evento finale misura il tempo fino al primo testo emesso dal server; `latency_ms` misura il completamento della risposta, non la fine della lettura. Queste misure non includono la latenza dell’altoparlante. Non è garantito che la voce preceda la fine di ogni risposta: una risposta breve può terminare prima che il modello vocale produca il primo segmento.

I test simulano eventi divisi anche dentro JSON e UTF-8, ricezione anticipata, troncamenti, disconnessioni, salvataggio atomico e interruzione di una lettura. Le prove con servizi reali vanno eseguite separatamente con credenziali personali; i test automatici non consumano credito.

Protocolli di riferimento: [Gemini GenerateContent/streamGenerateContent](https://aistudio.google.com/api-reference/generate-content), [documentazione ufficiale OpenAI sullo streaming](https://developers.openai.com/api/docs/guides/streaming-responses), [Claude Messages streaming](https://platform.claude.com/docs/en/build-with-claude/streaming), [OpenRouter streaming](https://openrouter.ai/docs/api_reference/streaming), [Ollama streaming](https://docs.ollama.com/api/streaming), [Hugging Face Chat Completion](https://huggingface.co/docs/inference-providers/tasks/chat-completion).
