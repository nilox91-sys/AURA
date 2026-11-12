# Scegliere l’AI per AURA

Una nuova copia di AURA mostra tutte le **13 connessioni**. In Impostazioni → Connessione filtra per tipo di servizio, scegli un provider, inserisci la tua chiave e premi **Salva e verifica** per leggere il catalogo. Scegli un modello e usa **Prova una risposta** prima di iniziare la conversazione.

Il filtro riguarda il servizio. Non tutti i modelli di un servizio con quota gratuita sono gratuiti: piano, paese, modello e quota del tuo account possono cambiare la disponibilità. Le tariffe aggiornate sono sempre raggiungibili dal collegamento **Piani e condizioni**. La prova di risposta può consumare credito; il catalogo non invia la tua conversazione.

| Connessione | Possibilità | Collegamento ufficiale |
| --- | --- | --- |
| OpenRouter | Modelli gratuiti con quota e modelli a consumo. `openrouter/free` sceglie fra i modelli gratuiti disponibili. AURA distingue i modelli a prezzo testuale zero da quelli a consumo quando il catalogo fornisce le tariffe. | [Modelli gratuiti e limiti](https://openrouter.ai/collections/free-models) |
| Google Gemini | Quota gratuita su alcuni modelli e piano a consumo. | [Piani](https://aistudio.google.com/docs/pricing) |
| Groq | Accesso gratuito con limiti e piani a consumo. | [Quote](https://console.groq.com/docs/rate-limits) |
| Mistral | Piano gratuito di valutazione e API a consumo. | [Piani](https://mistral.ai/pricing/) |
| Hugging Face | Crediti di prova limitati; consumo successivo secondo account e provider. | [Credito e fatturazione](https://huggingface.co/docs/inference-providers/pricing) |
| Cerebras | Eventuali crediti iniziali di prova e API a consumo. | [Piani](https://www.cerebras.ai/pricing) |
| OpenAI | API a consumo. La fatturazione API è distinta da ChatGPT; eventuali crediti promozionali dipendono dall’account. | [Tariffe API](https://developers.openai.com/api/docs/pricing) |
| Anthropic / Claude | API a consumo con credito del proprio account. | [Tariffe](https://platform.claude.com/docs/en/about-claude/pricing) |
| DeepSeek | API a consumo con saldo disponibile. | [Tariffe](https://api-docs.deepseek.com/quick_start/pricing) |
| xAI / Grok | API a consumo, con catalogo del proprio account. | [Modelli e tariffe](https://docs.x.ai/developers/models) |
| Ollama | Modello sul PC: installa il programma e un modello adatto all’hardware, quindi verifica il server. | [Download](https://ollama.com/download) |
| LM Studio | Modello sul PC: carica un modello e avvia il server locale. La chiave è facoltativa, secondo la sua configurazione. | [Server locale](https://lmstudio.ai/docs/developer/core/server) |
| Compatibile | Un servizio con Chat Completions compatibile, locale o HTTPS. Inserisci base URL, eventuale chiave e modello. | Consulta i termini del servizio scelto. |

## Il tuo menu può rimanere essenziale

Dopo una prova riuscita premi **Mantieni solo questo modello**. La selezione viene salvata soltanto nel tuo profilo e disattiva i fallback. Il pulsante **Mostra tutte le connessioni** riapre il catalogo, conservando modello e chiavi già salvati. Non avvia prove o chiamate a pagamento automaticamente.

Un blocco di credito, rete o quota del proprietario del progetto non viene copiato a chi scarica AURA. Ogni persona usa il proprio account. Anche la selezione personale del modello e l’account GitHub restano fuori dal repository.

## Dati e verifiche

Le chiavi restano sul PC e non sono incluse nelle esportazioni o nel repository. Le conversazioni vengono inviate al provider scelto; con Ollama o LM Studio selezionati esplicitamente non vengono inviati a un servizio AI cloud come fallback. Le voci online e il riconoscimento del browser sono funzioni separate.

OpenAI e xAI usano Responses con `store=false`; gli altri provider usano le rispettive API. Questo parametro non sostituisce le politiche di conservazione e trattamento del provider. Cerebras e xAI sono verificati mediante test con risposte simulate; disponibilità reale, credito e permessi richiedono la propria chiave e la prova locale. Nessun credito a pagamento viene acquistato o attivato da AURA.
