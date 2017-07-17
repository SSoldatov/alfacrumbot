import datetime
import re
import time
import traceback

import boto3
from boto3.dynamodb.conditions import Key

import telebot
from telebot import types

TOKEN = ''

PRE_NOTIFICATION_OFFSET_IN_MINUTES = 1

DEFAULT_MESSAGE = 'Daily standup meeting.'
DEFAULT_PRE_MESSAGE = 'Daily standup meeting will begin in {} minute.'.format(PRE_NOTIFICATION_OFFSET_IN_MINUTES)

MOSCOW_TIME_ZONE_OFFSET_HOURS = '+03'
DEFAULT_TIME_ZONE_OFFSET = MOSCOW_TIME_ZONE_OFFSET_HOURS

NO_NOTIFICATIONS_MESSAGE = 'Оповещения отсутствуют.'
NO_TIME_ZONE_OFFSET_MESSAGE = 'Часовой пояс не установлен, используется московское время.'
OK_MESSAGE = 'Ok'
ERROR_MESSAGE = 'Ошибка'
WRONG_INPUT_DATA_MESSAGE = 'Неверный формат команды.'
NO_TASKS = 'Задачи отсутствуют.'
NO_TASK = 'Задача {task_id} отсутствует.'

EMOJI_BACKLOG = u'\u23FA\uFE0F'
EMOJI_TODO = u'\u23F8\uFE0F'
EMOJI_IN_PROGRESS = u'\u25B6\uFE0F'
EMOJI_CODE_REVIEW = u'\u23EF\uFE0F'
EMOJI_DONE = u'\u2714\uFE0F'

DEFAULT_INDENT = '    '

TASK_SORTING_ORDER = ['BACKLOG', 'TODO', 'IN PROGRESS', 'CODE REVIEW', 'DONE']

STATUS_CHANGE_CONFIRM_TIME_IN_SECOND = 10

bot = telebot.TeleBot(TOKEN)

dynamo_db = boto3.resource('dynamodb')


# Обработчик входящих сообщений
def handle(event, context):
    update = telebot.types.Update.de_json(str(event).replace("'", "\"").replace("True", "true"))
    if update.message:
        bot.process_new_messages([update.message])
    if update.callback_query:
        bot.process_new_callback_query([update.callback_query])
    time.sleep(1.5)


# Обработчик команд '/settmz'.
@bot.message_handler(commands=['settmz'])
def handle_set_timezone_offset(message):
    try:
        pattern_string = "^/.*? ([+-])([01]?[0-9]|2[0-3])$"
        pattern = re.compile(pattern_string)
        match_result = pattern.match(message.text)
        if match_result:
            time_zone_offset = match_result.group(1) + add_leading_zero(match_result.group(2))
            table = dynamo_db.Table("chat_data")
            chat_id = str(message.chat.id)
            response = table.get_item(Key={'chat_id': chat_id})

            data = get_data(response)
            data['time_zone_offset'] = time_zone_offset

            table.put_item(Item={'chat_id': chat_id, 'data': data})
            bot.send_message(message.chat.id, OK_MESSAGE)
        else:
            bot.send_message(message.chat.id, WRONG_INPUT_DATA_MESSAGE)
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


# Обработчик команд '/showtmz'.
@bot.message_handler(commands=['showtmz'])
def handle_show_timezone_offset(message):
    try:
        offset = read_offset(message.chat.id)
        if offset:
            bot.send_message(message.chat.id, offset)
        else:
            bot.send_message(message.chat.id, NO_TIME_ZONE_OFFSET_MESSAGE)
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


# Обработчик команд '/removetmz'.
@bot.message_handler(commands=['removetmz'])
def handle_remove_timezone_offset(message):
    try:
        chat_id = get_chat_id(message)
        data = get_chat_data(chat_id)
        if 'time_zone_offset' in data:
            del data['time_zone_offset']
            save_chat_data(chat_id, data)
        bot.send_message(message.chat.id, OK_MESSAGE)
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


