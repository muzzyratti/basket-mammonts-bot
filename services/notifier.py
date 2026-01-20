from datetime import datetime, timedelta
from config import config
from services.google_sheets import sheets
from services.date_tools import DAYS_MAP
import logging
import asyncio

async def check_and_send_reminders(bot):
    """
    Запускается каждую минуту. Проверяет, нужно ли слать напоминалку об опросе.
    """
    try:
        settings = await sheets.get_settings()
        
        poll_day_str = settings.get("день_опроса", "").lower().strip()
        poll_time_str = settings.get("время_опроса", "").strip()
        
        remind_before_str = str(settings.get("напоминалка_об_опросе_до", "5")).replace("мин", "").strip()
        before_min = int(remind_before_str) if remind_before_str.isdigit() else 0
        
        remind_after_str = str(settings.get("напоминалка_об_опросе_после", "")).replace("мин", "")
        after_delays = []
        for s in remind_after_str.split(","):
            if s.strip().isdigit():
                after_delays.append(int(s.strip()))
        
        now = datetime.now()
        target_weekday = DAYS_MAP.get(poll_day_str)
        
        if target_weekday is None or now.weekday() != target_weekday:
            return

        try:
            h, m = map(int, poll_time_str.split(":"))
            poll_start_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        except ValueError:
            logging.error(f"Неверный формат времени опроса: {poll_time_str}")
            return

        # 1. Напоминание ДО
        if before_min > 0:
            trigger_time_before = poll_start_dt - timedelta(minutes=before_min)
            if now.hour == trigger_time_before.hour and now.minute == trigger_time_before.minute:
                logging.info("🔔 Сработал триггер: Напоминание ДО опроса")
                await send_pre_poll_notification(bot)

        # 2. Напоминание ПОСЛЕ
        for delay in after_delays:
            trigger_time_after = poll_start_dt + timedelta(minutes=delay)
            if now.hour == trigger_time_after.hour and now.minute == trigger_time_after.minute:
                logging.info(f"🔔 Сработал триггер: Напоминание ПОСЛЕ (+{delay} мин)")
                await send_post_poll_reminders(bot, game_date_key="дата_текущей_игры")

    except Exception as e:
        logging.error(f"Notifier Error: {e}")

async def send_pre_poll_notification(bot):
    user_ids = await sheets.get_users_for_notification()
    count = 0
    for uid in user_ids:
        try:
            await bot.send_message(
                chat_id=uid,
                text="⏳ <b>Готовность 5 минут!</b>\nСкоро в чате появится опрос на игру. Не пропусти!",
                parse_mode="HTML"
            )
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    logging.info(f"📤 Pre-poll sent to {count} users")

async def send_post_poll_reminders(bot, game_date_key):
    settings = await sheets.get_settings()
    game_date = settings.get(game_date_key)
    
    if not game_date:
        return

    voted_nicks = await sheets.get_all_voters_nicks(game_date)
    ws_mammoths = await sheets._get_ws("Мамонты")
    mammoths = await ws_mammoths.get_all_records()
    
    count = 0
    for m in mammoths:
        uid = m.get("ID Telegram")
        nick = str(m.get("Ник", "")).replace("@", "").strip().lower()
        name = m.get("Имя", "Мамонт")
        notify = str(m.get("Отправлять уведомления", "")).lower()
        
        if notify != "да": continue
        if nick in voted_nicks: continue
            
        try:
            await bot.send_message(
                chat_id=uid,
                text=f"👋 Эй, <b>{name}</b>!\n\nТы забыл отметиться в опросе на игру ({game_date})! 🏀\nЗайди в общий чат и нажми кнопку.",
                parse_mode="HTML"
            )
            count += 1
            await asyncio.sleep(0.05)
        except: pass
            
    logging.info(f"📤 Post-poll reminder sent to {count} lazy mammoths")

