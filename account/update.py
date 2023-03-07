import glob
import json
import pathlib
import shutil

from hashlib import md5

from asyncpg import Pool
from loguru import logger

from account import TelegramAccount


async def update_accounts(pool: Pool) -> bool:
    account = None
    for filename in glob.iglob(f'{pathlib.Path(__file__).parent}/update/*/files/*.json'):
        with open(filename, 'r') as inf:
            account = json.loads(inf.read())
        await TelegramAccount(**account).insert(pool=pool)
        shutil.move(
            f'{pathlib.Path(__file__).parent}/update/{md5(account["phone_number"].encode()).hexdigest()}',
            f'{pathlib.Path(__file__).parent.parent}/.aiotdlib'
        )
        logger.info(f'{account["phone_number"]} added in Telegram Accounts database')
    if account:
        return True
    return False
