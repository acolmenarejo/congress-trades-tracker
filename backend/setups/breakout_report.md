# Backtest de rupturas — 2026-10-10

Generado con `python breakout_backtest.py` (GitHub Actions, 542 tickers, 2020-2026, plan stop 2 ATR / objetivo 3 ATR, entrada en la apertura siguiente). Las columnas bbw 0.25 y 0.35 salieron iguales por un bug ya corregido (`is_base` ignoraba la variante).

Referencia (backtest_report.md): señal score ≥ 70 = +1,76%/operación con el mismo plan; muestra cualquiera ≈ +0,3-0,6%.

| Volumen ≥ | Base bbw ≤ | Periodo | N | Señales/semana | Ret. medio plan | % objetivo | % stop | Exceso 20d vs SPY |
|---|---|---|---|---|---|---|---|---|
| 1.3 | 0.15 | < 2025 | 965 | 4.1 | +0.35% | 33% | 47% | -0.29% |
| 1.3 | 0.15 | ≥ 2025 | 283 | 3.2 | +0.31% | 36% | 48% | +0.20% |
| 1.3 | 0.25 | < 2025 | 1473 | 6.3 | +0.52% | 34% | 46% | +0.10% |
| 1.3 | 0.25 | ≥ 2025 | 439 | 5.0 | +0.19% | 35% | 49% | +0.04% |
| 1.5 | 0.15 | < 2025 | 671 | 2.9 | +0.45% | 33% | 46% | -0.19% |
| 1.5 | 0.15 | ≥ 2025 | 192 | 2.2 | +0.20% | 36% | 48% | -0.59% |
| 1.5 | 0.25 | < 2025 | 997 | 4.2 | +0.63% | 35% | 45% | +0.22% |
| 1.5 | 0.25 | ≥ 2025 | 311 | 3.6 | +0.17% | 34% | 49% | -0.80% |
| 2.0 | 0.15 | < 2025 | 297 | 1.3 | +0.59% | 31% | 43% | -0.27% |
| 2.0 | 0.15 | ≥ 2025 | 85 | 1.0 | +0.06% | 32% | 48% | -1.30% |
| 2.0 | 0.25 | < 2025 | 447 | 1.9 | +0.76% | 33% | 42% | -0.14% |
| 2.0 | 0.25 | ≥ 2025 | 143 | 1.7 | +0.38% | 33% | 46% | -0.66% |

Variante por defecto (vol ≥ 1.5, bbw ≤ 0.25), por score y volatilidad:
- score < 50: N=521, ret. medio +0.39%, objetivo 32%, exceso +0.05%
- score 50-69: N=754, ret. medio +0.51%, objetivo 35%, exceso -0.06%
- score ≥ 70: N=33, ret. medio +3.03%, objetivo 58%, exceso -0.43%
- ATR < 2,5%: N=788, ret. medio +0.52%, objetivo 35%, exceso -0.30%
- ATR ≥ 2,5%: N=520, ret. medio +0.53%, objetivo 33%, exceso +0.39%

**Conclusión:** ninguna variante bate al azar de forma consistente fuera de muestra. Solo se avisa para tickers que el usuario ya sigue, etiquetado como no probado.
