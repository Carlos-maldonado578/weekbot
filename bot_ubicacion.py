import logging
import schedule
import time
import threading
import asyncio
import os
from datetime import datetime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Cargar variables de entorno desde .env en desarrollo local
try:
    from dotenv import load_dotenv
    load_dotenv()  # Carga el archivo .env si existe
except ImportError:
    print("💡 Para desarrollo local, instala python-dotenv: pip install python-dotenv")

# Configuración desde variables de entorno
BOT_TOKEN = os.getenv(
    'BOT_TOKEN') or "7660393593:AAEF3cYcT4dha2xJxb9WwGB314dPtv-osI"
CHAT_ID_TUYO = os.getenv('CHAT_ID_TUYO')
CHAT_ID_ESPOSA = os.getenv('CHAT_ID_ESPOSA')

# Validar que las variables estén configuradas
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN no configurado en variables de entorno")
if not CHAT_ID_TUYO:
    print("⚠️  CHAT_ID_TUYO no configurado - configúralo después de obtener el ID")
if not CHAT_ID_ESPOSA:
    print("⚠️  CHAT_ID_ESPOSA no configurado - configúralo después de obtener el ID")

# IDs autorizados (solo ustedes dos)
AUTHORIZED_USERS = []
if CHAT_ID_TUYO:
    AUTHORIZED_USERS.append(CHAT_ID_TUYO)
if CHAT_ID_ESPOSA:
    AUTHORIZED_USERS.append(CHAT_ID_ESPOSA)

