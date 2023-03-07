import hashlib
import json
import re

import aiohttp as aiohttp
from aiohttp import client_exceptions

from asyncpg import Pool
from loguru import logger
from pydantic import BaseModel


class MtProtoProxy(BaseModel):

    class Proxy(BaseModel):
        host: str
        port: int
        secret: str

    __table__ = 'mtprotoproxies'
    __schema__ = f'''create table if not exists 
        {__table__} 
        (
           id text primary key,
           proxy json not null,
           ping numeric default 0,
           refused bool default False
        )'''
    id: str
    proxy: Proxy
    ping: float = 0
    refused: bool = False

    @classmethod
    async def create_table(cls, pool: Pool):
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(cls.__schema__)
            logger.info(f'Table {cls.__table__} created \n{cls.__schema__}')

    @classmethod
    async def drop_table(cls, pool: Pool):
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(f'''DROP TABLE IF EXISTS {cls.__table__}''')
            logger.warning(f'Table {cls.__table__} deleted')

    async def insert(self, pool: Pool):
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    f'''INSERT INTO {self.__table__} 
                    (id, proxy, ping, refused) VALUES ($1, $2, $3, $4) 
                    ON CONFLICT (id) DO UPDATE SET
                    (
                        ping,
                        refused
                    ) = (
                        EXCLUDED.ping,
                        EXCLUDED.refused
                    )''',
                    self.id, self.proxy.json(), self.ping if self.refused is False else 0, self.refused
                )

    @classmethod
    async def delete(cls, pool: Pool, proxy_id: str):
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    f'''DELETE FROM {cls.__table__} WHERE ID = $1''', proxy_id)

    @classmethod
    async def get_proxies(cls, pool: Pool) -> list:
        async with pool.acquire() as connection:
            async with connection.transaction():
                record = await connection.fetch(f'''SELECT row_to_json({cls.__table__}) FROM {cls.__table__}''')
                if record:
                    return [MtProtoProxy(**json.loads(*proxy)) for proxy in record]
                return []

    @classmethod
    async def update(cls, pool: Pool, mtproxy_public_channel: str):
        session = aiohttp.ClientSession('https://t.me')
        try:
            async with session.get(f'/s/{mtproxy_public_channel}') as response:
                page = await response.text()
        except client_exceptions.ClientConnectorError as exc:
            logger.warning(exc)
            return False
        finally:
            await session.close()
        parsed_proxies = re.findall(r'https://t.me/proxy\?server=([^&]*)&amp;port=(\d+)&amp;secret=(\w+)', page)
        stored_proxies = await MtProtoProxy.get_proxies(pool=pool)
        stored_to_clean_ids = [proxy.id for proxy in stored_proxies if proxy.refused]
        stored_good_ids = [proxy.id for proxy in stored_proxies if proxy.refused is False]
        for parsed_proxy in parsed_proxies:
            proxy = MtProtoProxy.Proxy(
                **dict(
                    host=parsed_proxy[0],
                    port=int(parsed_proxy[1]),
                    secret=parsed_proxy[2]
                )
            )
            proxy_id = hashlib.md5(f'{proxy.host}{proxy.port}{proxy.secret}'.encode()).hexdigest()
            if proxy_id in stored_to_clean_ids:
                stored_to_clean_ids.remove(proxy_id)
                continue
            elif proxy_id in stored_good_ids:
                continue
            else:
                await MtProtoProxy(**dict(id=proxy_id, proxy=proxy)).insert(pool=pool)
                logger.info(f'Added: {proxy.host}')
        for to_clean_id in stored_to_clean_ids:
            await MtProtoProxy.delete(pool=pool, proxy_id=to_clean_id)
            logger.warning(f'Deleted {to_clean_id}')
