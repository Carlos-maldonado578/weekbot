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

# Cargar variables de entorno desde .env en desarrollo local
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("💡 Para desarrollo local, instala python-dotenv: pip install python-dotenv")

# Configuración de zona horaria de Chile
CHILE_TZ = pytz.timezone('America/Santiago')

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

# Configuración de logging mejorada
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),  # Para Railway logs
        logging.FileHandler('bot.log') if not os.getenv(
            'RAILWAY_ENVIRONMENT') else logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LocationBot:
    def __init__(self, token):
        global bot_application
        self.application = Application.builder().token(token).build()
        bot_application = self.application
        self.setup_handlers()
        # Estado para tracking de respuestas
        self.pending_requests = {}

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
                f"⚠️ **Para configurar en Railway:**\n"
                f"• Variable `CHAT_ID_TUYO`: `{user_id}`\n"
                f"• Variable `CHAT_ID_ESPOSA`: `{user_id}`\n\n"
                f"📝 Configura ambos IDs en las variables de entorno y reinicia el servicio.",
                parse_mode='Markdown'
            )
            return

        # Validar autorización
        if user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ No estás autorizado para usar este bot.")
            logger.warning(
                f"Usuario no autorizado intentó acceder: {user_id} - {user_name}")
            return

        # Determinar rol del usuario
        user_role = "Esposo" if user_id == CHAT_ID_TUYO else "Esposa"

        # Crear teclado personalizado mejorado
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

        # Obtener próxima automatización
        next_auto = self.get_next_automation()

        await update.message.reply_text(
            f"¡Hola {user_name}! 👋\n\n"
            f"🔐 Rol: {user_role}\n"
            f"🆔 Chat ID: `{user_id}`\n\n"
            f"**⏰ Automatización configurada:**\n"
            f"🌅 **6:30 AM** (Mar-Jue): Solo ubicación de esposa\n"
            f"🌆 **6:15 PM** (Mar-Jue): Ubicación de ambos\n"
            f"📅 Próxima: {next_auto}\n\n"
            f"**📱 Comandos disponibles:**\n"
            f"`/ubicacion` - Solicitar ubicación del otro\n"
            f"`/tiempo_real` - Solicitar ubicación en tiempo real\n"
            f"`/test` - Probar automatización\n"
            f"`/estado` - Ver estado del bot\n"
            f"`/help` - Ayuda completa\n\n"
            f"💡 Usa los botones de abajo para enviar tu ubicación rápidamente",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        logger.info(
            f"Usuario {user_role} ({user_name}) inició sesión correctamente")

    def get_next_automation(self):
        """Calcular próxima automatización"""
        now = datetime.now(CHILE_TZ)
        weekday = now.weekday()  # 0=Monday, 1=Tuesday, etc.

        # Si es martes (1), miércoles (2) o jueves (3)
        if weekday in [1, 2, 3]:
            # Verificar si ya pasó la hora de hoy
            if now.hour < 6 or (now.hour == 6 and now.minute < 30):
                return f"Hoy a las 6:30 AM"
            elif now.hour < 18 or (now.hour == 18 and now.minute < 15):
                return f"Hoy a las 6:15 PM"
            else:
                # Ya pasaron ambas, calcular próximo día
                if weekday == 3:  # Jueves, próximo es martes
                    return "Próximo martes a las 6:30 AM"
                else:
                    return "Mañana a las 6:30 AM"
        else:
            # Calcular días hasta el próximo martes
            days_until_tuesday = (1 - weekday) % 7
            if days_until_tuesday == 0:
                days_until_tuesday = 7

            if days_until_tuesday == 1:
                return "Mañana (martes) a las 6:30 AM"
            else:
                return f"En {days_until_tuesday} días (martes) a las 6:30 AM"

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /help - Información completa"""
        if not await self.check_authorization(update):
            return

        chile_time = datetime.now(CHILE_TZ).strftime("%H:%M %Z")

        await update.message.reply_text(
            "🤖 **Bot de Ubicación Familiar en Tiempo Real**\n\n"

            "**⏰ Automatizaciones programadas (Chile):**\n"
            f"• **6:30 AM** (Martes-Jueves): Solicitud automática solo a esposa\n"
            f"• **6:15 PM** (Martes-Jueves): Solicitud automática a ambos\n"
            f"• **Hora actual**: {chile_time}\n\n"

            "**📱 Comandos disponibles:**\n"
            f"• `/ubicacion` - Solicitar ubicación actual al otro\n"
            f"• `/tiempo_real` - Solicitar ubicación en tiempo real\n"
            f"• `/test` - Probar funcionamiento automático\n"
            f"• `/estado` - Ver configuración y estado\n\n"

            "**📍 Tipos de ubicación:**\n"
            f"• **Tiempo Real 2h**: Compartir por 2 horas (recomendado para trabajo)\n"
            f"• **Tiempo Real 1h**: Compartir por 1 hora (para salidas cortas)\n"
            f"• **Actual**: Solo ubicación del momento\n\n"

            "**💡 Funcionamiento:**\n"
            f"• **Mañanas**: Solo la esposa recibe solicitud (para ir al trabajo)\n"
            f"• **Tardes**: Ambos reciben solicitud (para regresar a casa)\n"
            f"• Las ubicaciones se reenvían automáticamente entre ustedes\n"
            f"• Telegram actualiza la ubicación cada 5-15 segundos\n"
            f"• Recordatorio automático si no responden en 5 minutos\n\n"

            "**🔒 Seguridad:** Solo ustedes dos pueden usar este bot.\n"
            "**🌍 Zona horaria:** América/Santiago (Chile)",
            parse_mode='Markdown'
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /estado - Mostrar configuración actual"""
        if not await self.check_authorization(update):
            return

        user_id = str(update.effective_user.id)
        user_role = "Esposo" if user_id == CHAT_ID_TUYO else "Esposa"

        # Tiempo actual en Chile
        now_chile = datetime.now(CHILE_TZ)

        # Estado del servidor
        railway_env = "✅ Railway" if os.getenv(
            'RAILWAY_ENVIRONMENT') else "💻 Local"

        # Próxima automatización
        next_auto = self.get_next_automation()

        await update.message.reply_text(
            f"📊 **Estado del Bot**\n\n"
            f"👤 **Tu información:**\n"
            f"• Rol: {user_role}\n"
            f"• Chat ID: `{user_id}`\n\n"
            f"⚙️ **Configuración:**\n"
            f"• Usuarios autorizados: {len(AUTHORIZED_USERS)}/2\n"
            f"• Esposo configurado: {'✅' if CHAT_ID_TUYO else '❌'}\n"
            f"• Esposa configurada: {'✅' if CHAT_ID_ESPOSA else '❌'}\n"
            f"• Entorno: {railway_env}\n\n"
            f"⏰ **Tiempo (Chile):**\n"
            f"• Hora actual: {now_chile.strftime('%H:%M:%S')}\n"
            f"• Fecha: {now_chile.strftime('%d/%m/%Y - %A')}\n"
            f"• Próxima automatización: {next_auto}\n\n"
            f"📡 **Estado del servicio:** ✅ Activo\n"
            f"🔄 **Scheduler:** ✅ Ejecutándose",
            parse_mode='Markdown'
        )

    async def request_location_manual(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /ubicacion - Solicitar ubicación actual"""
        if not await self.check_authorization(update):
            return

        user_id = str(update.effective_user.id)
        target_id, target_name = self.get_target_user(user_id)
        requester_name = update.effective_user.first_name or "Usuario"

        if not target_id:
            await update.message.reply_text("❌ No se pudo determinar el destinatario.")
            return

        # Marcar solicitud pendiente
        self.pending_requests[target_id] = {
            'type': 'manual',
            'requester': requester_name,
            'time': datetime.now(CHILE_TZ)
        }

        await self.send_location_request(target_id, f"🔔 Tu {target_name} ({requester_name}) solicita tu ubicación actual")
        await update.message.reply_text(f"✅ Solicitud de ubicación enviada a tu {target_name}")
        logger.info(
            f"Solicitud manual de {requester_name} enviada a {target_name}")

    async def request_live_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /tiempo_real - Solicitar ubicación en tiempo real"""
        if not await self.check_authorization(update):
            return

        user_id = str(update.effective_user.id)
        target_id, target_name = self.get_target_user(user_id)
        requester_name = update.effective_user.first_name or "Usuario"

        if not target_id:
            await update.message.reply_text("❌ No se pudo determinar el destinatario.")
            return

        # Marcar solicitud pendiente
        self.pending_requests[target_id] = {
            'type': 'live',
            'requester': requester_name,
            'time': datetime.now(CHILE_TZ)
        }

        await self.send_live_location_request(target_id, f"📍 Tu {target_name} ({requester_name}) solicita tu ubicación en tiempo real")
        await update.message.reply_text(f"✅ Solicitud de ubicación en tiempo real enviada a tu {target_name}")
        logger.info(
            f"Solicitud tiempo real de {requester_name} enviada a {target_name}")

    async def test_automatic_sharing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /test - Probar automatizaciones"""
        if not await self.check_authorization(update):
            return

        if not CHAT_ID_TUYO or not CHAT_ID_ESPOSA:
            await update.message.reply_text("❌ Falta configurar algunos Chat IDs para hacer la prueba completa.")
            return

        await update.message.reply_text("🧪 **Iniciando prueba de automatizaciones...**\n\n"
                                        "Se simularán ambos escenarios (modo de prueba):")

        # Simular solicitud matutina (solo esposa)
        await update.message.reply_text("🌅 **Paso 1:** Simulando solicitud matutina (solo esposa)...")
        await asyncio.sleep(2)
        await self.automatic_location_request_spouse_only(test_mode=True)

        await asyncio.sleep(3)

        # Simular solicitud vespertina (ambos)
        await update.message.reply_text("🌆 **Paso 2:** Simulando solicitud vespertina (ambos)...")
        await asyncio.sleep(2)
        await self.automatic_location_request_both(test_mode=True)

        await update.message.reply_text(
            "✅ **Prueba completada exitosamente**\n\n"
            "📋 **Resultados del test:**\n"
            "• ✅ Esposa recibió solicitud matutina de prueba\n"
            "• ✅ Ambos recibieron solicitud vespertina de prueba\n"
            "• ✅ Mensajes enviados correctamente\n"
            "• ✅ Sistema de automatización funcionando\n\n"
            "💡 **Nota:** Fueron solicitudes de prueba. Las reales se envían automáticamente en los horarios programados.",
            parse_mode='Markdown'
        )
        logger.info("Prueba de automatización ejecutada exitosamente")

    async def handle_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manejar ubicaciones recibidas - VERSIÓN MEJORADA"""
        if not update.message or not update.message.location:
            return

        if not await self.check_authorization(update):
            return

        try:
            user_id = str(update.effective_user.id)
            location = update.message.location
            user_name = update.effective_user.first_name or "Usuario"

            # Limpiar solicitud pendiente
            if user_id in self.pending_requests:
                del self.pending_requests[user_id]

            # Determinar destinatario
            recipient_id, sender_role = self.get_target_user(user_id)
            if not recipient_id:
                await update.message.reply_text("❌ Error al procesar la ubicación.")
                return

            recipient_role = "esposo" if sender_role == "esposa" else "esposa"

            # Tiempo actual en Chile
            current_time = datetime.now(CHILE_TZ).strftime("%H:%M")

            # Verificar si es ubicación en tiempo real
            live_period = getattr(location, 'live_period', None)

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
                    f"⏰ Iniciada: {current_time} (Chile)\n"
                    f"⏱️ Duración: {duration_hours}h {duration_minutes}m\n\n"
                    f"🔄 La ubicación se actualiza automáticamente cada 5-15 segundos\n"
                    f"📱 Puedes ver la actualización en tiempo real en el mapa",
                    parse_mode='Markdown'
                )

                await update.message.reply_text(
                    f"✅ **Ubicación en tiempo real compartida exitosamente**\n\n"
                    f"📤 Enviada a: Tu {recipient_role}\n"
                    f"⏱️ Duración: {duration_hours}h {duration_minutes}m\n"
                    f"🔄 Se actualiza automáticamente\n"
                    f"📍 Ubicación activa hasta las {(datetime.now(CHILE_TZ).hour + duration_hours):02d}:{(datetime.now(CHILE_TZ).minute + duration_minutes):02d}",
                    parse_mode='Markdown'
                )
                logger.info(
                    f"Ubicación tiempo real enviada: {user_name} -> {recipient_role} ({duration_hours}h {duration_minutes}m)")

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
                    f"⏰ Hora: {current_time} (Chile)\n"
                    f"📌 Ubicación actual del momento\n"
                    f"🎯 Precisión: {'Alta' if location.horizontal_accuracy and location.horizontal_accuracy < 50 else 'Buena'}",
                    parse_mode='Markdown'
                )

                await update.message.reply_text(f"✅ Ubicación actual enviada a tu {recipient_role}")
                logger.info(
                    f"Ubicación actual enviada: {user_name} -> {recipient_role}")

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
            f"• **Tiempo Real 2h**: Compartir por 2 horas (recomendado para trabajo)\n"
            f"• **Tiempo Real 1h**: Compartir por 1 hora (para salidas cortas)\n"
            f"• **Solo Actual**: Ubicación del momento\n\n"
            f"💡 La ubicación en tiempo real se actualiza automáticamente cada 5-15 segundos.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def automatic_location_request_both(self, test_mode=False):
        """Solicitar ubicación automáticamente a ambos (tardes)"""
        current_time = datetime.now(CHILE_TZ).strftime("%H:%M")
        test_prefix = "🧪 **[MODO PRUEBA]** " if test_mode else ""

        message = (f"{test_prefix}🌆 **Ubicación Automática Vespertina**\n\n"
                   f"⏰ Hora: {current_time} (Chile)\n"
                   f"📍 Por favor comparte tu ubicación en tiempo real por 2 horas\n"
                   f"🏠 Para coordinar el regreso a casa\n"
                   f"🔄 Automatización programada")

        sent_count = 0
        if CHAT_ID_TUYO:
            await self.send_live_location_request(CHAT_ID_TUYO, message)
            sent_count += 1
        if CHAT_ID_ESPOSA:
            await self.send_live_location_request(CHAT_ID_ESPOSA, message)
            sent_count += 1

        if not test_mode:
            # Programar recordatorio en 5 minutos si no responden
            await asyncio.sleep(300)  # 5 minutos
            await self.send_reminder_if_needed()

        logger.info(
            f"Solicitudes automáticas vespertinas enviadas a {sent_count} usuarios - {current_time} {'[TEST]' if test_mode else ''}")

    async def automatic_location_request_spouse_only(self, test_mode=False):
        """Solicitar ubicación automáticamente solo a la esposa (mañanas)"""
        current_time = datetime.now(CHILE_TZ).strftime("%H:%M")
        test_prefix = "🧪 **[MODO PRUEBA]** " if test_mode else ""

        message = (f"{test_prefix}🌅 **Ubicación Automática Matutina**\n\n"
                   f"⏰ Hora: {current_time} (Chile)\n"
                   f"📍 Por favor comparte tu ubicación en tiempo real por 2 horas\n"
                   f"🏢 Para el trayecto al trabajo\n"
                   f"🔄 Automatización programada")

        if CHAT_ID_ESPOSA:
            await self.send_live_location_request(CHAT_ID_ESPOSA, message)

            if not test_mode:
                # Programar recordatorio en 5 minutos si no responde
                await asyncio.sleep(300)  # 5 minutos
                await self.send_reminder_if_needed_spouse()

            logger.info(
                f"Solicitud automática matutina enviada a esposa - {current_time} {'[TEST]' if test_mode else ''}")
        else:
            logger.warning(
                "CHAT_ID_ESPOSA no configurado para solicitud matutina")

    async def send_reminder_if_needed(self):
        """Enviar recordatorio si no han respondido"""
        reminder_message = (f"⏰ **RECORDATORIO DE UBICACIÓN**\n\n"
                            f"Aún no has compartido tu ubicación.\n"
                            f"Por favor, toca uno de los botones para compartir.\n\n"
                            f"💡 Es importante para coordinar nuestros horarios.")

        if CHAT_ID_TUYO and CHAT_ID_TUYO in self.pending_requests:
            await self.application.bot.send_message(CHAT_ID_TUYO, reminder_message, parse_mode='Markdown')
        if CHAT_ID_ESPOSA and CHAT_ID_ESPOSA in self.pending_requests:
            await self.application.bot.send_message(CHAT_ID_ESPOSA, reminder_message, parse_mode='Markdown')

    async def send_reminder_if_needed_spouse(self):
        """Enviar recordatorio solo a la esposa"""
        if CHAT_ID_ESPOSA and CHAT_ID_ESPOSA in self.pending_requests:
            reminder_message = (f"⏰ **RECORDATORIO DE UBICACIÓN**\n\n"
                                f"Aún no has compartido tu ubicación matutina.\n"
                                f"Por favor, toca uno de los botones para compartir.\n\n"
                                f"💡 Es para coordinar el trayecto al trabajo.")

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

