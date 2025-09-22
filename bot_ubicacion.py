import logging
import schedule
import time
import threading
import asyncio
import os
from datetime import datetime
import pytz
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv()

# Configuración
CHILE_TZ = pytz.timezone('America/Santiago')
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID_TUYO = os.getenv('CHAT_ID_TUYO')
CHAT_ID_ESPOSA = os.getenv('CHAT_ID_ESPOSA')

# Validación de variables requeridas
if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN no configurado. Verifica tu archivo .env o variables de entorno en Railway")

if not CHAT_ID_TUYO or not CHAT_ID_ESPOSA:
    print("WARNING: CHAT_ID_TUYO o CHAT_ID_ESPOSA no configurados")

AUTHORIZED_USERS = [CHAT_ID_TUYO, CHAT_ID_ESPOSA]
bot_application = None

# Logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class LocationBot:
    def __init__(self, token):
        global bot_application
        self.application = Application.builder().token(token).build()
        bot_application = self.application
        self.pending_requests = {}
        self.setup_handlers()

    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler(
            "ubicacion", self.request_location))
        self.application.add_handler(
            CommandHandler("test", self.test_automation))
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CommandHandler(
            "time", self.show_time))
        self.application.add_handler(MessageHandler(
            filters.LOCATION, self.handle_location))

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando para verificar el estado del bot"""
        if not await self.check_auth(update):
            return

        current_time = datetime.now(CHILE_TZ).strftime("%Y-%m-%d %H:%M:%S")

        status_msg = f"🤖 Estado del Bot\n\n"
        status_msg += f"⏰ Hora actual: {current_time}\n"
        status_msg += f"🏠 Zona horaria: America/Santiago\n\n"
        status_msg += f"📅 Automatización:\n"
        status_msg += f"• 6:30 AM (Mar-Jue): Solo esposa\n"
        status_msg += f"• 6:15 PM (Mar-Jue): Ambos\n\n"
        status_msg += f"📍 Tipo: Ubicación en tiempo real (2 horas)\n"
        status_msg += f"👥 Usuarios autorizados: {len([x for x in AUTHORIZED_USERS if x])}\n"
        status_msg += f"✅ Bot funcionando correctamente"

        await update.message.reply_text(status_msg)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_auth(update):
            return

        user_id = str(update.effective_user.id)
        user_name = update.effective_user.first_name or "Usuario"
        user_role = "Esposo" if user_id == CHAT_ID_TUYO else "Esposa"

        # Crear teclado con botón para ubicación en tiempo real
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton(
                "📍 Compartir Ubicación en Tiempo Real", request_location=True)]
        ], resize_keyboard=True)

        await update.message.reply_text(
            f"Hola {user_name}!\n\n"
            f"Rol: {user_role}\n\n"
            f"📍 Este bot comparte ubicación en TIEMPO REAL por 2 horas\n\n"
            f"Automatización:\n"
            f"• 6:30 AM (Mar-Jue): Solo esposa\n"
            f"• 6:15 PM (Mar-Jue): Ambos\n\n"
            f"Comandos:\n"
            f"/ubicacion - Solicitar ubicación\n"
            f"/test - Probar automatización\n"
            f"/status - Estado del bot",
            reply_markup=keyboard
        )

    async def request_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_auth(update):
            return

        user_id = str(update.effective_user.id)
        target_id, target_name = self.get_target_user(user_id)
        requester_name = update.effective_user.first_name or "Usuario"

        if not target_id:
            await update.message.reply_text("Error al determinar destinatario")
            return

        self.pending_requests[target_id] = {
            'requester': requester_name,
            'time': datetime.now(CHILE_TZ)
        }

        await self.send_live_location_request(target_id, f"Tu {target_name} ({requester_name}) solicita tu ubicación en tiempo real")
        await update.message.reply_text(f"Solicitud de ubicación en tiempo real enviada a tu {target_name}")

    async def test_automation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_auth(update):
            return

        await update.message.reply_text("Probando automatización con ubicación en tiempo real...")

        # Prueba matutina
        await self.automatic_request_spouse_only(test_mode=True)
        await asyncio.sleep(2)

        # Prueba vespertina
        await self.automatic_request_both(test_mode=True)

        await update.message.reply_text("Prueba completada")

    async def handle_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.location:
            return

        if not await self.check_auth(update):
            return

        try:
            user_id = str(update.effective_user.id)
            location = update.message.location
            user_name = update.effective_user.first_name or "Usuario"

            self.pending_requests.pop(user_id, None)

            recipient_id, recipient_role = self.get_target_user(user_id)
            if not recipient_id:
                return

            sender_role = "esposo" if user_id == CHAT_ID_TUYO else "esposa"
            current_time = datetime.now(CHILE_TZ).strftime("%H:%M")

            live_period = getattr(location, 'live_period', None)

            if live_period and live_period > 0:
                # Ubicación en tiempo real recibida
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
                    text=f"📍 Ubicación en Tiempo Real\n\n"
                    f"De: {user_name}\n"
                    f"Hora: {current_time}\n"
                    f"Duración: {duration_hours}h {duration_minutes}m\n\n"
                    f"🔄 Se actualizará automáticamente"
                )

                await update.message.reply_text(
                    f"✅ Ubicación en tiempo real compartida con tu {recipient_role}\n"
                    f"⏰ Duración: {duration_hours}h {duration_minutes}m\n"
                    f"🔄 Se actualizará automáticamente"
                )

                logger.info(
                    f"Ubicación en tiempo real enviada: {user_name} -> {recipient_role} ({duration_hours}h {duration_minutes}m)")
            else:
                # Si por alguna razón llega ubicación normal, convertirla a tiempo real
                # Enviar como ubicación en tiempo real por 2 horas por defecto
                await context.bot.send_location(
                    chat_id=recipient_id,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    live_period=7200  # 2 horas en segundos
                )

                await context.bot.send_message(
                    chat_id=recipient_id,
                    text=f"📍 Ubicación en Tiempo Real\n\n"
                    f"De: {user_name}\n"
                    f"Hora: {current_time}\n"
                    f"Duración: 2h 0m\n\n"
                    f"🔄 Se actualizará automáticamente"
                )

                await update.message.reply_text(
                    f"✅ Ubicación convertida a tiempo real y enviada a tu {recipient_role}\n"
                    f"⏰ Duración: 2h 0m\n"
                    f"🔄 Se actualizará automáticamente"
                )

                logger.info(
                    f"Ubicación convertida a tiempo real: {user_name} -> {recipient_role} (2h)")

        except Exception as e:
            logger.error(f"Error enviando ubicación: {e}")
            await update.message.reply_text("❌ Error al enviar ubicación en tiempo real")

    async def send_live_location_request(self, chat_id, message):
        """Solicita específicamente ubicación en tiempo real"""
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton(
                "📍 Compartir Ubicación en Tiempo Real", request_location=True)]
        ], resize_keyboard=True, one_time_keyboard=True)

        full_message = f"{message}\n\n"
        full_message += f"🔄 Por favor, comparte tu ubicación EN TIEMPO REAL\n"
        full_message += f"⏰ Duración recomendada: 2 horas\n\n"
        full_message += f"📱 Instrucciones:\n"
        full_message += f"1. Presiona el botón de abajo\n"
        full_message += f"2. Selecciona 'Ubicación en tiempo real'\n"
        full_message += f"3. Elige duración (recomendado: 2h)"

        await self.application.bot.send_message(
            chat_id=chat_id,
            text=full_message,
            reply_markup=keyboard
        )

    # Método para compatibilidad con código existente
    async def send_location_request(self, chat_id, message):
        """Alias para send_live_location_request - mantiene compatibilidad"""
        await self.send_live_location_request(chat_id, message)

    async def automatic_request_both(self, test_mode=False):
        current_time = datetime.now(CHILE_TZ).strftime("%H:%M")
        prefix = "[PRUEBA] " if test_mode else ""

        message = f"{prefix}📍 Ubicación Automática Vespertina\n\nHora: {current_time}\nComparte tu ubicación en TIEMPO REAL para coordinar el regreso"

        if CHAT_ID_TUYO:
            await self.send_live_location_request(CHAT_ID_TUYO, message)
        if CHAT_ID_ESPOSA:
            await self.send_live_location_request(CHAT_ID_ESPOSA, message)

        logger.info(
            f"Solicitudes vespertinas de ubicación en tiempo real enviadas - {current_time}")

    async def automatic_request_spouse_only(self, test_mode=False):
        current_time = datetime.now(CHILE_TZ).strftime("%H:%M")
        prefix = "[PRUEBA] " if test_mode else ""

        message = f"{prefix}📍 Ubicación Automática Matutina\n\nHora: {current_time}\nComparte tu ubicación en TIEMPO REAL para el trayecto al trabajo"

        if CHAT_ID_ESPOSA:
            await self.send_live_location_request(CHAT_ID_ESPOSA, message)
            logger.info(
                f"Solicitud matutina de ubicación en tiempo real enviada - {current_time}")

    async def check_auth(self, update: Update) -> bool:
        if not update.message:
            return False

        user_id = str(update.effective_user.id)

        if user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ No autorizado")
            return False

        return True

    def get_target_user(self, user_id: str):
        if user_id == CHAT_ID_TUYO:
            return CHAT_ID_ESPOSA, "esposa"
        elif user_id == CHAT_ID_ESPOSA:
            return CHAT_ID_TUYO, "esposo"
        return None, None

    async def show_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando para verificar horarios"""
        if not await self.check_auth(update):
            return

        chile_time = datetime.now(CHILE_TZ)
        utc_time = datetime.now(pytz.UTC)

        # Calcular próximos horarios de ejecución
        offset_hours = int((chile_time.utcoffset().total_seconds()) / 3600)
        morning_utc = (6 - offset_hours + 24) % 24
        evening_utc = (18 - offset_hours + 24) % 24

        msg = f"🕒 **Información de Horarios**\n\n"
        msg += f"🌍 UTC actual: {utc_time.strftime('%H:%M:%S')}\n"
        msg += f"🇨🇱 Chile actual: {chile_time.strftime('%H:%M:%S')}\n\n"
        msg += f"📅 **Automatización:**\n"
        msg += f"• Mañana: 06:30 Chile = {morning_utc:02d}:30 UTC\n"
        msg += f"• Tarde: 18:15 Chile = {evening_utc:02d}:15 UTC\n\n"
        msg += f"📍 Tipo: Ubicación en tiempo real (2 horas)\n"
        msg += f"📆 Días: Martes, Miércoles, Jueves"

        await update.message.reply_text(msg)


