# Sincronizzazione Programmata via Cron per wiki-mcp (Remote Mode)

Aggiunta del supporto per la sincronizzazione periodica basata su espressioni **Cron standard** (es. `*/5 * * * *`, `0 * * * *`) in **Remote Mode**, mantenendo inalterata la modalità locale (`stdio`). Il sistema supporterà l'esecuzione **solo webhook**, **solo cron**, oppure **entrambi insieme (modalità ibrida GitOps)** con protezione da race condition tramite lock asincrono.

## Decisioni Architetturali Confermate
1. **Local Mode (`stdio`):** Inalterata. Continua a operare direttamente sul filesystem locale senza background tasks né comandi git.
2. **Remote Mode (`Streamable HTTP`):** Supporta espressioni cron standard a 5 campi tramite la variabile d'ambiente `SYNC_CRON` o il flag CLI `--sync-cron`.
3. **Nessun intervallo in secondi:** Esclusivamente sintassi cron standard (più espressiva e allineata agli standard di produzione).
4. **Le 3 Modalità Operative Remote:**
   - **Solo Webhook:** `SYNC_CRON` non configurato. Il server reagisce solo a `POST /webhook`.
   - **Solo Cron:** `SYNC_CRON` configurato (es. `*/10 * * * *`), nessun webhook configurato su GitHub. Ideale per ambienti privati/VPC senza ingress pubblico.
   - **Ibrida (Webhook + Cron):** Entrambi attivi. Il webhook garantisce reattività a latenza zero sui push; il cron garantisce self-healing ed eventual consistency contro webhook persi o riavvii.
5. **Concurrency Safety:** `asyncio.Lock` condiviso tra l'endpoint `POST /webhook` e il background runner del cron per prevenire `git pull` concorrenti.
6. **Dipendenza:** `croniter>=2.0.0` aggiunta a `pyproject.toml`.

---

## User Review Required

> [!NOTE]
> Il formato standard atteso per `SYNC_CRON` è il classico cron a 5 campi: `minute hour day-of-month month day-of-week` (es. `*/5 * * * *` per ogni 5 minuti, `0 * * * *` per ogni ora, `0 2 * * *` per ogni notte alle 02:00).
> Se il valore fornito non è valido, il server logga un errore esplicito all'avvio e fallisce tempestivamente (fail-fast).

---

## Proposed Changes

### wiki-mcp Core & Scheduler

#### [MODIFY] [pyproject.toml](file:///Users/paolo/Projects/wiki-mcp/pyproject.toml)
- Aggiungere `croniter>=2.0.0` alle `dependencies`.

#### [MODIFY] [git_sync.py](file:///Users/paolo/Projects/wiki-mcp/src/wiki_mcp/git_sync.py)
- Aggiungere un `asyncio.Lock` per serializzare i `git pull`.
- Aggiungere una struttura di stato in-memory per tracciare:
  - `last_sync_at`: timestamp ISO 8601 dell'ultima sincronizzazione
  - `last_sync_status`: `"synced"` | `"error"` | `"idle"`
  - `last_sync_trigger`: `"startup"` | `"webhook"` | `"cron"`
  - `last_sync_commit`: hash breve del commit corrente
  - `last_sync_error`: eventuale messaggio di errore

#### [NEW] [scheduler.py](file:///Users/paolo/Projects/wiki-mcp/src/wiki_mcp/scheduler.py)
- Implementare `CronGitSyncScheduler`:
  - Valida l'espressione cron su inizializzazione tramite `croniter`.
  - Loop asincrono resiliente (`asyncio.create_task`): calcola i secondi rimanenti alla prossima occorrenza (`croniter.get_next() - now`), attende con `asyncio.sleep`, e acquisisce il lock per eseguire `pull_repo_async(wiki_dir)`.
  - Gestione pulita delle eccezioni (un fallimento di rete o git pull non crasha il loop, ma registra l'errore e programma il prossimo tick).
  - Metodi `start()` e `stop()` per avvio e cancellazione cooperativa (`asyncio.CancelledError`).

---

### Remote Server & CLI Integration

#### [MODIFY] [remote.py](file:///Users/paolo/Projects/wiki-mcp/src/wiki_mcp/remote.py)
- Accettare parametro opzionale `sync_cron: Optional[str] = None`.
- Se `sync_cron` è presente, istanziare e avviare `CronGitSyncScheduler` all'interno del context manager `lifespan` di Starlette, arrestandolo allo shutdown.
- Nel route `POST /webhook`, acquisire il medesimo lock e aggiornare lo stato con `trigger="webhook"`.
- Aggiornare `GET /health` per esporre la configurazione e lo stato del sync:
  ```json
  {
    "status": "healthy",
    "wiki": "/data/wiki",
    "commit": "a1b2c3d",
    "sync": {
      "mode": "hybrid",           // "webhook" | "cron" | "hybrid"
      "cron_expression": "*/5 * * * *",
      "last_sync_at": "2026-09-08T12:05:00Z",
      "last_sync_trigger": "cron",
      "last_sync_status": "synced"
    }
  }
  ```

#### [MODIFY] [cli.py](file:///Users/paolo/Projects/wiki-mcp/src/wiki_mcp/cli.py)
- Aggiungere argomento CLI `--sync-cron` e lettura dell'ambiente `SYNC_CRON`.
- Passare `sync_cron` solo se `args.remote` è attivo; non toccare la logica standard di local mode.

#### [MODIFY] [README.md](file:///Users/paolo/Projects/wiki-mcp/README.md)
- Aggiungere `SYNC_CRON` alla tabella delle variabili d'ambiente.
- Documentare le 3 modalità (Webhook-only, Cron-only, Hybrid) ed esempi Docker Compose / CLI.

---

### Test Suite

#### [NEW] [test_scheduler.py](file:///Users/paolo/Projects/wiki-mcp/tests/test_scheduler.py)
- Test validazione cron (espressioni valide e non valide).
- Test del calcolo del prossimo tick.
- Test esecuzione del task con mock di `git_cmd_async`.
- Test stop/cancellazione del task in background.

#### [MODIFY] [test_remote_server.py](file:///Users/paolo/Projects/wiki-mcp/tests/test_remote_server.py)
- Test endpoint `/health` che rifletta la modalità corretta (`webhook`, `cron`, `hybrid`).
- Test di mutua esclusione tra webhook e cron sync via lock.

---

## Verification Plan

### Automated Tests
1. Eseguire l'installazione in venv di `croniter` ed eseguire i test con pytest:
   ```bash
   cd /Users/paolo/Projects/wiki-mcp && uv run pytest -v
   ```
2. Verificare che non ci siano regressioni sui test esistenti (`test_server.py`, `test_git_sync.py`, `test_remote_server.py`, `test_repo_sync.py`).

### Manual Verification
1. Avvio con `SYNC_CRON="* * * * *"` (ogni minuto) per verificare nei log l'avvio e l'esecuzione del sync.
2. Verifica dell'output di `curl http://localhost:8000/health` prima e dopo il minuto.
3. Verifica che con `uv run wiki-mcp --wiki-dir /Users/paolo/Projects/dev-wiki` (local mode) nulla sia cambiato e continui a funzionare via `stdio`.
