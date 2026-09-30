from html import escape
import asyncio
import os
import uuid  # для формирования номера заказа в оплате в случайном формате


from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command,CommandObject
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

# Импорты клиента и форм
from client import (
    create_order,
    create_product,
    get_all_orders,
    get_all_products,
    get_product_by_id,
    get_product_by_title,
    get_order_by_id
)
from forms import AdminAddProduct, ProductSearch

# -------------------------------------------
load_dotenv()

# Безопасное считывание ADMIN_IDS из .env (поддерживает один или несколько ID через запятую)
raw_admin_ids = os.getenv("ADMIN_IDS", "0")
ADMIN_IDS = [
    int(admin_id.strip())
    for admin_id in raw_admin_ids.split(",")
    if admin_id.strip().isdigit()
]
API_URL = os.getenv("API_URL")
router = Router()


# Проверка на админа
def is_admin(user_id: int) -> bool:
  return user_id in ADMIN_IDS


# 1. СТАРТ: Реакция на команду /admin_add
@router.message(Command("admin_add"))
async def admin_add_start(msg: Message, state: FSMContext):
  if not is_admin(msg.from_user.id):
    await msg.answer("🚫 У вас нет прав доступа")
    return

  # ИСПРАВЛЕНО: Устанавливаем первое состояние — НАЗВАНИЕ
  await state.set_state(AdminAddProduct.title)
  await msg.answer("Введите название товара")


# 2. Обработка НАЗВАНИЯ товара
@router.message(AdminAddProduct.title)
async def admin_add_title(msg: Message, state: FSMContext):
  await state.update_data(title=msg.text)  # Сохраняем название

  # Переходим к ОПИСАНИЮ
  await state.set_state(AdminAddProduct.decsr)
  await msg.answer("Введите описание товара")


# 3. Обработка ОПИСАНИЯ товара
@router.message(AdminAddProduct.decsr)
async def admin_add_desc(msg: Message, state: FSMContext):
  await state.update_data(descr=msg.text)  # Сохраняем описание (как 'descr')

  # Переходим к ЦЕНЕ
  await state.set_state(AdminAddProduct.price)
  await msg.answer("Введите стоимость товара (число)")


# 4. Обработка ЦЕНЫ товара
@router.message(AdminAddProduct.price)
async def admin_add_price(msg: Message, state: FSMContext):
  try:
    price = float(msg.text.replace(",", "."))
  except ValueError:
    await msg.answer("Введите корректную цену (например, 49.99)")
    return

  await state.update_data(price=price)

  # Переходим к ИЗОБРАЖЕНИЮ
  await state.set_state(AdminAddProduct.image_url)
  await msg.answer("Укажите ссылку на изображение товара")


# 5. Обработка КАРТИНКИ и ЗАВЕРШЕНИЕ
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
#=======================================================================

# /admin_orders - просмотр заказов
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

    # Считаем сумму quantity по всем позициям
    total_quantity = sum(item.get("quantity", 1) for item in items)

    text += (
        f"<b>Заказ №{order['id']}</b>\n"
        f"Пользователь: <code>{order['user_id']}</code>\n"
        f"Статус: {order['status']}\n"
        f"Позиций: {len(items)} (всего {total_quantity} шт.)\n"
        f"---------------------\n"
    )

  await msg.answer(text, parse_mode=ParseMode.HTML)



#/admin_order <id> -просмотр заказа по ID
# project.routes
@router.message(Command("admin_order"))
async def order_details(msg: Message, command: CommandObject):
  if not is_admin(msg.from_user.id):
    await msg.answer("У вас нет доступа")
    return

  # Автоматическая проверка переданного аргумента (например, /admin_order 1)
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
  text += f"📦 Статус: {order['status']}\n\n"
  text += "<b>Состав заказа:</b>\n"

  for item in order.get("items", []):
    product_title = escape(item["product"]["title"])
    text += f"• {product_title} — {item['quantity']} шт.\n"

  await msg.answer(text, parse_mode=ParseMode.HTML)



# 1. СТАРТ И МЕНЮ
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


