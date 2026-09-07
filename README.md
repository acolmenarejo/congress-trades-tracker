# Congress Trades Tracker

Sigue las transacciones de bolsa de los miembros del Congreso de EEUU (STOCK Act
disclosures): API + web + ranking de mejores traders + bot de alertas Telegram.

**Estado actual: Fases 1, 2, 3 y 4 completas.** Backend + ingesta + API,
frontend (dashboard, feed, ranking, página de miembro, página de ticker con
velas), ranking con retorno estimado real, y bot de Telegram — bot + ingesta +
ranking corriendo 24/7 gratis en GitHub Actions.

**Repo**: https://github.com/acolmenarejo/congress-trades-tracker (público,
para minutos de GitHub Actions ilimitados gratis).
**Frontend**: https://congress-trades-tracker.netlify.app — el backend
todavía no está desplegado en ningún sitio público (ver sección de Despliegue),
así que el sitio en vivo no podrá cargar datos hasta que eso se resuelva.

⚠️ **Importante sobre el bot**: ningún sistema —este incluido— puede avisarte
*antes* de que el congresista publique su disclosure. La Ley STOCK permite hasta
45 días de retraso legal. Lo que este bot sí hace es avisarte en cuanto el
filing se hace público, cosa que muchas veces sigue dejando margen de reacción
real (ver ejemplo Pelosi/BE en el historial del proyecto: disclosure a 24-28
días del trade, y la acción siguió subiendo con fuerza semanas después).

## Fuentes de datos

