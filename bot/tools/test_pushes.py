"""
Запуск: python bot/tools/test_pushes.py
Тест-панель для push-системы. Работает в Replit, тянет config/.env,
не требует правок в остальных модулях.
"""

import os
import sys
import asyncio
from datetime import datetime
from pathlib import Path

# --- sys.path: корень проекта и bot/ ---
ROOT = Path(__file__).resolve().parents[2]   # /workspace
BOT_DIR = ROOT / "bot"
for p in (str(ROOT), str(BOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# --- config.py (он загрузит .env и .env.dev/.prod) ---
try:
    import config  # noqa: F401
except Exception as e:
    print("❌ Ошибка при загрузке config.py:", e)
    raise SystemExit(1)

# --- проектные импорты (существующие функции) ---
from db.supabase_client import supabase
from utils.push_scheduler import schedule_retention_nudges, schedule_paywall_followup
from workers.worker_pushes import process_push_queue
from utils.logger import setup_logger

logger = setup_logger()

# 👉 твой тестовый Telegram user_id
TEST_USER_ID = 276358220


async def list_queue():
    """Показать все задачи из push_queue."""
    res = (
        supabase.table("push_queue")
        .select("*")
        .order("scheduled_at", desc=False)
        .execute()
    )
    data = res.data or []
    if not data:
        print("📭 Очередь пуста.")
        return
    print(f"\n📬 В очереди {len(data)} задач(и):")
    for row in data:
        print(
            f"{'✅' if row.get('status') == 'sent' else '⏳'} "
            f"id={row.get('id')} | type={row.get('type')} | user={row.get('user_id')} | "
            f"scheduled_at={row.get('scheduled_at')} | status={row.get('status')} | error={row.get('error')}"
        )


async def clear_queue_for_user(user_id: int):
    """Удалить все пуши для выбранного пользователя."""
    supabase.table("push_queue").delete().eq("user_id", user_id).execute()
    print(f"🧹 Очередь для user={user_id} очищена.")


async def test_schedule_retention():
    """Добавить цепочку ретеншн-пушей (через feature_flag retention_policy)."""
    schedule_retention_nudges(TEST_USER_ID)
    print("✅ Retention цепочка добавлена по текущей policy.")


async def test_schedule_paywall():
    """Добавить follow-up после paywall."""
    schedule_paywall_followup(TEST_USER_ID, reason="manual_test")
    print("✅ Paywall follow-up добавлен.")


async def test_send_next_push():
    """
    Принудительно отправить ближайший НЕотправленный пуш:
    - выбираем самый ранний pending
    - если он в будущем — сдвигаем scheduled_at = now
    - вызываем process_push_queue() (он отправит всё due)
    """
    res = (
        supabase.table("push_queue")
        .select("*")
        .eq("status", "pending")
        .order("scheduled_at")
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        print("❌ Нет pending-пушей для отправки.")
        return

    row = rows[0]
    msg_id = row["id"]
    now_iso = datetime.utcnow().isoformat()

    # сдвигаем на сейчас, чтобы точно прошло проверку "lte now"
    supabase.table("push_queue").update({
        "scheduled_at": now_iso
    }).eq("id", msg_id).execute()

    print(f"▶️ Готовим к отправке id={msg_id} (type={row['type']}) пользователю {row['user_id']}")
    await process_push_queue()  # отправит все due задачи
    print("📤 Готово. Проверь Telegram и статус в очереди.")


async def main():
    print("""
==== МЕНЮ ТЕСТИРОВАНИЯ PUSH-СИСТЕМЫ ====

1️⃣  Показать очередь (что запланировано)
2️⃣  Очистить все пуши для тестового пользователя
3️⃣  Добавить цепочку ретеншн-пушей (через retention_policy)
4️⃣  Добавить follow-up после paywall
5️⃣  Принудительно отправить ближайший pending-пуш
0️⃣  Выход
==========================================
""")

    choice = input("Выбери действие (0-5): ").strip()

    if choice == "1":
        await list_queue()
    elif choice == "2":
        await clear_queue_for_user(TEST_USER_ID)
    elif choice == "3":
        await test_schedule_retention()
    elif choice == "4":
        await test_schedule_paywall()
    elif choice == "5":
        await test_send_next_push()
    else:
        print("Выход.")


if __name__ == "__main__":
    asyncio.run(main())
