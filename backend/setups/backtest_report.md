# Backtest de setups — 2026-09-26 12:14

Universo: 488 tickers (operados ≥5 veces por el Congreso desde 2021 + ETFs de commodities/sectores), liquidez ≥ $20M/día. Muestras cada 5 sesiones: 142118 (2020-06-11 → 2026-08-26). Horizonte 20 sesiones. Plan por defecto: stop 2.0 ATR, objetivo 3.0 ATR, entrada en la apertura siguiente.

**Sesgos conocidos:** supervivencia (solo tickers que Yahoo aún sirve), universo sesgado a large caps, muestras solapadas (no son independientes), sin comisiones ni slippage.

Referencia: exceso medio de *cualquier* muestra = +0.05%.

## In-sample (< 2025) — 103302 muestras

### Alcista: rendimiento por score

| Score | N | Exceso 20d vs SPY (a favor) | % aciertos dirección | Plan: ret. medio | Plan: % objetivo | Plan: % stop |
|---|---|---|---|---|---|---|
| [0, 30) | 50210 | +0.29% | 49% | +0.47% | 28% | 58% |
| [30, 40) | 17766 | +0.08% | 48% | +0.36% | 31% | 52% |
| [40, 50) | 20278 | -0.06% | 48% | +0.19% | 30% | 52% |
| [50, 60) | 12315 | -0.11% | 48% | +0.19% | 31% | 52% |
| [60, 70) | 2567 | -0.36% | 48% | +0.19% | 31% | 52% |
| [70, 101) | 166 | +1.44% | 57% | +1.76% | 40% | 40% |

### Bajista: rendimiento por score

| Score | N | Exceso 20d vs SPY (a favor) | % aciertos dirección | Plan: ret. medio | Plan: % objetivo | Plan: % stop |
|---|---|---|---|---|---|---|
| [0, 30) | 70207 | +0.01% | 52% | -0.28% | 24% | 65% |
| [30, 40) | 16357 | -0.20% | 52% | -0.78% | 23% | 59% |
| [40, 50) | 11349 | -0.59% | 51% | -1.03% | 22% | 58% |
| [50, 60) | 4606 | -0.56% | 50% | -1.13% | 21% | 56% |
| [60, 70) | 752 | -0.66% | 49% | -0.71% | 21% | 54% |
| [70, 101) | 31 | -1.41% | 52% | -3.91% | 10% | 58% |

## Out-of-sample (≥ 2025) — 38816 muestras

### Alcista: rendimiento por score

| Score | N | Exceso 20d vs SPY (a favor) | % aciertos dirección | Plan: ret. medio | Plan: % objetivo | Plan: % stop |
|---|---|---|---|---|---|---|
| [0, 30) | 20708 | -0.23% | 47% | +0.62% | 28% | 57% |
| [30, 40) | 6439 | -0.35% | 46% | +0.30% | 30% | 53% |
| [40, 50) | 6465 | -0.16% | 46% | +0.14% | 30% | 53% |
| [50, 60) | 4093 | +0.19% | 46% | +0.25% | 32% | 51% |
| [60, 70) | 1011 | +1.16% | 50% | +0.41% | 34% | 51% |
| [70, 101) | 100 | +3.03% | 59% | +1.76% | 41% | 45% |

### Bajista: rendimiento por score

| Score | N | Exceso 20d vs SPY (a favor) | % aciertos dirección | Plan: ret. medio | Plan: % objetivo | Plan: % stop |
|---|---|---|---|---|---|---|
| [0, 30) | 25208 | +0.06% | 53% | -0.47% | 22% | 66% |
| [30, 40) | 6027 | +0.50% | 55% | -0.64% | 24% | 57% |
| [40, 50) | 4708 | +0.35% | 54% | -0.88% | 23% | 56% |
| [50, 60) | 2312 | -0.09% | 49% | -0.94% | 21% | 56% |
| [60, 70) | 525 | -0.28% | 50% | -0.77% | 21% | 54% |
| [70, 101) | 36 | -0.26% | 61% | -2.80% | 17% | 50% |

## Qué bloque aporta (todo el periodo)

### long

