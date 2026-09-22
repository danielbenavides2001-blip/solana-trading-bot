# Guía de Despliegue 24/7 en PaaS (Railway / Render) con Alertas a Telegram

Tienes toda la razón: **Oracle Cloud suele tener el mensaje "Out of capacity"**, haciendo que conseguir un servidor gratuito sea una odisea.

Las plataformas **PaaS (Platform as a Service)** como **Railway** y **Render** son la alternativa más rápida, moderna y viable: despliegas en 5 minutos y no dependen de tu ordenador.

---

## 📱 Paso 1: Configurar Alertas en tu Teléfono con Telegram (2 Minutos)

Para que el bot te avise al móvil cada vez que compra, vende o actualiza el trailing stop:

1. Abre **Telegram** en tu celular o PC y busca a: **`@BotFather`**.
2. Escribe `/newbot` y dale un nombre (ej. `SolanaTraderBot`).
3. Te dará un **Token HTTP API** (se ve algo como `7123456789:ABCdefGhIjk...`). Guárdalo.
4. Ahora busca en Telegram a: **`@userinfobot`**.
5. Te responderá con tu número de **`Id`** (ej. `123456789`).
6. Inicia una conversación con tu nuevo bot (dale al botón **Iniciar / Start**).

¡Listo! Ya tienes tu canal de alertas privado.

---

## 🚀 Opción A: Despliegue en Railway (Recomendada para Bots 24/7)

**Railway** es la plataforma ideal para bots porque no apaga los procesos en segundo plano.

1. Ve a **[railway.app](https://railway.app)** e inicia sesión con tu cuenta de GitHub o correo.
2. Crea un nuevo proyecto: **New Project** -> **Deploy from GitHub repo** (o usa el botón *Upload*).
3. Sube la carpeta del bot (`solana_trading_bot`).
4. En la pestaña **Variables**, añade:
   * `EXECUTION_MODE`: `PAPER` (o `LIVE` cuando quieras dinero real)
   * `TELEGRAM_BOT_TOKEN`: El token que te dio BotFather
   * `TELEGRAM_CHAT_ID`: Tu ID numérico
   * `BINANCE_API_KEY`: Tu clave de Binance (solo si estás en LIVE)
   * `BINANCE_API_SECRET`: Tu secreto de Binance (solo si estás en LIVE)
5. Railway compilará el `Dockerfile` automáticamente y el bot empezará a correr **24/7 de inmediato**. Recibirás un mensaje de Telegram confirmando que está en línea.

---

## 🌐 Opción B: Despliegue en Render (Gratuito con Keep-Alive)

Render ofrece un nivel gratuito para servicios web. Como le agregamos un servidor web interno de salud al bot, Render lo acepta como un **Web Service**:

1. Ve a **[render.com](https://render.com)** y crea una cuenta.
2. Haz clic en **New +** -> **Web Service**.
3. Conecta tu repositorio de GitHub donde tengas este código.
4. Render leerá el archivo `render.yaml` automáticamente:
   * **Runtime:** Python 3
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `python bot_engine.py`
5. En **Environment Variables**, añade tu `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
6. Haz clic en **Create Web Service**.

> [!TIP]
> **Evitar que Render se duerma en el plan gratuito:**
> Render duerme los servicios gratuitos si no reciben tráfico en 15 minutos. Para que corra 24/7 continuo:
> 1. Copia la URL pública que te da Render (ej: `https://solana-bot.onrender.com`).
> 2. Ve a **[uptimerobot.com](https://uptimerobot.com)** (100% gratis).
> 3. Añade un monitor tipo **HTTP(s)** con esa URL que haga ping cada 10 minutos.
> ¡Así tu bot se mantendrá despierto 24/7 sin pagar nada!

---

## 🔍 Panel Web Móvil
Además de las alertas de Telegram, cuando esté en la nube puedes abrir la URL de tu bot desde cualquier navegador para ver en tiempo real:
* Saldo actual
* Si hay posición abierta
* Cuántos trades ganadores/perdedores lleva
