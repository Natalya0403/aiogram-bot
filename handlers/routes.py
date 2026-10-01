from html import escape
import asyncio
import os
import uuid

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
from cloudipsp import Api, Checkout
from dotenv import load_dotenv
import urllib3

# Импорты клиента и форм
from client import (
    create_order,
    create_product,
    get_all_orders,
    get_all_products,
    get_order_by_id,
    get_product_by_id,
    get_product_by_title,
    toggle_favorite_api,
)
from forms import AdminAddProduct, ProductSearch

# -------------------------------------------
load_dotenv()

# Отключаем предупреждения об отключенной проверке SSL для urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Безопасное считывание ADMIN_IDS из .env
raw_admin_ids = os.getenv("ADMIN_IDS", "0")
ADMIN_IDS = [
    int(admin_id.strip())
    for admin_id in raw_admin_ids.split(",")
    if admin_id.strip().isdigit()
]
API_URL = os.getenv("API_URL", "http://localhost")
USE_MOCK_FONDY = os.getenv("USE_MOCK_FONDY", "False").lower() in ("true", "1", "yes")

# ЕДИНСТВЕННОЕ объявление роутера на весь файл
router = Router()


# Проверка на админа
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# Вспомогательная функция сборки клавиатуры товара
def get_product_keyboard(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Купить", callback_data=f"buy:{product_id}"
                ),
                InlineKeyboardButton(
                    text="⭐ Избранное", callback_data=f"fav:{product_id}"
                ),
            ]
        ]
    )


# =====================================================================
# 1. АДМИН-ПАНЕЛЬ
# =====================================================================


@router.message(Command("admin_add"))
async def admin_add_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await msg.answer("🚫 У вас нет прав доступа")
        return

    await state.set_state(AdminAddProduct.title)
    await msg.answer("Введите название товара")


@router.message(AdminAddProduct.title)
async def admin_add_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text)
    await state.set_state(AdminAddProduct.decsr)
    await msg.answer("Введите описание товара")


@router.message(AdminAddProduct.decsr)
async def admin_add_desc(msg: Message, state: FSMContext):
    await state.update_data(descr=msg.text)
    await state.set_state(AdminAddProduct.price)
    await msg.answer("Введите стоимость товара (число)")


@router.message(AdminAddProduct.price)
async def admin_add_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.replace(",", "."))
    except ValueError:
        await msg.answer("Введите корректную цену (например, 49.99)")
        return

    await state.update_data(price=price)
    await state.set_state(AdminAddProduct.image_url)
    await msg.answer("Укажите ссылку на изображение товара")


@router.message(AdminAddProduct.image_url)
async def admin_add_finish(msg: Message, state: FSMContext):
    await state.update_data(image_url=msg.text)
    data = await state.get_data()

    success = await create_product({
        "title": data.get("title"),
        "descr": data.get("descr"),
        "price": data.get("price"),
        "image_url": data.get("image_url"),
    })

    if success:
        await msg.answer("✅ Товар успешно добавлен!")
    else:
        await msg.answer("❌ Произошла ошибка при сохранении товара.")

    await state.clear()


@router.message(Command("admin_orders"))
async def list_all_orders(msg: Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("У вас нет прав доступа")
        return

    orders = await get_all_orders()
    if not orders:
        await msg.answer("У вас пока нет заказов")
        return

    text = "<b>Все заказы:</b>\n\n"

    for order in orders:
        items = order.get("items", [])
        total_quantity = sum(item.get("quantity", 1) for item in items)

        text += (
            f"<b>Заказ №{order['id']}</b>\n"
            f"Пользователь: <code>{order['user_id']}</code>\n"
            f"Статус: {escape(str(order['status']))}\n"
            f"Позиций: {len(items)} (всего {total_quantity} шт.)\n"
            f"---------------------\n"
        )

    await msg.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("admin_order"))
async def order_details(msg: Message, command: CommandObject):
    if not is_admin(msg.from_user.id):
        await msg.answer("У вас нет доступа")
        return

    if not command.args or not command.args.isdigit():
        await msg.answer("Используйте формат: /admin_order <id>")
        return

    order_id = int(command.args)
    order = await get_order_by_id(order_id)

    if not order:
        await msg.answer("Заказ не найден")
        return

    text = f"<b>Заказ #{order['id']}</b>\n"
    text += f"👤 Пользователь: <a href='tg://user?id={order['user_id']}'>Написать</a> (ID: <code>{order['user_id']}</code>)\n"
    text += f"📦 Статус: {escape(str(order['status']))}\n\n"
    text += "<b>Состав заказа:</b>\n"

    for item in order.get("items", []):
        product_title = escape(item["product"]["title"])
        text += f"• {product_title} — {item['quantity']} шт.\n"

    await msg.answer(text, parse_mode=ParseMode.HTML)


