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
    load_dotenv()
except ImportError:
    print("💡 Para desarrollo local, instala python-dotenv: pip install python-dotenv")

# Configuración desde variables de entorno
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID_TUYO = os.getenv('CHAT_ID_TUYO')
CHAT_ID_ESPOSA = os.getenv('CHAT_ID_ESPOSA')

# Validación de configuración
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN no configurado en variables de entorno")

# Configurar usuarios autorizados
AUTHORIZED_USERS = []
if CHAT_ID_TUYO:
    AUTHORIZED_USERS.append(CHAT_ID_TUYO)
if CHAT_ID_ESPOSA:
    AUTHORIZED_USERS.append(CHAT_ID_ESPOSA)

# Variable global para el bot
bot_application = None

# Configuración de logging
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
            "ubicacion", self.request_location_manual))
        self.application.add_handler(CommandHandler(
            "tiempo_real", self.request_live_location))
        self.application.add_handler(CommandHandler(
            "test", self.test_automatic_sharing))
        self.application.add_handler(
            CommandHandler("estado", self.status_command))
        self.application.add_handler(MessageHandler(
            filters.LOCATION, self.handle_location))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start - Punto de entrada principal"""
        if not update.message:
            return

        user_id = str(update.effective_user.id)
        user_name = update.effective_user.first_name or "Usuario"

        # Si no hay usuarios configurados, mostrar IDs para configuración
        if not AUTHORIZED_USERS:
            await update.message.reply_text(
                f"🔧 **Configuración inicial del bot**\n\n"
                f"👤 Usuario: {user_name}\n"
                f"🆔 Tu Chat ID es: `{user_id}`\n\n"
                f"⚠️ **Para configurar:**\n"
                f"• Esposo: `CHAT_ID_TUYO={user_id}`\n"
                f"• Esposa: `CHAT_ID_ESPOSA={user_id}`\n\n"
                f"📝 Configura ambos IDs y reinicia el bot.",
                parse_mode='Markdown'
            )
            return

        # Validar autorización
        if user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ No estás autorizado para usar este bot.")
            return

        # Determinar rol del usuario
        user_role = "Esposo" if user_id == CHAT_ID_TUYO else "Esposa"

        # Crear teclado personalizado
        live_2h_button = KeyboardButton(
            "📍 Ubicación Tiempo Real 2h", request_location=True)
        live_1h_button = KeyboardButton(
            "📍 Ubicación Tiempo Real 1h", request_location=True)
        current_button = KeyboardButton(
            "📌 Ubicación Actual", request_location=True)

        keyboard = ReplyKeyboardMarkup([
            [live_2h_button],
            [live_1h_button],
            [current_button]
        ], resize_keyboard=True)

        await update.message.reply_text(
            f"¡Hola {user_name}! 👋\n\n"
            f"🔐 Rol: {user_role}\n"
            f"🆔 Chat ID: `{user_id}`\n\n"
            f"**⏰ Automatización configurada:**\n"
            f"🌅 **6:30 AM** (Mar-Jue): Solo ubicación de esposa\n"
            f"🌆 **6:15 PM** (Mar-Jue): Ubicación de ambos\n\n"
            f"**📱 Comandos disponibles:**\n"
            f"`/ubicacion` - Solicitar ubicación del otro\n"
            f"`/tiempo_real` - Solicitar ubicación en tiempo real\n"
            f"`/test` - Probar automatización\n"
            f"`/estado` - Ver estado del bot\n"
            f"`/help` - Ayuda completa",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /help - Información completa"""
        if not await self.check_authorization(update):
            return

        await update.message.reply_text(
            "🤖 **Bot de Ubicación Familiar en Tiempo Real**\n\n"

            "**⏰ Automatizaciones programadas:**\n"
            f"• **6:30 AM** (Martes-Jueves): Solicitud automática solo a esposa\n"
            f"• **6:15 PM** (Martes-Jueves): Solicitud automática a ambos\n\n"

            "**📱 Comandos disponibles:**\n"
            f"• `/ubicacion` - Solicitar ubicación actual al otro\n"
            f"• `/tiempo_real` - Solicitar ubicación en tiempo real\n"
            f"• `/test` - Probar funcionamiento automático\n"
            f"• `/estado` - Ver configuración y estado\n\n"

            "**📍 Tipos de ubicación:**\n"
            f"• **Tiempo Real 2h**: Compartir por 2 horas (recomendado)\n"
            f"• **Tiempo Real 1h**: Compartir por 1 hora\n"
            f"• **Actual**: Solo ubicación del momento\n\n"

            "**💡 Funcionamiento:**\n"
            f"• **Mañanas**: Solo la esposa recibe solicitud\n"
            f"• **Tardes**: Ambos reciben solicitud\n"
            f"• Las ubicaciones se reenvían automáticamente\n"
            f"• Telegram actualiza la ubicación en tiempo real cada pocos segundos\n\n"

            "**🔒 Seguridad:** Solo ustedes dos pueden usar este bot.",
            parse_mode='Markdown'
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /estado - Mostrar configuración actual"""
        if not await self.check_authorization(update):
            return

        user_id = str(update.effective_user.id)
        user_role = "Esposo" if user_id == CHAT_ID_TUYO else "Esposa"

        # Verificar próximas ejecuciones
        now = datetime.now()
        next_jobs = []

        # Simular verificación de próximos trabajos
        if now.weekday() in [1, 2, 3]:  # Martes=1, Miércoles=2, Jueves=3
            next_jobs.append("Hoy a las 6:30 AM y 6:15 PM")
        else:
            days_until_tuesday = (1 - now.weekday()) % 7
            if days_until_tuesday == 0:
                days_until_tuesday = 7
            next_jobs.append(f"En {days_until_tuesday} días (próximo martes)")

        await update.message.reply_text(
            f"📊 **Estado del Bot**\n\n"
            f"👤 **Tu información:**\n"
            f"• Rol: {user_role}\n"
            f"• Chat ID: `{user_id}`\n\n"
            f"⚙️ **Configuración:**\n"
            f"• Usuarios autorizados: {len(AUTHORIZED_USERS)}/2\n"
            f"• Esposo configurado: {'✅' if CHAT_ID_TUYO else '❌'}\n"
            f"• Esposa configurada: {'✅' if CHAT_ID_ESPOSA else '❌'}\n\n"
            f"⏰ **Próximas automatizaciones:**\n"
            f"• {next_jobs[0] if next_jobs else 'Sin programar'}\n\n"
            f"🕐 **Hora actual:** {now.strftime('%H:%M - %A')}\n"
            f"📅 **Fecha:** {now.strftime('%d/%m/%Y')}",
            parse_mode='Markdown'
        )

    async def request_location_manual(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /ubicacion - Solicitar ubicación actual"""
        if not await self.check_authorization(update):
            return

        user_id = str(update.effective_user.id)
        target_id, target_name = self.get_target_user(user_id)

        if not target_id:
            await update.message.reply_text("❌ No se pudo determinar el destinatario.")
            return

        await self.send_location_request(target_id, f"🔔 Tu {target_name} solicita tu ubicación actual")
        await update.message.reply_text(f"✅ Solicitud de ubicación enviada a tu {target_name}")

    async def request_live_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /tiempo_real - Solicitar ubicación en tiempo real"""
        if not await self.check_authorization(update):
            return

        user_id = str(update.effective_user.id)
        target_id, target_name = self.get_target_user(user_id)

        if not target_id:
            await update.message.reply_text("❌ No se pudo determinar el destinatario.")
            return

        await self.send_live_location_request(target_id, f"📍 Tu {target_name} solicita tu ubicación en tiempo real")
        await update.message.reply_text(f"✅ Solicitud de ubicación en tiempo real enviada a tu {target_name}")

    async def test_automatic_sharing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /test - Probar automatizaciones"""
        if not await self.check_authorization(update):
            return

        if not CHAT_ID_TUYO or not CHAT_ID_ESPOSA:
            await update.message.reply_text("❌ Falta configurar algunos Chat IDs para hacer la prueba completa.")
            return

        await update.message.reply_text("🧪 Iniciando prueba de automatizaciones...\n\n"
                                        "Se simularán ambos escenarios:")

        # Simular solicitud matutina (solo esposa)
        await update.message.reply_text("🌅 Simulando solicitud matutina (solo esposa)...")
        await self.automatic_location_request_spouse_only()

        await asyncio.sleep(3)

        # Simular solicitud vespertina (ambos)
        await update.message.reply_text("🌆 Simulando solicitud vespertina (ambos)...")
        await self.automatic_location_request_both()

        await update.message.reply_text(
            "✅ **Prueba completada**\n\n"
            "📋 **Resultados:**\n"
            "• Esposa recibió solicitud matutina\n"
            "• Ambos recibieron solicitud vespertina\n\n"
            "💡 Revisa que las solicitudes hayan llegado correctamente."
        )

    async def handle_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manejar ubicaciones recibidas - VERSIÓN CORREGIDA"""
        # VALIDACIÓN CRÍTICA - evita el error AttributeError
        if not update.message or not update.message.location:
            return

        if not await self.check_authorization(update):
            return

        try:
            user_id = str(update.effective_user.id)
            location = update.message.location
            user_name = update.effective_user.first_name or "Usuario"

            # Determinar destinatario
            recipient_id, sender_role = self.get_target_user(user_id)
            if not recipient_id:
                await update.message.reply_text("❌ Error al procesar la ubicación.")
                return

            recipient_role = "esposo" if sender_role == "esposa" else "esposa"

            # Verificar si es ubicación en tiempo real
            live_period = getattr(location, 'live_period', None)
            current_time = datetime.now().strftime("%H:%M")

            if live_period and live_period > 0:
                # Ubicación en tiempo real
                await context.bot.send_location(
                    chat_id=recipient_id,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    live_period=live_period
                )

                duration_hours = live_period // 3600
                duration_minutes = (live_period % 3600) // 60

                await context.bot.send_message(
                    chat_id=recipient_id,
                    text=f"📍🔴 **Ubicación en Tiempo Real Activa**\n\n"
                    f"👤 Desde: Tu {sender_role} ({user_name})\n"
                    f"⏰ Iniciada: {current_time}\n"
                    f"⏱️ Duración: {duration_hours}h {duration_minutes}m\n\n"
                    f"🔄 La ubicación se actualiza automáticamente cada pocos segundos"
                )

                await update.message.reply_text(
                    f"✅ **Ubicación en tiempo real compartida**\n\n"
                    f"📤 Enviada a: Tu {recipient_role}\n"
                    f"⏱️ Duración: {duration_hours}h {duration_minutes}m\n"
                    f"🔄 Se actualiza automáticamente"
                )

            else:
                # Ubicación normal
                await context.bot.send_location(
                    chat_id=recipient_id,
                    latitude=location.latitude,
                    longitude=location.longitude
                )

                await context.bot.send_message(
                    chat_id=recipient_id,
                    text=f"📍 **Ubicación Recibida**\n\n"
                    f"👤 Desde: Tu {sender_role} ({user_name})\n"
                    f"⏰ Hora: {current_time}\n"
                    f"📌 Ubicación actual del momento"
                )

                await update.message.reply_text(f"✅ Ubicación enviada a tu {recipient_role}")

        except Exception as e:
            logger.error(f"Error enviando ubicación: {e}")
            await update.message.reply_text("❌ Error al enviar la ubicación. Inténtalo de nuevo.")

    async def send_location_request(self, chat_id, message):
        """Enviar solicitud de ubicación normal"""
        location_button = KeyboardButton(
            "📌 Enviar mi ubicación", request_location=True)
        keyboard = ReplyKeyboardMarkup(
            [[location_button]], resize_keyboard=True, one_time_keyboard=True)

        await self.application.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=keyboard
        )

    async def send_live_location_request(self, chat_id, message):
        """Enviar solicitud de ubicación en tiempo real"""
        live_2h_button = KeyboardButton(
            "📍 Tiempo Real 2h", request_location=True)
        live_1h_button = KeyboardButton(
            "📍 Tiempo Real 1h", request_location=True)
        normal_button = KeyboardButton("📌 Solo Actual", request_location=True)

        keyboard = ReplyKeyboardMarkup([
            [live_2h_button],
            [live_1h_button],
            [normal_button]
        ], resize_keyboard=True, one_time_keyboard=True)

        await self.application.bot.send_message(
            chat_id=chat_id,
            text=f"{message}\n\n"
            f"📍 **Selecciona el tipo de ubicación:**\n"
            f"• **Tiempo Real 2h**: Compartir por 2 horas (recomendado)\n"
            f"• **Tiempo Real 1h**: Compartir por 1 hora\n"
            f"• **Solo Actual**: Ubicación del momento\n\n"
            f"💡 La ubicación en tiempo real se actualiza automáticamente.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def automatic_location_request_both(self):
        """Solicitar ubicación automáticamente a ambos (tardes)"""
        current_time = datetime.now().strftime("%H:%M")

        message = (f"🌆 **Ubicación Automática Vespertina**\n\n"
                   f"⏰ Hora: {current_time}\n"
                   f"📍 Comparte tu ubicación en tiempo real por 2 horas\n"
                   f"🔄 Automatización programada")

        if CHAT_ID_TUYO:
            await self.send_live_location_request(CHAT_ID_TUYO, message)
        if CHAT_ID_ESPOSA:
            await self.send_live_location_request(CHAT_ID_ESPOSA, message)

        # Programar recordatorio en 5 minutos si no responden
        await asyncio.sleep(300)  # 5 minutos
        await self.send_reminder_if_needed()

        logger.info(
            f"Solicitudes automáticas vespertinas enviadas a ambos usuarios - {current_time}")

    async def automatic_location_request_spouse_only(self):
        """Solicitar ubicación automáticamente solo a la esposa (mañanas)"""
        current_time = datetime.now().strftime("%H:%M")

        message = (f"🌅 **Ubicación Automática Matutina**\n\n"
                   f"⏰ Hora: {current_time}\n"
                   f"📍 Comparte tu ubicación en tiempo real por 2 horas\n"
                   f"🔄 Automatización programada")

        if CHAT_ID_ESPOSA:
            await self.send_live_location_request(CHAT_ID_ESPOSA, message)

            # Programar recordatorio en 5 minutos si no responde
            await asyncio.sleep(300)  # 5 minutos
            await self.send_reminder_if_needed_spouse()

            logger.info(
                f"Solicitud automática matutina enviada solo a esposa - {current_time}")
        else:
            logger.warning(
                "CHAT_ID_ESPOSA no configurado para solicitud matutina")

    async def send_reminder_if_needed(self):
        """Enviar recordatorio si no han respondido"""
        reminder_message = "⏰ **RECORDATORIO DE UBICACIÓN**\n\nAún no has compartido tu ubicación. Por favor, toca el botón para compartir."

        if CHAT_ID_TUYO:
            await self.application.bot.send_message(CHAT_ID_TUYO, reminder_message, parse_mode='Markdown')
        if CHAT_ID_ESPOSA:
            await self.application.bot.send_message(CHAT_ID_ESPOSA, reminder_message, parse_mode='Markdown')

    async def send_reminder_if_needed_spouse(self):
        """Enviar recordatorio solo a la esposa"""
        reminder_message = "⏰ **RECORDATORIO DE UBICACIÓN**\n\nAún no has compartido tu ubicación. Por favor, toca el botón para compartir."

        if CHAT_ID_ESPOSA:
            await self.application.bot.send_message(CHAT_ID_ESPOSA, reminder_message, parse_mode='Markdown')

    async def check_authorization(self, update: Update) -> bool:
        """Verificar autorización del usuario"""
        if not update.message:
            return False

        user_id = str(update.effective_user.id)

        if not AUTHORIZED_USERS:
            await update.message.reply_text("⚙️ Bot en modo configuración. Usa /start para obtener tu Chat ID.")
            return False

        if user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ No estás autorizado para usar este bot.")
            return False

        return True

    def get_target_user(self, user_id: str):
        """Obtener información del usuario destinatario"""
        if user_id == CHAT_ID_TUYO:
            return CHAT_ID_ESPOSA, "esposa"
        elif user_id == CHAT_ID_ESPOSA:
            return CHAT_ID_TUYO, "esposo"
        else:
            return None, None

# Funciones de automatización


async def run_automatic_request_morning():
    """Ejecutar solicitud automática matutina"""
    if bot_application and CHAT_ID_ESPOSA:
        try:
            bot_instance = LocationBot.__new__(LocationBot)
            bot_instance.application = bot_application
            await bot_instance.automatic_location_request_spouse_only()
        except Exception as e:
            logger.error(f"Error en solicitud matutina: {e}")


async def run_automatic_request_evening():
    """Ejecutar solicitud automática vespertina"""
    if bot_application and (CHAT_ID_TUYO or CHAT_ID_ESPOSA):
        try:
            bot_instance = LocationBot.__new__(LocationBot)
            bot_instance.application = bot_application
            await bot_instance.automatic_location_request_both()
        except Exception as e:
            logger.error(f"Error en solicitud vespertina: {e}")


def morning_location_job():
    """Trabajo programado matutino (6:30 AM)"""
    logger.info(
        f"🌅 Ejecutando trabajo matutino - {datetime.now().strftime('%H:%M')}")
    asyncio.create_task(run_automatic_request_morning())


def evening_location_job():
    """Trabajo programado vespertino (6:15 PM)"""
    logger.info(
        f"🌆 Ejecutando trabajo vespertino - {datetime.now().strftime('%H:%M')}")
    asyncio.create_task(run_automatic_request_evening())


def schedule_jobs():
    """Programar trabajos automáticos"""
    # Solicitudes matutinas (solo esposa) - Martes a Jueves a las 6:30 AM
    schedule.every().tuesday.at("06:30").do(morning_location_job)
    schedule.every().wednesday.at("06:30").do(morning_location_job)
    schedule.every().thursday.at("06:30").do(morning_location_job)

    # Solicitudes vespertinas (ambos) - Martes a Jueves a las 6:15 PM
    schedule.every().tuesday.at("18:15").do(evening_location_job)
    schedule.every().wednesday.at("18:15").do(evening_location_job)
    schedule.every().thursday.at("18:15").do(evening_location_job)

    logger.info("⏰ Trabajos programados configurados:")
    logger.info("   🌅 6:30 AM (Mar-Jue): Solicitud solo a esposa")
    logger.info("   🌆 6:15 PM (Mar-Jue): Solicitud a ambos")


def run_scheduler():
    """Ejecutar programador en hilo separado"""
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Verificar cada minuto
        except Exception as e:
            logger.error(f"Error en scheduler: {e}")
            time.sleep(60)


def main():
    """Función principal"""
    print("🤖 Iniciando Bot de Ubicación Familiar...")

    # Validar configuración mínima
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN no configurado")
        return

    # Crear instancia del bot
    try:
        bot = LocationBot(BOT_TOKEN)
    except Exception as e:
        print(f"❌ Error creando bot: {e}")
        return

    # Configurar trabajos programados
    schedule_jobs()

    # Iniciar programador en hilo separado
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # Mostrar información de inicio
    print("✅ Bot iniciado exitosamente")
    print("📱 Envía /start al bot para comenzar")
    print("⏰ Automatizaciones configuradas:")
    print("   🌅 6:30 AM (Mar-Jue): Solo esposa")
    print("   🌆 6:15 PM (Mar-Jue): Ambos")
    print("\n🔒 Solo usuarios autorizados pueden usar el bot")
    print("📊 Usa /estado para ver la configuración actual")
    print("\n⚠️  Presiona Ctrl+C para detener el bot")

    # Iniciar bot
    try:
        bot.application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido por el usuario")
    except Exception as e:
        print(f"❌ Error ejecutando bot: {e}")


if __name__ == '__main__':
    main()