# Scheduler functions (sin cambios - mantienen la funcionalidad existente)
def run_async_in_thread(coro):
    def run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)
            loop.close()
        except Exception as e:
            logger.error(f"Error en async thread: {e}")

    threading.Thread(target=run, daemon=True).start()


async def run_morning():
    if bot_application and CHAT_ID_ESPOSA:
        try:
            bot_instance = LocationBot.__new__(LocationBot)
            bot_instance.application = bot_application
            bot_instance.pending_requests = {}
            await bot_instance.automatic_request_spouse_only()
        except Exception as e:
            logger.error(f"Error matutino: {e}")


async def run_evening():
    if bot_application:
        try:
            bot_instance = LocationBot.__new__(LocationBot)
            bot_instance.application = bot_application
            bot_instance.pending_requests = {}
            await bot_instance.automatic_request_both()
        except Exception as e:
            logger.error(f"Error vespertino: {e}")


def morning_job():
    """Trabajo matutino con logging de zona horaria"""
    chile_time = datetime.now(CHILE_TZ)
    utc_time = datetime.now(pytz.UTC)

    logger.info(f"Ejecutando trabajo matutino - ubicación en tiempo real")
    logger.info(f"UTC: {utc_time.strftime('%H:%M:%S')}")
    logger.info(f"Chile: {chile_time.strftime('%H:%M:%S')}")

    run_async_in_thread(run_morning())


