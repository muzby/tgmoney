import json

from dataclasses import dataclass
from hashlib import md5

from asyncpg import Pool
from pydantic import BaseModel
from loguru import logger


class TelegramAccount(BaseModel):

    @dataclass
    class Wallets:
        TON = 'ton'
        PAYEER = 'payeer'
        YANDEX = 'yandex'

    class Subscription(BaseModel):
        id: int
        url: str
        type: str
        leave_time: int

    class Channels(BaseModel):
        total: int = 0
        last_message: int = 0

    class Views(BaseModel):
        total: int = 0
        last_message: int = 0

    class Bonus(BaseModel):
        total: int = 0
        paid: int = 0

    class Cabinet(BaseModel):

        class Balance(BaseModel):
            referrals: float = 0
            frozen: float = 0
            wait_payout: float = 0
            total_withdrawn: float = 0
            total_earned: float = 0
            main_balance: float = 0

        class Complete(BaseModel):

            class Quest(BaseModel):
                complete: int = 0
                num1: bool = False
                num2: bool = False

            bots: int = 0
            groups: int = 0
            channels: int = 0
            views: int = 0
            quests: Quest = Quest()
            bonus: int = 0

        balance: Balance = Balance()
        complete: Complete = Complete()

    class Wallet(BaseModel):
        ton: str | None
        payeer: str | None
        yandex: str | None

    __table__ = 'telegram_accounts'
    __schema__ = f'''create table if not exists 
        {__table__} 
        (
           phone_number text primary key,
           api_id integer not null,
           api_hash text not null,
           system_language_code text not null,
           device_model text not null,
           system_version text not null,
           application_version text not null,
           subscriptions json[] default null,
           notifications bigint default null,
           channels json default null,
           views json default null,
           bonus json default null,
           cabinet json default null,
           wallets json default null,
           need_init bool default true,
           referral text default false,
           flood integer default null
        )'''
    phone_number: str
    api_id: int
    api_hash: str
    system_language_code: str
    device_model: str
    system_version: str
    application_version: str
    subscriptions: list[Subscription] | list = []
    notifications: int = 0
    channels: Channels = Channels()
    views: Views = Views()
    bonus: Bonus = Bonus()
    cabinet: Cabinet = Cabinet()
    wallets: Wallet | None
    need_init: bool | None = True
    referral: str = 'false'
    flood: int = 0

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
                    f'''insert into {self.__table__} 
                    (
                        phone_number,
                        api_id,
                        api_hash,
                        system_language_code,
                        device_model,
                        system_version,
                        application_version,
                        subscriptions,
                        notifications,
                        channels,
                        views,
                        bonus,
                        cabinet,
                        wallets,
                        need_init,
                        referral,
                        flood
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17) 
                    ON CONFLICT (phone_number) DO UPDATE SET
                    (
                        subscriptions,
                        notifications,
                        channels,
                        views,
                        bonus,
                        cabinet,
                        wallets,
                        need_init,
                        referral,
                        flood
                    ) = (
                        EXCLUDED.subscriptions,
                        EXCLUDED.notifications,
                        EXCLUDED.channels,
                        EXCLUDED.views,
                        EXCLUDED.bonus,
                        EXCLUDED.cabinet,
                        EXCLUDED.wallets,
                        EXCLUDED.need_init,
                        EXCLUDED.referral,
                        EXCLUDED.flood
                    )''',
                    self.phone_number,
                    self.api_id,
                    self.api_hash,
                    self.system_language_code,
                    self.device_model,
                    self.system_version,
                    self.application_version,
                    [sub.json() for sub in self.subscriptions],
                    self.notifications,
                    self.channels.json(),
                    self.views.json(),
                    self.bonus.json(),
                    self.cabinet.json(),
                    self.wallets.json() if self.wallets else None,
                    self.need_init,
                    self.referral,
                    self.flood
                )

    @classmethod
    async def delete(cls, pool: Pool, phone_number: str):
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    f'''delete from {cls.__table__} where phone_number = $1''', phone_number)

    @classmethod
    async def get_accounts(cls, pool: Pool) -> list:
        async with pool.acquire() as connection:
            async with connection.transaction():
                record = await connection.fetch(f'''select row_to_json({cls.__table__}) from {cls.__table__}''')
                if record:
                    return [TelegramAccount(**json.loads(*account)) for account in record]

    @classmethod
    async def get_account(cls, pool: Pool, hashed: str):
        accounts = await TelegramAccount.get_accounts(pool=pool)
        try:
            return [account for account in accounts if md5(account.phone_number.encode()).hexdigest() == hashed][0]
        except IndexError:
            return None