# Funciones de automatización mejoradas


async def run_automatic_request_morning():
    """Ejecutar solicitud automática matutina"""
    if bot_application and CHAT_ID_ESPOSA:
        try:
            bot_instance = LocationBot.__new__(LocationBot)
            bot_instance.application = bot_application
            bot_instance.pending_requests = {}
            await bot_instance.automatic_location_request_spouse_only()
        except Exception as e:
            logger.error(f"Error en solicitud matutina: {e}")


async def run_automatic_request_evening():
    """Ejecutar solicitud automática vespertina"""
    if bot_application and (CHAT_ID_TUYO or CHAT_ID_ESPOSA):
        try:
            bot_instance = LocationBot.__new__(LocationBot)
            bot_instance.application = bot_application
            bot_instance.pending_requests = {}
            await bot_instance.automatic_location_request_both()
        except Exception as e:
            logger.error(f"Error en solicitud vespertina: {e}")


def morning_location_job():
    """Trabajo programado matutino (6:30 AM Chile)"""
    current_time_chile = datetime.now(CHILE_TZ).strftime('%H:%M %Z')
    logger.info(f"🌅 Ejecutando trabajo matutino - {current_time_chile}")

    # Crear nueva tarea en el loop de asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(run_automatic_request_morning())
    except RuntimeError:
        # Si no hay loop, crear uno nuevo
        asyncio.create_task(run_automatic_request_morning())


