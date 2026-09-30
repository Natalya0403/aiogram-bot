import asyncio
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from cloudipsp import Api, Checkout
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
import uuid #для формирования номера заказа в оплате в случайном формате
# Импорты клиента и форм
from project.client import create_order, get_all_products, get_product_by_title, get_product_by_id
from project.forms import ProductSearch

router = Router()


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

# Подтверждение заказа в корзине

# Флаг локальной разработки.
# Поставьте True, если api.fondy.eu заблокирован сетевым провайдером.
USE_MOCK_FONDY = True


def generate_fondy_url(total_cents: int, order_id: str) -> str:
  """Синхронная функция генерации ссылки Fondy."""
  if USE_MOCK_FONDY:
    # Возвращает рабочий тестовый шлюз без обращения к api.fondy.eu
    return f"https://pay.fondy.eu/example_checkout?order_id={order_id}&amount={total_cents}"

  # Реальный вызов (будет работать при включенном VPN или на боевом сервере)
  api = Api(merchant_id=1396424, secret_key="test")
  checkout = Checkout(api=api)
  payment_data = {
      "currency": "USD",
      "amount": total_cents,
      "order_id": order_id,
      "order_desc": "Оплата заказа в Telegram",
      "server_callback_url": (
          "https://landmass-unclaimed-gathering.ngrok-free.dev/webhook/fondy"
      ),
  }
  return checkout.url(payment_data).get("checkout_url")