# Обработчик команд '/start' и '/help'.
@bot.message_handler(commands=['start', 'help'])
def handle_start_help(message):
    text_message = '/settmz <+/-ЧЧ> - указать часовой пояс для текущего чата (смещение от UTC в часах).' \
                   '\n' \
                   '\n' \
                   '/showtmz - показать часовой пояс для текущего чата (смещение от UTC в часах).' \
                   '\n' \
                   '\n' \
                   '/removetmz - удалить часовой пояс.' \
                   '\n' \
                   '\n' \
                   '/add <ЧЧ:MM> <ТЕКСТ ОПОВЕЩЕНИЯ> <ТЕКСТ ПРЕДВАРИТЕЛЬНОГО ОПОВЕЩЕНИЯ> - добавить новое оповещение в указанное время,' \
                   ' для текущего чата.' \
                   '\n' \
                   '{indent}-при указании времени используется часовой пояс заданный командой /settmz.' \
                   '\n' \
                   '{indent}-если часовой пояс не указан, используется время московское.' \
                   '\n' \
                   '{indent}-если текст оповещения отсутствует, будет использоваться сообщение по умолчанию.' \
                   '\n' \
                   '{indent}-если текст предварительного оповещения отсутствует, будет использоваться сообщение по умолчанию.' \
                   '\n' \
                   '{indent}-предварительное оповещение будет отправлено за {pre_notification_offset_in_minutes}' \
                   ' минуту до указанного времени.' \
                   '\n' \
                   '{indent}-если существует ранее добавленное оповещение в указанное время, оно будет обновлено.' \
                   '\n' \
                   '\n' \
                   '/list - вывести список оповещений для текущего чата.' \
                   '\n' \
                   '\n' \
                   '/remove <ЧЧ:MM> - удалить оповещение в указанное время, для текущего чата.' \
                   '\n' \
                   '\n' \
                   '/removeall - удалить все оповещения для текущего чата.' \
                   '\n' \
                   '\n' \
                   '/tasks - вывести список загруженных для текущего чата задач.' \
                   '\n' \
                   '    -под номером задачи выводится emoji символ, обозначающий ее статус:' \
                   '\n' \
                   '{indent}{indent}{backlog_emoji} - BACKLOG' \
                   '\n' \
                   '{indent}{indent}{todo_emoji} - To Do' \
                   '\n' \
                   '{indent}{indent}{in_progress_emoji} - In Progress' \
                   '\n' \
                   '{indent}{indent}{code_review_emoji} - Code review' \
                   '\n' \
                   '{indent}{indent}{done_emoji} - Done' \
                   '\n' \
                   '\n' \
                   '/removetasks - удалить все загруженные для текущего чата задачи.' \
                   '\n' \
                   '\n' \
                   '/<ИДЕНТИФИКАТОР ЗАДАЧИ> - изменить статус задачи на следующий (порядок следования статусов изложен в описании команды /tasks).' \
                   '\n' \
                   '    -данные об изменениях статусов будут добавлены в JIRA при следующей синхронизации.'.format(
        pre_notification_offset_in_minutes=PRE_NOTIFICATION_OFFSET_IN_MINUTES, indent=DEFAULT_INDENT, backlog_emoji=EMOJI_BACKLOG,
        todo_emoji=EMOJI_TODO, in_progress_emoji=EMOJI_IN_PROGRESS, code_review_emoji=EMOJI_CODE_REVIEW, done_emoji=EMOJI_DONE)

    bot.send_message(message.chat.id, text_message)


