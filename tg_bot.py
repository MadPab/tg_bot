import random
import sqlite3
import configparser

from telebot import types, TeleBot, custom_filters
from telebot.storage import StateMemoryStorage
from telebot.handler_backends import State, StatesGroup

print('Start telegram bot...')

conn = sqlite3.connect('words.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS words
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   word TEXT NOT NULL,
                   translate TEXT NOT NULL,
                   user_id INTEGER)''')
conn.commit()

state_storage = StateMemoryStorage()
config = configparser.ConfigParser()
config.read("settings.ini")
token_bot = config["TGBOT"]["token"]
bot = TeleBot(token_bot, state_storage=state_storage)

known_users = []
userStep = {}
buttons = []

def show_hint(*lines):
    return '\n'.join(lines)

def show_target(data):
    return f"{data['target_word']} -> {data['translate_word']}"

class Command:
    ADD_WORD = 'Добавить слово ➕'
    DELETE_WORD = 'Удалить слово🔙'
    NEXT = 'Дальше ⏭'

class MyStates(StatesGroup):
    target_word = State()
    translate_word = State()
    another_words = State()

def get_user_step(uid):
    if uid in userStep:
        return userStep[uid]
    else:
        known_users.append(uid)
        userStep[uid] = 0
        print("New user detected, who hasn't used \"/start\" yet")
        return 0

@bot.message_handler(commands=['cards', 'start'])
def create_cards(message):
    cid = message.chat.id
    if cid not in known_users:
        known_users.append(cid)
        userStep[cid] = 0
        bot.send_message(cid, "Привет 👋 Давай попрактикуемся в английском языке. Тренировки можешь проходить в удобном для себя темпе.\n\nУ тебя есть возможность использовать тренажёр, как конструктор, и собирать свою собственную базу для обучения. Для этого воспользуйся инструментами:\n\nДобавить слово ➕\nУдалить слово 🔙")

    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    
    global buttons
    buttons = []
    
    cursor.execute('SELECT word, translate FROM words WHERE user_id IS NULL OR user_id = ?', (cid,))
    rows = cursor.fetchall()
    
    if rows:
        target_word, translate = random.choice(rows)
        target_word_btn = types.KeyboardButton(target_word)
        buttons.append(target_word_btn)
        
        others = [row[0] for row in random.sample(rows, min(len(rows), 4)) if row[0] != target_word]
        other_words_btns = [types.KeyboardButton(word) for word in others]
        buttons.extend(other_words_btns)
        
        random.shuffle(buttons)
        
        next_btn = types.KeyboardButton(Command.NEXT)
        add_word_btn = types.KeyboardButton(Command.ADD_WORD)
        delete_word_btn = types.KeyboardButton(Command.DELETE_WORD)
        buttons.extend([next_btn, add_word_btn, delete_word_btn])
        
        markup.add(*buttons)
        
        greeting = f"Выбери перевод слова:\n🇷🇺 {translate}"
        bot.send_message(message.chat.id, greeting, reply_markup=markup)
        bot.set_state(message.from_user.id, MyStates.target_word, message.chat.id)
        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            data['target_word'] = target_word
            data['translate_word'] = translate
            data['other_words'] = others
    else:
        bot.send_message(cid, "Ваша база данных пуста. Добавьте новые слова с помощью команды 'Добавить слово ➕'.")

@bot.message_handler(func=lambda message: message.text == Command.NEXT)
def next_cards(message):
    create_cards(message)

@bot.message_handler(func=lambda message: message.text == Command.DELETE_WORD)
def delete_word(message):
    cid = message.chat.id
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        target_word = data['target_word']
        
        cursor.execute('DELETE FROM words WHERE word = ? AND user_id = ?', (target_word, cid))
        conn.commit()
        
        bot.send_message(cid, f"Слово '{target_word}' удалено из вашей базы данных.")
        create_cards(message)

@bot.message_handler(func=lambda message: message.text == Command.ADD_WORD)
def add_word(message):
    cid = message.chat.id
    bot.send_message(cid, "Отправьте новое слово в формате 'слово перевод', например 'Hello Привет'.")

    userStep[cid] = 1
    bot.set_state(message.from_user.id, MyStates.another_words, message.chat.id)

@bot.message_handler(state=MyStates.another_words, content_types=['text'])
def save_word(message):
    cid = message.chat.id
    text = message.text
    try:
        word, translate = text.split(maxsplit=1)
        cursor.execute('INSERT INTO words (word, translate, user_id) VALUES (?, ?, ?)', (word, translate, cid))
        conn.commit()
        bot.send_message(cid, f"Слово '{word}' с переводом '{translate}' добавлено в вашу базу данных.")
    except ValueError:
        bot.send_message(cid, "Ошибка в формате. Пожалуйста, отправьте слово и перевод в формате 'слово перевод'.")
    
    userStep[cid] = 0
    bot.set_state(message.from_user.id, None, message.chat.id)
    create_cards(message)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def message_reply(message):
    text = message.text
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        target_word = data['target_word']
        if text == target_word:
            hint = show_target(data)
            hint_text = ["Отлично!❤", hint]
            next_btn = types.KeyboardButton(Command.NEXT)
            add_word_btn = types.KeyboardButton(Command.ADD_WORD)
            delete_word_btn = types.KeyboardButton(Command.DELETE_WORD)
            buttons.extend([next_btn, add_word_btn, delete_word_btn])
            hint = show_hint(*hint_text)
        else:
            for btn in buttons:
                if btn.text == text:
                    btn.text = text + '❌'
                    break
            hint = show_hint("Допущена ошибка!",
                             f"Попробуй ещё раз вспомнить слово 🇷🇺{data['translate_word']}")
    markup.add(*buttons)
    bot.send_message(message.chat.id, hint, reply_markup=markup)

bot.add_custom_filter(custom_filters.StateFilter(bot))

bot.infinity_polling(skip_pending=True)
