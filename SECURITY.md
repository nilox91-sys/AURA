# Sicurezza

AURA è un’app personale locale, verificata su Windows. Il server resta su loopback. Non usare un tunnel pubblico o cambiare l’ascolto per esporla in rete: manca un’infrastruttura di sicurezza per ospitare utenti remoti.

Le richieste del browser vengono controllate per origine e formato. Le credenziali non vengono restituite alle pagine e i messaggi di errore dei provider sono ripuliti. Le chiavi rimangono in chiaro in `.env`/`settings.json`; la sessione GitHub usa una chiave locale casuale esclusa da Git. Questi controlli non proteggono da software o utenti che possono leggere i file del tuo account Windows.

Per segnalare una vulnerabilità evita issue pubbliche con token, conversazioni, percorsi personali o database. Se il repository attiva la segnalazione privata GitHub, usa quella. Altrimenti segnala solo l’esistenza del problema e concorda un canale privato con il proprietario. Non inserire segreti negli esempi.
