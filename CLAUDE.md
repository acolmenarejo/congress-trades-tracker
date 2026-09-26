# Congress Trades Tracker — contexto para Claude

Sigue transacciones bursátiles de miembros del Congreso de EEUU (STOCK Act).
Monorepo: `backend/` (FastAPI + SQLite), `frontend/` (React/Vite), `bot/`
(Telegram, wrappers finos sobre `backend/app/bot_*.py`).

## En vivo

- Frontend: https://congress-trades-tracker.netlify.app (Netlify)
- Backend: https://congress-trades-tracker-api.vercel.app (Vercel, Python nativo)
- Repo: https://github.com/acolmenarejo/congress-trades-tracker (público — necesario
  para minutos de GitHub Actions ilimitados gratis)
- Bot Telegram: @CongressCalls_bot

Todo gratis, sin tarjeta en ningún proveedor. Netlify y Vercel se desplegaron
vía sus CLIs (`netlify`, `vercel`), **no** están conectados al repo de GitHub
para auto-deploy — cada cambio requiere redeploy manual (ver más abajo).

## Arquitectura y por qué es así

**La base de datos es un fichero SQLite commiteado al repo**
(`backend/data/congress_trades.db`). GitHub Actions la actualiza y hace push
de vuelta. Esto es deliberado (capa gratuita sin volumen persistente de pago),
pero tiene una consecuencia importante: **Vercel sirve esa DB en modo
solo-lectura en producción**. Cualquier código que corra en el backend de
Vercel y necesite escribir (cache de precios, estado del bot) debe degradar
con gracia (try/except) o directamente no ejecutarse ahí — ver `app/prices.py`
y el diseño del bot más abajo.

**El bot de Telegram NO corre en Vercel.** Su lógica real vive en
`backend/app/bot_commands.py` y `backend/app/bot_notify.py` (import desde
`app/` a propósito — ver "Vercel solo empaqueta lo que está en `app/`" abajo),
pero se **ejecuta vía GitHub Actions**, que sí puede escribir y hacer commit.
Vercel solo actúa de disparador fiable:

```
cron-job.org (gratis, ping cada 1-2 min)
  → GET /internal/trigger-poll?secret=CRON_SECRET  (Vercel)
    → llama a la API de GitHub: workflow_dispatch de bot-poll.yml
      → GitHub Actions ejecuta bot/commands.py de verdad (lee/escribe la DB, commit+push)
```

Por qué: el `schedule:` de GitHub Actions es **muy poco fiable** a intervalos
de 5 min (medido: media de ~3h de retraso real entre ejecuciones, hasta 6h30).
`workflow_dispatch` vía API, en cambio, dispara casi al instante. `GITHUB_TOKEN`
y `CRON_SECRET` están guardados como env vars en Vercel (nunca expuestos al
pinger externo). Si algún día cron-job.org deja de disparar, revisa ahí primero
antes de sospechar del código.

**Vercel solo empaqueta de forma fiable el directorio del entrypoint
(`backend/app/`).** Cualquier import de un paquete hermano (`ranking/`,
`ingestion/`, `bot/`) se pierde en producción con `ModuleNotFoundError`,
aunque funcione perfecto en local — ya pasó dos veces (`ranking/prices.py` →
se movió a `app/prices.py`; lógica del bot → se copió a `app/bot_*.py`).
**Regla**: si un módulo lo necesita un endpoint de la API, vive en `app/`,
punto. Los scripts de `backend/ranking/` y `bot/` son entrypoints finos que
importan desde `app/` para no duplicar lógica, pero solo se ejecutan vía
GitHub Actions (ahí sí se puede importar cualquier cosa, `sys.path` se
configura a mano en cada script).

**Recharts v3 rompe compatibilidad con `<Scatter>` en ejes categóricos
compartidos.** `Scatter` construye su propia escala a partir del tamaño de
*su propio* array de datos, no del eje compartido con las velas — con pocos
trades sobre muchas velas, todos los marcadores se apilaban al principio del
gráfico. Arreglado usando los hooks reales de v3 (`useXAxisScale`/
`useYAxisScale`) en `CandlestickChart.tsx`. `<Customized>` está deprecado en
v3 (ya no recibe `xAxisMap`/`yAxisMap`) — no usarlo.

## Fuentes de datos (ver README.md para detalle completo)

4 fuentes con fallback cruzado, deduplicadas por `unique_id`: FMP (`fmp_congress`,
en vivo, requiere `FMP_API_KEY` gratis, limitado a page=0 → últimos ~100
disclosures), mirror de House en GitHub (histórico completo), mirror de Senado
en GitHub (muerto desde 2021, solo histórico), CongressInvests (intermitente,
no confirmado). `unitedstates/congress-legislators` enriquece con
partido/estado/comités/bioguide — **ninguna fuente de trades trae el partido**.

## Comandos que se repiten