# =====================================================================
# 2. ПОЛЬЗОВАТЕЛЬСКИЙ ФУНКЦИОНАЛ И КАТАЛОГ
# =====================================================================


@router.message(Command("start"))
@router.message(F.text.lower() == "меню")
async def welcome_message(msg: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Найти товар по названию",
                    callback_data="search_by_title",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Каталог товаров", callback_data="show_catalog:0"
                )
            ],
        ]
    )

    await msg.answer(
        "Добро пожаловать! Выберите, что хотите сделать:",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "search_by_title")
async def ask_for_title(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProductSearch.title)
    await callback.message.answer("Введите название товара для поиска:")
    await callback.answer()


@router.message(ProductSearch.title)
async def process_title_search(msg: Message, state: FSMContext):
    title = msg.text.strip()
    products = await get_product_by_title(title)

    if not products:
        await msg.answer("❌ Товар не найден")
    else:
        for product in products:
            safe_title = escape(product.get("title", ""))
            safe_descr = escape(product.get("descr", ""))

            text = (
                f"<b>{safe_title}</b>\n\n"
                f"{safe_descr}\n\n"
                f"<b>Цена:</b> {product['price']} $"
            )
            btns = get_product_keyboard(product['id'])

            await msg.answer_photo(
                photo=product['image_url'],
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=btns,
            )

    await state.clear()


@router.callback_query(F.data.startswith("show_catalog"))
async def show_catalog(callback: CallbackQuery):
    products = await get_all_products()
    if not products:
        await callback.answer("❌ Каталог пуст", show_alert=True)
        return

    index = int(callback.data.split(":")[1])

    if index < 0 or index >= len(products):
        index = 0

    product = products[index]

    safe_title = escape(product.get("title", ""))
    safe_descr = escape(product.get("descr", ""))

    text = (
        f"<b>{safe_title}</b>\n\n"
        f"{safe_descr}\n\n"
        f"<b>Цена:</b> {product['price']} $"
    )

    nav_buttons = []
    if index > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="◀️ Назад", callback_data=f"show_catalog:{index - 1}"
            )
        )
    if index < len(products) - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Вперед ▶️", callback_data=f"show_catalog:{index + 1}"
            )
        )

    pagination = InlineKeyboardMarkup(
        inline_keyboard=[
            nav_buttons,
            [
                InlineKeyboardButton(
                    text="💳 Купить", callback_data=f"buy:{product['id']}"
                ),
                InlineKeyboardButton(
                    text="⭐ Избранное", callback_data=f"fav:{product['id']}"
                ),
            ],
        ]
    )

    media = InputMediaPhoto(
        media=product['image_url'], caption=text, parse_mode=ParseMode.HTML
    )

    try:
        if callback.message.photo:
            await callback.message.edit_media(media=media, reply_markup=pagination)
        else:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=product['image_url'],
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=pagination,
            )
    except TelegramBadRequest as e:
        if "message to edit has no photo" in str(e) or "message is not modified" in str(e):
            await callback.message.answer_photo(
                photo=product['image_url'],
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=pagination,
            )

    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_handler(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[1])

    data = await state.get_data()
    cart = data.get("cart", [])

    item_found = False
    for item in cart:
        if item["product_id"] == product_id:
            item["quantity"] += 1
            item_found = True
            break

    if not item_found:
        cart.append({"product_id": product_id, "quantity": 1})

    await state.update_data(cart=cart)
    await callback.answer("✅ Товар добавлен в корзину!")


# =====================================================================
# 3. КОРЗИНА
# =====================================================================


