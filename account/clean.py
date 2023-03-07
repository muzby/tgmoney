import time

from aiotdlib import Client
from aiotdlib.api import BadRequest, ChatTypeSupergroup, ChatTypeBasicGroup, Ok, ChatTypePrivate, ChatTypeSecret
from asyncpg import Pool
from loguru import logger

from account import TelegramAccount


async def clean_subscriptions(client: Client, account: TelegramAccount, pool: Pool, chats_ids: list):
    for subs in chats_ids:
        try:
            chat = await client.get_chat(chat_id=subs)
        except BadRequest as exc:
            logger.warning(exc)
            continue

        '''if isinstance(chat.type_, ChatTypeSupergroup) or isinstance(chat.type_, ChatTypeBasicGroup):
            try:
                result = await client.api.leave_chat(chat_id=chat.id)
                if isinstance(result, Ok):
                    #account.subscriptions.remove(subs)
                    logger.info(
                        f'{client.settings.phone_number} leave {chat.id} '
                        #f'{subs.username if subs.username else subs.invite}'
                    )
                else:
                    logger.error(chat)
                    continue
            except BadRequest as exc:
                logger.warning(exc)
                continue
'''
        if isinstance(chat.type_, ChatTypePrivate):
            try:
                result = await client.api.delete_chat_history(chat_id=chat.id, remove_from_chat_list=True, revoke=True)
                print(result)
                if isinstance(result, Ok):
                    logger.info(f'{client.settings.phone_number} history clear {chat.id} ')
                result = await client.api.delete_chat(chat_id=chat.id)
                if isinstance(result, Ok):
                    # account.subscriptions.remove(subs)
                    logger.info(
                        f'{client.settings.phone_number} deleted {chat.id} '
                        #    f'{subs.username if subs.username else subs.invite}'
                    )
                else:
                    continue
            except BadRequest as exc:
                logger.warning(exc)
                continue

        '''elif isinstance(chat.type_, ChatTypePrivate):
            if chat.can_be_deleted_for_all_users:
                try:
                    #result = await client.api.delete_chat(chat_id=chat.id)
                    result = await client.api.delete_chat_history(chat_id=chat.id, revoke=True)
                    print(result)
                    if isinstance(result, Ok):
                        #account.subscriptions.remove(subs)
                        logger.info(
                            f'{client.settings.phone_number} deleted {chat.id} '
                        #    f'{subs.username if subs.username else subs.invite}'
                        )
                    else:
                        continue
                except BadRequest as exc:
                    logger.warning(exc)
                    continue

        elif isinstance(chat.type_, ChatTypeSecret):
            print(chat.type_)
            print("___________SECRET FOR TEST!!!_________")
            # await client.api.close_secret_chat(secret_chat_id=chat.id)

    #await TelegramAccount(**account.dict()).insert(pool=pool)'''