# Обработчик команд '/add'.
@bot.message_handler(commands=['add'])
def handle_add(message):
    try:
        pattern_string = "^/.*? ([01]?[0-9]|2[0-3]):([0-5][0-9])( ([^ ]*))?( ([^ ]*))?$"
        pattern = re.compile(pattern_string)
        match_result = pattern.match(message.text)
        if match_result:

            time_zone_offset = read_offset(message.chat.id)
            if not time_zone_offset:
                time_zone_offset = DEFAULT_TIME_ZONE_OFFSET

            hours = add_leading_zero(hour_to_utc(match_result.group(1), time_zone_offset))
            minutes = add_leading_zero(match_result.group(2))

            message_text = match_result.group(4)
            if not message_text:
                message_text = DEFAULT_MESSAGE

            pre_message_text = match_result.group(6)
            if not pre_message_text:
                pre_message_text = DEFAULT_PRE_MESSAGE

            chat_id = str(message.chat.id)
            notification_time = hours + minutes
            notification_id = chat_id + notification_time

            table = dynamo_db.Table("notification")
            table.put_item(Item={'id': notification_id, 'notification_time': hours + minutes, 'chat_id': chat_id, 'message': message_text,
                                 'pre_message': pre_message_text})

            bot.send_message(message.chat.id, OK_MESSAGE)
        else:
            bot.send_message(message.chat.id, WRONG_INPUT_DATA_MESSAGE)
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


# Обработчик команд '/remove'.
@bot.message_handler(commands=['remove'])
def handle_remove(message):
    try:
        pattern_string = "^/.*? ([01]?[0-9]|2[0-3]):([0-5][0-9])$"
        pattern = re.compile(pattern_string)
        match_result = pattern.match(message.text)
        if match_result:

            time_zone_offset = read_offset(message.chat.id)
            if not time_zone_offset:
                time_zone_offset = DEFAULT_TIME_ZONE_OFFSET

            hours = add_leading_zero(hour_to_utc(match_result.group(1), time_zone_offset))
            minutes = add_leading_zero(match_result.group(2))
            chat_id = str(message.chat.id)
            notification_time = hours + minutes
            notification_id = chat_id + notification_time

            table = dynamo_db.Table("notification")
            table.delete_item(Key={'id': notification_id})

            bot.send_message(message.chat.id, OK_MESSAGE)
        else:
            bot.send_message(message.chat.id, WRONG_INPUT_DATA_MESSAGE)
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


# Обработчик команд '/removeall'.
@bot.message_handler(commands=['removeall'])
def handle_remove_all(message):
    try:
        table = dynamo_db.Table("notification")
        response = table.query(IndexName='chat_id-index', KeyConditionExpression=Key('chat_id').eq(str(message.chat.id)))
        for item in response['Items']:
            table.delete_item(Key={'id': item['id']})

        bot.send_message(message.chat.id, OK_MESSAGE)
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


# Обработчик команд '/list'.
@bot.message_handler(commands=['list'])
def handle_list(message):
    try:

        time_zone_offset = read_offset(message.chat.id)
        if not time_zone_offset:
            time_zone_offset = DEFAULT_TIME_ZONE_OFFSET

        table = dynamo_db.Table("notification")
        response = table.query(IndexName='chat_id-index', KeyConditionExpression=Key('chat_id').eq(str(message.chat.id)))

        sb = []
        for item in response['Items']:
            sb.append(str(hour_to_timezone(item['notification_time'][:2], time_zone_offset)))
            sb.append(':')
            sb.append(item['notification_time'][2:])
            sb.append(' - ')
            sb.append(item['message'])
            sb.append(' - ')
            sb.append(item['pre_message'])
            sb.append('\n')

        if sb:
            bot.send_message(message.chat.id, ''.join(sb))
        else:
            bot.send_message(message.chat.id, NO_NOTIFICATIONS_MESSAGE)
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


# Обработчик команд '/tasks'.
@bot.message_handler(commands=['tasks'])
def handle_tasks(message):
    try:
        show_tasks(get_chat_id(message))
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


# Обработчик команд '/removetasks'.
@bot.message_handler(commands=['removetasks'])
def handle_tasks(message):
    try:
        chat_id = get_chat_id(message)
        data = get_chat_data(chat_id)
        if 'tasks' in data:
            del data['tasks']
            save_chat_data(chat_id, data)
        bot.send_message(chat_id, OK_MESSAGE)
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