async def render_cart(message: Message, state: FSMContext, is_callback: bool = False):
    """Вспомогательная функция отрисовки корзины."""
    data = await state.get_data()
    cart = data.get("cart", [])

    if not cart:
        text = "❌ Ваша корзина пуста"
        if is_callback:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    text = "<b>🧺 Ваша корзина:</b>\n\n"
    remove_buttons = []

    for idx, item in enumerate(cart, start=1):
        product_id = item["product_id"]
        quantity = item["quantity"]
        product = await get_product_by_id(product_id)

        if product and "title" in product:
            product_title = escape(product["title"])
        else:
            product_title = f"Товар №{product_id}"

        text += f"{idx}. {product_title} — {quantity} шт.\n"

        remove_buttons.append([
            InlineKeyboardButton(
                text=f"❌ Удалить {product_title}",
                callback_data=f"remove_item:{product_id}",
            )
        ])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Оформить заказ", callback_data="confirm_order"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Очистить корзину", callback_data="clear_cart"
                ),
            ],
        ]
        + remove_buttons
    )

    if is_callback:
        await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.message(Command("cart"))
async def view_cart(message: Message, state: FSMContext):
    await render_cart(message, state, is_callback=False)


@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery, state: FSMContext):
    await state.update_data(cart=[])
    await callback.message.edit_text("🧹 Корзина очищена")
    await callback.answer()


@router.callback_query(F.data.startswith("remove_item:"))
async def remove_item(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    cart = data.get("cart", [])
    cart = [item for item in cart if item["product_id"] != product_id]

    await state.update_data(cart=cart)
    await render_cart(callback.message, state, is_callback=True)
    await callback.answer("Товар удален из корзины")


# =====================================================================
# 4. ОПЛАТА И ИЗБРАННОЕ
# =====================================================================


def generate_fondy_url(total_cents: int, order_id: str) -> str:
    """Синхронная функция генерации ссылки Fondy."""
    if USE_MOCK_FONDY:
        return "https://pay.fondy.eu/merchants/test/index.html"

    api = Api(merchant_id=1396424, secret_key="test")
    api.session.session.verify = False

    checkout = Checkout(api=api)
    payment_data = {
        "currency": "USD",
        "amount": int(total_cents),
        "order_id": str(order_id),
        "order_desc": f"Оплата заказа #{order_id} в Telegram",
        "server_callback_url": f"{API_URL}/webhook/fondy",
    }
    return checkout.url(payment_data).get("checkout_url")


@router.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    cart = data.get("cart", [])

    if not cart:
        await callback.message.answer("❗ Ваша корзина пуста.")
        return

    try:
        result = await create_order(callback.from_user.id, cart)
    except Exception as e:
        print(f"Ошибка при вызове create_order: {e}")
        result = None

    if result:
        if isinstance(result, dict):
            db_id = result.get("id", "unknown")
        elif isinstance(result, int):
            db_id = result
        else:
            db_id = "unknown"

        order_id = f"order_{db_id}_{uuid.uuid4().hex[:6]}"

        total_cents = 0
        all_products = await get_all_products() or []
        for item in cart:
            for p in all_products:
                if int(item["product_id"]) == int(p["id"]):
                    price = float(p.get("price", 0))
                    quantity = int(item.get("quantity", 1))
                    total_cents += int(price * 100 * quantity)

        if total_cents == 0:
            total_cents = 100

        try:
            url = await asyncio.wait_for(
                asyncio.to_thread(generate_fondy_url, total_cents, order_id),
                timeout=15.0,
            )

            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить заказ", url=url)]
                ]
            )

            await callback.message.answer(
                "✅ Ваш заказ оформлен!\nПерейдите по кнопке для оплаты:",
                reply_markup=markup,
            )

            await state.update_data(cart=[])

            await callback.message.answer(
                "💬 После успешной оплаты с вами свяжется наш менеджер."
            )

        except asyncio.TimeoutError:
            print("⚠️ Fondy недоступен (Connect Timeout)")
            await callback.message.answer(
                "❌ Сервис оплаты временно недоступен (таймаут соединения). Попробуйте позже."
            )
        except Exception as e:
            print(f"Ошибка Fondy: {e}")
            await callback.message.answer(
                "❌ Ошибка при формировании ссылки на оплату."
            )
    else:
        await callback.message.answer(
            "❌ Ошибка при оформлении заказа на сервере. Попробуйте позже."
        )


@router.callback_query(F.data.startswith("fav:"))
async def process_favorite_button(callback: CallbackQuery):
    try:
        product_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка в данных товара", show_alert=True)
        return

    user_id = callback.from_user.id
    res = await toggle_favorite_api(user_id, product_id)

    if res and isinstance(res, dict):
        msg = res.get("message", "Готово")
    else:
        msg = "Ошибка сервера при добавлении в избранное"

    await callback.answer(text=msg, show_alert=False)