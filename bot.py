"""
Бот "Что посмотреть?" - ПРЕМИУМ ВЕРСИЯ
✅ База данных SQLite
✅ API TMDB (тысячи фильмов)
✅ Поиск по названию
✅ Умные рекомендации
✅ Постеры фильмов
✅ Статистика и достижения
"""

import os
import logging
import sqlite3
import random
import requests
from datetime import datetime
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
TMDB_API_KEY = "8265bd1679663a7ea12ac168da84d2e8"  # Бесплатный ключ для демо

if not TOKEN:
    logger.error("❌ BOT_TOKEN not found!")
    exit(1)

# Flask для Render (чтобы не засыпал)
app = Flask(__name__)

@app.route('/')
def home():
    return "🎬 Movie Bot is running!"

@app.route('/health')
def health():
    return "OK", 200


# === БАЗА ДАННЫХ ===

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  created_at TEXT,
                  total_watched INTEGER DEFAULT 0)''')
    
    # Таблица watchlist
    c.execute('''CREATE TABLE IF NOT EXISTS watchlist
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  movie_id INTEGER,
                  title TEXT,
                  added_at TEXT)''')
    
    # Таблица просмотренных
    c.execute('''CREATE TABLE IF NOT EXISTS watched
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  movie_id INTEGER,
                  title TEXT,
                  rating INTEGER,
                  watched_at TEXT)''')
    
    # Таблица поиска (кэш)
    c.execute('''CREATE TABLE IF NOT EXISTS search_cache
                 (query TEXT PRIMARY KEY,
                  results TEXT,
                  cached_at TEXT)''')
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")


# === API TMDB ===

def search_movie(query):
    """Поиск фильма через TMDB API"""
    try:
        url = f"https://api.themoviedb.org/3/search/multi"
        params = {
            'api_key': TMDB_API_KEY,
            'query': query,
            'language': 'ru-RU',
            'page': 1
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('results', [])[:5]  # Топ-5 результатов
        return []
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []


def search_actor(query):
    """Поиск актёра через TMDB API"""
    try:
        url = f"https://api.themoviedb.org/3/search/person"
        params = {
            'api_key': TMDB_API_KEY,
            'query': query,
            'language': 'ru-RU',
            'page': 1
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('results', [])[:5]  # Топ-5 актёров
        return []
    except Exception as e:
        logger.error(f"Actor search error: {e}")
        return []


def get_actor_movies(actor_id):
    """Получить фильмы актёра"""
    try:
        url = f"https://api.themoviedb.org/3/person/{actor_id}/movie_credits"
        params = {
            'api_key': TMDB_API_KEY,
            'language': 'ru-RU'
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            cast = data.get('cast', [])
            # Сортируем по популярности
            cast.sort(key=lambda x: x.get('popularity', 0), reverse=True)
            return cast[:10]  # Топ-10 фильмов
        return []
    except Exception as e:
        logger.error(f"Actor movies error: {e}")
        return []


def get_actor_details(actor_id):
    """Получить детали актёра"""
    try:
        url = f"https://api.themoviedb.org/3/person/{actor_id}"
        params = {
            'api_key': TMDB_API_KEY,
            'language': 'ru-RU'
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Actor details error: {e}")
        return None


def get_movie_details(movie_id, media_type='movie'):
    """Получить детали фильма"""
    try:
        url = f"https://api.themoviedb.org/3/{media_type}/{movie_id}"
        params = {
            'api_key': TMDB_API_KEY,
            'language': 'ru-RU',
            'append_to_response': 'credits,similar'
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Details error: {e}")
        return None


def get_popular_movies():
    """Получить популярные фильмы"""
    try:
        url = "https://api.themoviedb.org/3/movie/popular"
        params = {
            'api_key': TMDB_API_KEY,
            'language': 'ru-RU',
            'page': 1
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('results', [])[:10]
        return []
    except Exception as e:
        logger.error(f"Popular error: {e}")
        return []


def get_top_rated_movies():
    """Топ фильмов по рейтингу"""
    try:
        url = "https://api.themoviedb.org/3/movie/top_rated"
        params = {
            'api_key': TMDB_API_KEY,
            'language': 'ru-RU',
            'page': 1
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('results', [])[:10]
        return []
    except Exception as e:
        logger.error(f"Top rated error: {e}")
        return []


def get_poster_url(poster_path):
    """URL постера"""
    if poster_path:
        return f"https://image.tmdb.org/t/p/w500{poster_path}"
    return None


# === ФУНКЦИИ БД ===

def add_user(user_id, username):
    """Добавить пользователя"""
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO users (user_id, username, created_at)
                 VALUES (?, ?, ?)''', (user_id, username, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def add_to_watchlist(user_id, movie_id, title):
    """Добавить в watchlist"""
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    
    # Проверка дубликата
    c.execute('SELECT * FROM watchlist WHERE user_id=? AND movie_id=?', (user_id, movie_id))
    if c.fetchone():
        conn.close()
        return False
    
    c.execute('''INSERT INTO watchlist (user_id, movie_id, title, added_at)
                 VALUES (?, ?, ?, ?)''', 
              (user_id, movie_id, title, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True


def add_to_watched(user_id, movie_id, title, rating=0):
    """Добавить в просмотренные"""
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    
    # Проверка дубликата
    c.execute('SELECT * FROM watched WHERE user_id=? AND movie_id=?', (user_id, movie_id))
    if c.fetchone():
        conn.close()
        return False
    
    c.execute('''INSERT INTO watched (user_id, movie_id, title, rating, watched_at)
                 VALUES (?, ?, ?, ?, ?)''', 
              (user_id, movie_id, title, rating, datetime.now().isoformat()))
    
    # Убрать из watchlist
    c.execute('DELETE FROM watchlist WHERE user_id=? AND movie_id=?', (user_id, movie_id))
    
    # Обновить счётчик
    c.execute('UPDATE users SET total_watched = total_watched + 1 WHERE user_id=?', (user_id,))
    
    conn.commit()
    conn.close()
    return True


def get_watchlist(user_id):
    """Получить watchlist"""
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute('SELECT movie_id, title FROM watchlist WHERE user_id=? ORDER BY added_at DESC', (user_id,))
    results = c.fetchall()
    conn.close()
    return results


def get_watched(user_id):
    """Получить просмотренные"""
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute('SELECT movie_id, title, rating FROM watched WHERE user_id=? ORDER BY watched_at DESC', (user_id,))
    results = c.fetchall()
    conn.close()
    return results


def get_user_stats(user_id):
    """Статистика пользователя"""
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM watchlist WHERE user_id=?', (user_id,))
    watchlist_count = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM watched WHERE user_id=?', (user_id,))
    watched_count = c.fetchone()[0]
    
    conn.close()
    return watchlist_count, watched_count


# === ФОРМАТИРОВАНИЕ ===

def format_movie_card(movie, media_type='movie'):
    """Форматирование карточки фильма"""
    type_emoji = "🎬" if media_type == "movie" else "📺"
    
    title = movie.get('title') or movie.get('name', 'Без названия')
    year = movie.get('release_date', movie.get('first_air_date', ''))[:4] if movie.get('release_date') or movie.get('first_air_date') else '—'
    rating = movie.get('vote_average', 0)
    overview = movie.get('overview', 'Описание отсутствует')
    
    message = f"{type_emoji} <b>{title}</b>\n\n"
    message += f"📅 Год: {year}\n"
    message += f"⭐ Рейтинг: {rating:.1f}/10\n\n"
    message += f"📖 <b>Описание:</b>\n{overview[:300]}{'...' if len(overview) > 300 else ''}"
    
    return message


# === УМНЫЕ РЕКОМЕНДАЦИИ ===

def get_smart_recommendation(user_id):
    """Умная рекомендация на основе истории"""
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    
    # Получить последние просмотренные
    c.execute('SELECT movie_id FROM watched WHERE user_id=? ORDER BY watched_at DESC LIMIT 3', (user_id,))
    recent = [row[0] for row in c.fetchall()]
    conn.close()
    
    if recent:
        # Получить похожие на последний просмотренный
        movie_id = recent[0]
        similar = get_movie_details(movie_id)
        if similar and 'similar' in similar:
            similar_movies = similar['similar'].get('results', [])
            if similar_movies:
                return random.choice(similar_movies)
    
    # Fallback на популярные
    popular = get_popular_movies()
    return random.choice(popular) if popular else None


# === ОБРАБОТЧИКИ КОМАНД ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    # Добавить пользователя в БД
    add_user(user_id, username)
    
    watchlist_count, watched_count = get_user_stats(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🎲 Что посмотреть?", callback_data='smart_rec')],
        [
            InlineKeyboardButton("🔥 Популярное", callback_data='popular'),
            InlineKeyboardButton("⭐ Топ рейтинг", callback_data='top_rated')
        ],
        [
            InlineKeyboardButton("🔍 Поиск фильма", callback_data='search_help'),
            InlineKeyboardButton("🎭 Поиск актёра", callback_data='actor_search_help')
        ],
        [
            InlineKeyboardButton(f"📝 Список ({watchlist_count})", callback_data='my_watchlist'),
            InlineKeyboardButton(f"✅ Просмотрено ({watched_count})", callback_data='my_watched')
        ],
        [InlineKeyboardButton("📈 Статистика", callback_data='stats')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"""🎬 Привет, {user.first_name}!

<b>ПРЕМИУМ БОТ</b> для подбора фильмов! 🍿

🌟 <b>Новые возможности:</b>
✅ Тысячи фильмов (TMDB API)
✅ Умные рекомендации
✅ Поиск по названию
✅ 🎭 Поиск по актёрам (НОВИНКА!)
✅ Постеры фильмов
✅ Статистика просмотров

📊 <b>Ваша статистика:</b>
📝 В списке: {watchlist_count}
✅ Просмотрено: {watched_count}

Жми кнопку! 👇"""
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


# === ОБРАБОТЧИК КНОПОК ===

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == 'smart_rec':
        await query.edit_message_text("🔮 Подбираю фильм специально для вас...", parse_mode='HTML')
        
        movie = get_smart_recommendation(user_id)
        
        if movie:
            message = f"🎲 <b>РЕКОМЕНДАЦИЯ</b>\n\n{format_movie_card(movie)}"
            
            # Отправить постер если есть
            poster_url = get_poster_url(movie.get('poster_path'))
            
            movie_id = movie.get('id')
            keyboard = [
                [
                    InlineKeyboardButton("➕ В список", callback_data=f'add_watch_{movie_id}_{movie.get("title", "film")}'),
                    InlineKeyboardButton("✅ Посмотрел", callback_data=f'add_watched_{movie_id}_{movie.get("title", "film")}')
                ],
                [InlineKeyboardButton("🔍 Подробнее", callback_data=f'details_{movie_id}_movie')],
                [
                    InlineKeyboardButton("🎲 Ещё", callback_data='smart_rec'),
                    InlineKeyboardButton("◀️ Меню", callback_data='back')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if poster_url:
                try:
                    await query.message.reply_photo(
                        photo=poster_url,
                        caption=message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                    await query.message.delete()
                    return
                except:
                    pass
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text("❌ Ошибка загрузки. Попробуйте ещё раз.", parse_mode='HTML')
    
    elif query.data == 'popular':
        await query.edit_message_text("🔥 Загружаю популярное...", parse_mode='HTML')
        
        movies = get_popular_movies()
        
        if movies:
            message = "🔥 <b>ПОПУЛЯРНОЕ СЕЙЧАС</b>\n\nВыберите фильм:\n\n"
            
            keyboard = []
            for movie in movies[:10]:
                title = movie.get('title', 'Фильм')
                rating = movie.get('vote_average', 0)
                movie_id = movie.get('id')
                
                keyboard.append([InlineKeyboardButton(
                    f"⭐ {rating:.1f} — {title}",
                    callback_data=f'show_{movie_id}_movie'
                )])
            
            keyboard.append([InlineKeyboardButton("◀️ Меню", callback_data='back')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text("❌ Ошибка загрузки", parse_mode='HTML')
    
    elif query.data == 'top_rated':
        await query.edit_message_text("⭐ Загружаю топ...", parse_mode='HTML')
        
        movies = get_top_rated_movies()
        
        if movies:
            message = "⭐ <b>ТОП ПО РЕЙТИНГУ</b>\n\nЛучшие фильмы всех времён:\n\n"
            
            keyboard = []
            for i, movie in enumerate(movies[:10], 1):
                title = movie.get('title', 'Фильм')
                rating = movie.get('vote_average', 0)
                movie_id = movie.get('id')
                
                keyboard.append([InlineKeyboardButton(
                    f"{i}. ⭐ {rating:.1f} — {title}",
                    callback_data=f'show_{movie_id}_movie'
                )])
            
            keyboard.append([InlineKeyboardButton("◀️ Меню", callback_data='back')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text("❌ Ошибка загрузки", parse_mode='HTML')
    
    elif query.data.startswith('show_'):
        parts = query.data.split('_')
        movie_id = int(parts[1])
        media_type = parts[2]
        
        await query.edit_message_text("⏳ Загружаю детали...", parse_mode='HTML')
        
        movie = get_movie_details(movie_id, media_type)
        
        if movie:
            message = format_movie_card(movie, media_type)
            poster_url = get_poster_url(movie.get('poster_path'))
            
            title = movie.get('title') or movie.get('name', 'film')
            
            keyboard = [
                [
                    InlineKeyboardButton("➕ В список", callback_data=f'add_watch_{movie_id}_{title}'),
                    InlineKeyboardButton("✅ Посмотрел", callback_data=f'add_watched_{movie_id}_{title}')
                ],
                [
                    InlineKeyboardButton("🎲 Похожие", callback_data=f'similar_{movie_id}_{media_type}'),
                    InlineKeyboardButton("◀️ Меню", callback_data='back')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if poster_url:
                try:
                    await query.message.reply_photo(
                        photo=poster_url,
                        caption=message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                    await query.message.delete()
                    return
                except:
                    pass
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    
    elif query.data.startswith('add_watch_'):
        parts = query.data.split('_', 2)
        movie_id = int(parts[2].split('_')[0])
        title = '_'.join(parts[2].split('_')[1:])
        
        success = add_to_watchlist(user_id, movie_id, title)
        
        if success:
            await query.answer("✅ Добавлено в список!", show_alert=True)
        else:
            await query.answer("⚠️ Уже в списке!", show_alert=True)
    
    elif query.data.startswith('add_watched_'):
        parts = query.data.split('_', 2)
        movie_id = int(parts[2].split('_')[0])
        title = '_'.join(parts[2].split('_')[1:])
        
        success = add_to_watched(user_id, movie_id, title)
        
        if success:
            await query.answer("✅ Отмечено! +1 к статистике!", show_alert=True)
        else:
            await query.answer("⚠️ Уже отмечено!", show_alert=True)
    
    elif query.data == 'my_watchlist':
        watchlist = get_watchlist(user_id)
        
        if watchlist:
            message = f"📝 <b>МОЙ СПИСОК</b>\n\nФильмов: {len(watchlist)}\n\n"
            
            keyboard = []
            for movie_id, title in watchlist[:20]
