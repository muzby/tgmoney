#!/usr/bin/python3
# -*- coding: utf-8 -*-

import asyncio
import os
import pathlib
import shutil
import sys
from hashlib import md5
from multiprocessing import Process

import asyncpg
import yaml

from aiotdlib import Client
from asyncpg import Pool
from loguru import logger

from pydantic import BaseModel

from mtproto_proxy import MtProtoProxy
from telegram_client import get_client
from account import TelegramAccount, update_accounts, clean_subscriptions
from top_tg_money import TopTgMoney, init


class Config(BaseModel):
    class Database(BaseModel):
        database: str
        user: str
        password: str
        host: str
        port: int
        need_to_create: bool

    database: Database
    threads: int
    mtproxy_public_channel: str


async def get_engine():
    return await asyncpg.create_pool(
        database=config.database.database,
        user=config.database.user,
        password=config.database.password,
        host=config.database.host,
        port=config.database.port
    )


async def move_account_for_check(client: Client, pool: Pool):
    directory = md5(client.settings.phone_number.encode()).hexdigest()
    shutil.move(
        f'{pathlib.Path(__file__).parent.parent}/.aiotdlib/{directory}',
        f'{pathlib.Path(__file__).parent.parent}/account/check'
    )
    await TelegramAccount.delete(pool=pool, phone_number=client.settings.phone_number)


async def create_tables():
    pool = await get_engine()
    await MtProtoProxy.create_table(pool=pool)
    await MtProtoProxy.update(pool=pool, mtproxy_public_channel=config.mtproxy_public_channel)
    proxies = await MtProtoProxy.get_proxies(pool=pool)
    if len(proxies) < 1:
        sys.exit('MtProto parser no work! Check code!')
    await TelegramAccount.create_table(pool=pool)
    least_one = await update_accounts(pool=pool)
    if least_one is False:
        sys.exit("You don't have an account, check the update folder")
    config.database.need_to_create = False
    yaml.dump(config.dict(), stream=open('config.yml', 'w'))
    await pool.close()


# if not new tasks for account, other tasks no init
async def run_notifications_task(client: Client, account: TelegramAccount, pool: Pool, command) -> bool:
    logger.info(f'{client.settings.phone_number} >>> Notifications Job')
    try:
        messages_ids = list()
        async for message in client.iter_chat_history(
                chat_id=TopTgMoney.NOTIF_ID,
                from_message_id=0,
                limit=100
        ):
            if message.id <= account.notifications:
                break
            messages_ids.append(message.id)
        if len(messages_ids) > 0:
            account.notifications = max(messages_ids)
            await TelegramAccount(**account.dict()).insert(pool=pool)
            await client.send_text(chat_id=TopTgMoney.BOT_ID, text=command)
            return True
        return False
    except Exception as exc:
        logger.critical(f'{client.settings.phone_number} {exc}')
        return False


async def job(account):
    pool = await get_engine()
    account = await TelegramAccount.get_account(pool=pool, hashed=account)
   #await MtProtoProxy.update(pool=pool, mtproxy_public_channel=config.mtproxy_public_channel)
    client = None
    clean = False
    print(account)
    try:
        client = await get_client(account=account, pool=pool)
        chats_ids = [chat.id for chat in await client.get_main_list_chats(limit=500)]
        await clean_subscriptions(client=client, account=account, pool=pool, chats_ids=chats_ids)
        '''await TelegramAccount(**account.dict()).insert(pool=pool)
        if account.need_init:
            clean = False
            is_init = await init(client=client, account=account, pool=pool)
            if is_init is False:
                await move_account_for_check(client=client, pool=pool)
                logger.critical(f'{client.settings.phone_number} check account for spam!')
            await asyncio.sleep(3)
        if clean:
            chats_ids = [chat.id for chat in await client.get_main_list_chats(limit=500)]
            await clean_subscriptions(client=client, account=account, pool=pool, chats_ids=chats_ids)
        if str(account.referral).isdigit():
            command = TopTgMoney.Command.REFERRALS
        else:
            command = TopTgMoney.Command.EARN
        run_tasks = await run_notifications_task(client=client, account=account, pool=pool, command=command)
        if run_tasks:
            await client.idle()'''
        await client.stop()
    except Exception as exc:
        sys.exit(f'RUN {exc}')
    finally:
        await pool.close()
        if client:
            await client.stop()
        sys.exit()


async def drop():
    pool = await get_engine()
    await TelegramAccount.drop_table(pool=pool)
    await pool.close()


def create_database_tables():
    asyncio.run(create_tables())


def main(account):
    asyncio.run(job(account))


if __name__ == '__main__':
    config = Config(**yaml.load(stream=open('config.yml', 'r'), Loader=yaml.Loader))

    if config.database.need_to_create:
        creation = Process(target=create_database_tables, )
        creation.start()
        creation.join()

    accounts = list()
    for root, dirs, files in os.walk(f'{pathlib.Path(__file__).parent}/.aiotdlib/'):
        accounts = dirs
        break
    #while True:
    for _account in accounts:
        print(_account)
        p = Process(target=main, args=(_account,))
        p.start()
        p.join()
