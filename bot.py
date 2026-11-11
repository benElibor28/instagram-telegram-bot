import html
import io
import json
import logging
import os
import re
import zipfile
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuración de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Directorio donde se guardarán los archivos extraídos y limpios
OUTPUT_DIR = os.path.join(os.getcwd(), "extracted_files")


def extract_followers(content: str) -> list[str]:
    """Extrae la lista limpia de nombres de usuario de seguidores.
    
    Elimina URLs y marcas de tiempo, dejando únicamente los nombres de usuario.
    Soporta formato HTML de Instagram y formato markdown/texto plano.
    """
    # 1. Búsqueda en enlaces HTML de Instagram
    usernames = re.findall(r'href="https?://(?:www\.)?instagram\.com/([^"/?#]+)"', content)

    # 2. Si no es HTML, búsqueda en formato texto/markdown: [usuario](https://...)
    if not usernames:
        usernames = re.findall(r'\[([^\]]+)\]\(https?://(?:www\.)?instagram\.com/[^\)]+\)', content)

    # Palabras clave y rutas que no corresponden a usuarios reales
    ignored = {"_u", "instagram", "about", "help", "legal", "terms"}
    return [u.strip() for u in usernames if u.strip() and u.strip().lower() not in ignored]


def extract_following(content: str) -> list[str]:
    """Extrae la lista limpia de nombres de usuario de seguidos.
    
    Elimina URLs y marcas de tiempo, dejando únicamente los nombres de usuario.
    Soporta formato HTML de Instagram y formato markdown/texto plano.
    """
    # 1. Búsqueda en encabezados <h2> de Instagram
    usernames = re.findall(r'<h2[^>]*>([^<]+)</h2>', content)

    # 2. Si no encontró en <h2>, buscar en enlaces /_u/<usuario>
    if not usernames:
        usernames = re.findall(r'https?://(?:www\.)?instagram\.com/_u/([^\s"/?#<]+)', content)

    # Palabras clave y títulos que no corresponden a usuarios
    ignored = {"_u", "instagram", "about", "help", "legal", "seguidos", "following"}
    return [u.strip() for u in usernames if u.strip() and u.strip().lower() not in ignored]


def find_not_following_back(following: list[str], followers: list[str]) -> list[str]:
    """Retorna los usuarios que están en following pero no en followers.
    
    Preserva el orden original y elimina posibles duplicados.
    """
    followers_set = {u.strip().lower() for u in followers}
    seen = set()
    not_following = []

    for u in following:
        norm = u.strip().lower()
        if norm not in followers_set and norm not in seen:
            seen.add(norm)
            not_following.append(u.strip())

    return not_following


async def send_not_following_list(
    update: Update,
    not_following: list[str],
) -> None:
    """Envía la lista de usuarios que no siguen de vuelta en fragmentos para no exceder límites de Telegram."""
    if not update.message:
        return

    total = len(not_following)
    if total == 0:
        await update.message.reply_html(
            "🎉 <b>¡Increíble!</b> Todos los usuarios a los que sigues te siguen de vuelta."
        )
        return

    # Tamaño de lote por mensaje para evitar superar el límite de 4096 caracteres
    batch_size = 40

    for i in range(0, total, batch_size):
        batch = not_following[i : i + batch_size]
        start_idx = i + 1
        end_idx = min(i + batch_size, total)

        formatted_items = [
            f"{idx}. <a href=\"https://www.instagram.com/{html.escape(user)}\">{html.escape(user)}</a>"
            for idx, user in enumerate(batch, start_idx)
        ]

        if i == 0:
            header = f"🚫 <b>Usuarios que no te siguen de vuelta ({total:,} en total):</b>\n"
            header += f"<i>Mostrando {start_idx}-{end_idx} de {total}:</i>\n\n"
        else:
            header = f"<i>(Continuación {start_idx}-{end_idx} de {total}):</i>\n\n"

        text = header + "\n".join(formatted_items)

        await update.message.reply_html(
            text,
            disable_web_page_preview=True,
        )

    # Enviar además el archivo .txt descargable
    file_content = "\n".join(not_following).encode("utf-8")
    doc_buffer = io.BytesIO(file_content)
    doc_buffer.name = "no_te_siguen_de_vuelta.txt"

    await update.message.reply_document(
        document=doc_buffer,
        caption=f"📄 Lista descargable de {total:,} cuentas que no te siguen de vuelta.",
    )