# Обработчик команд '/tonextstatus'.
@bot.message_handler(regexp="^/[A-Z, a-z]*_[0-9]*$")
def handle_tonextstatus(message):
    try:
        pattern_string = "^/([A-Z, a-z]*_[0-9]*)$"
        pattern = re.compile(pattern_string)
        match_result = pattern.match(message.text)
        if match_result:
            task_id = match_result.group(1).replace('_', '-')
            chat_id = get_chat_id(message)
            data = get_chat_data(get_chat_id(message))
            if 'tasks' in data:
                tasks = data['tasks']
                if tasks:
                    task = get_task(task_id, tasks)
                    if task:
                        next_status = get_next_status(task['status_name'])
                        yes_no_keyboard = create_yes_no_keyboard(task_id, next_status)
                        bot.send_message(chat_id, "Сменить статус задачи {task_key} на {next_status}?".format(task_key=task_id,
                                                                                                              next_status=next_status),
                                         reply_markup=yes_no_keyboard)
        else:
            bot.send_message(message.chat.id, WRONG_INPUT_DATA_MESSAGE)
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


def create_yes_no_keyboard(task_id, status_name):
    keyboard = types.InlineKeyboardMarkup()
    yes_button = types.InlineKeyboardButton(text="Да", callback_data=create_callback_data('yes', task_id, status_name))
    no_button = types.InlineKeyboardButton(text="Нет", callback_data=create_callback_data('no'))
    keyboard.add(yes_button)
    keyboard.add(no_button)
    return keyboard


def create_callback_data(action, task_id=None, status_name=None):
    return "{action}:{task_id}:{status_name}:{time}".format(action=action, task_id=task_id, status_name=status_name,
                                                            time=get_current_time_in_second())


def get_current_time_in_second():
    return int(round(time.time()))


def change_task_status(task_id, chat_id, next_status):
    data = get_chat_data(chat_id)
    if 'tasks' in data:
        tasks = data['tasks']
        if tasks:
            task = get_task(task_id, tasks)
            if task:
                current_status = task['status_name']
                if current_status == next_status:
                    return False
                task['status_name'] = next_status
                if not 'transitions' in data:
                    data['transitions'] = dict()
                transitions = data['transitions']
                transitions_count = 0
                if task_id in transitions:
                    transitions_count = transitions[task_id]
                transitions_count = transitions_count + 1
                transitions[task_id] = transitions_count
                save_chat_data(chat_id, data)
                return True
    return False


# Обработчик команд '/removetransitions'.
@bot.message_handler(commands=['removetransitions'])
def handle_removetransitions(message):
    try:
        chat_id = get_chat_id(message)
        data = get_chat_data(get_chat_id(message))
        if 'transitions' in data:
            del data['transitions']
            save_chat_data(chat_id, data)
        bot.send_message(chat_id, OK_MESSAGE)
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    try:
        if call.message:
            chat_id = call.message.chat.id
            data = call.data.split(':')
            action = data[0]
            task_id = data[1]
            status_name = data[2]
            confirm_time = int(data[3])
            if get_current_time_in_second() - confirm_time <= STATUS_CHANGE_CONFIRM_TIME_IN_SECOND:
                if action == "yes":
                    if change_task_status(task_id, chat_id, status_name):
                        bot.send_message(chat_id, "Статус задачи {task_id} изменен на {status_name}".format(task_id=task_id,
                                                                                                            status_name=status_name))
                    else:
                        bot.send_message(chat_id, "Статус задачи не изменен")
                else:
                    bot.send_message(chat_id, "Статус задачи не изменен")
    except Exception:
        print(traceback.format_exc())
        bot.send_message(message.chat.id, ERROR_MESSAGE)


def get_task(task_id, tasks):
    search_results = list(filter(lambda task: task['key'] == task_id or len(
        list(filter(lambda sub_task: sub_task['key'] == task_id, task['sub_tasks'] if 'sub_tasks' in task else []))) > 0, tasks))
    if search_results:
        task = search_results[0]
        if not task['key'] == task_id:
            task = list(filter(lambda sub_task: sub_task['key'] == task_id, task['sub_tasks']))[0]
        return task
    return None


