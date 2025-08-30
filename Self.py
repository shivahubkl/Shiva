import asyncio
import re
import requests
from telethon import TelegramClient, events, functions

# ==== FIXED VALUES ====
api_id = 25545804
api_hash = "9f93cef711ef40b986eb7ea99dca9ef3"
phone = "+917457933933"

client = TelegramClient('mm_selfbot', api_id, api_hash)

OWNER_ID = 6645008875
VOUCH_LINK = "t.me/dullxd"
REDIRECT_LINK = "t.me/cryntox"
UPI_ID = "shivaxtrivedi@fam"

# ==== FUNCTIONS ====
async def is_owner(event):
    sender = await event.get_sender()
    return sender.id == OWNER_ID

def parse_duration(duration_str):
    match = re.match(r"(\d+)([smh])", duration_str)
    if not match:
        raise ValueError("Invalid duration format. Use 's', 'm', or 'h'.")
    value, unit = int(match.group(1)), match.group(2)
    return value * {"s": 1, "m": 60, "h": 3600}[unit]

# ==== COMMANDS ====
@client.on(events.NewMessage(pattern=r'^\.mm$'))
async def create_mm_group(event):
    if not await is_owner(event):
        return
    try:
        result = await client(functions.channels.CreateChannelRequest(
            title="Brontz MM | @middlegg",
            about="Official Middleman Group",
            megagroup=True
        ))
        group_id = result.chats[0].id
        link = await client(functions.messages.ExportChatInviteRequest(peer=group_id))
        await event.edit(f"**Group Created:** [Brontz MM | @middlegg ]({link.link})")
    except Exception as e:
        await event.edit(f"❌ Failed to create group: {e}")

@client.on(events.NewMessage(pattern=r'^\.close (\d+[smh])$'))
async def auto_close_group_handler(event):
    if not await is_owner(event):
        return
    try:
        duration_str = event.pattern_match.group(1)
        seconds = parse_duration(duration_str)

        for remaining in range(seconds, 0, -1):
            mins, secs = divmod(remaining, 60)
            await event.edit(
                f"<b>⏳ Attention! This group will be deleted in {mins}:{secs:02} ⏳</b>\n\n"
                "<b>🙏 Thank you sincerely for trusting me as your Middleman.</b>\n"
                "<b><i>Your confidence means a lot, and I’m honored to have helped make your trade safe and smooth.</i></b>\n\n"
                "<b><i>💼 If you need my service again or want updates, don’t hesitate to reach out!</i></b>\n\n"
                "<b>Wishing you many successful trades ahead! 🚀</b>",
                parse_mode='html'
            )
            await asyncio.sleep(1)

        entity = await client.get_entity(event.chat_id)
        await client(functions.channels.DeleteChannelRequest(channel=entity))

    except Exception as e:
        await event.edit(f"❌ An error occurred: {str(e)}")

@client.on(events.NewMessage(pattern=r'^\.upi$'))
async def show_upi(event):
    if not await is_owner(event):
        return
    text = (
        "<b>💳 Please make your payment to the following UPI:</b>\n"
        f"<code>{UPI_ID}</code>\n\n"
        "<b><i>🙏 Your timely payment is greatly appreciated!</i></b>\n"
        "<b><i>🔒 Secure, fast, and hassle-free.</i></b>"
    )
    await event.edit(text, parse_mode='html')

@client.on(events.NewMessage(pattern=r'^\.chnl$'))
async def redirect_link(event):
    if not await is_owner(event):
        return
    await event.edit(
        f"<b>👉 Join all my channels! 📢✨</b>\n\n"
        f"<b><i>Stay ahead with exclusive news, tips, and surprises you won’t find anywhere else! 🚀💥</i></b>\n\n"
        f"<b><i>Don’t miss out — be part of the action! 🎯🔗</i></b>\n\n"
        f"Here is the link 🖇️ <b><i>{REDIRECT_LINK}</i></b>",
        parse_mode='html'
    )