# 2. ПОИСК ПО НАЗВАНИЮ (ЗАПРОС ВВОДА)
@router.callback_query(F.data == "search_by_title")
async def ask_for_title(callback: CallbackQuery, state: FSMContext):
  await state.set_state(ProductSearch.title)
  await callback.message.answer("Введите название товара для поиска:")
  await callback.answer()


# 3. ОБРАБОТКА ВВОДА НАЗВАНИЯ
@router.message(ProductSearch.title)
async def process_title_search(msg: Message, state: FSMContext):
  title = msg.text.strip()
  products = await get_product_by_title(title)

  if not products:
    await msg.answer("❌ Товар не найден")
  else:
    for product in products:
      text = (
          f"<b>{product['title']}</b>\n\n"
          f"{product['descr']}\n\n"
          f"<b>Цена:</b> {product['price']} $"
      )
      btns = InlineKeyboardMarkup(
          inline_keyboard=[
              [
                  InlineKeyboardButton(
                      text="🧺 Купить", callback_data=f"buy:{product['id']}"
                  )
              ]
          ]
      )
      await msg.answer_photo(
          photo=product['image_url'],
          caption=text,
          parse_mode=ParseMode.HTML,
          reply_markup=btns,
      )

  await state.clear()


# 4. ПРОСМОТР КАТАЛОГА (ПАГИНАЦИЯ)
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

  text = (
      f"<b>{product['title']}</b>\n\n"
      f"{product['descr']}\n\n"
      f"<b>Цена:</b> {product['price']} $"
  )

  buttons = []
  if index > 0:
    buttons.append(
        InlineKeyboardButton(
            text="◀️ Назад", callback_data=f"show_catalog:{index - 1}"
        )
    )
  if index < len(products) - 1:
    buttons.append(
        InlineKeyboardButton(
            text="Вперед ▶️", callback_data=f"show_catalog:{index + 1}"
        )
    )

  pagination = InlineKeyboardMarkup(
      inline_keyboard=[
          buttons,
          [
              InlineKeyboardButton(
                  text="🧺 Купить", callback_data=f"buy:{product['id']}"
              )
          ],
      ]
  )

  media = InputMediaPhoto(
      media=product['image_url'], caption=text, parse_mode=ParseMode.HTML
  )

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

  await callback.answer()


# 5. ОБРАБОТЧИК КНОПКИ "КУПИТЬ" (ДОБАВЛЕНИЕ В КОРЗИНУ)
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

# ----------Корзина--------------------------------------------------
@router.message(Command("cart"))
async def view_cart(message: Message, state: FSMContext):
  data = await state.get_data()
  cart = data.get("cart", [])

  if not cart:
    await message.answer("❌ Ваша корзина пуста")
    return

  text = "<b>🧺 Ваша корзина:</b>\n\n"
  remove_buttons = []

  for idx, item in enumerate(cart, start=1):
    product_id  = item["product_id"]
    quantity = item["quantity"]
    # получаем словарь товара по его id тут уже делаем запрос к бд поэтому await и используем функцию из client
    product = await get_product_by_id(product_id)
    # проверяем есть ли в базе
    if product and 'title' in product:
        product_title = product['title']
    else:
        product_title = f"Товар №{product_id}"
    # 3. Формируем красивую строку для текста сообщения
    text += f'{idx}. Товар: {product_title} — Кол-во: {quantity} шт.\n'

  # 2. Формируем динамический список кнопок для удаления каждого товара
    remove_buttons.append([
            InlineKeyboardButton(
              text=f"❌ Удалить товар {product_title}",
              callback_data=f"remove_item:{product_id}",
          )
    ])

  # 3. Собираем итоговую клавиатуру
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

  await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# очистка корзины
@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback:CallbackQuery, state: FSMContext):
    await state.update_data(cart=[])# просто делаем корзину пустой
    await callback.message.edit_text('🧹Корзина очищена')
    await callback.answer()

