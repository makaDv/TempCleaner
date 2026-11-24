# Sicurezza / Security Policy

## Segnalare una vulnerabilità

Non aprire una issue pubblica per problemi di sicurezza.
Usa la segnalazione privata di GitHub: scheda **Security** > **Report a vulnerability** di questa repository.

Esempi di problemi da segnalare: il programma elimina file fuori da una cartella `Temp`/`tmp`, segue un collegamento simbolico o una junction, oppure ignora la conferma.

## Principi di sicurezza del progetto

- Elimina solo il contenuto di cartelle chiamate `Temp` o `tmp`, mai la cartella stessa.
- Non segue collegamenti simbolici né junction; controlla che ogni file stia davvero dentro la cartella Temp prima di eliminarlo.
- Non chiede privilegi di amministratore da solo.
- Nessuna connessione di rete, nessuna telemetria, nessuna dipendenza esterna.
- Prima di eliminare chiede di accettare l'[esclusione di responsabilità](DISCLAIMER.md).

## Versioni supportate

Solo l'ultima versione sul ramo `main` riceve correzioni.
