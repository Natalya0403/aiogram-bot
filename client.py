import os
import httpx
from dotenv import load_dotenv

load_dotenv()

# Безопасное чтение переменной окружения
API_URL = (os.getenv("API_URL") or "http://127.0.0.1:8000").rstrip("/")


async def get_all_products(order_by: str = "id", direction: str = "asc"):
  async with httpx.AsyncClient() as client:
    try:
      # ИСПРАВЛЕНО: /product вместо /products (согласно роутеру FastAPI)
      response = await client.get(
          f"{API_URL}/product",
          params={"order_by": order_by, "direction": direction},
      )
      if response.status_code == 200:
        return response.json()
      return []
    except Exception as e:
      print(f"Ошибка при получении списка товаров: {e}")
      return []


# ИСПРАВЛЕНО: Переименовано в get_product_by_title
async def get_product_by_title(product_title: str):
  async with httpx.AsyncClient() as client:
    try:
      response = await client.get(f"{API_URL}/product/search/{product_title}")
      if response.status_code == 200:
        return response.json()
      return []
    except Exception as e:
      print(f"Ошибка при поиске товара: {e}")
      return []


async def create_order(user_id: int, items: list[dict]):
  async with httpx.AsyncClient() as client:
    try:
      response = await client.post(
          f"{API_URL}/order/add", json={"user_id": user_id, "items": items}
      )
      # ИСПРАВЛЕНО: is_success проверяет и 200, и 201 Created
      if response.is_success:
        data = response.json()
        return data.get("id")
      else:
        return None
    except Exception as e:
      print(f"Ошибка при создании заказа: {e}")
      return False

# опишем дополнительную функцию для получения информации о товаре по id
async def get_product_by_id(product_id: int):
  async with httpx.AsyncClient() as client:
    try:
      resp = await client.get(f"{API_URL}/product/{product_id}")
      if resp.status_code == 200:
        return resp.json()
    except Exception as e:
      print('Ошибка при получении товара',e)
    return None

#=====================================================================
async def create_product(data: dict):
  async with httpx.AsyncClient() as client:
    try:
      response = await client.post(
          f"{API_URL}/product/add", json=data
      )
      # ИСПРАВЛЕНО: is_success проверяет и 200, и 201 Created
      return response.is_success
    except Exception as e:
      print(f"Ошибка при создании заказа: {e}")
      return False

async def get_all_orders():
  async with httpx.AsyncClient() as client:
    try:
      response = await client.get(
          f"{API_URL}/orders")
      if response.status_code == 200:
        return response.json()
      return []
    except Exception as e:
      print(f"Ошибка при получении списка заказов: {e}")
      return []
#================================================================================
async def get_order_by_id(order_id: int):
    async with httpx.AsyncClient() as client:
      try:
        resp = await client.get(f"{API_URL}/orders/{order_id}")
        if resp.status_code == 200:
          return resp.json()
      except Exception as e:
        print('Ошибка при получении товара', e)
      return None
#================================================================================

# async def update_user_by_id(user_id: int, name: str, email: str):
#     async with httpx.AsyncClient() as client:
#         try:
#             response = await client.put(f"{API_URL}/users/{user_id}", json={"name": name, "email": email})
#             return response.status_code == 200
#         except Exception as e:
#             print("Ошибка при получении пользователей:", e)
#             return None
        

# async def delete_user_by_id(user_id: int):
#     async with httpx.AsyncClient() as client:
#         try:
#             response = await client.delete(f"{API_URL}/users/{user_id}")
#             return response.status_code == 200
#         except Exception as e:
#             print("Ошибка при получении пользователей:", e)
#             return None