@router.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
  # 1. Отвечаем мгновенно
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
    order_db_id = (
        result.get("id", uuid.uuid4().hex[:6])
        if isinstance(result, dict)
        else uuid.uuid4().hex[:6]
    )

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

    order_id = f"tg_order_{order_db_id}"

    # 3. Безопасное получение URL
    try:
      url = await asyncio.wait_for(
          asyncio.to_thread(generate_fondy_url, total_cents, order_id),
          timeout=5.0,
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

      # Очищаем корзину после успешной отправки кнопки
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

#------------------------------код для корзины fondy---------------------------------------------------
# Флаг локальной разработки.
# Поставьте True, если api.fondy.eu заблокирован сетевым провайдером.
USE_MOCK_FONDY = True


def generate_fondy_url(total_cents: int, order_id: str) -> str:
  """Синхронная функция генерации ссылки Fondy."""
  if USE_MOCK_FONDY:
    # Возвращаем рабочую ссылку на тестовый мерчант Fondy или любой внешнюю страницу
    # (чтобы браузер не открывал ошибку Amazon S3 AccessDenied)
    return "https://pay.fondy.eu/merchants/test/index.html"

  # Реальный вызов
  api = Api(merchant_id=1396424, secret_key="test")
  checkout = Checkout(api=api)
  payment_data = {
      "currency": "USD",
      "amount": total_cents,
      "order_id": order_id,
      "order_desc": "Оплата заказа в Telegram",
      "server_callback_url": (
          "https://landmass-unclaimed-gathering.ngrok-free.dev/webhook/fondy"
      ),
  }
  return checkout.url(payment_data).get("checkout_url")


@router.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
  # 1. Отвечаем мгновенно
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
    order_db_id = (
        result.get("id", uuid.uuid4().hex[:6])
        if isinstance(result, dict)
        else uuid.uuid4().hex[:6]
    )

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

    order_id = f"tg_order_{order_db_id}"

    # 3. Безопасное получение URL
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

      # Очищаем корзину после успешной отправки кнопки
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
# НАСТРОЙКИ PAYBOX / FREEDOM PAY
# =====================================================================
PAYBOX_MERCHANT_ID = "YOUR_TEST_MERCHANT_ID"  # Ваш ID мерчанта в PayBox
PAYBOX_SECRET_KEY = "YOUR_TEST_SECRET_KEY"  # Ваш секретный ключ в PayBox
PAYBOX_TEST_MODE = "1"  # "1" - тестовый режим (песочница), "0" - боевой


def generate_paybox_signature(
    script_name: str, params: dict, secret_key: str
) -> str:
  """Формирует MD5-подпись для PayBox (Freedom Pay).

  Параметры сортируются по алфавиту ключей, склеиваются через ';' с именем
  скрипта и секретным ключом.
  """
  sorted_params = sorted(params.items(), key=lambda x: x[0])
  string_to_hash = (
      [script_name] + [str(val) for _, val in sorted_params] + [secret_key]
  )
  raw_string = ";".join(string_to_hash)
  return hashlib.md5(raw_string.encode("utf-8")).hexdigest()


async def generate_paybox_url(total_amount: float, order_id: str) -> str:
  """Асинхронная генерация ссылки на оплату через PayBox API (с заглушкой для

  локальных тестов).
  """
  # 1. ЗАГЛУШКА ДЛЯ ЛОКАЛЬНОЙ РАЗРАБОТКИ
  # Если ключи реального аккаунта еще не указаны, возвращаем тестовую форму
  if PAYBOX_MERCHANT_ID == "YOUR_TEST_MERCHANT_ID":
    return f"https://paybox.money/payment/test?order={order_id}&amount={total_amount:.2f}"

  # 2. РЕАЛЬНЫЙ ВЫЗОВ (Сработает при указании настоящих Merchant ID и Secret Key)
  params = {
      "pg_merchant_id": PAYBOX_MERCHANT_ID,
      "pg_amount": f"{total_amount:.2f}",
      "pg_currency": "KGS",
      "pg_order_id": str(order_id),
      "pg_description": "Оплата заказа в Telegram",
      "pg_result_url": (
          "https://landmass-unclaimed-gathering.ngrok-free.dev/webhook/paybox"
      ),
      "pg_testing_mode": PAYBOX_TEST_MODE,
      "pg_salt": uuid.uuid4().hex[:10],
  }

  params["pg_sig"] = generate_paybox_signature(
      "init_payment.php", params, PAYBOX_SECRET_KEY
  )

  url = "https://api.paybox.money/init_payment.php"

  async with httpx.AsyncClient(follow_redirects=True) as client:
    response = await client.post(url, data=params, timeout=10.0)

    if response.status_code != 200:
      raise Exception(f"HTTP Status {response.status_code}")

    root = ET.fromstring(response.text)
    status = root.findtext("pg_status")

    if status == "ok":
      redirect_url = root.findtext("pg_redirect_url")
      if redirect_url:
        return redirect_url
      raise Exception("В ответе PayBox отсутствует pg_redirect_url")
    else:
      error_code = root.findtext("pg_error_code")
      error_desc = root.findtext("pg_error_description")
      raise Exception(f"Ошибка PayBox {error_code}: {error_desc}")
# =====================================================================
# ХЕНДЛЕР ПОДТВЕРЖДЕНИЯ ЗАКАЗА
# =====================================================================
@router.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
  await callback.answer()

  data = await state.get_data()
  cart = data.get("cart", [])

  if not cart:
    await callback.message.answer("❗ Ваша корзина пуста.")
    return

  # 1. Отправляем заказ в FastAPI
  try:
    result = await create_order(callback.from_user.id, cart)
  except Exception as e:
    print(f"Ошибка при вызове create_order: {e}")
    result = None

  if result:
    order_db_id = (
        result.get("id", uuid.uuid4().hex[:6])
        if isinstance(result, dict)
        else uuid.uuid4().hex[:6]
    )

    # 2. Считаем итоговую сумму заказа
    total_amount = 0.0
    all_products = await get_all_products() or []
    for item in cart:
      for p in all_products:
        if int(item["product_id"]) == int(p["id"]):
          price = float(p.get("price", 0))
          quantity = int(item.get("quantity", 1))
          total_amount += price * quantity

    if total_amount == 0:
      total_amount = 100.0  # Дефолтное значение для тестов

    order_id = f"tg_order_{order_db_id}"

    # 3. Запрашиваем ссылку у PayBox
    try:
      url = await generate_paybox_url(total_amount, order_id)

      markup = InlineKeyboardMarkup(
          inline_keyboard=[
              [InlineKeyboardButton(text="💳 Оплатить заказ", url=url)]
          ]
      )

      await callback.message.answer(
          "✅ Ваш заказ оформлен!\nПерейдите по кнопке для оплаты:",
          reply_markup=markup,
      )

      # Очищаем корзину
      await state.update_data(cart=[])

      await callback.message.answer(
          "💬 После успешной оплаты с вами свяжется наш менеджер."
      )

    except asyncio.TimeoutError:
      print("⚠️ PayBox недоступен (Connect Timeout)")
      await callback.message.answer(
          "❌ Сервис оплаты временно недоступен. Попробуйте позже."
      )
    except Exception as e:
      print(f"Ошибка PayBox: {e}")
      await callback.message.answer(
          "❌ Ошибка при формировании ссылки на оплату."
      )
  else:
    await callback.message.answer(
        "❌ Ошибка при оформлении заказа на сервере. Попробуйте позже."
    )