# кнопка удаления одного товара из корзины
@router.callback_query(F.data.startswith ('remove_item:'))
async def remove_item(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    cart = data.get("cart", [])
    cart = [item for item in cart if item["product_id"] != product_id] # немного всратая логика что мы перебираем все элементы корзины если не совпало с лок переменн product_id -возвращаем в корзину
    await state.update_data(cart=cart)# обновляем состояние
    await callback.message.edit_text('❌ Товар удален из корзины')
    await callback.answer()

# =====================================================================
# Подтверждение заказа в корзине


# Флаг локальной разработки.
# Поставьте True, если api.fondy.eu заблокирован сетевым провайдером.

USE_MOCK_FONDY = os.getenv("USE_MOCK_FONDY", "False").lower() in ("true", "1", "yes")

router = Router()


def generate_fondy_url(total_cents: int, order_id: str) -> str:
    """Синхронная функция генерации ссылки Fondy."""
    if USE_MOCK_FONDY:
        # Возвращаем рабочую ссылку на тестовый мерчант Fondy или любую внешнюю страницу
        return "https://pay.fondy.eu/merchants/test/index.html"

    # Реальный вызов
    api = Api(merchant_id=1396424, secret_key="test")
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
    # 1. Отвечаем мгновенно, чтобы Telegram не выдал таймаут на кнопку
    await callback.answer()

    data = await state.get_data()
    cart = data.get("cart", [])

    if not cart:
        await callback.message.answer("❗ Ваша корзина пуста.")
        return

    # 2. Отправляем заказ в FastAPI
    try:
        result = await create_order(callback.from_user.id, cart)
    except Exception as e:
        print(f"Ошибка при вызове create_order: {e}")
        result = None

    if result:
        # Безопасно извлекаем ID из результата (работает и для dict, и для int)
        if isinstance(result, dict):
            db_id = result.get("id", "unknown")
        elif isinstance(result, int):
            db_id = result
        else:
            db_id = "unknown"

        # Формируем уникальный order_id
        order_id = f"order_{db_id}_{uuid.uuid4().hex[:6]}"

        # Расчет суммы
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

        # 3. Безопасное получение URL через поток
        try:
            url = await asyncio.wait_for(
                asyncio.to_thread(generate_fondy_url, total_cents, order_id),
                timeout=15.0
            )

            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить заказ", url=url)]
                ]
            )

            await callback.message.answer(
                "✅ Ваш заказ оформлен!\nПерейдите по кнопке для оплаты:",
                reply_markup=markup
            )

            # Очищаем корзину после успешной генерации ссылки
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
# =====================================================================
# Подтверждение заказа
# @router.callback_query(F.data == "confirm_order")
# async def confirm_order(callback: CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     cart = data.get("cart", [])
#
#     if not cart:
#         await callback.message.answer("❗ Ваша корзина пуста.")
#         return
#
#     # Отправляем заказ в FastAPI
#     result = await create_order(callback.from_user.id, cart)
#
#     if result:
#         total_cents = 0
#         all_products = await get_all_products()
#         for item in cart:
#             for p in all_products:
#                 if item['product_id'] == p['id']:
#                     total_cents += int(p['price']) * 100 * item['quantity']
#
#
#         api = Api(merchant_id=1396424, secret_key='test')
#         checkout = Checkout(api=api)
#         data = {
#             "currency": "USD",
#             "amount": total_cents,
#             "order_id": f"order_{result}_{uuid.uuid4().hex[:6]}",
#             "order_desc": "Оплата заказа в Telegram",
#             "server_callback_url": "https://your-api.com/webhook/fondy"
#         }
#         url = checkout.url(data).get("checkout_url")
#
#         # Кнопка на оплату
#         markup = InlineKeyboardMarkup(inline_keyboard=[
#             [InlineKeyboardButton(text="💳 Оплатить заказ", url=url)]
#         ])
#
#         await callback.message.answer("✅ Ваш заказ оформлен!\nПерейдите по кнопке для оплаты:", reply_markup=markup)
#
#         import asyncio
#         await asyncio.sleep(3)
#
#         # 📩 Отправляем напоминание
#         await callback.message.answer("💬 После успешной оплаты с вами свяжется наш менеджер.")
#         await state.update_data(cart=[])  # Очистить корзину
#     else:
#         await callback.message.answer("❌ Ошибка при оформлении заказа. Попробуйте позже.")
#
#     await callback.answer()
