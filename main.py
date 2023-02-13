import datetime
import logging
import os

from sqlalchemy.orm import sessionmaker
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.helpers import escape_markdown

from db_sqlalchemy import User, Valentine, engine

Session = sessionmaker(bind=engine)
session = Session()


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


VALENTINE, RECIPIENT, ANONIMITY, CONFIRMATION = range(4)

VALENTINE_COOLDOWN = 20

# Группа администраторов
ADMIN_GROUP = os.environ.get("ADMIN_GROUP")
# Канал куда будут приходит валентинки
CHANNEL_ID = os.environ.get("CHANNEL_ID")


def db_add_valentine(
    sender: User,
    recipient: str,
    text: str,
    date: datetime,
    admin_message_id: int,
) -> None:
    valentine = Valentine(
        sender=sender.id,
        recipient=recipient,
        text=str(text),
        date=date,
        admin_message_id=admin_message_id,
    )

    session.add(valentine)
    session.commit()


def db_create_user(user_id: int, full_name: str, user_name: str, phone: str) -> None:
    user = User(
        user_id=int(user_id),
        full_name=str(full_name),
        user_name=str(user_name),
        phone=str(phone),
    )

    session.add(user)
    session.commit()


# Проверка на то, что пользователь может отправить валентинку. Кулдаун настраивается в VALENTINE_COOLDOWN
def can_post(user_id: int) -> bool:
    try:
        user = session.query(User).filter(User.user_id == user_id).first()

        last_valentine = (
            session.query(Valentine)
            .filter(Valentine.sender == user.id)
            .order_by(Valentine.id.desc())
            .first()
        )
    except Exception as e:
        logger.warning(e)
        session.rollback()
        return False
    finally:
        session.close()

    now_utc = datetime.datetime.now(datetime.timezone.utc)

    if last_valentine is None:
        return True

    if now_utc.replace(tzinfo=None) - last_valentine.date > datetime.timedelta(
        minutes=VALENTINE_COOLDOWN
    ):
        return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await update.message.reply_text(
        "Привет\! Я бот\, который поможет Вам отправить валентинку💌\n\nПосмотреть отправленные валентинки можно [тут](https://google.com)📫\n\nЧтобы продолжить\, подтвердите Ваш номер телефона кнопкой ниже\nПосле этого отправьте /help\, чтобы узнать больше о боте🤖",
        reply_markup=reply_keyboard,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "/start - Запустить бота\n/help - Помощь и информация о боте\n/valentine - Отправить валентинку \n\nПросто отправьте нужную команду и Вам будут показаны дальнейшие инструкции. Не бойтесь, перед отправкой валентинки Вас попросят подтвердить отправку. Отправлять можно только текст каждые 20 минут.\n\nДИСКЛЕЙМЕР:\nМы собираем следующую информацию о Вас: имя и фамилия, юзернейм, номер телефона, информация о валентинках(текст, получатель). Эта информация необходима для того, чтобы мы могли связаться с Вами в случае каких-либо проблем.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def ticket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = (
            session.query(User)
            .filter(User.user_id == update.message.from_user.id)
            .first()
        )
    except Exception as e:
        session.rollback()
        logger.warning(e)
    finally:
        session.close()

    if not user:
        await update.message.reply_text(
            "Пожалуйста, подтвердите Ваш номер телефона. После подтверждения вы сможете использовать команду /valentine",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("Отправить номер телефона", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return

    if user.blocked:
        await update.message.reply_text(
            "Вы заблокированы. Обратитесь к администрации.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if not can_post(update.message.from_user.id):
        await update.message.reply_text(
            "Не торопитесь, вы уже отправили валентинку💌\n\nПопробуйте позже",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        text="Напишите текст для Вашей валентинки💌\n\nОтмена - /cancel",
        reply_markup=ReplyKeyboardRemove(),
    )
    return VALENTINE


async def valentine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return ConversationHandler.END

    if update.message.text == "/cancel":
        await update.message.reply_text("Отмена", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if update.message.text == "/valentine" or update.message.text == "/valentine ":
        await update.message.reply_text(
            text="Напишите текст для Вашей валентинки💌 \n\nОтмена - /cancel",
            reply_markup=ReplyKeyboardRemove(),
        )
        return VALENTINE

    if len(update.message.text) > 500:
        await update.message.reply_text(
            "Ваше послание слишком длинное. Пожалуйста, введите сообщение короче 500 символов",
            reply_markup=ReplyKeyboardRemove(),
        )
        return VALENTINE
    else:
        context.user_data[VALENTINE] = update.message
        try:
            await update.message.reply_text(
                text="Кто получит валентинку? \n\nPS: Вы можете ввести имя пользователя и имя\nПример: @Barnacle Арстан",
                reply_markup=ReplyKeyboardRemove(),
            )
        except Exception as e:
            logger.warning(e)
            await update.message.reply_text(
                text="Что-то пошло не так, свяжитесь с @Barnacle",
                reply_markup=ReplyKeyboardRemove(),
            )
        return RECIPIENT


async def recipient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return ConversationHandler.END

    if update.message.text == "/cancel":
        await update.message.reply_text("Отмена", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if update.message.text == "/valentine" or update.message.text == "/valentine ":
        await update.message.reply_text(
            text="Кто получит валентинку? \n\nPS: Вы можете ввести имя пользователя и имя\nПример: @Barnacle Арстан",
            reply_markup=ReplyKeyboardRemove(),
        )
        return RECIPIENT

    reply_keyboard = [["Да", "Нет"]]

    if len(update.message.text) > 64:
        await update.message.reply_text(
            "Слишком длинное имя адресата. Введите имя короче",
            reply_markup=ReplyKeyboardRemove(),
        )
        return RECIPIENT

    context.user_data[RECIPIENT] = update.message

    await update.message.reply_text(
        text="Отправить анонимно? \n\n",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard,
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="Анонимно?",
        ),
    )

    return ANONIMITY


async def anonimity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return ConversationHandler.END

    if update.message.text == "/cancel":
        await update.message.reply_text("Отмена", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    context.user_data[ANONIMITY] = update.message.text
    reply_keyboard = [["Отправить", "Отменить"]]
    if update.message.text.lower() == "да":
        msg = await update.message.reply_text(
            "Окей, никто не увидит Ваше имя. \n\nВалентинка будет выглядеть так: \n\n",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True,
                input_field_placeholder="Отправить?",
            ),
        )
        await msg.reply_text(
            text=f"*От:* Анонима \n*Кому:* {escape_markdown(context.user_data[RECIPIENT].text, version=2)} \n\n{escape_markdown(context.user_data[VALENTINE].text, version=2)}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    elif update.message.text.lower() == "нет":
        msg = await update.message.reply_text(
            "Окей, валентинка будет отправлена от Вашего имени. \n\nОна будет выглядеть так: \n\n",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True,
                input_field_placeholder="Отправить?",
            ),
        )
        first_name = update.message.from_user.first_name or "Нет имени"
        user_name = update.message.from_user.username or "Нет ника"

        await msg.reply_text(
            text=f"*От:* {escape_markdown(first_name, version=2)} \| @{escape_markdown(user_name, version=2)}\n*Кому:* {escape_markdown(context.user_data[RECIPIENT].text, version=2)} \n\n{escape_markdown(context.user_data[VALENTINE].text, version=2)}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    return CONFIRMATION


async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return ConversationHandler.END

    if update.message.text.lower() == "отправить":
        first_name = update.message.from_user.first_name or "Нет имени"
        user_name = update.message.from_user.username or "Нет ника"
        sender = (
            "Анонима"
            if context.user_data[ANONIMITY] == "Да"
            else f"{first_name} | @{user_name}"
        )

        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"*От:* {escape_markdown(sender, version=2)}\n*Кому:* {escape_markdown(context.user_data[RECIPIENT].text, version=2)} \n\n{escape_markdown(context.user_data[VALENTINE].text, version=2)}\n\n@bilimkana\_cupidbot",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        admin_message_id = await bot.send_message(
            chat_id=ADMIN_GROUP,
            text=f"От: {sender} \nКому: {context.user_data[RECIPIENT].text} \n\n{context.user_data[VALENTINE].text}",
        )

        await update.message.reply_text(
            "Ваша валентинка отправлена\!📫 Найти ее можно [тут](https://t.me/bk_valentines)💌",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        try:
            user = (
                session.query(User)
                .filter(User.user_id == update.message.from_user.id)
                .first()
            )
            if user:
                db_add_valentine(
                    sender=user,
                    recipient=context.user_data[RECIPIENT].text,
                    text=context.user_data[VALENTINE].text,
                    date=datetime.datetime.now(datetime.timezone.utc),
                    admin_message_id=admin_message_id.message_id,
                )
        except Exception as e:
            session.rollback()
            logger.warning(e)
            await update.message.reply_text(
                "Ошибка базы данных! Обратитесь к @Barnacle",
                reply_markup=ReplyKeyboardRemove(),
            )
        finally:
            session.close()

    elif update.message.text.lower() == "отменить":
        await update.message.reply_text(
            "Валентинка не будет отправлена!",
            reply_markup=ReplyKeyboardRemove(),
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отмена", reply_markup=ReplyKeyboardRemove())

    return ConversationHandler.END


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = (
            session.query(User)
            .filter(User.user_id == update.message.from_user.id)
            .first()
        )
        if user:
            await update.message.reply_text(
                "Вы уже подтвердили свой номер телефона!\n\nОтправьте /valentine",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
    except Exception as e:
        session.rollback()
        logger.warning(e)
        await update.message.reply_text(
            "Ошибка базы данных! Обратитесь к @Barnacle",
            reply_markup=ReplyKeyboardRemove(),
        )
    finally:
        session.close()

    try:
        contact = update.message.contact
        full_name = (
            f"{contact.first_name} {contact.last_name}"
            if contact.last_name
            else contact.first_name
        )
    except Exception as e:
        logger.warning(e)

    try:
        db_create_user(
            user_id=contact.user_id,
            full_name=full_name,
            user_name=update.message.from_user.username,
            phone=contact.phone_number,
        )
    except Exception as e:
        logger.warning(e)
        await update.message.reply_text(
            "Пожалуйста, отправьте свой контакт с помощью кнопки ниже",
            reply_markup=ReplyKeyboardMarkup(
                [
                    [
                        KeyboardButton(
                            "Отправить номер телефона",
                            request_contact=True,
                        )
                    ]
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return

    await update.message.reply_text(
        "Спасибо за подтверждение номера телефона!",
        reply_markup=ReplyKeyboardRemove(),
    )


async def block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != str(ADMIN_GROUP):
        return

    if update.message.reply_to_message:
        message_id = update.message.reply_to_message.message_id

        try:
            user = (
                session.query(User)
                .join(Valentine)
                .filter(Valentine.admin_message_id == message_id)
                .first()
            )
        except Exception as e:
            session.rollback()
            logger.warning(e)
            await update.message.reply_text("Что-то пошло не так!")
            return
        finally:
            session.close()

        try:
            reason = update.effective_message.text.split(maxsplit=1)[-1]
            if reason == "/block" or reason == "" or reason == " ":
                reason = "Причина не указана"

            user = session.query(User).filter(User.user_id == user.user_id).first()
            user.blocked = True
            user.blocked_reason = reason
            session.commit()

            await update.message.reply_text("Пользователь заблокирован!")
            return

        except Exception as e:
            session.rollback()
            logger.warning(e)
            await update.message.reply_text("Пользователь не найден!")
            return
        finally:
            session.close()


async def who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != str(ADMIN_GROUP):
        return

    if update.message.reply_to_message:
        message_id = update.message.reply_to_message.message_id

        try:
            user = (
                session.query(User)
                .join(Valentine)
                .filter(Valentine.admin_message_id == message_id)
                .first()
            )
        except Exception as e:
            session.rollback()
            logger.warning(e)
            await update.message.reply_text("Что-то пошло не так!")
            return
        finally:
            session.close()

        try:
            await update.message.reply_text(
                f"Username: {'@' + str(user.user_name) if user.user_name != 'None' else 'Нет ника'}\nИмя: {user.full_name or 'Нет имени'}\nНомер: https://t.me/+{user.phone}\nЗаблокирован: {user.blocked or 'Не заблокирован'}\nПричина: {user.blocked_reason or 'Не заблокирован'}"
            )
            return

        except Exception as e:
            session.rollback()
            logger.warning(e)
            await update.message.reply_text("Пользователь не найден!")
            return
        finally:
            session.close()


def main() -> None:
    assert (bot_token := os.environ.get("TOKEN"))

    application = ApplicationBuilder().token(bot_token).build()
    global bot
    bot = application.bot
    application.add_handler(CommandHandler("start", start, filters.ChatType.PRIVATE))
    application.add_handler(
        CommandHandler("help", help_command, filters.ChatType.PRIVATE)
    )
    application.add_handler(CommandHandler("block", block, filters.ChatType.GROUPS))
    application.add_handler(CommandHandler("who", who, filters.ChatType.GROUPS))

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("valentine", ticket_handler, filters.ChatType.PRIVATE)
        ],
        states={
            VALENTINE: [MessageHandler(filters.TEXT, valentine)],
            RECIPIENT: [MessageHandler(filters.TEXT, recipient)],
            ANONIMITY: [MessageHandler(filters.Regex("^(Да|Нет)$"), anonimity)],
            CONFIRMATION: [
                MessageHandler(filters.Regex("^(Отправить|Отменить)$"), confirmation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    application.add_handler(conv_handler)
    application.run_polling()


if __name__ == "__main__":
    if ADMIN_GROUP is None:
        print("ADMIN_GROUP is not set!")
        exit(1)
    if CHANNEL_ID is None:
        print("CHANNEL_ID is not set!")
        exit(1)
    main()
