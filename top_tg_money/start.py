from aiotdlib import Client
from aiotdlib.api import Chat, Message, MessageText, Ok
from asyncpg import Pool
from loguru import logger

from account import TelegramAccount
from top_tg_money import TopTgMoney


async def join_top_tg_money(client: Client, referral: str) -> bool:
    chats_ids = [chat.id for chat in await client.get_main_list_chats(limit=500)]

    if TopTgMoney.NOTIF_ID not in chats_ids:
        chat = await client.api.search_public_chat(username='Bot_notifications')
        if isinstance(chat, Chat):
            result = await client.api.join_chat(chat_id=chat.id)
            if isinstance(result, Ok):
                logger.info(f'{client.settings.phone_number} joined Bot_notifications')
            else:
                return False
        else:
            return False
    else:
        logger.warning(f'{client.settings.phone_number} Bot_notifications already exists')

    if TopTgMoney.CHANNELS_ID not in chats_ids:
        chat = await client.api.search_public_chat(username='CheatFollowers')
        if isinstance(chat, Chat):
            result = await client.api.join_chat(chat_id=chat.id)
            if isinstance(result, Ok):
                logger.info(f'{client.settings.phone_number} joined CheatFollowers')
            else:
                return False
        else:
            return False
    else:
        logger.warning(f'{client.settings.phone_number} CheatFollowers already exists')

    if TopTgMoney.BOT_ID not in chats_ids:
        chat = await client.api.search_public_chat(username='Toptgmoney_bot')
        if isinstance(chat, Chat):
            print(referral)
            result = await client.api.send_bot_start_message(
                bot_user_id=chat.id,
                chat_id=chat.id,
                parameter=referral
            )
            if isinstance(result, Message) and isinstance(result.content, MessageText):
                logger.info(f'{client.settings.phone_number} {result.content.text.text}')
            else:
                return False
        else:
            return False
    else:
        logger.warning(f'{client.settings.phone_number} Toptgmoney_bot already exists')
    return True


async def init(client: Client, account: TelegramAccount, pool: Pool) -> bool:
    referral = [ref for ref in await TelegramAccount.get_accounts(pool=pool) if ref.referral.isdigit()]
    if len(referral) > 0:
        referral = referral[0].referral
    else:
        account.referral = await client.get_my_id()
        referral = ''
    return await join_top_tg_money(client=client, referral=referral)
