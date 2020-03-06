"""
This is a NetCity bot.
"""

import logging
import os

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup

import asyncio

from netcity import NetCityClient
import uvloop

logger = logging.getLogger()
logger.setLevel(logging.INFO)

loop = uvloop.new_event_loop()
asyncio.set_event_loop(loop)
API_TOKEN = os.getenv('API_TOKEN')

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN)

# For example use simple MemoryStorage for Dispatcher.
storage = RedisStorage2()
dp = Dispatcher(bot, storage=storage)
welcom_msg = "Я могу информировать и пересылать задания из электронного дневника http://netcity.eimc.ru/\n"

# Initialize netcity client
netcity = NetCityClient()

# States
class Form(StatesGroup):
    login = State()  # Will be represented in storage as 'Form:name'
    password = State()  # Will be represented in storage as 'Form:age'

@dp.message_handler(commands='help')
async def send_welcome(message: types.Message):
    """
    This handler will be called when user sends `/start` or `/help` command
    """
    await message.reply(welcom_msg +
                        "Вы можете управлять мной, отправляя команды:\n"
                        "/start - настроить\n"
                        "/assignment - текущие задания\n"
                        "/help\n")

@dp.message_handler(commands='start')
async def cmd_start(message: types.Message):
    """
    Conversation's entry point
    """
    # Set state
    await Form.login.set()

    await message.reply(welcom_msg + "Какой твой логин?")

# You can use state '*' if you need to handle all states
@dp.message_handler(state='*', commands='cancel')
@dp.message_handler(Text(equals='cancel', ignore_case=True), state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    """
    Allow user to cancel any action
    """
    current_state = await state.get_state()
    if current_state is None:
        return

    logging.info('Cancelling state %r', current_state)
    # Cancel state and inform user about it
    await state.finish()
    # And remove keyboard (just in case)
    await message.reply('Cancelled.', reply_markup=types.ReplyKeyboardRemove())


@dp.message_handler(state=Form.login)
async def process_name(message: types.Message, state: FSMContext):
    """
    Process user name
    """
    async with state.proxy() as data:
        data['login'] = message.text

    await Form.next()
    await message.reply("Какой твой пароль?")


@dp.message_handler(state=Form.password)
async def process_password(message: types.Message, state: FSMContext):
    """
    Process password
    """
    async with state.proxy() as data:
        data['password'] = message.text
        await netcity.auth(message.chat.id, data=data)
        if netcity.headers[message.chat.id].get('at'):
            await message.reply("авторизация успешна")
        else:
            await message.reply("ошибка авторизации, попробуйте другой логин или пароль")

    await state.finish()


@dp.message_handler(commands='assignment')
async def process_assignment(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        if message.chat.id not in netcity.sessions:
            await message.reply("Авторизауйся /start")
            return
        nc = netcity.sessions[message.chat.id]
        if not netcity.headers[message.chat.id].get('at'):
            await netcity.auth(message.chat.id, data=data)
        if not nc.get('student_id'):
            await netcity.student_diary_init(message.chat.id)
        assignments = await netcity.get_assignments_today(message.chat.id)
        if assignments:
            await message.reply("\n".join(assignments))
        else:
            await message.reply("Заданий нет")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
