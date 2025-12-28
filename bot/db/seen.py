from datetime import datetime
from db.supabase_client import supabase, TIME_MAP, ENERGY_MAP, location_MAP
import logging
from random import choice, random


def _norm(s):
    return s.lower().strip() if isinstance(s, str) else ""


def _matches_multivalue(user_value: str, activity_value: str) -> bool:
    if not activity_value:
        return False
    if not user_value:
        return True
    return _norm(user_value) in _norm(activity_value)


def _check_age_overlap(user_min, user_max, act_min, act_max):
    if act_min is None or act_max is None: return False
    if user_min is None or user_max is None: return True
    try:
        act_min, act_max = int(act_min), int(act_max)
    except ValueError:
        return False
    return not (act_max < user_min or act_min > user_max)


def _has_video(activity: dict) -> bool:
    """Проверяет наличие видео в активности (dev или prod поле)."""
    vid_dev = str(activity.get("video_file_id") or "")
    vid_prod = str(activity.get("video_file_id_prod") or "")
    # Считаем, что видео есть, если строка длиннее 5 символов
    return (len(vid_dev) > 5) or (len(vid_prod) > 5)


def get_next_activity_with_filters(user_id: int,
                                   age_min: int,
                                   age_max: int,
                                   time_required: str,
                                   energy: str,
                                   location: str):

    # 0. Инфо
    logging.info(
        f"[🔍 ФИЛЬТРЫ] Юзер={user_id} | Возраст={age_min}-{age_max} | "
        f"Время={time_required} | Энергия={energy} | Место={location}"
    )

    mapped_time = TIME_MAP.get(time_required, time_required)
    mapped_energy = ENERGY_MAP.get(energy, energy)
    mapped_location = location_MAP.get(location, location)

    # 1. Загрузка данных
    activities_resp = supabase.table("activities").select("*").execute()
    all_activities = activities_resp.data or []

    seen_resp = supabase.table("seen_activities").select("activity_id").eq("user_id", user_id).execute()
    seen_ids = set(row["activity_id"] for row in (seen_resp.data or []))

    # 2. Логика Новичка (Onboarding: первые 5 идей)
    force_video_onboarding = len(seen_ids) < 5

    if force_video_onboarding:
        logging.info(f"[👶 НОВИЧОК] Просмотрено: {len(seen_ids)}. Режим: СТРОГО ВИДЕО 🎥")

    candidates_pool = []

    # Формируем пул кандидатов
    for a in all_activities:
        if a["id"] in seen_ids: continue

        # Если это онбординг, мы жестко фильтруем без видео
        if force_video_onboarding:
            if not _has_video(a):
                continue

        candidates_pool.append(a)

    # Лог размера пула
    pool_ids = [a['id'] for a in candidates_pool]
    # Ограничиваем вывод ID в лог, чтобы не спамить
    preview = str(pool_ids[:10]) + ("..." if len(pool_ids) > 10 else "")
    logging.info(f"[🎱 ПУЛ] Кандидатов: {len(pool_ids)}. Первые ID: {preview}")

    # Fallback для онбординга: если с видео совсем пусто, снимаем блок
    if force_video_onboarding and not candidates_pool:
        logging.warning("[⚠️ ВНИМАНИЕ] Идеи с видео закончились! Снимаем ограничение новичка.")
        candidates_pool = [a for a in all_activities if a["id"] not in seen_ids]

    # 3. Smart Fallback Loop + Soft Priority
    strategies = [
        ("1. Строгое совпадение", True, True, True, True),
        ("2. Игнорируем время ⏳", True, False, True, True),
        ("3. Игнорируем время+энергию ⚡️", True, False, False, True),
        ("4. Игнорируем возраст (только место) 🌍", False, False, False, True),
        ("5. Показать любую доступную 🎲", False, False, False, False)
    ]

    selected_id = None

    for name, use_age, use_time, use_energy, use_loc in strategies:
        matches = []
        for a in candidates_pool:
            if use_age and not _check_age_overlap(age_min, age_max, a.get("age_min"), a.get("age_max")): continue
            if use_time and not _matches_multivalue(mapped_time, a.get("time_required")): continue
            if use_energy and not _matches_multivalue(mapped_energy, a.get("energy")): continue
            if use_loc and not _matches_multivalue(mapped_location, a.get("location")): continue

            # Сохраняем весь объект активности, чтобы потом проверить видео
            matches.append(a)

        if matches:
            # === SOFT PRIORITY LOGIC (70/30) ===
            video_matches = [m for m in matches if _has_video(m)]
            text_matches = [m for m in matches if not _has_video(m)]

            final_choice = None

            # 1. Если есть только один тип контента — выбора нет
            if not video_matches:
                final_choice = choice(text_matches)
                logging.info(f"[⚖️ ВЫБОР] Только текст. (Видео нет в этой выборке)")
            elif not text_matches:
                final_choice = choice(video_matches)
                logging.info(f"[⚖️ ВЫБОР] Только видео. (Текста нет в этой выборке)")
            else:
                # 2. Если есть и то и другое — кидаем кубик
                # 0.7 = 70% вероятность выбрать видео
                if random() < 0.7:
                    final_choice = choice(video_matches)
                    logging.info(f"[⚖️ ВЫБОР] 🎲 Выпало ВИДЕО (Вероятность 70%)")
                else:
                    final_choice = choice(text_matches)
                    logging.info(f"[⚖️ ВЫБОР] 🎲 Выпал ТЕКСТ (Вероятность 30%)")

            selected_id = final_choice["id"]

            logging.info(f"[✅ НАЙДЕНО] Стратегия: '{name}'. Кандидатов: {len(matches)}. Выбран ID: {selected_id}")
            break

    if selected_id:
        return selected_id, False

    # 4. Глобальный сброс
    logging.info("[♻️ ГЛОБАЛЬНЫЙ СБРОС] Просмотрено вообще всё. Очистка истории.")
    supabase.table("seen_activities").delete().eq("user_id", user_id).execute()
    logging.info("[🔄 РЕСТАРТ] Поиск заново...")
    return get_next_activity_with_filters(user_id, age_min, age_max, time_required, energy, location)