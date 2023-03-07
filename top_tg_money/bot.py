import asyncio
import pathlib
import re
import shutil
import sys
import time

from dataclasses import dataclass
from hashlib import md5

from aiotdlib import Client
from aiotdlib.api import (
    MessageText, UpdateNewMessage, MessageSenderUser, ReplyMarkupInlineKeyboard, InlineKeyboardButton,
    InlineKeyboardButtonTypeCallback, CallbackQueryPayloadData, InlineKeyboardButtonTypeUrl, ChatTypePrivate,
    UpdateMessageEdited, BaseObject, Message, ChatInviteLinkInfo, CallbackQueryAnswer, BadRequest, Ok, Chat)
from asyncpg import Pool
from loguru import logger
from pydantic import BaseModel

from account import TelegramAccount


class TopTgMoney:

    BOT_ID = 721511477
    NOTIF_ID = -1001177537855
    VIEWS_ID = -1001671077741
    CHANNELS_ID = -1001297304486
    DMITRY_ID = -1001556260642
    LEAVE_TIME = 691200
    BONUS_TIME = 86400
    WALID_BALANCE = 15
    TIMEOUT = 300
    THROTTLING = 3

    @dataclass
    class Command:
        START = '/start'
        EARN = '💳 Заработать'
        CABINET = '🔐 Личный кабинет'
        REFERRALS = '🤝 Мои партнёры'

    @dataclass
    class Inline:
        NEWS = 'Новости'
        LANG = '🇷🇺 Русский'
        WITHDRAW = '💸 Вывести'
        BOTS = '🤖 Перейти в бота +0.2₽'
        GROUPS = '👤 Вступить в группу +0.2₽'
        VIEWS = '👁 Смотреть посты +0.03₽'
        BONUS = '🎁 Бонус +0.02₽'
        QUESTS = '⭐️ Квесты +₽'
        QUEST_N = 'Квесты №1 - №9'
        QUEST_N1 = 'Квест №1'
        QUEST_N2 = 'Квест №2'
        GO_QUEST = '💪🏻 Взять квест'
        GO_BOT = '1️⃣ Перейти к боту'
        GO_GROUP = '1️⃣ Перейти к группе'
        GO_PRIVATE_GROUP = ''
        CHECK_GROUP = '2️⃣ Проверить членство'
        GO_CHANNEL = '📳 Перейти к каналу'
        GET_BONUS = '💸 Получить бонус'
        SPONSOR = '📢 Стать спонсором'
        CHECK_CHANNEL = '💵 Проверить подписку +0.25RUB'
        SKIP_TASK = '▶️ Пропустить задание'
        VIEW_TXT = '💰 +0.03RUB'
        VIEW_IMG = '💰'
        QUEST_DONE = '✅ Подтвердить'

    class AvailableTasks(BaseModel):
        channels: int
        views: int
        bots: int
        groups: int

    class Referrals(BaseModel):
        level1: int
        level2: int
        active: int
        no_active: int

    @dataclass
    class Text:
        MENU = '🚀 Как Вы хотите заработать?'
        REFERRALS = '💣 Партнёрская акция 💣'
        GO_BOT = '📝 Перейдите в бота'
        QUESTS = '💡 Выполняйте специальные'
        QUEST_N = '💡 Выполняйте Квесты (Миссии)'
        QUEST_N1 = '👨‍🔧Реферальный Квест №1'
        QUEST_N2 = '👨‍🔧Денежный Квест №2'
        GO_GROUP = '📝 Вступите в группу'
        CHANNELS = '❗️ Для использования бота подпишитесь на наши каналы'
        USERNAME = 'Вам необходимо установить Имя пользователя (@username)'
        PHOTO = 'Вам необходимо установить Фото профиля (аватарку)'
        LANGUAGE = 'Выберите язык: Choose language:'
        CAPTCHA = 'Для проверки, что Вы не робот, решите пример:'
        FINISH = '😞 Задания кончились! '
        CABINET = '📱 Ваш кабинет:'
        BOT_DONE = '💰 Вам начислено 0.2₽ за переход в бота!'
        GROUP_DONE = '💰 Вам начислено 0.2₽ за вступление в группу!'

    def __init__(self, client: Client, account: TelegramAccount, pool: Pool):
        self.client = client
        self.account = account
        self.pool = pool
        self.bot_id = None
        self.bot_message_id = None
        self._timeout = True
        self.__skip = None
        self.__is_channels_task = True
        self.__is_views_task = False
        self.__is_bots_task = False
        self.__is_groups_task = False
        self.__is_bonus_task = False
        self.__is_withdraw_task = False

    # parse group or channel username
    @staticmethod
    async def parse_username(url: str) -> str | None:
        try:
            return re.findall(r'https://t.me/(.*)', url)[0]
        except IndexError:
            return None

    # bot url parser
    @staticmethod
    async def parse_bot_url(url: str):
        try:
            bot = re.findall(r'https://t.me/(.*)\?start=(.*)', url)[0]
            if '@' in bot[0]:
                return None, None
            return bot[0], bot[1]
        except IndexError:
            try:
                bot = re.findall(r'https://t.me/(.*)', url)[0]
                if '@' in bot:
                    return None, None
                return bot, None
            except IndexError:
                return None, None

    # parse captcha
    @staticmethod
    async def parse_captcha(text: str) -> str | None:
        try:
            numbs = re.findall(r'(\d+)\+(\d+)=', text)[0]
            return str(int(numbs[0]) + int(numbs[1]))
        except IndexError:
            return None

    @staticmethod
    async def parse_referrals(text: str) -> Referrals | None:
        try:
            ref = re.findall(
                r'1 уровень: (\d+) рефералов [\s\S]*'
                r'2 уровень: (\d+) рефералов [\s\S]*'
                r'Активных рефералов: (\d+)\n'
                r'Не активных рефералов: (\d+)', text)[0]
            return TopTgMoney.Referrals(
                **dict(
                    level1=ref[0],
                    level2=ref[1],
                    active=ref[2],
                    no_active=ref[3]
                )
            )
        except IndexError:
            return None

    @staticmethod
    async def parse_available_tasks(text: str) -> AvailableTasks:
        try:
            tasks = re.findall(
                r'📢 Заданий на подписку: (\d+) ?\n'
                r'👁 Заданий на просмотр: (\d+) ?\n'
                r'🤖 Заданий на боты: (\d+) ?\n'
                r'👤 Заданий на группы: (\d+) ?\n', text)[0]
            return TopTgMoney.AvailableTasks(
                **dict(
                    channels=tasks[0],
                    views=tasks[1],
                    bots=tasks[2],
                    groups=tasks[3]
                )
            )
        except IndexError:
            sys.exit(f'Cant parse available tasks, check code!')

    # move session db in check dir, and delete account from accounts db
    async def move_account_for_check(self):
        directory = md5(self.client.settings.phone_number.encode()).hexdigest()
        shutil.move(
            f'{pathlib.Path(__file__).parent.parent}/.aiotdlib/{directory}',
            f'{pathlib.Path(__file__).parent.parent}/account/check'
        )
        await TelegramAccount.delete(pool=self.pool, phone_number=self.client.settings.phone_number)

    # update cabinet date and save in db
    async def update_cabinet(self, text: str):
        try:
            cabinet = re.findall(
                r'🤖 Сделано переходов: (\d+)\n'
                r'👥 Сделано подписок \(группа\): (\d+)\n'
                r'👥 Сделано подписок \(канал\): (\d+)[\s\S]*'
                r'👁 Просмотрено постов: (\d+)\n'
                r'⭐️ Выполнено квестов: (\d+)\n'
                r'🎁 Получено бонусов: (\d+)[\s\S]*'
                r'👤 Заработано с рефералов: (.*)₽[\s\S]*'
                r'❄️ Заморожено средств: (.*)₽\n'
                r'⏳ Ожидается к выплате: (.*)₽\n'
                r'💳 Выведено всего: (.*)₽\n'
                r'💸 Заработано всего: (.*)₽\n\n'
                r'💰 Основной баланс: (.*)₽', text)[0]
            self.account.cabinet.complete.bots = cabinet[0]
            self.account.cabinet.complete.groups = cabinet[1]
            self.account.cabinet.complete.channels = cabinet[2]
            self.account.cabinet.complete.views = cabinet[3]
            self.account.cabinet.complete.quests.complete = cabinet[4]
            self.account.cabinet.complete.bonus = cabinet[5]
            self.account.cabinet.balance.referrals = cabinet[6]
            self.account.cabinet.balance.frozen = cabinet[7]
            self.account.cabinet.balance.wait_payout = cabinet[8]
            self.account.cabinet.balance.total_withdrawn = cabinet[9]
            self.account.cabinet.balance.total_earned = cabinet[10]
            self.account.cabinet.balance.main_balance = cabinet[11]
            await TelegramAccount(**self.account.dict()).insert(self.pool)
        except IndexError:
            sys.exit('Cant update cabinet, check code!')

    # click inline button
    async def click_button(self, chat_id: int, message_id: int, data: str) -> bool:
        try:
            answer = await self.client.api.get_callback_query_answer(
                chat_id=chat_id,
                message_id=message_id,
                payload=CallbackQueryPayloadData(data=data)
            )
            if isinstance(answer, CallbackQueryAnswer):
                return True
        except Exception as exc:
            logger.warning(exc)
            return False

    # join in chat by url
    async def join_chat(self, url: str) -> Chat | bool:
        if '+' in url:
            try:
                link = await self.client.api.check_chat_invite_link(invite_link=url)
                if isinstance(link, ChatInviteLinkInfo):
                    chat = await self.client.api.join_chat_by_invite_link(invite_link=url)
                    if isinstance(chat, Chat):
                        self.account.subscriptions.append(
                            TelegramAccount.Subscription(
                                **dict(
                                    id=chat.id,
                                    url=url,
                                    type=chat.type_.ID,
                                    leave_time=round(time.time() + TopTgMoney.LEAVE_TIME)
                                )
                            )
                        )
                        await TelegramAccount(**self.account.dict()).insert(pool=self.pool)
                        return chat

            except BadRequest as exc:
                if 'INVITE_REQUEST_SENT' in exc.message:
                    logger.info(f'{self.client.settings.phone_number} {url} {exc.message}')
                    await asyncio.sleep(10)
                    return True
                if 'USER_ALREADY_PARTICIPANT' in exc.message:
                    logger.warning(f'{self.client.settings.phone_number} {url} {exc}')
                    self.account.subscriptions.append(
                        TelegramAccount.Subscription(
                            **dict(
                                id=link.chat_id,
                                url=url,
                                type=link.type_.ID,
                                leave_time=round(time.time() + TopTgMoney.LEAVE_TIME)
                            )
                        )
                    )
                    await TelegramAccount(**self.account.dict()).insert(pool=self.pool)
                    return True
                logger.warning(f'{self.client.settings.phone_number} {url} {exc}')
                await asyncio.sleep(TopTgMoney.THROTTLING)
                return False
            except Exception as exc:
                sys.exit(exc)

        else:
            username = await self.parse_username(url=url)
            if username is None:
                return False

            try:
                chat = await self.client.api.search_public_chat(username=username)
                if isinstance(chat, Chat):
                    result = await self.client.api.join_chat(chat_id=chat.id)
                    if isinstance(result, Ok):
                        self.account.subscriptions.append(
                            TelegramAccount.Subscription(
                                **dict(
                                    id=chat.id,
                                    url=url,
                                    type=chat.type_.ID,
                                    leave_time=round(time.time() + TopTgMoney.LEAVE_TIME)
                                )
                            )
                        )
                        await TelegramAccount(**self.account.dict()).insert(pool=self.pool)
                        return chat
            except BadRequest as exc:
                logger.warning(f'{self.client.settings.phone_number} {url} {exc}')
                await asyncio.sleep(TopTgMoney.THROTTLING)
                return False
            except Exception as exc:
                sys.exit(exc)

    # start bot by link
    async def start_bot(self, url: str) -> bool:
        username = None
        try:
            username, referral = await self.parse_bot_url(url=url)
            if username is None:
                return False
            bot = await self.client.api.search_public_chat(username=username)
            if isinstance(bot, Chat) and isinstance(bot.type_, ChatTypePrivate):
                message = await self.client.api.send_bot_start_message(
                    bot_user_id=bot.id,
                    chat_id=bot.id,
                    parameter=referral if referral else ''
                )
                if isinstance(message, Message):
                    self.bot_id = bot.id
                    self.bot_message_id = message.id
                    self.account.subscriptions.append(
                        TelegramAccount.Subscription(
                            **dict(
                                id=bot.id,
                                url=url,
                                type=bot.type_.ID,
                                leave_time=round(time.time() + TopTgMoney.LEAVE_TIME)
                            )
                        )
                    )
                    await TelegramAccount(**self.account.dict()).insert(self.pool)
                    return True
            return False
        except BadRequest as exc:
            if 'USERNAME_INVALID' in exc.message:
                logger.warning(f'{self.client.settings.phone_number} {username} {exc.message}')
                return False
        except Exception as exc:
            logger.critical(f'{self.client.settings.phone_number} {exc}')
            return False

    # run channels join channel and click susses
    async def run_channels_task(self):
        stored_ids = [chat.url for chat in self.account.subscriptions]
        try:
            messages_ids = list()
            async for message in self.client.iter_chat_history(
                    chat_id=TopTgMoney.CHANNELS_ID,
                    from_message_id=0,
                    limit=50
            ):
                if message.id <= self.account.channels.last_message:
                    break
                messages_ids.append(message.id)

                if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                    for buttons in message.reply_markup.rows:
                        for button in buttons:
                            if isinstance(button, InlineKeyboardButton):

                                if button.text == TopTgMoney.Inline.GO_CHANNEL:
                                    if isinstance(button.type_, InlineKeyboardButtonTypeUrl):
                                        if button.type_.url in stored_ids:
                                            break
                                        await self.join_chat(url=button.type_.url)
                                        await asyncio.sleep(TopTgMoney.THROTTLING)

                                if button.text == TopTgMoney.Inline.CHECK_CHANNEL:
                                    if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                        await self.click_button(
                                            chat_id=TopTgMoney.CHANNELS_ID,
                                            message_id=message.id,
                                            data=button.type_.data
                                        )
            if len(messages_ids) > 0:
                self.account.channels.last_message = max(messages_ids)
                await TelegramAccount(**self.account.dict()).insert(pool=self.pool)
        except BadRequest as exc:
            logger.critical(f'{self.client.settings.phone_number} {exc}')

    # run task click views inline buttons
    async def run_views_task(self):
        try:
            messages_ids = list()
            async for message in self.client.iter_chat_history(
                    chat_id=TopTgMoney.VIEWS_ID,
                    from_message_id=0,
                    limit=50
            ):
                if message.id <= self.account.views.last_message:
                    break
                messages_ids.append(message.id)

                if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                    for buttons in message.reply_markup.rows:
                        for button in buttons:
                            if button.text == TopTgMoney.Inline.VIEW_IMG:
                                if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                    await self.click_button(
                                        chat_id=TopTgMoney.VIEWS_ID,
                                        message_id=message.id,
                                        data=button.type_.data
                                    )
                                    await asyncio.sleep(TopTgMoney.THROTTLING)
                            if button.text == TopTgMoney.Inline.VIEW_TXT:
                                if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                    await self.click_button(
                                        chat_id=TopTgMoney.VIEWS_ID,
                                        message_id=message.id,
                                        data=button.type_.data
                                    )
                                    await asyncio.sleep(TopTgMoney.THROTTLING)

            if len(messages_ids) > 0:
                self.account.views.last_message = max(messages_ids)
                await TelegramAccount(**self.account.dict()).insert(pool=self.pool)
        except Exception as exc:
            logger.critical(f'{self.client.settings.phone_number} {exc}')

    # exit where bot not response, or code have problem
    async def timeout(self, timeout: int = TIMEOUT):
        while any(
                [
                    self.__is_bots_task,
                    self.__is_bonus_task,
                    self.__is_groups_task,
                    self.__is_withdraw_task,
                    self.__is_views_task,
                    self.__is_channels_task
                ]
        ) and timeout > 0:
            await asyncio.sleep(1)
            timeout -= 1
        if self.__skip:
            await self.click_button(
                chat_id=self.__skip['chat_id'],
                message_id=self.__skip['message_id'],
                data=self.__skip['data']
            )
            self.__skip = None
        if timeout == 0:
            sys.exit(f'{self.client.settings.phone_number} long Timeout! Check code or bot!')
        sys.exit(f'{self.client.settings.phone_number} Job done!')

    # Event handler
    async def client_event_handler(self, client: Client, update: BaseObject):
        if self._timeout:
            self._timeout = False
            await self.timeout()

        if isinstance(update, UpdateMessageEdited):
            if update.chat_id == TopTgMoney.BOT_ID:
                try:
                    edited_message = await self.client.api.get_message(
                        chat_id=update.chat_id,
                        message_id=update.message_id
                    )
                except Exception as exc:
                    sys.exit(exc)

                if isinstance(edited_message.content, MessageText):
                    if TopTgMoney.Text.FINISH in edited_message.content.text.text:
                        if self.__is_bots_task:
                            self.__is_bonus_task = True
                            self.__is_bots_task = False
                            await asyncio.sleep(TopTgMoney.THROTTLING)
                            await self.client.send_text(chat_id=TopTgMoney.BOT_ID, text=TopTgMoney.Command.EARN)

                        if self.__is_groups_task:
                            self.__is_withdraw_task = True
                            self.__is_groups_task = False
                            await asyncio.sleep(TopTgMoney.THROTTLING)
                            await self.client.send_text(chat_id=TopTgMoney.BOT_ID, text=TopTgMoney.Command.CABINET)

                if isinstance(edited_message.reply_markup, ReplyMarkupInlineKeyboard):
                    for buttons in edited_message.reply_markup.rows:
                        for button in buttons:
                            if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                if button.text in TopTgMoney.Inline.GET_BONUS:
                                    await self.click_button(
                                        chat_id=TopTgMoney.BOT_ID,
                                        message_id=edited_message.id,
                                        data=button.type_.data
                                    )
                                    self.account.bonus.paid = round(time.time() + TopTgMoney.BONUS_TIME)
                                    await TelegramAccount(**self.account.dict()).insert(pool=self.pool)
                                    self.__is_groups_task = True
                                    self.__is_bonus_task = False
                                    await asyncio.sleep(TopTgMoney.THROTTLING)
                                    await self.client.send_text(chat_id=TopTgMoney.BOT_ID, text=TopTgMoney.Command.EARN)
                                    return True

                                if button.text in TopTgMoney.Inline.SPONSOR:
                                    self.__is_groups_task = True
                                    self.__is_bonus_task = False
                                    self.account.bonus.paid = round(time.time() + TopTgMoney.BONUS_TIME)
                                    await TelegramAccount(**self.account.dict()).insert(pool=self.pool)
                                    await asyncio.sleep(TopTgMoney.THROTTLING)
                                    await self.client.send_text(chat_id=TopTgMoney.BOT_ID, text=TopTgMoney.Command.EARN)
                                    return True

        if isinstance(update, UpdateNewMessage):

            if isinstance(update.message.sender_id, MessageSenderUser):
                sender = update.message.sender_id
                message = update.message

                if sender.user_id == self.bot_id and message.id != self.bot_message_id:
                    await self.client.forward_messages(
                        from_chat_id=self.bot_id,
                        chat_id=TopTgMoney.BOT_ID,
                        message_ids=[message.id]
                    )
                    self.bot_id = self.bot_message_id = None

                if sender.user_id == TopTgMoney.BOT_ID:

                    if isinstance(message.content, MessageText):
                        text = message.content.text.text
                        print(text)
                        click = False

                        if TopTgMoney.Text.USERNAME in text or TopTgMoney.Text.PHOTO in text:
                            await self.move_account_for_check()
                            sys.exit(f'{self.client.settings.phone_number} moved for check!')

                        if TopTgMoney.Text.CAPTCHA in text:
                            captcha = await self.parse_captcha(text=text)
                            if captcha:
                                if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                    for buttons in message.reply_markup.rows:
                                        for button in buttons:
                                            if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                                if button.text == captcha:
                                                    click = await self.click_button(
                                                        chat_id=TopTgMoney.BOT_ID,
                                                        message_id=message.id,
                                                        data=button.type_.data
                                                    )
                            if click is False:
                                sys.exit('Cant click bot captcha!, check code!')

                        if TopTgMoney.Text.LANGUAGE in text:
                            if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                for buttons in message.reply_markup.rows:
                                    for button in buttons:
                                        if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                            if button.text == TopTgMoney.Inline.LANG:
                                                click = await self.click_button(
                                                    chat_id=TopTgMoney.BOT_ID,
                                                    message_id=message.id,
                                                    data=button.type_.data
                                                )
                            if click is False:
                                sys.exit('Cant click language!, check code!')

                        if TopTgMoney.Text.CHANNELS in text:
                            if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                for buttons in message.reply_markup.rows:
                                    for button in buttons:
                                        if isinstance(button.type_, InlineKeyboardButtonTypeUrl):
                                            if button.text == TopTgMoney.Inline.NEWS:
                                                chat = await self.join_chat(url=button.type_.url)
                                                if chat is False:
                                                    sys.exit(f'{self.client.settings.phone_number} cant join in Dmitry')
                                                await asyncio.sleep(TopTgMoney.THROTTLING)
                                                await self.client.send_text(
                                                    chat_id=TopTgMoney.BOT_ID,
                                                    text=TopTgMoney.Command.EARN
                                                )

                        if TopTgMoney.Text.GO_GROUP in text:
                            stored_urls = [chat.url for chat in self.account.subscriptions]
                            if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                chat = False
                                for buttons in message.reply_markup.rows:
                                    for button in buttons:
                                        if isinstance(button.type_, InlineKeyboardButtonTypeUrl):
                                            if button.text == TopTgMoney.Inline.GO_GROUP:
                                                if button.type_.url in stored_urls:
                                                    continue
                                                chat = await self.join_chat(url=button.type_.url)

                                        if button.text == TopTgMoney.Inline.CHECK_GROUP and chat:
                                            if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                                await self.click_button(
                                                    chat_id=TopTgMoney.BOT_ID,
                                                    message_id=message.id,
                                                    data=button.type_.data
                                                )

                                        if button.text == TopTgMoney.Inline.SKIP_TASK and chat is False:
                                            if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                                await self.click_button(
                                                    chat_id=TopTgMoney.BOT_ID,
                                                    message_id=message.id,
                                                    data=button.type_.data
                                                )

                                        if button.text == TopTgMoney.Inline.SKIP_TASK:
                                            if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                                self.__skip = dict(
                                                    chat_id=TopTgMoney.BOT_ID,
                                                    message_id=message.id,
                                                    data=button.type_.data
                                                )

                        if TopTgMoney.Text.GO_BOT in text:
                            if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                start = False
                                for buttons in message.reply_markup.rows:
                                    for button in buttons:

                                        if isinstance(button.type_, InlineKeyboardButtonTypeUrl):
                                            if button.text == TopTgMoney.Inline.GO_BOT:
                                                start = await self.start_bot(url=button.type_.url)

                                        if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                            if button.text == TopTgMoney.Inline.SKIP_TASK and start is False:
                                                await self.click_button(
                                                    chat_id=TopTgMoney.BOT_ID,
                                                    message_id=message.id,
                                                    data=button.type_.data
                                                )
                                            elif button.text == TopTgMoney.Inline.SKIP_TASK:
                                                self.__skip = dict(
                                                    chat_id=TopTgMoney.BOT_ID,
                                                    message_id=message.id,
                                                    data=button.type_.data
                                                )
                        if TopTgMoney.Text.BOT_DONE in text:
                            self.__skip = None
                            await asyncio.sleep(TopTgMoney.THROTTLING)
                            await self.client.send_text(chat_id=TopTgMoney.BOT_ID, text=TopTgMoney.Command.EARN)

                        if TopTgMoney.Text.GROUP_DONE in text:
                            self.__skip = None
                            await asyncio.sleep(TopTgMoney.THROTTLING)
                            await self.client.send_text(chat_id=TopTgMoney.BOT_ID, text=TopTgMoney.Command.EARN)

                        if TopTgMoney.Text.QUESTS in text:
                            if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                for buttons in message.reply_markup.rows:
                                    for button in buttons:
                                        if button.text == TopTgMoney.Inline.QUEST_N:
                                            if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                                click = await self.click_button(
                                                    chat_id=TopTgMoney.BOT_ID,
                                                    message_id=message.id,
                                                    data=button.type_.data
                                                )
                                                if click is False:
                                                    sys.exit('Cant click Quest Num, check code!')

                        if TopTgMoney.Text.QUEST_N in text:
                            if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                num = TopTgMoney.Inline.QUEST_N1
                                if self.account.need_init is None:
                                    num = TopTgMoney.Inline.QUEST_N2
                                for buttons in message.reply_markup.rows:
                                    for button in buttons:
                                        if button.text == num:
                                            click = await self.click_button(
                                                chat_id=TopTgMoney.BOT_ID,
                                                message_id=message.id,
                                                data=button.type_.data
                                            )
                                            if click is False:
                                                sys.exit(f'{self.client.settings.phone_number} click {num} error')

                        if TopTgMoney.Text.QUEST_N1 in text:
                            if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                for buttons in message.reply_markup.rows:
                                    for button in buttons:
                                        if button.text == TopTgMoney.Inline.GO_QUEST:
                                            await self.click_button(
                                                chat_id=TopTgMoney.BOT_ID,
                                                message_id=message.id,
                                                data=button.type_.data
                                            )
                                        if button.text == TopTgMoney.Inline.QUEST_DONE:
                                            await self.click_button(
                                                chat_id=TopTgMoney.BOT_ID,
                                                message_id=message.id,
                                                data=button.type_.data
                                            )
                                            self.account.cabinet.complete.quests.num1 = True
                                self.account.need_init = None
                                await TelegramAccount(**self.account.dict()).insert(pool=self.pool)
                                await asyncio.sleep(TopTgMoney.THROTTLING)
                                await self.client.send_text(chat_id=TopTgMoney.BOT_ID, text=TopTgMoney.Command.EARN)

                        if TopTgMoney.Text.QUEST_N2 in text:
                            if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                for buttons in message.reply_markup.rows:
                                    for button in buttons:
                                        if button.text == TopTgMoney.Inline.GO_QUEST:
                                            await self.click_button(
                                                chat_id=TopTgMoney.BOT_ID,
                                                message_id=message.id,
                                                data=button.type_.data
                                            )
                                        if button.text == TopTgMoney.Inline.QUEST_DONE:
                                            await self.click_button(
                                                chat_id=TopTgMoney.BOT_ID,
                                                message_id=message.id,
                                                data=button.type_.data
                                            )
                                            self.account.cabinet.complete.quests.num2 = True
                                self.account.need_init = False
                                await TelegramAccount(**self.account.dict()).insert(pool=self.pool)
                                await asyncio.sleep(TopTgMoney.THROTTLING)
                                await self.client.send_text(chat_id=TopTgMoney.BOT_ID, text=TopTgMoney.Command.EARN)

                        if TopTgMoney.Text.REFERRALS in text:
                            referrals = await self.parse_referrals(text=text)
                            if referrals is None:
                                logger.critical(f'Check referrals code!')
                            logger.info(f'{self.client.settings.phone_number} have ref l1: {referrals.level1}')
                            if referrals.level1 >= 10:
                                self.account.referral = 'done'
                                await TelegramAccount(**self.account.dict()).insert(pool=self.pool)
                            await asyncio.sleep(TopTgMoney.THROTTLING)
                            await self.client.send_text(chat_id=TopTgMoney.BOT_ID, text=TopTgMoney.Command.EARN)

                        if TopTgMoney.Text.CABINET in text:
                            logger.info(f'{self.client.settings.phone_number} >>> Withdraw Job')
                            await self.update_cabinet(text=text)
                            self.__is_withdraw_task = False

                        if TopTgMoney.Text.MENU in text:

                            available_tasks = await self.parse_available_tasks(text=text)

                            if self.__is_channels_task:
                                logger.info(f'{self.client.settings.phone_number} >>> Channels Job')
                                if available_tasks.channels == 0:
                                    self.__is_channels_task = False
                                    self.__is_views_task = True
                                else:
                                    await self.run_channels_task()
                                    self.__is_channels_task = False
                                    self.__is_views_task = True

                            if self.__is_views_task:
                                logger.info(f'{self.client.settings.phone_number} >>> Views Job')
                                if self.account.need_init:
                                    if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                        for buttons in message.reply_markup.rows:
                                            for button in buttons:
                                                if isinstance(button.type_, InlineKeyboardButtonTypeUrl):
                                                    if button.text == TopTgMoney.Inline.VIEWS:
                                                        joined = await self.join_chat(url=button.type_.url)
                                                        if joined is False:
                                                            sys.exit(
                                                                f'{self.client.settings.phone_number} cant join Views'
                                                            )
                                                        logger.info(
                                                            f'{self.client.settings.phone_number} joined in Views')

                                if available_tasks.views == 0:
                                    self.__is_views_task = False
                                    self.__is_bots_task = True
                                else:
                                    await self.run_views_task()
                                    self.__is_views_task = False
                                    self.__is_bots_task = True

                            task = None

                            if self.account.need_init or self.account.need_init is None or (
                                    self.account.cabinet.complete.quests.complete < 2 and
                                    self.account.cabinet.balance.main_balance > 10 and
                                    self.account.cabinet.complete.quests.num2 is False
                            ):
                                logger.info(f'{self.client.settings.phone_number} >>> Quests Job')
                                task = TopTgMoney.Inline.QUESTS
                            else:

                                if self.__is_bots_task:
                                    logger.info(f'{self.client.settings.phone_number} >>> Bots Job')
                                    task = TopTgMoney.Inline.BOTS
                                    if available_tasks.bots == 0:
                                        self.__is_bonus_task = True
                                        self.__is_bots_task = False

                                if self.__is_bonus_task:
                                    logger.info(f'{self.client.settings.phone_number} >>> Bonus Job')
                                    task = TopTgMoney.Inline.BONUS
                                    if self.account.bonus.paid > round(time.time()):
                                        self.__is_groups_task = True
                                        self.__is_bonus_task = False

                                if self.__is_groups_task:
                                    logger.info(f'{self.client.settings.phone_number} >>> Groups Job')
                                    task = TopTgMoney.Inline.GROUPS
                                    if available_tasks.groups == 0:
                                        self.__is_withdraw_task = True
                                        self.__is_groups_task = False

                            if task:
                                if isinstance(message.reply_markup, ReplyMarkupInlineKeyboard):
                                    for buttons in message.reply_markup.rows:
                                        for button in buttons:
                                            if isinstance(button.type_, InlineKeyboardButtonTypeCallback):
                                                if task in button.text:
                                                    click = await self.click_button(
                                                        chat_id=TopTgMoney.BOT_ID,
                                                        message_id=message.id,
                                                        data=button.type_.data
                                                    )
                                                    if click is False:
                                                        sys.exit(f'Cant click Menu {task}')