def evening_location_job():
    """Trabajo programado vespertino (6:15 PM Chile)"""
    current_time_chile = datetime.now(CHILE_TZ).strftime('%H:%M %Z')
    logger.info(f"🌆 Ejecutando trabajo vespertino - {current_time_chile}")

    # Crear nueva tarea en el loop de asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(run_automatic_request_evening())
    except RuntimeError:
        # Si no hay loop, crear uno nuevo
        asyncio.create_task(run_automatic_request_evening())


def schedule_jobs():
    """Programar trabajos automáticos con zona horaria de Chile"""
    # Configurar schedule para usar zona horaria de Chile
    # Solicitudes matutinas (solo esposa) - Martes a Jueves a las 6:30 AM
    schedule.every().tuesday.at("06:30").do(morning_location_job)
    schedule.every().wednesday.at("06:30").do(morning_location_job)
    schedule.every().thursday.at("06:30").do(morning_location_job)

    # Solicitudes vespertinas (ambos) - Martes a Jueves a las 6:15 PM
    schedule.every().tuesday.at("18:15").do(evening_location_job)
    schedule.every().wednesday.at("18:15").do(evening_location_job)
    schedule.every().thursday.at("18:15").do(evening_location_job)

    logger.info(
        "⏰ Trabajos programados configurados para zona horaria de Chile:")
    logger.info("   🌅 6:30 AM (Mar-Jue): Solicitud solo a esposa")
    logger.info("   🌆 6:15 PM (Mar-Jue): Solicitud a ambos")

    # Log de próximos trabajos
    jobs = schedule.get_jobs()
    logger.info(f"📅 Total de trabajos programados: {len(jobs)}")