Desplegar tras cualquier cambio (no hay auto-deploy):

```bash
# Backend (Vercel) — solo si tocaste backend/
cd /d/proyectos/congress-trades-tracker
npx --yes vercel deploy --prod --yes

# Frontend (Netlify) — casi siempre
cd frontend
VITE_API_BASE="https://congress-trades-tracker-api.vercel.app" npm run build
cd ..
netlify deploy --prod
```

Ranking + mejores trades (tarda ~1-2 min si el caché de precios está caliente,
~30 min en frío): `cd backend/ranking && python calculate_rankings.py`. Corre
solo vía `rankings.yml` (diario), pero se puede lanzar a mano con
`gh workflow run rankings.yml --repo acolmenarejo/congress-trades-tracker`.

Antes de tocar `backend/data/congress_trades.db` en local: **siempre
`git pull` primero** — los tres crons (`ingest.yml`, `bot-poll.yml` cada vez
que hay actividad real, `rankings.yml`) la modifican constantemente en remoto.
Un conflicto en ese binario se resuelve con `git checkout --ours` (o `--theirs`
según qué lado quieras conservar) — no se puede hacer merge de un SQLite.

Después de tocar `backend/ingestion/sources/legislators.py` o cualquier
enriquecimiento de `Member`: los campos ya rellenados (`committees`, etc.) no
se refrescan solos porque el código solo rellena si el campo está `NULL`. Para
forzar un refresco: `UPDATE members SET committees = NULL` (o el campo que
toque) y volver a correr `fetch_trades.py`.

## Verificación en local antes de desplegar

Playwright se usa para pruebas de humo del frontend contra datos reales, pero
**nunca debe quedar en `package.json`** — instalar con `--no-save` y/o
`npm uninstall playwright` después. Se ha colado por error varias veces esta
sesión; revisar `git diff frontend/package.json` antes de cada commit si se
usó Playwright.

## Estado a 2026-09-20 (última sesión)

Fases 1-4 completas y en producción. Diagnóstico en curso: el usuario reporta
"sin alertas nuevas desde el jueves" (17 sept). Investigado: **los 3 crons
están sanos** (`ingest.yml` cada ~6h, `bot-poll.yml` cada ~1-2 min vía el
trigger de Vercel, `rankings.yml` diario, todos `success`). El 15 de
septiembre sí se enviaron 7 alertas reales (Josh Gottheimer, verificado en
logs). Desde el 16 de septiembre, los trades nuevos detectados son todos de
miembros fuera de la watchlist (Pfluger, Donalds, Armstrong, Franklin, Taylor)
y ningún ticker vigilado — **no parece un bug, es una semana floja para la
lista de 21 miembros + 7 tickers vigilados actual**. Antes de investigar más
a fondo: confirmar con el usuario si esto encaja con lo que espera, y
considerar si vale la pena ampliar la watchlist o construir el "digest
diario" del backlog (avisa de actividad relevante aunque no haya match
exacto) en vez de seguir cazando un bug que probablemente no existe.

Pendiente de mejora (pedido explícitamente, no empezado): calidad de datos
más allá de lo ya arreglado (bioguide_id, comités, mojibake del guion largo),
y revisión general de mejoras de frontend.

## Alertas técnicas y de directivos (2026-09-26)

- `app/setups.py` + `setups.yml` (diario tras cierre): score 0-100 (acumulación
  tipo Konkorde, momentum, compresión, volumen, flujo del Congreso). Solo se
  alerta **largo con score ≥ 70** (máx. 3/día, 1 por ticker cada 30 días) con
  entrada/objetivo/stop por ATR. Backtest en `backend/setups/backtest.py`
  (necesita pandas, no está en requirements a propósito; caché de precios en
  `backend/setups/.cache/`, gitignorada) → `backtest_report.md`. Resultado:
  ~0,6 señales/semana, +1,5%/operación, positivo todos los años; los cortos
  pierden dinero en todos los niveles, por eso no se alertan. No reajustar
  pesos mirando el backtest sin separar in/out-of-sample.
- `app/insiders.py` + `insiders.yml` (cada 30 min, con `concurrency`): compras
  en mercado abierto (Form 4, código P) de SEC EDGAR. SEC exige email en el
  User-Agent → secreto `SEC_USER_AGENT`. Fuera de `bot-poll.yml` a propósito:
  un escaneo tarda minutos y solaparía pushes del SQLite.
- Ambas alertas van a **todos** los suscriptores, no dependen de la watchlist.
  `SetupSignal` guarda cada señal enviada para medir el acierto en vivo.

## Backlog (ver README.md para la lista completa)

Notas rápidas de lo no implementado: digest diario/telegram, comparativa
demócratas/republicanos más allá del gráfico de compra/venta, simulador
"qué hubiera pasado si copio a X", detección de trades inusuales cruzando
calendario legislativo, webhook genérico (Discord/email), heatmap por sector.
