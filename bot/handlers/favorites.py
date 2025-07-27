from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from db.supabase_client import add_favorite, get_favorites
from db.supabase_client import supabase

favorites_router = Router()


@favorites_router.callback_query(F.data.startswith("favorite_add:"))
async def favorite_add(callback: types.CallbackQuery):
    activity_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    add_favorite(user_id=user_id, activity_id=activity_id)

    # Получаем активность
    response = supabase.table("activities").select("*").eq("id", activity_id).execute()
    if not response.data:
        await callback.message.answer("😔 Не удалось найти активность.")
        await callback.answer()
        return

    activity = response.data[0]

    summary = "\n".join([f"💡 {s}" for s in (activity['summary'] or [])])
    text = (
        f"🎲 *{activity['title']}*\n\n"
        f"⏱️ {activity['time_required']} • ⚡️ {activity['energy']} • 📍 {activity['location']}\n\n"
        f"Материалы: {activity['materials'] or 'Не требуются'}\n\n"
        f"{activity['full_description']}\n\n"
        f"{summary}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Убрать из любимых ✖️", callback_data=f"remove_fav:{activity_id}"),
            InlineKeyboardButton(text="Покажи еще идею", callback_data="activity_next")
        ]]
    )

    try:
        await callback.message.edit_caption(
            caption=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception:
        await callback.message.answer_photo(
            photo=activity["image_url"],
            caption=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    await callback.answer("Добавлено в любимые ❤️")


async def list_favorites(message_or_callback: types.Message | types.CallbackQuery):
    user_id = message_or_callback.from_user.id

    favorites_response = supabase.table("favorites") \
        .select("activity_id") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()

    if not favorites_response.data:
        text = "У вас пока нет любимых активностей 🌱"
        if isinstance(message_or_callback, types.CallbackQuery):
            try:
                await message_or_callback.message.edit_text(text)
            except Exception:
                await message_or_callback.message.answer(text)
            await message_or_callback.answer()
        else:
            await message_or_callback.answer(text)
        return

    activity_ids = [fav["activity_id"] for fav in favorites_response.data]

    activities_response = supabase.table("activities") \
        .select("*") \
        .in_("id", activity_ids) \
        .execute()

    if not activities_response.data:
        await message_or_callback.answer("Не удалось загрузить активности 😔")
        return

    id_to_activity = {a["id"]: a for a in activities_response.data}
    sorted_activities = [id_to_activity[aid] for aid in activity_ids if aid in id_to_activity]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=activity["title"],
                    callback_data=f"activity_details:{activity['id']}"),
                InlineKeyboardButton(
                    text="✖️",
                    callback_data=f"remove_fav:{activity['id']}")
            ]
            for activity in sorted_activities
        ]
    )

    if isinstance(message_or_callback, types.CallbackQuery):
        try:
            await message_or_callback.message.edit_text("Ваши любимые активности:", reply_markup=keyboard)
        except Exception:
            await message_or_callback.message.answer("Ваши любимые активности:", reply_markup=keyboard)
        await message_or_callback.answer()
    else:
        await message_or_callback.answer("Ваши любимые активности:", reply_markup=keyboard)


@favorites_router.message(Command("favorites"))
async def show_favorites_command(message: types.Message):
    await list_favorites(message)


@favorites_router.callback_query(F.data.startswith("remove_fav:"))
async def remove_favorite(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    activity_id = int(callback.data.split(":")[1])

    supabase.table("favorites") \
        .delete() \
        .eq("user_id", user_id) \
        .eq("activity_id", activity_id) \
        .execute()

    await list_favorites(callback)