def get_emoji_alias_name(status_name):
    status_name = status_name.upper()
    if status_name == 'BACKLOG':
        return EMOJI_BACKLOG
    if status_name == 'TODO':
        return EMOJI_TODO
    elif status_name == 'IN PROGRESS':
        return EMOJI_IN_PROGRESS
    elif status_name == 'CODE REVIEW':
        return EMOJI_CODE_REVIEW
    elif status_name == 'DONE':
        return EMOJI_DONE
    else:
        return ''


def show_tasks(chat_id):
    data = get_chat_data(chat_id)
    if 'tasks' in data:
        tasks = data['tasks']
        if tasks:
            sb = []
            for task in tasks:
                sb.append('*')
                sb.append(get_emoji_alias_name(task['status_name']))
                sb.append(' ')
                sb.append(task['summary'])
                sb.append('*')
                sb.append('\n')
                if not is_last_status(task['status_name']):
                    sb.append('/')
                sb.append(task['key'].replace("-", "\_"))
                if 'assignee_display_name' in task:
                    sb.append(' - ')
                    sb.append(task['assignee_display_name'])
                sb.append('\n')
                sb.append('\n')
                if 'sub_tasks' in task:
                    for sub_task in task['sub_tasks']:
                        sb.append(DEFAULT_INDENT)
                        sb.append(get_emoji_alias_name(sub_task['status_name']))
                        sb.append(' ')
                        sb.append('*')
                        sb.append(sub_task['summary'])
                        sb.append('*')
                        sb.append('\n')
                        sb.append(DEFAULT_INDENT)
                        if not is_last_status(sub_task['status_name']):
                            sb.append('/')
                        sb.append(sub_task['key'].replace("-", "\_"))
                        if 'assignee_display_name' in sub_task:
                            sb.append(' - ')
                            sb.append(sub_task['assignee_display_name'])
                        sb.append('\n')
                        sb.append('\n')
                    sb.append('\n')

            bot.send_message(parse_mode='markdown', chat_id=chat_id, text=''.join(sb))
        else:
            bot.send_message(chat_id, NO_TASKS)
    else:
        bot.send_message(chat_id, NO_TASKS)


def hour_to_utc(hour, time_zone_offset):
    return (
    datetime.datetime.combine(datetime.date.today(), datetime.time(hour=int(hour))) - datetime.timedelta(hours=int(time_zone_offset))).hour


def hour_to_timezone(hour, time_zone_offset):
    return (
    datetime.datetime.combine(datetime.date.today(), datetime.time(hour=int(hour))) + datetime.timedelta(hours=int(time_zone_offset))).hour


def add_leading_zero(hour, width=2):
    return str(hour).zfill(width)


def read_offset(chat_id):
    table = dynamo_db.Table("chat_data")
    response = table.get_item(Key={'chat_id': str(chat_id)})
    data = get_data(response)
    if 'time_zone_offset' in data:
        return data['time_zone_offset']
    else:
        return None


def get_next_status(current_status):
    current_status = current_status.upper()
    current_index = TASK_SORTING_ORDER.index(current_status)
    next_index = current_index + 1
    if next_index > len(TASK_SORTING_ORDER) - 1:
        return None
    return TASK_SORTING_ORDER[next_index]


def is_last_status(current_status):
    current_status = current_status.upper()
    current_index = TASK_SORTING_ORDER.index(current_status)
    return len(TASK_SORTING_ORDER) == current_index + 1


def get_data(response):
    if 'Item' in response:
        data = response['Item']['data']
    else:
        data = dict()
    return data


def get_chat_data(chat_id):
    table = dynamo_db.Table("chat_data")
    return get_data(table.get_item(Key={'chat_id': str(chat_id)}))


def save_chat_data(chat_id, data):
    table = dynamo_db.Table("chat_data")
    table.put_item(Item={'chat_id': str(chat_id), 'data': data})


def get_chat_id(message):
    return str(message.chat.id)


if __name__ == "__main__":
    print('')