async def check_payment_reminders(bot):
    """
    Проверяет долги и тегает.
    """
    try:
        settings = await sheets.get_settings()
        remind_times_str = settings.get("напоминалки_об_оплате", "")
        if not remind_times_str:
            return

        now = datetime.now()
        current_time_str = now.strftime("%H:%M")
        
        # Проверяем время (убираем пробелы при проверке)
        should_remind = False
        target_times = [t.strip() for t in remind_times_str.split(",")]
        
        if current_time_str in target_times:
            should_remind = True
            logging.info(f"⏰ Время напоминания об оплате: {current_time_str}")
        else:
            return

        # Получаем должников
        pending_payments = await sheets.get_pending_payments()
        if not pending_payments:
            logging.info("✅ Долгов нет, все молодцы.")
            return

        ws_m = await sheets._get_ws("Мамонты")
        all_users = await ws_m.get_all_records()

        for payment in pending_payments:
            raw_ids = payment.get('debtors_ids')
            
            debtors_ids = []
            
            # --- ЛОГИКА ОБРАБОТКИ ФОРМАТОВ ---
            if isinstance(raw_ids, str):
                # Нормальная строка "123, 456"
                debtors_ids = [x.strip() for x in raw_ids.split(",") if x.strip()]
            elif isinstance(raw_ids, (int, float)):
                # ОШИБКА: Гугл превратил строку в число ("колбаса")
                val_str = str(int(raw_ids)) # Убираем .0 если есть
                logging.warning(f"⚠️ ВНИМАНИЕ: Гугл Таблица отдала число вместо строки ID: {val_str}. Возможно, пропали запятые! Проверь формат ячейки 'Финансы' (столбец F).")
                # Мы не можем разделить это число, но попробуем добавить его как есть, вдруг это один должник
                debtors_ids = [val_str]
            elif isinstance(raw_ids, list):
                debtors_ids = [str(x).strip() for x in raw_ids if str(x).strip()]
            
            if not debtors_ids:
                continue

            game_date = payment['date']
            cost = payment['cost']
            payer = payment['payer']
            
            mentions = []
            ids_for_dm = []
            
            logging.info(f"🔍 Обработка долга за {game_date}. Исходные данные: {raw_ids} -> Parse: {debtors_ids}")

            for d_id in debtors_ids:
                # Ищем юзера
                user_info = next((u for u in all_users if str(u.get("ID Telegram")).strip() == d_id), None)
                
                if user_info:
                    nick = user_info.get("Ник", "")
                    name = user_info.get("Имя", "Мамонт")
                    if nick and "@" in nick:
                        mentions.append(nick)
                    else:
                        mentions.append(f"<a href='tg://user?id={d_id}'>{name}</a>")
                    ids_for_dm.append(d_id)
                else:
                    logging.warning(f"⚠️ Не нашел в базе Мамонтов ID: {d_id}")

            if not mentions:
                logging.info("Некого тегать (возможно, ID не совпали).")
                continue
                
            text = (
                f"💸 <b>НАПОМИНАНИЕ ОБ ОПЛАТЕ ({game_date})</b>\n"
                f"Мы все еще ждем перевод <b>{cost} ₽</b> для {payer}.\n\n"
                f"Должники: {', '.join(mentions)}\n\n"
                f"<i>Пожалуйста, нажмите кнопку «Я перевел» в сообщении об оплате выше!</i>"
            )
            
            try:
                await bot.send_message(config.GROUP_CHAT_ID, text, parse_mode="HTML")
                logging.info("📢 Напоминание отправлено в общий чат.")
            except Exception as e:
                logging.error(f"Ошибка отправки в общий чат: {e}")
            
            for uid in ids_for_dm:
                try:
                    await bot.send_message(uid, f"👋 Привет! Не забудь перевести {cost}р за игру {game_date}. {payer} ждет.")
                except: pass

    except Exception as e:
        logging.error(f"Payment Notifier Error: {e}")