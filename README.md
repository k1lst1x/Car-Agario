# 🚗 Car Agario — Multiplayer Battle Arena

**Car Agario** — это динамичная браузерная онлайн-игра, где игроки на машинах соревнуются друг с другом на огромной карте. Собирайте бонусы, прокачивайте свою машину, стреляйте по соперникам и доминируйте на арене!

---

## ✨ Основные фичи

- **🎮 Реалтайм мультиплеер:** WebSocket (Django Channels)
- **🖥️ Камера:** Следит за игроком для полного погружения
- **🚘 SVG-графика:** Красочные SVG-машины с поворотами и анимацией
- **⚔️ Прокачка:** Улучшайте HP, скорость, урон и скорострельность
- **💎 Орбы:** Подбирайте бонусы и усиливайтесь прямо на поле боя

---

## 🛠️ Технологии

- **Backend:** Django, Django Channels (WebSockets), Asyncio
- **Frontend:** JavaScript, HTML5 Canvas, SVG
- **База данных:** PostgreSQL / SQLite (по умолчанию)

---

## 🚀 Быстрый старт

```bash
git clone https://github.com/yourusername/car-agario.git
cd car-agario

# Установка зависимостей
pip install -r requirements.txt

# Запуск сервера
python manage.py runserver