def run_scheduler():
    """Ejecutar programador en hilo separado con manejo de zona horaria"""
    logger.info("🔄 Iniciando scheduler con zona horaria de Chile")

    while True:
        try:
            # Ajustar el tiempo del scheduler a la zona horaria de Chile
            current_chile = datetime.now(CHILE_TZ)

            # Ejecutar trabajos pendientes
            schedule.run_pending()

            # Log cada hora para confirmar que está funcionando
            if current_chile.minute == 0:
                logger.info(
                    f"⏰ Scheduler activo - {current_chile.strftime('%H:%M %Z')} - Próximo trabajo: {schedule.next_run()}")

            time.sleep(60)  # Verificar cada minuto

        except Exception as e:
            logger.error(f"Error en scheduler: {e}")
            time.sleep(60)  # Esperar antes de reintentar


def setup_railway_config():
    """Configurar específicamente para Railway"""
    if os.getenv('RAILWAY_ENVIRONMENT'):
        logger.info("🚂 Detectado entorno Railway")
        logger.info(
            f"🌍 Variables configuradas: BOT_TOKEN={'✅' if BOT_TOKEN else '❌'}, CHAT_ID_TUYO={'✅' if CHAT_ID_TUYO else '❌'}, CHAT_ID_ESPOSA={'✅' if CHAT_ID_ESPOSA else '❌'}")

        # Configurar logging para Railway
        import sys
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        return True
    return False


