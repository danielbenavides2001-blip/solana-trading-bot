# Bot Cuantitativo SOL/USDT (Binance Futuros 5x)

Sistema automatizado de trading para **SOL/USDT** en Binance Futuros, diseñado para cuentas de capital reducido ($21.79 USDT) con control estricto de riesgo y monitoreo en tiempo real.

---

## Características Principales

1. **Monitoreo en Tiempo Real**: Visualización en vivo en terminal con precios de SOL, volumen, volatilidad ATR, indicadores y estado de la cuenta.
2. **Estrategia Cuantitativa Robusta**:
   * **Filtro Macro (1h)**: Solo opera a favor de la tendencia principal (LONG si precio > EMA 50 > EMA 200, SHORT si precio < EMA 50 < EMA 200).
   * **Entradas Micro (15m)**: Detecta retrocesos hacia la media con rebote de RSI y confirmación de velas.
   * **Gestión de Riesgo Asimétrica (1:2.3)**: Arriesga ~$1.20 para ir a buscar ~$2.50 a $3.00 por trade.
   * **Trailing Stop a Breakeven**: Al alcanzar +1.5% de beneficio, mueve automáticamente el Stop Loss al precio de entrada para garantizar riesgo CERO.
3. **Seguridad Total**:
   * Modo **Paper Trading** por defecto para simular con datos en vivo sin arriesgar capital.
   * En modo real: **Margen Aislado** estricto a **5x**.

---

## Guía Rápida de Uso

### 1. Ver el Mercado en Tiempo Real
Haz doble clic en `run_monitor.bat` o ejecuta:
```powershell
python live_monitor.py
```
*Esto abrirá una pantalla en vivo que se actualiza cada 5 segundos mostrando el análisis del mercado de SOL y el estado de tu cuenta.*

### 2. Ejecutar el Bot en Simulación (Paper Trading)
Haz doble clic en `run_bot.bat` o ejecuta:
```powershell
python bot_engine.py --mode PAPER
```
*El bot evaluará el mercado continuamente y ejecutará compras/ventas virtuales registrando tus ganancias y pérdidas en `portfolio_state.json`.*

### 3. Evaluar el Historial (Backtesting)
Para probar la estrategia con los últimos 30 o 60 días de datos reales de Binance:
```powershell
python backtester.py --days 30
```

### 4. Pasar a Dinero Real (Cuando estés listo)
1. Copia `.env.example` a un archivo `.env`.
2. Introduce tu `BINANCE_API_KEY` y `BINANCE_API_SECRET`.
   *(Asegúrate de que en Binance solo tenga permisos de "Lectura" y "Futuros". NUNCA retiros).*
3. Cambia `EXECUTION_MODE=LIVE` en `.env` o ejecuta:
```powershell
python bot_engine.py --mode LIVE
```

---

## Archivos del Proyecto

* `config.py`: Parámetros de la estrategia, apalancamiento, comisiones y límites de capital.
* `market_data.py`: Conexión directa a Binance Futuros para obtener precios y velas históricas.
* `strategy.py`: Lógica matemática de indicadores (EMA, RSI, ATR, Bandas de Bollinger) y generador de señales.
* `live_monitor.py`: Panel visual interactivo en la terminal con actualización en tiempo real.
* `bot_engine.py`: Motor de ejecución que abre, gestiona (trailing stop) y cierra operaciones.
* `backtester.py`: Simulador histórico para verificar rendimiento con datos del mercado.