def get_welcome_text(user_mention: str) -> str:
    """Genera el mensaje de bienvenida detallado con instrucciones paso a paso e iconos."""
    return (
        f"👋 <b>¡Bienvenido/a {user_mention}!</b>\n\n"
        "🛡️ <b>Nota de Privacidad y Seguridad:</b>\n"
        "Este chat <b>no interactúa</b> con tu cuenta de Instagram ni con la de ningún usuario, "
        "no requiere contraseñas ni permisos. Solo interactúa y procesa de forma 100% privada "
        "los archivos que nos vas a enviar.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📲 <b>¿Cómo conseguir tus archivos de Instagram?</b>\n\n"
        "1️⃣ Abre la app de <b>Instagram</b> y dirígete a tu perfil.\n"
        "2️⃣ Accede a <b>Configuración y privacidad</b> ➔ <b>Centro de cuentas de Meta</b>.\n"
        "3️⃣ Selecciona <b>Tu información y permisos</b> ➔ <b>Descargar tu información</b>.\n"
        "4️⃣ Toca en <b>Descargar o transferir información</b> y selecciona tu perfil de Instagram.\n"
        "5️⃣ Elige la opción <b>Descargar en el dispositivo</b>.\n\n"
        "⚙️ <b>2 configuraciones más y muy necesarias:</b>\n"
        "• 📌 <b>Personalizar información:</b> Desmarca todas las casillas excepto la de "
        "<b>Conexiones</b> (contactos, seguidores y seguidos) ➔ Toca <b>[Guardar]</b>.\n"
        "• 📅 <b>Intervalo de fechas:</b> Selecciona <b>Desde el principio</b> ➔ Toca <b>[Guardar]</b>.\n"
        "• 📄 <i>Formato recomendado:</i> <b>HTML</b>.\n\n"
        "6️⃣ Toca en <b>Iniciar exportación</b> (o Crear archivos), ingresa tu contraseña y continúa.\n"
        "7️⃣ Esto iniciará la preparación de la carpeta; tomará unos minutos y recibirás notificaciones y correos "
        "directamente de Instagram informándote del estado.\n\n"
        "📦 <b>Paso final:</b>\n"
        "Cuando esté lista la carpeta comprimida en tus archivos (por ejemplo: "
        "<code>instagram-tu_usuario-fecha-código.zip</code>), <b>¡solo envíamela aquí por el chat!</b>\n\n"
        "La procesaré al instante y te mostraré exactamente quiénes no te siguen de vuelta. 🚀"
    )


# Comando: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /start dando la bienvenida al usuario con instrucciones completas."""
    user = update.effective_user
    mention = user.mention_html() if user else "Usuario"
    if update.message:
        await update.message.reply_html(get_welcome_text(mention))


# Comando: /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /help mostrando la guía de exportación y comandos."""
    user = update.effective_user
    mention = user.mention_html() if user else "Usuario"
    if update.message:
        await update.message.reply_html(get_welcome_text(mention))


