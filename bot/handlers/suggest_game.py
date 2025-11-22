import os
import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.supabase_client import supabase
from utils.amplitude_logger import log_event
from handlers.user_state import user_data

# --- НАСТРОЙКА ---
raw_admin_id = os.getenv("ADMIN_ID_FOR_SUGGESTS")
try:
    ADMIN_ID = int(raw_admin_id) if raw_admin_id else None
except ValueError:
    ADMIN_ID = None

suggest_router = Router()

# Временное хранилище для отслеживания обрабатываемых альбомов
# Ключ: f"{user_id}_{media_group_id}", Значение: True
album_tracker = {}

class SuggestGame(StatesGroup):
    waiting_for_content = State()
    waiting_for_attribution = State()

# 1. Старт
@suggest_router.message(Command("suggest"))
async def cmd_suggest(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    session_id = user_data.get(user_id, {}).get("session_id")

    log_event(user_id, "suggest_game_start", {}, session_id=session_id)

    await message.answer(
        "🧩 <b>Предложить свою игру</b>\n\n"
        "Мы ищем классные идеи! Лучшие игры мы опубликуем в боте, "
        "а в описании, если захотите, укажем ссылку на ваш канал/паблик.\n\n"
        "✍️ <b>Шаг 1 из 2:</b>\n"
        "Напишите название игры, правила и что для неё нужно.\n"
        "Можно прислать несколько фото или видео с подписью.",
        parse_mode="HTML"
    )
    await state.set_state(SuggestGame.waiting_for_content)


# 2. Получаем контент (с защитой от дублей альбома)
@suggest_router.message(StateFilter(SuggestGame.waiting_for_content))
async def process_content(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # Базовая валидация
    if not (message.text or message.caption or message.photo or message.video):
         await message.answer("Пожалуйста, пришлите описание текстом или медиа-файл 🙂")
         return

    # --- ЛОГИКА АЛЬБОМОВ ---
    current_caption = message.caption or message.text or ""
    media_group_id = message.media_group_id

    is_album_duplicate = False

    if media_group_id:
        tracker_key = f"{user_id}_{media_group_id}"
        if tracker_key in album_tracker:
            is_album_duplicate = True
        else:
            # Это первое фото из альбома — помечаем как обработанное
            album_tracker[tracker_key] = True
            # (Опционально) Очистка трекера через 10 секунд, чтобы память не текла
            asyncio.create_task(clear_tracker(tracker_key))

    # --- СБОР ДАННЫХ ---
    # Пытаемся достать данные, которые УЖЕ есть в стейте (от предыдущего фото этого же альбома)
    current_state_data = await state.get_data()
    saved_content = current_state_data.get("content", "")

    # Если в текущем сообщении есть текст — берем его. 
    # Если нет, но был в сохраненном (saved_content) — оставляем сохраненный.
    # Это решает проблему "пустого content" в БД.
    final_content = current_caption if current_caption else saved_content

    media_id = None
    if message.photo:
        media_id = message.photo[-1].file_id
    elif message.video:
        media_id = message.video.file_id

    # Сохраняем media_id (если это дубль, перезапишем на новое фото, но это не страшно, 
    # главное, что админ получит все фото в личку)
    await state.update_data(
        content=final_content, 
        media_id=media_id, 
        media_group_id=media_group_id 
    )

    # --- ОТПРАВКА АДМИНУ ---
    if ADMIN_ID:
        try:
            # Пишем заголовок ТОЛЬКО если это НЕ дубль
            if not is_album_duplicate:
                await message.bot.send_message(
                    ADMIN_ID, 
                    f"🔥 <b>Новая заявка от @{message.from_user.username}:</b>", 
                    parse_mode="HTML", 
                    disable_notification=True
                )
            # Форвард делаем ВСЕГДА (чтобы ты получил все 3 фотки)
            await message.forward(chat_id=ADMIN_ID, disable_notification=True)
        except Exception as e:
            print(f"[Suggest] Forward error: {e}")

    # --- ЕСЛИ ЭТО ДУБЛЬ АЛЬБОМА — СТОП ---
    # Мы обновили контент (если нашли текст), переслали фото админу, но НЕ отвечаем юзеру снова
    if is_album_duplicate:
        return

    # --- ОТВЕТ ЮЗЕРУ (Только 1 раз) ---
    await message.answer(
        "Супер! Идея принята 👍\n\n"
        "✍️ <b>Шаг 2 из 2:</b>\n"
        "Мы хотим указать ваше авторство красивой ссылкой.\n\n"
        "Пожалуйста, пришлите мне <b>Название вашего канала</b> и <b>Ссылку</b> на него.\n"
        "<i>(Если канала нет, просто напишите «нет»)</i>",
        parse_mode="HTML",
        disable_web_page_preview=True 
    )

    await state.set_state(SuggestGame.waiting_for_attribution)


# 3. Получаем данные об авторе
@suggest_router.message(StateFilter(SuggestGame.waiting_for_attribution))
async def process_attribution(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()

    # --- FIX "ХВОСТОВ" АЛЬБОМА ---
    # Если сообщение пришло с тем же ID альбома, что мы обрабатывали на шаге 1
    # Значит, это запоздалое фото из той же пачки (гонка обновлений)
    if message.media_group_id and message.media_group_id == data.get("media_group_id"):
        # Просто шлем админу и проверяем текст
        if ADMIN_ID:
            try:
                await message.forward(chat_id=ADMIN_ID, disable_notification=True)
            except: pass

        # Если вдруг описание оказалось ТУТ, а не в первом фото
        capt = message.caption or message.text
        if capt and not data.get("content"):
             await state.update_data(content=capt)
        return

    # --- НОРМАЛЬНЫЙ ФЛОУ ---
    text_input = message.text

    if not text_input and (message.photo or message.video):
         text_input = message.caption or "[Прислано медиа вместо ссылки]"

    if not text_input:
        await message.answer("Пожалуйста, пришлите название канала и ссылку текстом.")
        return

    attribution_info = text_input
    if text_input.lower() in ["нет", "-", "no", "нету", "не хочу"]:
        attribution_info = None

    if ADMIN_ID:
        try:
            await message.bot.send_message(
                ADMIN_ID, 
                f"👤 <b>Авторство (@{message.from_user.username}):</b>\n{text_input}", 
                parse_mode="HTML"
            )
        except: pass

    # Перед сохранением снова берем данные (вдруг обновились из хвоста альбома)
    final_data = await state.get_data()

    try:
        supabase.table("activity_suggestions").insert({
            "user_id": user_id,
            "username": message.from_user.username,
            "content": final_data.get('content'), # Тут теперь точно будет текст
            "media_id": final_data.get('media_id'),
            "attribution_info": attribution_info,
            "status": "pending"
        }).execute()

    except Exception as e:
        print(f"[Suggest] Error saving: {e}")

    session_id = user_data.get(user_id, {}).get("session_id")
    log_event(user_id, "suggest_game_completed", {"has_attribution": bool(attribution_info)}, session_id=session_id)

    await message.answer(
        "✅ <b>Спасибо за вашу идею! Мы всё сохранили.</b>\n\n"
        "Если игра пройдет модерацию, вы увидите её в боте.",
        parse_mode="HTML"
    )
    await state.clear()

# Очистка памяти от старых ID альбомов
async def clear_tracker(key: str):
    await asyncio.sleep(10) # храним ID 10 секунд
    if key in album_tracker:
        del album_tracker[key]