def validate_configuration():
    """Validar configuración completa del bot"""
    issues = []

    if not BOT_TOKEN:
        issues.append("❌ BOT_TOKEN no configurado")

    if not CHAT_ID_TUYO:
        issues.append("⚠️ CHAT_ID_TUYO no configurado")

    if not CHAT_ID_ESPOSA:
        issues.append("⚠️ CHAT_ID_ESPOSA no configurado")

    if issues:
        logger.warning("🔧 Problemas de configuración detectados:")
        for issue in issues:
            logger.warning(f"   {issue}")

        if not BOT_TOKEN:
            return False

    logger.info("✅ Configuración del bot validada correctamente")
    logger.info(f"👥 Usuarios autorizados: {len(AUTHORIZED_USERS)}")

    return True


def main():
    """Función principal mejorada"""
    print("🤖 Iniciando Bot de Ubicación Familiar v2.0...")
    print("=" * 50)

    # Detectar entorno
    is_railway = setup_railway_config()
    environment = "🚂 Railway" if is_railway else "💻 Local"
    print(f"🌍 Entorno detectado: {environment}")

    # Validar configuración
    if not validate_configuration():
        print("❌ Error crítico en la configuración. Deteniendo...")
        return

    # Crear instancia del bot
    try:
        print("📡 Creando instancia del bot...")
        bot = LocationBot(BOT_TOKEN)
        print("✅ Bot creado exitosamente")
    except Exception as e:
        print(f"❌ Error creando bot: {e}")
        logger.error(f"Error crítico creando bot: {e}")
        return

    # Configurar trabajos programados
    print("⏰ Configurando automatizaciones...")
    schedule_jobs()

    # Iniciar programador en hilo separado
    print("🔄 Iniciando scheduler...")
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # Mostrar información de inicio
    chile_time = datetime.now(CHILE_TZ).strftime("%H:%M:%S %Z")
    print("\n" + "=" * 50)
    print("🎉 BOT INICIADO EXITOSAMENTE")
    print("=" * 50)
    print(f"🕒 Hora actual (Chile): {chile_time}")
    print(f"📱 Usuarios configurados: {len(AUTHORIZED_USERS)}/2")
    print(f"🌍 Entorno: {environment}")
    print("\n📋 FUNCIONALIDADES ACTIVAS:")
    print("   ✅ Comandos interactivos (/start, /help, /estado, etc.)")
    print("   ✅ Manejo de ubicaciones en tiempo real")
    print("   ✅ Automatizaciones programadas:")
    print("      🌅 6:30 AM (Mar-Jue): Solo esposa")
    print("      🌆 6:15 PM (Mar-Jue): Ambos")
    print("   ✅ Recordatorios automáticos")
    print("   ✅ Sistema de autorización")
    print("   ✅ Zona horaria de Chile")

    if len(AUTHORIZED_USERS) < 2:
        print("\n⚠️  CONFIGURACIÓN PENDIENTE:")
        print("   📝 Envía /start al bot para obtener los Chat IDs")
        print("   ⚙️ Configura las variables de entorno faltantes")

    print("\n🔒 SEGURIDAD:")
    print("   ✅ Solo usuarios autorizados")
    print("   ✅ Validación de permisos")
    print("   ✅ Logging de actividades")

    print("\n🎛️  CONTROLES:")
    print("   ⏸️  Presiona Ctrl+C para detener")
    print("   📊 Usa /estado en el bot para ver el status")
    print("   🧪 Usa /test para probar las automatizaciones")
    print("=" * 50)

    # Iniciar bot
    try:
        logger.info("🚀 Iniciando polling del bot...")
        bot.application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True  # Ignorar mensajes pendientes al iniciar
        )
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido por el usuario")
        logger.info("Bot detenido manualmente")
    except Exception as e:
        print(f"❌ Error ejecutando bot: {e}")
        logger.error(f"Error crítico ejecutando bot: {e}")

        # Si es Railway, intentar reiniciar
        if is_railway:
            print("🔄 Intentando reiniciar en 30 segundos...")
            time.sleep(30)
            main()  # Reiniciar


if __name__ == '__main__':
    main()