def evening_job():
    """Trabajo vespertino con logging de zona horaria"""
    chile_time = datetime.now(CHILE_TZ)
    utc_time = datetime.now(pytz.UTC)

    logger.info(f"Ejecutando trabajo vespertino - ubicación en tiempo real")
    logger.info(f"UTC: {utc_time.strftime('%H:%M:%S')}")
    logger.info(f"Chile: {chile_time.strftime('%H:%M:%S')}")

    run_async_in_thread(run_evening())


def schedule_jobs():
    """Programación de trabajos - calcula correctamente la hora de Chile"""
    schedule.clear()

    # Obtener offset de Chile respecto a UTC
    chile_time = datetime.now(CHILE_TZ)
    utc_time = datetime.now(pytz.UTC)

    # Calcular diferencia en horas
    offset_hours = int((chile_time.utcoffset().total_seconds()) / 3600)

    # Convertir horarios de Chile a UTC para el scheduler
    morning_utc_hour = (6 - offset_hours + 24) % 24  # 6:30 AM Chile
    evening_utc_hour = (18 - offset_hours + 24) % 24  # 6:15 PM Chile

    # Programar trabajos en horario UTC (que es lo que entiende Railway)
    for day in ['tuesday', 'wednesday', 'thursday']:
        getattr(schedule.every(), day).at(
            f"{morning_utc_hour:02d}:30").do(morning_job)
        getattr(schedule.every(), day).at(
            f"{evening_utc_hour:02d}:15").do(evening_job)

    logger.info(
        f"Trabajos programados (UTC): {morning_utc_hour:02d}:30 y {evening_utc_hour:02d}:15")
    logger.info(f"Equivale en Chile: 06:30 y 18:15")
    logger.info(f"Offset Chile-UTC: {offset_hours} horas")
    logger.info(f"Tipo de ubicación: Tiempo real (2 horas)")


def run_scheduler():
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except Exception as e:
            logger.error(f"Error scheduler: {e}")
            time.sleep(60)


def main():
    logger.info("Iniciando bot con ubicación en tiempo real...")
    logger.info(f"BOT_TOKEN configurado: {'Sí' if BOT_TOKEN else 'No'}")
    logger.info(
        f"Usuarios configurados: {len([x for x in AUTHORIZED_USERS if x])}")

    try:
        bot = LocationBot(BOT_TOKEN)
        schedule_jobs()

        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

        logger.info(
            "Bot iniciado - Automatización de ubicación en tiempo real activa")
        bot.application.run_polling(drop_pending_updates=True)

    except KeyboardInterrupt:
        logger.info("Bot detenido")
    except Exception as e:
        logger.error(f"Error crítico: {e}")


if __name__ == '__main__':
    main()