@client.on(events.NewMessage(pattern=r'^\.fee (.+)'))
async def calculate_fee(event):
    if not await is_owner(event):
        return
    try:
        expression = event.pattern_match.group(1)
        if '+' in expression and '%' in expression:
            base_str, fee_str = expression.split('+')
            base = float(base_str)
            percent = float(fee_str.strip('%'))
            fee = base * (percent / 100)
            total = base + fee
            text = (
                f"<b>💰 Total Amount:</b>\n"
                f"<code>{expression} = ₹{total:.2f} ✅</code>\n\n"
                f"<b><i>📩 Please make the payment to the provided UPI.</i></b>\n\n"
                f"<b><i>🖼️ Once done, kindly send a screenshot as confirmation.</i></b>\n\n"
                f"<b><i>🙏 Thank you for your cooperation!</i></b>"
            )
            await event.edit(text, parse_mode='html')
        else:
            await event.edit("❌ Invalid format. Use `.fee 100+0.5%`")
    except Exception:
        await event.edit("❌ Error processing calculation.")

@client.on(events.NewMessage(pattern=r'^\.cal (.+)'))
async def calculate_expression(event):
    if not await is_owner(event):
        return
    expression = event.pattern_match.group(1)
    try:
        await event.edit("🧠 <b><i>Calculating your expression… Please wait a moment!</i></b>", parse_mode='html')
        await asyncio.sleep(1.5)
        if not re.match(r'^[0-9+\-*/(). ]+$', expression):
            await event.edit("❌ Invalid characters in expression.")
            return
        result = eval(expression)
        await event.edit(f"<b>🧮 Calculation Result:</b>\n<code>{expression} = {result}</code>", parse_mode='html')
    except Exception as e:
        await event.edit(f"❌ Error: {e}")

@client.on(events.NewMessage(pattern=r'^\.deal$'))
async def deal_message(event):
    if not await is_owner(event):
        return
    buyer_username = "buyer_username"
    seller_username = "seller_username"
    item_of_deal = "item of deal"
    total_amount = "TOTAL amount"
    text = (
        "```\n"
        "⚖️ Middleman Deal Initiated\n\n"
        f"Buyer: @{buyer_username}  \n"
        f"Seller: @{seller_username}  \n"
        f"Item: {item_of_deal}\n"
        f"Amount: {total_amount}\n"
        "```"
    )
    await event.edit(text)

@client.on(events.NewMessage(pattern=r'^\.yes$'))
async def payment_received(event):
    if not await is_owner(event):
        return
    text = (
        "<u><b>✨ MM Update! </b></u>\n\n"
        "<b><i>💰 Payment received successfully! ☑️</i></b>\n\n"
        "<b><i>Thank you for your prompt transaction — the deal is moving forward smoothly! 🚀</i></b>"
    )
    await event.edit(text, parse_mode='html')

@client.on(events.NewMessage(pattern=r'^\.no$'))
async def payment_not_received(event):
    if not await is_owner(event):
        return
    text = (
        "<b>‼️ MM Update! ‼️</b>\n\n"
        "<b><i><s>💰 Payment not received yet! 🚨⚠️</s></i></b>\n"
        "<b><i>Please double-check your payment status to avoid delays. Your cooperation is appreciated! ⏳</i></b>"
    )
    await event.edit(text, parse_mode='html')

@client.on(events.NewMessage(pattern=r'^\.cmds$'))
async def show_commands(event):
    if not await is_owner(event):
        return
    cmds = (
        "<b>MM SELFBOT</b>\n\n"
        "<b><i>Available Commands:</i></b>\n\n"
        "<code>• .mm            — Create MM group</code>\n"
        "<code>• .close 30s/m/h — Close group with countdown</code>\n"
        "<code>• .fee 100+0.5%  — Calculate total price with fee</code>\n"
        "<code>• .cal 100+50-20 — Calculate math expression</code>\n"
        "<code>• .upi           — Show UPI ID</code>\n"
        "<code>• .chnl          — Show channels link</code>\n"
        "<code>• .deal          — Show deal template</code>\n"
        "<code>• .yes / .no     — MM payment updates</code>\n"
        "<code>• .cmds          — Show this help message</code>"
    )
    await event.edit(cmds, parse_mode='html')

# ==== START BOT ====
print("Starting the MM Selfbot...")

client.start(phone=phone)
client.run_until_disconnected()
