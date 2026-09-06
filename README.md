# Congress Trades Tracker

Sigue las transacciones de bolsa de los miembros del Congreso de EEUU (STOCK Act
disclosures): API + web + ranking de mejores traders + bot de alertas Telegram.

**Estado actual: Fase 1 completa (backend + ingesta + API).** Fases 2-4
(frontend, ranking con yfinance, bot Telegram) en construcción.

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
bot/              # (Fase 4)
.github/workflows/ingest.yml  # cron cada 6h que corre la ingesta y commitea la DB
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
- `GET /members/ranking?sort_by=&limit=` (vacío hasta Fase 3)
- `GET /members/{match_key}`
- `GET /members/{match_key}/trades`
- `GET /tickers/{ticker}`

## Ingesta periódica (gratis)

`.github/workflows/ingest.yml` corre `fetch_trades.py` cada 6 horas en GitHub
Actions y commitea `backend/data/congress_trades.db` de vuelta al repo. Es
idempotente: correrlo muchas veces no duplica filas. Cuando conectes el repo a
GitHub, añade el secret `FMP_API_KEY` en Settings → Secrets and variables →
Actions para que el cron también traiga datos en vivo.

## Despliegue gratuito (pendiente de activar)

Documentado aquí para cuando tengas cuentas creadas — de momento todo corre en
local:

- **Backend**: Railway o Fly.io (free tier). Como la DB se commitea al repo vía
  Actions, no hace falta un volumen persistente de pago: en cada deploy se
  parte del `.db` más reciente del repo.
- **Frontend**: Vercel (free tier), Fase 2.
- **Bot Telegram**: puede correr como job dentro del mismo cron de GitHub
  Actions, o como proceso separado en Railway/Fly, Fase 4.

## Backlog (ideas extra del encargo, no implementadas aún)

- Digest diario/semanal por Telegram
- Ranking de "peor cumplimiento" del plazo de 45 días del STOCK Act
- Comparativa demócratas vs. republicanos
- Simulador "qué hubiera pasado si copio a X"
- Detección de trades inusuales cruzando calendario legislativo
- Webhook genérico (Discord/email) además de Telegram
- API pública de solo lectura