# Variables globales para el bot
bot_application = None

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class LocationBot:
    def __init__(self, token):
        global bot_application
        self.application = Application.builder().token(token).build()
        bot_application = self.application
        self.setup_handlers()

    def setup_handlers(self):
        """Configurar manejadores de comandos y mensajes"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler(
            "solicitar_ubicacion", self.request_location_manual))
        self.application.add_handler(CommandHandler(
            "ubicacion_tiempo_real", self.request_live_location))
        self.application.add_handler(CommandHandler(
            "test", self.test_automatic_sharing))
        self.application.add_handler(MessageHandler(
            filters.LOCATION, self.handle_location))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        user_id = str(update.effective_user.id)
        user_name = update.effective_user.first_name

        # TEMPORAL: Permitir a cualquiera obtener su Chat ID para configuración inicial
        await update.message.reply_text(
            f"🔧 **Configuración inicial del bot**\n\n"
            f"👤 Usuario: {user_name}\n"
            f"🆔 Tu Chat ID es: `{user_id}`\n\n"
            f"⚠️ **Configurar en archivo .env:**\n"
            f"• Si eres el esposo: `CHAT_ID_TUYO={user_id}`\n"
            f"• Si eres la esposa: `CHAT_ID_ESPOSA={user_id}`\n\n"
            f"📝 **Siguiente paso:**\n"
            f"1. Ambos obtengan sus Chat IDs\n"
            f"2. Actualicen el archivo .env\n"
            f"3. Reinicien el bot\n\n"
            f"💡 Una vez configurado, este mensaje cambiará.",
            parse_mode='Markdown'
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /help"""
        await update.message.reply_text(
            "🤖 **Bot de Ubicación en Tiempo Real**\n\n"
            "**🕕 Automatizaciones activas:**\n"
            "• **6:30 AM** (Martes-Jueves): Solo ubicación de esposa en tiempo real por 2h\n"
            "• **6:15 PM** (Martes-Jueves): Ubicación de ambos en tiempo real por 2h\n\n"
            "**📱 Comandos manuales:**\n"
            "• `/solicitar_ubicacion` - Solicitar ubicación actual\n"
            "• `/ubicacion_tiempo_real` - Solicitar ubicación en tiempo real\n"
            "• `/test` - Probar compartir automático\n\n"
            "**⚙️ Funcionamiento:**\n"
            "• **Mañanas:** Solo la esposa recibe solicitud automática\n"
            "• **Tardes:** Ambos reciben solicitud automática\n"
            "• Telegram permite compartir por hasta 8 horas seguidas\n\n"
            "**💡 Tip:** Cuando recibas la solicitud, toca el botón de ubicación tiempo real para activarlo.",
            parse_mode='Markdown'
        )

    async def request_location_manual(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Solicitar ubicación actual manualmente"""
        user_id = str(update.effective_user.id)

        if user_id not in AUTHORIZED_USERS:
            return

        # Determinar a quién solicitar
        if user_id == CHAT_ID_TUYO:
            target_id = CHAT_ID_ESPOSA
            target_name = "esposa"
        else:
            target_id = CHAT_ID_TUYO
            target_name = "esposo"

        await self.send_location_request(target_id, f"🔔 Tu {target_name} solicita tu ubicación actual")
        await update.message.reply_text(f"✅ Solicitud enviada a tu {target_name}")

    async def request_live_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Solicitar ubicación en tiempo real manualmente"""
        user_id = str(update.effective_user.id)

        if user_id not in AUTHORIZED_USERS:
            return

        # Determinar a quién solicitar
        if user_id == CHAT_ID_TUYO:
            target_id = CHAT_ID_ESPOSA
            target_name = "esposa"
        else:
            target_id = CHAT_ID_TUYO
            target_name = "esposo"

        await self.send_live_location_request(target_id, f"📍 Tu {target_name} solicita tu ubicación en tiempo real")
        await update.message.reply_text(f"✅ Solicitud de ubicación tiempo real enviada a tu {target_name}")

    async def test_automatic_sharing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Probar el compartir automático"""
        user_id = str(update.effective_user.id)

        if user_id not in AUTHORIZED_USERS:
            return

        await update.message.reply_text("🧪 Iniciando prueba de ubicación automática...")

        # Simular solicitud automática matutina (solo esposa)
        await self.automatic_location_request_spouse_only()
        await asyncio.sleep(2)  # Esperar un poco
        # Simular solicitud automática vespertina (ambos)
        await self.automatic_location_request_both()

        await update.message.reply_text("✅ Prueba completada. La esposa recibió solicitud matutina, ambos recibieron solicitud vespertina.")

    async def handle_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manejar ubicaciones recibidas"""
        user_id = str(update.effective_user.id)

        if user_id not in AUTHORIZED_USERS:
            return

        location = update.message.location
        user_name = update.effective_user.first_name

        # Determinar destinatario
        if user_id == CHAT_ID_TUYO:
            recipient_id = CHAT_ID_ESPOSA
            sender_name = "Tu esposo"
        else:
            recipient_id = CHAT_ID_TUYO
            sender_name = "Tu esposa"

        # Verificar si es ubicación en tiempo real
        live_period = location.live_period if hasattr(
            location, 'live_period') else None

        if live_period:
            # Es ubicación en tiempo real
            await context.bot.send_location(
                chat_id=recipient_id,
                latitude=location.latitude,
                longitude=location.longitude,
                live_period=live_period  # Mantener el período en tiempo real
            )

            current_time = datetime.now().strftime("%H:%M")
            duration_hours = live_period // 3600
            duration_minutes = (live_period % 3600) // 60

            await context.bot.send_message(
                chat_id=recipient_id,
                text=f"📍🔴 {sender_name} ({user_name}) está compartiendo ubicación EN TIEMPO REAL\n"
                f"⏰ Iniciado a las {current_time}\n"
                f"⏱️ Duración: {duration_hours}h {duration_minutes}m"
            )

            await update.message.reply_text(f"✅ Ubicación en tiempo real compartida por {duration_hours}h {duration_minutes}m!")

        else:
            # Ubicación normal
            await context.bot.send_location(
                chat_id=recipient_id,
                latitude=location.latitude,
                longitude=location.longitude
            )

            current_time = datetime.now().strftime("%H:%M")
            await context.bot.send_message(
                chat_id=recipient_id,
                text=f"📍 {sender_name} ({user_name}) compartió su ubicación a las {current_time}"
            )

            await update.message.reply_text("✅ Ubicación enviada correctamente!")

    async def send_location_request(self, chat_id, message):
        """Enviar solicitud de ubicación normal"""
        location_button = KeyboardButton(
            "📌 Compartir mi ubicación", request_location=True)
        keyboard = ReplyKeyboardMarkup(
            [[location_button]], resize_keyboard=True, one_time_keyboard=True)

        await self.application.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=keyboard
        )

    async def send_live_location_request(self, chat_id, message):
        """Enviar solicitud de ubicación en tiempo real"""
        # Botones para diferentes duraciones
        live_1h_button = KeyboardButton(
            "📍 Tiempo Real 1h", request_location=True)
        live_2h_button = KeyboardButton(
            "📍 Tiempo Real 2h", request_location=True)
        normal_button = KeyboardButton(
            "📌 Ubicación Normal", request_location=True)

        keyboard = ReplyKeyboardMarkup([
            [live_2h_button],  # Opción recomendada arriba
            [live_1h_button],
            [normal_button]
        ], resize_keyboard=True, one_time_keyboard=True)

        await self.application.bot.send_message(
            chat_id=chat_id,
            text=f"{message}\n\n"
            f"📍 **Selecciona el tipo de ubicación:**\n"
            f"• **Tiempo Real 2h** - Recomendado para horarios programados\n"
            f"• **Tiempo Real 1h** - Para seguimiento corto\n"
            f"• **Normal** - Solo ubicación actual",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def automatic_location_request_both(self):
        """Solicitar ubicación automáticamente a ambos usuarios (tardes)"""
        current_time = datetime.now().strftime("%H:%M")

        # Mensaje para ambos
        message = (f"🌆 **Ubicación Automática Vespertina - {current_time}**\n\n"
                   f"📍 Por favor, comparte tu ubicación en **tiempo real por 2 horas**\n"
                   f"🔄 Esto es parte de la automatización programada")

        # Enviar a ambos usuarios
        await self.send_live_location_request(CHAT_ID_TUYO, message)
        await self.send_live_location_request(CHAT_ID_ESPOSA, message)

        print(
            f"📍 {current_time} - Solicitudes automáticas de ubicación enviadas a ambos")

    async def automatic_location_request_spouse_only(self):
        """Solicitar ubicación automáticamente solo a la esposa (mañanas)"""
        current_time = datetime.now().strftime("%H:%M")

        # Mensaje solo para la esposa
        message = (f"🌅 **Ubicación Automática Matutina - {current_time}**\n\n"
                   f"📍 Por favor, comparte tu ubicación en **tiempo real por 2 horas**\n"
                   f"🔄 Esto es parte de la automatización programada")

        # Enviar solo a la esposa
        await self.send_live_location_request(CHAT_ID_ESPOSA, message)

        print(
            f"📍 {current_time} - Solicitud automática de ubicación enviada solo a esposa")

# Funciones de programación automática


async def run_automatic_request_morning():
    """Ejecutar solicitud automática matutina (solo esposa)"""
    if bot_application:
        bot_instance = LocationBot.__new__(LocationBot)
        bot_instance.application = bot_application
        await bot_instance.automatic_location_request_spouse_only()


async def run_automatic_request_evening():
    """Ejecutar solicitud automática vespertina (ambos)"""
    if bot_application:
        bot_instance = LocationBot.__new__(LocationBot)
        bot_instance.application = bot_application
        await bot_instance.automatic_location_request_both()


def morning_location_job():
    """Trabajo matutino - 6:30 AM (solo esposa)"""
    print(f"🌅 {datetime.now().strftime('%H:%M')} - Ejecutando solicitud matutina automática (solo esposa)")
    asyncio.create_task(run_automatic_request_morning())


def evening_location_job():
    """Trabajo vespertino - 6:15 PM (ambos)"""
    print(f"🌆 {datetime.now().strftime('%H:%M')} - Ejecutando solicitud vespertina automática (ambos)")
    asyncio.create_task(run_automatic_request_evening())


def schedule_jobs():
    """Programar trabajos automáticos"""
    # Martes a Jueves - 6:30 AM
    schedule.every().tuesday.at("06:30").do(morning_location_job)
    schedule.every().wednesday.at("06:30").do(morning_location_job)
    schedule.every().thursday.at("06:30").do(morning_location_job)

    # Martes a Jueves - 6:15 PM
    schedule.every().tuesday.at("18:15").do(evening_location_job)
    schedule.every().wednesday.at("18:15").do(evening_location_job)
    schedule.every().thursday.at("18:15").do(evening_location_job)

    print("⏰ Trabajos programados:")
    print("   🌅 6:30 AM (Mar-Jue): Solicitud automática solo a esposa")
    print("   🌆 6:15 PM (Mar-Jue): Solicitud automática a ambos")


def run_scheduler():
    """Ejecutar el programador en un hilo separado"""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Verificar cada minuto


def main():
    """Función principal"""
    print("🤖 Iniciando Bot de Ubicación en Tiempo Real...")

    # Crear instancia del bot
    bot = LocationBot(BOT_TOKEN)

    # Programar trabajos automáticos
    schedule_jobs()

    # Iniciar programador en hilo separado
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    print("✅ Bot iniciado. Presiona Ctrl+C para detener.")
    print("📱 Envía /start al bot para obtener tu Chat ID")
    print("⏰ Ubicaciones automáticas:")
    print("   🌅 6:30AM (Mar-Jue): Solo esposa")
    print("   🌆 6:15PM (Mar-Jue): Ambos")

    # Iniciar bot
    bot.application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
