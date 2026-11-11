# Telegram Bot - Detector de No Seguidores de Instagram

Bot de Telegram desarrollado en Python con [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot) para procesar exportaciones de datos de Instagram (`.zip`), extraer los seguidores y seguidos, y reportar exactamente quiénes no te siguen de vuelta.

## 🚀 Requisitos

- Python 3.10+ (o [uv](https://github.com/astral-sh/uv))
- Token de bot de Telegram (proporcionado por [@BotFather](https://t.me/BotFather)) en el archivo `.env`.

## ▶️ Ejecución

```powershell
# Usando Python del entorno:
.venv\Scripts\python.exe bot.py

# O con el Python configurado en VS Code:
& 'C:\Users\ruben\.local\bin\python3.15.exe' bot.py
```

## 🛠️ Cómo funciona

1. **Recepción del ZIP**:
   - Envías el archivo `.zip` que descargas de Instagram al bot.
2. **Extracción y limpieza**:
   - Extrae automáticamente `following.html` y `followers_1.html`.
   - Limpia los datos removiendo URLs y marcas de tiempo, obteniendo listas limpias de nombres de usuario.
3. **Comparación**:
   - Identifica a todos los usuarios que están en `following` pero no en `followers` (quiénes no te siguen de vuelta).
4. **Respuesta completa**:
   - Envía en el chat de Telegram la lista completa con enlaces clicables a los perfiles de Instagram (dividida en partes si supera el límite de longitud).
   - Envía el archivo `no_te_siguen_de_vuelta.txt` descargable.
   - Imprime los totales y la lista completa en la consola del servidor.
