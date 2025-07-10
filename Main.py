from pyrogram import Client, filters from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton import json import os from datetime import datetime, timedelta from flask import Flask from threading import Thread

API_ID = 25545804 API_HASH = "9f93cef711ef40b986eb7ea99dca9ef3" BOT_TOKEN = "8193387280:AAEDrXi0JkckYajblf99BFx7EhSgGQWwzxE"

ADMIN_ID = 6645008875 DATABASE_FILE = "balance.json" DEPOSIT_LOG = "deposit_log.json" WITHDRAW_MIN = 0.10 WITHDRAW_MIN_INR = 10

app = Client("casino_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN) web_app = Flask('')

@web_app.route('/') def home(): return "Bot is running."

def run(): web_app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

def load_data(file): if not os.path.exists(file): with open(file, "w") as f: json.dump({}, f) with open(file, "r") as f: return json.load(f)

def save_data(file, data): with open(file, "w") as f: json.dump(data, f)

def get_balance(user_id): data = load_data(DATABASE_FILE) return data.get(str(user_id), 0)

def update_balance(user_id, amount): data = load_data(DATABASE_FILE) data[str(user_id)] = get_balance(user_id) + amount save_data(DATABASE_FILE, data)

def log_deposit(user_id): data = load_data(DEPOSIT_LOG) data[str(user_id)] = datetime.utcnow().isoformat() save_data(DEPOSIT_LOG, data)

def can_withdraw(user_id): data = load_data(DEPOSIT_LOG) date_str = data.get(str(user_id)) if not date_str: return False deposit_date = datetime.fromisoformat(date_str) return datetime.utcnow() >= deposit_date + timedelta(days=3)

@app.on_message(filters.command("start")) def start(client, message): keyboard = InlineKeyboardMarkup([ [InlineKeyboardButton("\ud83d\udcb0 Balance", callback_data="bal"), InlineKeyboardButton("\ud83c\udfb2 Play", callback_data="play")], [InlineKeyboardButton("\ud83d\udd27 Help", callback_data="help")] ]) message.reply_text("\ud83c\udf10 Welcome to Shiva Casino Bot!\nSend real emoji to play: 🎲 🎯 ⚽️ 🎳 🏀", reply_markup=keyboard)

@app.on_callback_query() def callback_handler(client, callback_query): user_id = callback_query.from_user.id if callback_query.data == "bal": bal = get_balance(user_id) callback_query.message.edit_text(f"\ud83d\udcb0 Your Balance: ${bal:.2f}") elif callback_query.data == "help": callback_query.message.edit_text( "\ud83d\udd27 Casino Bot Help:\nSend 🎲 🎯 ⚽️ 🎳 🏀 real emoji to play!\n/admin only: /addbal user_id amount\n/withdraw to request payout." ) elif callback_query.data == "play": callback_query.message.edit_text("Send any real emoji now: 🎲 🎯 ⚽️ 🎳 🏀")

@app.on_message(filters.dice) def handle_real_dice(client, message): user_id = message.from_user.id bal = get_balance(user_id) emoji = message.dice.emoji value = message.dice.value

bet_amount = 1
if bal < bet_amount:
    message.reply_text("\u274c Not enough balance.")
    return

result_text = f"{emoji} Result: {value}\n"

if emoji == "🎲":
    if value >= 4:
        win_amount = bet_amount * 1.92
        update_balance(user_id, win_amount)
        result_text += f"You won +${win_amount:.2f}!"
    else:
        update_balance(user_id, -bet_amount)
        result_text += f"You lost -${bet_amount:.2f}."

elif emoji == "🎯":
    if value == 6:
        win_amount = bet_amount * 2
        update_balance(user_id, win_amount)
        result_text += f"Bullseye! +${win_amount:.2f}!"
    else:
        update_balance(user_id, -bet_amount)
        result_text += f"Missed -${bet_amount:.2f}."

elif emoji in ["⚽️", "🎳", "🏀"]:
    if value >= 4:
        win_amount = bet_amount * 1.5
        update_balance(user_id, win_amount)
        result_text += f"Win! +${win_amount:.2f}!"
    else:
        update_balance(user_id, -bet_amount)
        result_text += f"Lost -${bet_amount:.2f}."

message.reply_text(result_text)

@app.on_message(filters.command("addbal") & filters.user(ADMIN_ID)) def add_balance(client, message): try: user_id = int(message.text.split()[1]) amount = float(message.text.split()[2]) update_balance(user_id, amount) log_deposit(user_id) message.reply_text(f"\u2705 Added ${amount:.2f} to {user_id}'s balance.") except Exception as e: message.reply_text(f"\u26a0\ufe0f Usage: /addbal user_id amount\n{e}")

@app.on_message(filters.command("withdraw")) def withdraw_request(client, message): user_id = message.from_user.id bal = get_balance(user_id)

if bal < WITHDRAW_MIN:
    message.reply_text(f"\u274c Minimum withdraw is ${WITHDRAW_MIN}/₹{WITHDRAW_MIN_INR}. Your balance: ${bal:.2f}")
    return

if not can_withdraw(user_id):
    message.reply_text("\u274c Withdraw available only after 3 days from first deposit.")
    return

message.reply_text("\u2705 Withdraw request sent to admin. Please wait for approval.")
client.send_message(
    ADMIN_ID,
    f"\ud83d\udce4 Withdraw Request:\nUser ID: {user_id}\nBalance: ${bal:.2f}\nApprove manually!"
)

app.run()

