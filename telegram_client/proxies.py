import asyncio
import hashlib
import random
import sys

from aiotdlib import TDLibLogVerbosity, ClientProxySettings, ClientProxyType
from aiotdlib.api import BadRequest, ProxyTypeMtproto, Proxy, API
from asyncpg import Pool
from loguru import logger
from pydantic.types import SecretStr

from telegram_client.client import Client
from account import TelegramAccount
from mtproto_proxy import MtProtoProxy
from top_tg_money import TopTgMoney


async def update_ping(client: Client, proxy: Proxy, pool: Pool):
    if isinstance(proxy.type_, ProxyTypeMtproto):
        try:
            ping = await client.api.ping_proxy(proxy_id=proxy.id)
            #print(ping)
            await MtProtoProxy(
                **dict(
                    id=hashlib.md5(f'{proxy.server}{proxy.port}{proxy.type_.secret}'.encode()).hexdigest(),
                    proxy=dict(
                        host=proxy.server,
                        port=proxy.port,
                        secret=proxy.type_.secret
                    ),
                    ping=ping.seconds,
                    refused=False
                )
            ).insert(pool=pool)
            #logger.info(f'Ping: {ping.seconds} {proxy.server}')
        except BadRequest as exc:
            await MtProtoProxy(
                **dict(
                    id=hashlib.md5(f'{proxy.server}{proxy.port}{proxy.type_.secret}'.encode()).hexdigest(),
                    proxy=dict(
                        host=proxy.server,
                        port=proxy.port,
                        secret=proxy.type_.secret
                    ),
                    ping=0,
                    refused=True
                )
            ).insert(pool=pool)
            await client.api.remove_proxy(proxy_id=proxy.id)
            #logger.warning(f'{proxy.server} {exc.message}')


async def get_client(account: TelegramAccount, pool: Pool) -> Client | None:
    mtproto = random.choice([proxy for proxy in await MtProtoProxy.get_proxies(pool=pool) if proxy.refused is False])
    client = Client(
        phone_number=account.phone_number,
        api_id=account.api_id,
        api_hash=SecretStr(account.api_hash),
        system_language_code=account.system_language_code,
        device_model=account.device_model,
        system_version=account.system_version,
        application_version=account.application_version,
        #tdlib_verbosity=TDLibLogVerbosity.WARNING,
        proxy_settings=ClientProxySettings(
            host=mtproto.proxy.host,
            port=mtproto.proxy.port,
            type=ClientProxyType.MTPROTO,
            secret=mtproto.proxy.secret)
    )
    '''client.add_event_handler(
        TopTgMoney(
            client=client,
            account=account,
            pool=pool
        ).client_event_handler,
        update_type=API.Types.ANY
    )'''
    try:
        logger.info(f'{client.settings.phone_number} >>> Ping proxies')
        await client.start()
        sessions = await client.api.get_active_sessions()
        for ses in sessions.sessions:
            if ses.is_current:
                print(ses.ip, ses.country, ses.region)
                #await client.api.get_countries()
        proxies = await client.api.get_proxies()
        tasks = list()
        counter = 10
        for proxy in proxies.proxies:
            task = asyncio.create_task(
                update_ping(
                    client=client,
                    proxy=proxy,
                    pool=pool
                )
            )
            tasks.append(task)
            counter -= 1
            if counter == 0:
                await asyncio.gather(*tasks)
                counter = 10
                tasks.clear()
        await asyncio.gather(*tasks)
        return client
    except BadRequest as exc:
        if 'Wrong proxy secret' in exc.message:
            mtproto.refused = True
            await MtProtoProxy(**mtproto.dict()).insert(pool=pool)
            logger.error(f'{client.settings.phone_number} {exc}')
            sys.exit()
    except asyncio.exceptions.TimeoutError as exc:
        mtproto.refused = True
        await MtProtoProxy(**mtproto.dict()).insert(pool=pool)
        logger.error(f'{client.settings.phone_number} {exc}')
        sys.exit()
    except Exception as exc:
        logger.critical(f'{client.settings.phone_number} {exc}')
        sys.exit()