| Fuente | Estado | Notas |
|---|---|---|
| Financial Modeling Prep (`fmp_congress`) | ✅ En vivo, Senado + Cámara | Requiere `FMP_API_KEY` gratuita ([registro](https://site.financialmodelingprep.com/register), plan Basic). Free tier: 250 req/día, pero el parámetro `page` queda fijo en `0` → solo trae los ~100 disclosures más recientes por cámara. Perfecto como fuente "en vivo": cada corrida trae lo último y el dedup por `unique_id` hace inofensivo repetir. Incluye `disclosure_date` real y bioguide id. |
| House (Cámara), `house_stock_watcher` | ✅ En vivo (backfill histórico) | El proyecto original `housestockwatcher.com` está caído (DNS no resuelve). Usamos el mirror activo [TattooedHead/house-stock-watcher-data](https://github.com/TattooedHead/house-stock-watcher-data), que publica el mismo formato JSON y da profundidad histórica completa (FMP solo cubre lo reciente). |
| Senate, `senate_stock_watcher` | ⚠️ Solo histórico (hasta marzo 2021) | [timothycarambat/senate-stock-watcher-data](https://github.com/timothycarambat/senate-stock-watcher-data) dejó de actualizarse en 2021. `efdsearch.senate.gov` (fuente oficial) bloquea tráfico no-navegador vía Akamai desde IPs de datacenter/CI, así que no se scrapea directamente. Cubre el histórico 2012-2021; FMP cubre lo reciente — entre ambos no hay hueco grande. |
| CongressInvests.com | ⚠️ Implementado pero endpoint sin confirmar | Agregador gratuito de ambas cámaras (100 req/día, sin key) mencionado en el encargo. En pruebas dio timeout de conexión (servicio caído en ese momento) y luego 404 en `/api/trades` (endpoint real no documentado públicamente). Con FMP cubriendo ya el hueco de "Senado en vivo", queda como fuente extra de bajo esfuerzo — el adaptador falla de forma segura si no responde. |

El pipeline combina las cuatro fuentes, deduplicando por un `unique_id` calculado
a partir de miembro normalizado + cámara + ticker + tipo + fecha + importe, así
que si una fuente falla o dos coinciden en el mismo trade no se duplica nada.
`fmp_congress` corre primero (fuente más fresca y con bioguide id), y las demás
solo rellenan huecos o añaden profundidad histórica.

## Estructura del repo

```
backend/
  app/            # FastAPI: modelos, esquemas, endpoints
  ingestion/      # fetch_trades.py + adaptadores por fuente + normalización
  data/           # congress_trades.db (SQLite, se commitea vía GitHub Actions)
frontend/         # (Fase 2)
bot/              # Bot de Telegram: comandos + alertas (Fase 4)
.github/workflows/
  ingest.yml      # cron cada 6h: ingesta + alertas de trades nuevos + commit de la DB
  bot-poll.yml    # cron cada 5 min: procesa comandos pendientes del bot (/watch, /list...)
```

## Backend — instalación local

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt

cp .env.example .env   # y rellena FMP_API_KEY (gratis, ver tabla de fuentes arriba)

# Ingesta inicial (tarda ~1-2 min, trae datos reales)
cd ingestion
python fetch_trades.py

# API
cd ..
uvicorn app.main:app --reload --port 8000
```

Endpoints disponibles:

- `GET /health`
- `GET /kpis` — totales globales
- `GET /trades?member=&ticker=&chamber=&party=&transaction_type=&date_from=&date_to=&limit=&offset=`
- `GET /members/ranking?sort_by=&limit=` — `sort_by` acepta `total_return_pct`,
  `annualized_return_pct`, `alpha_vs_sp500_pct`, `volume_estimate`,
  `trade_count`, `win_rate_pct` o `avg_disclosure_lag_days` (ranking de "peor
  cumplimiento" del plazo de 45 días de la Ley STOCK — mayor retraso primero)
- `GET /members/{match_key}`
- `GET /members/{match_key}/trades`
- `GET /tickers/{ticker}` — incluye la tabla de operaciones (comprador, fecha, importe)
- `GET /tickers/{ticker}/prices?days=` — histórico OHLC diario para el gráfico de velas

## Ranking de mejores traders (Fase 3)

`backend/ranking/calculate_rankings.py` recalcula el ranking una vez al día
(`.github/workflows/rankings.yml`, cron diario — es el job más lento, una
llamada a Yahoo Finance por ticker, con caché en `price_cache`). Metodología:

- Para cada compra de una acción normal, se emparejan con la venta posterior
  más próxima del mismo miembro+ticker (FIFO). Si no hay venta, se usa el
  precio actual ("todavía en cartera").
- Retorno de cada trade = `(precio_salida / precio_entrada - 1)`, ponderado
  por el importe medio del trade.
- `alpha_vs_sp500_pct` = el mismo cálculo pero restando el retorno de SPY en
  la misma ventana de fechas.
- Solo se consideran trades de los últimos 2 años (`RANKING_LOOKBACK_DAYS`)
  — el histórico de Senado 2012-2021 multiplicaría muchísimo el número de
  tickers a consultar en Yahoo por poco valor de ranking real; se puede subir
  ese número si en algún momento interesa un ranking "histórico total".
- Precios vía la chart API de Yahoo Finance directamente (con User-Agent de
  navegador) en vez de la librería `yfinance`, que daba 429 en pruebas.

**Extra no pedido explícitamente pero incluido**: la misma tabla sirve como
ranking de "peor cumplimiento" del plazo de 45 días de la Ley STOCK
(`avg_disclosure_lag_days`) — ángulo periodístico interesante que estaba en
el backlog original. En el frontend, cualquier miembro por encima de 45 días
se resalta en rojo.

## Ticker page (velas + compradores)

`/tickers/{TICKER}` en el frontend: gráfico de velas (OHLC diario, sin
librería externa — un `<Bar>` de Recharts con `shape` custom dibuja mecha +
cuerpo) con triángulos verdes/rojos incrustados en la fecha de cada compra/venta
del Congreso, más la tabla de operaciones (miembro, tipo, importe, fecha)
enlazada desde el Feed y desde la página de cada miembro.

## Frontend — instalación local

React + Vite + TypeScript + Tailwind v4 + Recharts + React Router.

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, con proxy /api -> backend en :8000
```

Páginas: Dashboard (KPIs + gráficos), Feed (tabla filtrable), Ranking
(ordenable, con datos reales), página de miembro (timeline de trades), página
de ticker (velas + tabla de compradores). Modo oscuro con toggle persistido en
`localStorage`. El backend debe estar corriendo en `:8000` para que el proxy
de Vite funcione (o define `VITE_API_BASE` para apuntar a un backend remoto).

Pendiente: gráfico de rendimiento simulado vs S&P 500 en la página de
miembro (simulador "qué hubiera pasado si copio a X"), heatmap de actividad
por sector.

## Ingesta periódica (gratis)

`.github/workflows/ingest.yml` corre `fetch_trades.py` cada 6 horas en GitHub
Actions y commitea `backend/data/congress_trades.db` de vuelta al repo. Es
idempotente: correrlo muchas veces no duplica filas. Cuando conectes el repo a
GitHub, añade el secret `FMP_API_KEY` en Settings → Secrets and variables →
Actions para que el cron también traiga datos en vivo.

## Bot de Telegram

Bot: **@CongressCalls_bot**. Llamadas directas a la Bot API (sin librería),
como pedía el encargo.

```bash
cd bot
python -m venv .venv   # o reutiliza backend/.venv, comparte las mismas deps + sqlalchemy
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # y rellena TELEGRAM_BOT_TOKEN (@BotFather -> /newbot)

python commands.py     # procesa mensajes pendientes una vez (esto es lo que corre el cron)
python notify.py       # envía alertas de trades nuevos no notificados aún
python poll_loop.py    # SOLO para desarrollo: repite commands.py cada 5s
```

Comandos disponibles (por chat, cada usuario tiene su propia lista):

- `/start` — se suscribe y arranca con la lista por defecto (Pelosi, Gottheimer, Khanna, Crenshaw, Mullin)
- `/watch NOMBRE` / `/unwatch NOMBRE`
- `/watchticker TICKER` / `/unwatchticker TICKER`
- `/list`

Arquitectura pensada para free tier: nada corre 24/7. `bot-poll.yml` (cron cada
5 min) procesa mensajes pendientes vía `getUpdates` con offset persistido en
SQLite (tabla `telegram_state`), e `ingest.yml` llama a `notify.py` justo
después de cada ingesta para avisar de trades nuevos que coincidan con algún
watch. El flag `Trade.notified` evita reenvíos si algo falla a mitad de proceso.

Falta por añadir cuando conectes GitHub: el secret `TELEGRAM_BOT_TOKEN` (Settings
→ Secrets and variables → Actions), igual que `FMP_API_KEY`.

## Despliegue gratuito

- **Bot Telegram + ingesta + ranking**: ya corren solos en GitHub Actions
  (ver arriba), no necesitan ningún servicio adicional.
- **Frontend**: desplegado en Netlify — https://congress-trades-tracker.netlify.app
  (`netlify.toml` en la raíz, build de `frontend/`). **Pendiente**: hacer el
  sitio público (quedó en "Private" bajo el visitor access del plan de prueba
  de la cuenta Netlify — Site configuration → Visitor access → marcar
  "Public"). Intenté meter el backend también como Netlify Function en Python
  para no depender de otro servicio, pero **esta versión de Netlify no soporta
  funciones en Python** (solo Node/Go/Rust o Edge Functions en Deno) — lo
  confirmé con `netlify functions:create --language python`, que falla con
  "Invalid language: python". Se descartó esa vía.
- **Backend**: aún sin desplegar en ningún sitio público — el frontend en
  Netlify no podrá cargar datos hasta que esto se resuelva. Como la DB se
  commitea al repo vía Actions, no hace falta un volumen persistente de pago
  en ningún proveedor: en cada deploy se parte del `.db` más reciente del
  repo. Opciones gratuitas típicas: Render (free tier, sin tarjeta) o Railway
  (trial). Una vez desplegado, configura `VITE_API_BASE` en Netlify con la URL
  pública y vuelve a desplegar el frontend.

## Backlog (ideas extra del encargo, no implementadas aún)

- Digest diario/semanal por Telegram (ahora mismo solo hay alertas instantáneas)
- Comparativa demócratas vs. republicanos más allá del gráfico compra/venta del dashboard
- Simulador "qué hubiera pasado si copio a X" (cartera virtual con evolución)
- Detección de trades inusuales cruzando calendario legislativo
- Webhook genérico (Discord/email) además de Telegram
- API pública de solo lectura documentada
- Heatmap de actividad por sector/ticker
