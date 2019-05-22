import asyncio
import re
from collections import namedtuple
from contextlib import suppress

import discord

__all__ = [
    'button',
    'command',
    'Session',
    'EVERYONE',
]

class _EVERYONE:
    """Allows everyone to take part in a session"""
    def __contains__(self, other):
        return True

EVERYONE = _EVERYONE()

_Button = namedtuple('_Button', 'emoji press')

def button(emoji, *, unpress=False):
    """Decorates a function that will be called when a user reacts with
    a given emoji

    Parameters
    ----------
    emoji: str
        The emoji that will trigger this button
    unpress: Optional[bool]
        Whether the callback will be called when pressing or releasing the
        button. Defaults to False, or when it's pressed.
    """

    def decorator(func):
        func.__ui_button__ = _Button(emoji=emoji, press=not unpress)
        return func
    return decorator

def command(pattern):
    """Decorates a function that will be called when a user inputs a
    text command that fits a given pattern.
    """
    def decorator(func):
        func.__ui_command__ = pattern
        return func
    return decorator

class Session:
    """Base class for all interactive sessions.

    Parameters
    ----------
    timeout: Optional[float]
        Max time in seconds to wait for a message or reaction event.
        Defaults to no timeout.
    delete_after: bool
        Whether or not to delete the message once the session is finished.
        Defaults to False
    allowed_users: Container[int]
        A container of IDs of users who are allowed to interact with
        the session. If not passed, it will be the context's author
        upon calling Session.start().

        To allow anyone to interact with it, pass ui.EVERYONE.

    Attributes
    ----------
    context: Context
        The current context
    message: discord.Message
        The first message sent by the session. None if the session
        hasn't started yet.
    """

    def __init__(self, timeout=None, delete_after=False, allowed_users=None):
        self.timeout = timeout
        self.delete_after = delete_after
        self.allowed_users = allowed_users

        self.context = None
        self.message = None

        # We're using a listener based approach so we need a queue to keep
        # things synchronized
        self._queue = asyncio.Queue()

    def __init_subclass__(cls, **kwargs):
        buttons = {}
        commands = {}
        unbuttons = {}

        def base_class_attr_update(base, field, mapping):
            base_fields = getattr(b, field, None)
            if not base_fields:
                return

            for name, value in base_fields.items():
                mapping[name] = value

        # Go through bases in reverse-MRO order, excluding the class itself.
        # It's reversed so that subclasses can override earlier buttons/commands.
        for b in cls.__mro__[-1:0:-1]:
            base_class_attr_update(b, '__ui_buttons__', buttons)
            base_class_attr_update(b, '__ui_commands__', commands)
            base_class_attr_update(b, '__ui_unbuttons__', unbuttons)

        # Go through the dictionary to add new buttons/commands/unbuttons.
        for name, value in cls.__dict__.items():
            button = getattr(value, '__ui_button__', None)
            if button:
                if button.press:
                    buttons[button.emoji] = value
                else:
                    unbuttons[button.emoji] = value

            command = getattr(value, '__ui_command__', None)
            if command:
                commands[command] = value

        cls.__ui_buttons__ = buttons
        cls.__ui_commands__ = commands
        cls.__ui_unbuttons__ = unbuttons

    async def on_message(self, message):
        if message.channel.id != self.message.channel.id:
            return

        if message.author.id not in self.allowed_users:
            return

        match = callback = None
        for pattern, command in self.__ui_commands__.items():
            match = re.fullmatch(pattern, message.content)
            if not match:
                continue

            callback = command.__get__(self, self.__class__)
            await self._queue.put((callback, message, *match.groups()))
            break

    async def on_raw_reaction_action(self, payload, *, pressed=True):
        if payload.message_id != self.message.id:
            return

        if payload.user_id not in self.allowed_users:
            return

        if pressed:
            lookup = self.__ui_buttons__
        else:
            lookup = self.__ui_unbuttons__

        button = lookup.get(str(payload.emoji))
        if not button:
            return

        callback = button.__get__(self, self.__class__)
        await self._queue.put((callback, payload))

    async def on_raw_reaction_add(self, payload):
        await self.on_raw_reaction_action(payload, pressed=True)

    async def on_raw_reaction_remove(self, payload):
        await self.on_raw_reaction_action(payload, pressed=False)

    async def on_raw_message_delete(self, payload):
        if payload.message_id == self.message.id:
            await self.stop()

    async def send_initial_message(self):
        """Returns the first message sent by this session

        Subclasses must implement this.
        """
        raise NotImplementedError

    async def __loop(self):
        while True:
            job = await asyncio.wait_for(self._queue.get(), self.timeout)

            if job is None:
                break

            func, *args = job
            await func(*args)

    async def _prepare(self):
        bot = self.context.bot

        bot.add_listener(self.on_message)
        bot.add_listener(self.on_raw_reaction_add)
        bot.add_listener(self.on_raw_reaction_remove)
        bot.add_listener(self.on_raw_message_delete)

        async def add_reactions():
            for emoji in self.__ui_buttons__:
                await self.message.add_reaction(emoji)

        bot.loop.create_task(add_reactions())

    async def _cleanup(self):
        bot = self.context.bot

        bot.remove_listener(self.on_message)
        bot.remove_listener(self.on_raw_reaction_add)
        bot.remove_listener(self.on_raw_reaction_remove)
        bot.remove_listener(self.on_raw_message_delete)

        with suppress(discord.HTTPException):
            if self.delete_after:
                await self.message.delete()
            else:
                await self.message.clear_reactions()

        self.message = None

    async def start(self, ctx):
        """Starts the session"""

        self.context = ctx

        if self.allowed_users is None:
            self.allowed_users = {ctx.author.id}

        self.message = await self.send_initial_message()

        await self._prepare()

        try:
            await self.__loop()
        finally:
            await self._cleanup()

    async def stop(self):
        """Signal the session to stop.

        .. note::
        The session might not stop right away if there are other
        messages or reactions being processed before this is called.
        However, any messages or reactions that get added afterwards
        will be ignored.
        """

        await self._queue.put(None)

