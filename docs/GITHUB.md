# GitHub: pubblicazione e accesso sono due funzioni distinte

## Pubblicare il progetto

Questa cartella contiene il sorgente pronto per un repository pubblico. Prima del caricamento controlla `git status --short` e il contenuto dei file selezionati. Non aggiungere manualmente file ignorati con `git add -f`.

Sono esclusi `.env`, impostazioni, database, sessioni, backup, audio, ambienti Python, modelli vocali, modelli Live2D e Cubism Core. Il README spiega come preparare i componenti opzionali. Rivedi la licenza proposta prima della prima pubblicazione.

Crea un repository vuoto chiamato **AURA** nel tuo profilo, quindi collega questa cartella al suo URL usando GitHub Desktop o Git. Il collegamento GitHub in Codex può aiutare a pubblicare il codice, ma non collega automaticamente il profilo dentro AURA.

## Accedi con GitHub in AURA

1. Apri [creazione OAuth App](https://github.com/settings/applications/new) nel tuo account.
2. Nome: **AURA personale**. Homepage: `http://127.0.0.1:5001`. Callback: `http://127.0.0.1:5001/login` (Device Flow non usa un callback, ma il modulo GitHub lo richiede).
3. Nella pagina dell’app abilita **Enable Device Flow**.
4. Copia il **Client ID** in AURA → Impostazioni → Account e dati. Il Client ID è pubblico; non generare né condividere un client secret per questa funzione.
5. Premi **Salva e accedi con GitHub**. Apri la pagina ufficiale indicata, inserisci il codice e autorizza l’app. AURA verifica il profilo usando `/user` senza richiedere scope aggiuntivi.
6. Solo dopo il collegamento puoi attivare **Richiedi l’accesso a GitHub** e salvare. L’account collegato diventa l’unico ammesso finché il blocco è attivo. Ogni browser deve accedere separatamente.

Questo flusso non concede accesso ai repository, non sincronizza conversazioni e non abilita Copilot o API di modelli. I token GitHub vengono scartati dopo la verifica. Scollegare AURA elimina il profilo locale; per revocare anche l’autorizzazione usa [Authorized OAuth Apps](https://github.com/settings/applications).

### Recuperare l’accesso locale

Se non riesci più ad accedere, chiudi AURA e avvia:

```text
start_aura.bat --reset-github-login
```

Quindi riavvia normalmente. Il comando disattiva il requisito GitHub senza cancellare chiavi o conversazioni. È un recupero per il proprietario del PC; non esporre AURA in rete.

Riferimento: [Device Flow ufficiale GitHub](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow).