| Bloque | Exceso medio si bloque ≥ mitad de su máximo | si no | Diferencia |
|---|---|---|---|
| acumulacion (N=58824) | -0.03% | +0.10% | -0.13% |
| momentum (N=60853) | -0.01% | +0.10% | -0.11% |
| compresion (N=27921) | +0.00% | +0.06% | -0.06% |
| volumen (N=6264) | +0.07% | +0.05% | +0.02% |
| congreso (N=1318) | +0.49% | +0.04% | +0.44% |

### short

| Bloque | Exceso medio si bloque ≥ mitad de su máximo | si no | Diferencia |
|---|---|---|---|
| distribucion (N=34570) | -0.17% | -0.01% | -0.17% |
| momentum (N=43232) | -0.16% | +0.00% | -0.16% |
| compresion (N=27921) | -0.00% | -0.06% | +0.06% |
| volumen (N=7564) | -0.41% | -0.03% | -0.39% |
| congreso (N=525) | +0.92% | -0.05% | +0.98% |

## Indicadores sueltos: exceso 20d por quintil (todo el periodo)

| Indicador | Q1 (bajo) | Q2 | Q3 | Q4 | Q5 (alto) | Q5−Q1 |
|---|---|---|---|---|---|---|
| rsi | +0.17% | +0.09% | -0.13% | +0.02% | +0.09% | -0.09% |
| cmf | +0.16% | +0.01% | -0.03% | -0.05% | +0.16% | +0.00% |
| obv_slope | +0.18% | +0.12% | +0.03% | -0.03% | -0.06% | -0.24% |
| mfi | +0.14% | +0.08% | -0.00% | -0.05% | +0.08% | -0.07% |
| bbw_pct | +0.02% | +0.10% | -0.05% | +0.00% | +0.17% | +0.15% |
| rs60 | +0.41% | +0.05% | -0.13% | -0.11% | +0.03% | -0.38% |
| dist_hi52 | +0.53% | +0.08% | -0.03% | -0.14% | -0.21% | -0.74% |
| rel_vol | -0.05% | -0.02% | -0.03% | +0.10% | +0.25% | +0.29% |
| atr_pct | -0.52% | -0.39% | -0.22% | +0.28% | +1.10% | +1.61% |
| nvi_above (False / True) | +0.15% | | | | +0.01% | -0.14% |
| congreso (neto vende / neutro / neto compra) | -0.09% | | +0.07% | | -0.03% | +0.06% |

## Rejilla stop/objetivo (ret. medio por operación)

Señales long con score ≥ 60 (N=3844)

| Stop ATR \ Objetivo ATR | 2.0 | 3.0 | 4.0 |
|---|---|---|---|
| 1.5 | +0.18% | +0.26% | +0.30% |
| 2.0 | +0.30% | +0.36% | +0.42% |
| 2.5 | +0.35% | +0.41% | +0.47% |

Señales short con score ≥ 60 (N=1344)

| Stop ATR \ Objetivo ATR | 2.0 | 3.0 | 4.0 |
|---|---|---|---|
| 1.5 | -0.43% | -0.85% | -1.07% |
| 2.0 | -0.38% | -0.86% | -1.16% |
| 2.5 | -0.53% | -1.04% | -1.33% |


## Compras de congresistas: qué marcaban los indicadores en las que funcionaron

| Cuartil resultado | N | long_score | rsi | cmf | obv_slope | mfi | bbw_pct | rs60 | dist_hi52 | rel_vol | atr_pct | nvi_above | exceso 20d |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Peor 25% | 1205 | 36.23 | 51.93 | 0.01 | 0.02 | 51.60 | 0.48 | 0.02 | 0.83 | 1.03 | 0.03 | 0.73 | -9.94% |
| Q2 | 1205 | 36.53 | 51.80 | 0.02 | 0.03 | 51.54 | 0.51 | -0.00 | 0.86 | 1.02 | 0.03 | 0.80 | -2.55% |
| Q3 | 1206 | 37.73 | 52.41 | 0.02 | 0.05 | 52.31 | 0.50 | 0.00 | 0.86 | 1.03 | 0.03 | 0.80 | +1.92% |
| Mejor 25% | 1204 | 35.93 | 50.91 | 0.00 | 0.00 | 51.46 | 0.52 | 0.01 | 0.81 | 1.04 | 0.03 | 0.73 | +10.64% |

Compras de congresistas con score largo ≥ 50: N=1395, exceso medio +0.12%; con score < 50: N=3425, -0.03%.
Todas las compras (desde la fecha de *disclosure*): N=4820, exceso medio +0.02%.
