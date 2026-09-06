# Congress Trades Tracker

Sigue las transacciones de bolsa de los miembros del Congreso de EEUU (STOCK Act
disclosures): API + web + ranking de mejores traders + bot de alertas Telegram.

**Estado actual: Fase 1 completa (backend + ingesta + API).** Fases 2-4
(frontend, ranking con yfinance, bot Telegram) en construcción.

## Fuentes de datos

| Fuente | Estado | Notas |
|---|---|---|
| House (Cámara) | ✅ En vivo | El proyecto original `housestockwatcher.com` está caído (DNS no resuelve). Usamos el mirror activo [TattooedHead/house-stock-watcher-data](https://github.com/TattooedHead/house-stock-watcher-data), que publica el mismo formato JSON y se actualiza con filings reales y recientes. |
| Senate | ⚠️ Solo histórico (hasta marzo 2021) | [timothycarambat/senate-stock-watcher-data](https://github.com/timothycarambat/senate-stock-watcher-data) dejó de actualizarse en 2021. `efdsearch.senate.gov` (fuente oficial) bloquea tráfico no-navegador vía Akamai desde IPs de datacenter/CI, así que no se scrapea directamente. El código intenta además "reports" diarios recientes del mismo repo (`fetch_recent_daily_reports`) por si el scraping original se reanuda algún día — no cuesta nada extra si no hay archivos nuevos. |
| CongressInvests.com | ⚠️ Implementado pero no verificado | Agregador gratuito de ambas cámaras (100 req/día, sin key) mencionado en el encargo. Desde este entorno de desarrollo el host da timeout de conexión (posible bloqueo de red del sandbox, no necesariamente el servicio caído). El adaptor está listo (`backend/ingestion/sources/congress_invests.py`) y falla de forma segura (log + lista vacía) si no responde. Puede que sí funcione desde GitHub Actions/Railway — probar ahí. |

El pipeline combina las tres fuentes, deduplicando por un `unique_id` calculado
a partir de miembro normalizado + cámara + ticker + tipo + fecha + importe, así
que si una fuente falla o dos coinciden en el mismo trade no se duplica nada.

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
idempotente: correrlo muchas veces no duplica filas.

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