# Manejador de documentos (.zip)
async def handle_zip_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recibe un archivo .zip, extrae, limpia, compara y envía la lista de usuarios que no te siguen."""
    if not update.message or not update.message.document:
        return

    doc = update.message.document
    file_name = doc.file_name or "archivo.zip"

    # Verificar que sea un archivo ZIP
    if not file_name.lower().endswith(".zip"):
        await update.message.reply_text(
            "⚠️ Por favor envía un archivo comprimido en formato .zip (exportado de Instagram)."
        )
        return

    # Verificar límite de 20 MB de la API de Telegram
    max_size_bytes = 20 * 1024 * 1024
    if doc.file_size and doc.file_size > max_size_bytes:
        await update.message.reply_text(
            "⚠️ El archivo supera los 20 MB (límite máximo permitido por la API de Telegram para bots)."
        )
        return

    status_message = await update.message.reply_text(
        f"📦 Recibiendo: <code>{file_name}</code>\n⏳ Descargando y procesando...",
        parse_mode="HTML",
    )

    try:
        # Descargar el archivo a memoria
        telegram_file = await context.bot.get_file(doc.file_id)
        file_bytes = await telegram_file.download_as_bytearray()
        zip_buffer = io.BytesIO(file_bytes)

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        found_files = {}

        with zipfile.ZipFile(zip_buffer, "r") as zip_ref:
            all_entries = zip_ref.namelist()

            for entry in all_entries:
                norm_entry = entry.replace("\\", "/").lower()

                # Buscar following.html
                if (
                    norm_entry.endswith("connections/followers_and_following/following.html")
                    or norm_entry.endswith("/followers_and_following/following.html")
                    or norm_entry.endswith("/following.html")
                    or norm_entry == "following.html"
                ):
                    found_files["following"] = entry

                # Buscar followers_1.html (o followers_*.html)
                elif (
                    norm_entry.endswith("connections/followers_and_following/followers_1.html")
                    or norm_entry.endswith("/followers_and_following/followers_1.html")
                    or norm_entry.endswith("/followers_1.html")
                    or norm_entry == "followers_1.html"
                ):
                    found_files["followers_1"] = entry

            if not found_files:
                sample_entries = "\n".join(f"• {e}" for e in all_entries[:8])
                await status_message.edit_text(
                    "❌ No se encontraron los archivos <code>following.html</code> ni <code>followers_1.html</code> "
                    "dentro del ZIP.\n\n"
                    f"Archivos encontrados (muestra):\n<code>{sample_entries}</code>",
                    parse_mode="HTML",
                )
                return

            followers_list = []
            following_list = []

            # Procesar y limpiar followers_1
            if "followers_1" in found_files:
                followers_raw = zip_ref.read(found_files["followers_1"]).decode("utf-8", errors="replace")
                followers_list = extract_followers(followers_raw)

                # Guardar HTML y lista limpia en extracted_files/
                with open(os.path.join(OUTPUT_DIR, "followers_1.html"), "w", encoding="utf-8") as f:
                    f.write(followers_raw)
                with open(os.path.join(OUTPUT_DIR, "followers.json"), "w", encoding="utf-8") as f:
                    json.dump(followers_list, f, indent=2, ensure_ascii=False)

            # Procesar y limpiar following
            if "following" in found_files:
                following_raw = zip_ref.read(found_files["following"]).decode("utf-8", errors="replace")
                following_list = extract_following(following_raw)

                # Guardar HTML y lista limpia en extracted_files/
                with open(os.path.join(OUTPUT_DIR, "following.html"), "w", encoding="utf-8") as f:
                    f.write(following_raw)
                with open(os.path.join(OUTPUT_DIR, "following.json"), "w", encoding="utf-8") as f:
                    json.dump(following_list, f, indent=2, ensure_ascii=False)

            # Comparar las dos listas
            not_following = find_not_following_back(following_list, followers_list)

            # Guardar lista de no seguidores
            with open(os.path.join(OUTPUT_DIR, "not_following_back.json"), "w", encoding="utf-8") as f:
                json.dump(not_following, f, indent=2, ensure_ascii=False)
            with open(os.path.join(OUTPUT_DIR, "not_following_back.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(not_following))

            # Guardar en user_data
            context.user_data["followers"] = followers_list
            context.user_data["following"] = following_list
            context.user_data["not_following"] = not_following

            # Imprimir en consola los resultados completos
            print("\n" + "=" * 60)
            print("📊 [COMPARACIÓN COMPLETADA CON ÉXITO]")
            print(f"👥 Total Followers (seguidores): {len(followers_list):,} usuarios")
            print(f"👤 Total Following (seguidos):   {len(following_list):,} usuarios")
            print(f"🚫 NO te siguen de vuelta:       {len(not_following):,} usuarios")
            print("=" * 60)
            print("Lista de usuarios que no te siguen:")
            for idx, user in enumerate(not_following, 1):
                print(f"{idx}. {user}")
            print("=" * 60 + "\n")

            logger.info(
                "Comparación lista: %d followers, %d following, %d no siguen",
                len(followers_list),
                len(following_list),
                len(not_following),
            )

        # Mensaje de resumen inicial con aclaración de cuentas desactivadas
        summary_text = (
            "✅ <b>¡Análisis completado con éxito!</b>\n\n"
            f"👥 <b>Tus seguidores (followers):</b> {len(followers_list):,} usuarios\n"
            f"👤 <b>Tus seguidos (following):</b> {len(following_list):,} usuarios\n"
            f"🚫 <b>No te siguen de vuelta:</b> {len(not_following):,} usuarios\n\n"
            "ℹ️ <i><b>Nota importante:</b> El número de tus seguidos puede variar respecto al que ves "
            "en tu app de Instagram, ya que la lista oficial descargada incluye cuentas que fueron desactivadas "
            "temporalmente o suspendidas por sus propios usuarios.</i>"
        )
        await status_message.edit_text(summary_text, parse_mode="HTML")

        # Enviar la lista de usuarios completa como respuesta
        await send_not_following_list(update, not_following)

    except zipfile.BadZipFile:
        await status_message.edit_text("❌ Error: El archivo no es un archivo .zip válido o está dañado.")
    except Exception as e:
        logger.error("Error al procesar el archivo ZIP:", exc_info=True)
        await status_message.edit_text(f"❌ Error al procesar el archivo: {str(e)}")


# Manejador de mensajes de texto (eco)
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde con el mismo mensaje que envía el usuario (eco)."""
    if update.message and update.message.text:
        await update.message.reply_text(f"Recibí: {update.message.text}")


# Manejador de errores
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra cualquier error que ocurra durante el manejo de actualizaciones."""
    logger.error("Excepción al procesar actualización:", exc_info=context.error)


def main() -> None:
    """Inicia y corre el bot de Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token or token == "tu_token_aqui":
        logger.error(
            "❌ ERROR: Variable TELEGRAM_BOT_TOKEN no configurada.\n"
            "Crea un archivo .env en la raíz del proyecto con la siguiente línea:\n"
            "TELEGRAM_BOT_TOKEN=tu_token_aqui\n"
            "Obtén tu token hablando con @BotFather en Telegram."
        )
        return

    # Crear la aplicación del bot
    application = ApplicationBuilder().token(token).build()

    # Registrar comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Registrar manejador de documentos (.zip)
    application.add_handler(MessageHandler(filters.Document.ALL, handle_zip_document))

    # Registrar mensajes de texto (eco)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Registrar manejador de errores
    application.add_error_handler(error_handler)

    # Iniciar bot mediante polling
    logger.info("🤖 Bot iniciado correctamente. Esperando mensajes... (Presiona Ctrl+C para detener)")
    application.run_polling()


if __name__ == "__main__":
    main()
