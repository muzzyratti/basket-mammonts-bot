import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import config
from services.google_sheets import sheets
from services.poll_message import start_poll_routine
from services.notifier import check_and_send_reminders, check_payment_reminders
from services.balancer import form_teams
from services.date_tools import get_next_game_date, DAYS_MAP

scheduler = AsyncIOScheduler()

async def check_and_post_poll(bot):
    """Задача 1: Проверка запуска опроса"""
    try:
        # --- ПРОВЕРКА РУБИЛЬНИКА (Без учета регистра) ---
        settings = await sheets.get_settings()
        is_active = str(settings.get("бот_активен", "Да")).strip().lower()
        if is_active == "нет":
            return
        # ---------------------------

        now = datetime.now()
        current_weekday = now.weekday()
        current_time = now.strftime("%H:%M")
        
        target_day_str = settings.get("день_опроса", "").lower().strip()
        target_time = settings.get("время_опроса", "").strip()
        
        target_weekday = DAYS_MAP.get(target_day_str)

        if target_weekday == current_weekday and target_time == current_time:
            logging.info("⏰ Время пришло! Запускаем авто-опрос.")
            result = await start_poll_routine(bot)
            
            # Отправляем отчет всем админам
            for admin_id in config.admin_ids_list:
                try:
                    await bot.send_message(chat_id=admin_id, text=f"🤖 Авто-запуск опроса:\n{result}")
                except Exception as e:
                    logging.warning(f"Не смог отправить отчет админу {admin_id}: {e}")

    except Exception as e:
        logging.error(f"Scheduler Poll Error: {e}")

async def check_and_post_teams(bot):
    """Задача 2: Авто-формирование команд"""
    try:
        # --- ПРОВЕРКА РУБИЛЬНИКА ---
        settings = await sheets.get_settings()
        is_active = str(settings.get("бот_активен", "Да")).strip().lower()
        if is_active == "нет":
            return
        # ---------------------------

        now = datetime.now()
        current_weekday = now.weekday()
        current_time = now.strftime("%H:%M")
        
        announce_day_str = settings.get("день_оглашения_составов", "").lower().strip()
        announce_time = settings.get("время_оглашения_составов", "").strip()
        game_day_str = settings.get("день_игры", "суббота")
        
        target_weekday = DAYS_MAP.get(announce_day_str)

        if target_weekday == current_weekday and announce_time == current_time:
            logging.info("⏰ Время оглашения составов! Формируем команды...")
            _, game_date = get_next_game_date(game_day_str)
            teams, report = await form_teams(game_date)
            
            if teams:
                await bot.send_message(chat_id=config.GROUP_CHAT_ID, text=report, parse_mode="HTML")
                # Уведомляем всех админов
                for admin_id in config.admin_ids_list:
                    try:
                        await bot.send_message(chat_id=admin_id, text=f"🤖 Авто-составы опубликованы!")
                    except: pass
            else:
                # Ошибка сбора (мало людей), пишем всем админам
                for admin_id in config.admin_ids_list:
                    try:
                        await bot.send_message(chat_id=admin_id, text=f"⚠️ Авто-составы не собрались: {report}")
                    except: pass

    except Exception as e:
        logging.error(f"Scheduler Teams Error: {e}")

async def check_and_send_reminders_wrapper(bot):
    settings = await sheets.get_settings()
    if str(settings.get("бот_активен", "Да")).strip().lower() == "нет":
        return
    await check_and_send_reminders(bot)

async def check_payment_reminders_wrapper(bot):
    settings = await sheets.get_settings()
    if str(settings.get("бот_активен", "Да")).strip().lower() == "нет":
        return
    await check_payment_reminders(bot)

def start_scheduler(bot):
    # 1. Опрос (00 сек)
    scheduler.add_job(check_and_post_poll, CronTrigger(second='0'), kwargs={"bot": bot}, max_instances=3, replace_existing=True)
    # 2. Уведомления (20 сек)
    scheduler.add_job(check_and_send_reminders_wrapper, CronTrigger(second='20'), kwargs={"bot": bot}, max_instances=3, replace_existing=True)
    # 3. Составы (40 сек)
    scheduler.add_job(check_and_post_teams, CronTrigger(second='40'), kwargs={"bot": bot}, max_instances=3, replace_existing=True)
    # 4. Оплата (10 сек)
    scheduler.add_job(check_payment_reminders_wrapper, CronTrigger(second='10'), kwargs={"bot": bot}, max_instances=3, replace_existing=True)
    
    if not scheduler.running:
        scheduler.start()
    else:
        print("⚠️ Scheduler уже запущен.")