# -*- coding: UTF-8 -*-

from fbchat import log, Client
from fbchat.models import *
from fbchat.graphql import graphql_color_to_enum
import sqlite3
import json


class KeepBot(Client):

    listening = True

    def __init__(self, email, password, db_file_name='db.sqlite3', max_tries=1, *args, **kwargs):
        self.email = email
        self.password = password

        # Default vars
        self.default_color = ThreadColor.MESSENGER_BLUE
        self.default_emoji = ""

        # SQLITE
        self.conn = sqlite3.connect(db_file_name)
        self.c = self.conn.cursor()

        # Create tables
        self.c.executescript('''
            CREATE TABLE IF NOT EXISTS login (
                id INTEGER PRIMARY KEY,
                user_id TEXT UNIQUE,
                email TEXT UNIQUE,
                password TEXT, 
                session_cookies TEXT 
            );
            CREATE TABLE IF NOT EXISTS threads (
                id INTEGER PRIMARY KEY,
                thread_id TEXT UNIQUE, 
                color TEXT,
                emoji TEXT
            );
            CREATE TABLE IF NOT EXISTS nicknames (
                id INTEGER PRIMARY KEY,
                thread_id TEXT,
                user_id TEXT, 
                nickname TEXT 
            );
        ''')

        # Load session_cookies
        self.c.execute('SELECT session_cookies FROM login WHERE email = ?', (self.email,))
        self.session_cookies = self.c.fetchone()
        self.session_cookies = json.loads(self.session_cookies[0]) if self.session_cookies else None

        # Login
        if self.session_cookies:
            Client.__init__(self, email, password, session_cookies=self.session_cookies, max_tries=max_tries, *args, **kwargs)
            self.new_session_cookies = self.getSession()
        else:
            Client.__init__(self, email, password, max_tries=max_tries, *args, **kwargs)
            self.new_session_cookies = self.getSession()

        # Update session_cookies in DB
        if self.new_session_cookies != self.session_cookies:
            self.session_cookies = self.new_session_cookies

            self.c.execute('''
                INSERT OR REPLACE INTO login (
                    id, user_id, email, password, session_cookies
                ) VALUES (
                    (SELECT id FROM LOGIN where user_id = :user_id), :user_id, :email, :password, :session_cookies
                )
            ''', {
                'user_id': self.uid,
                'email': self.email,
                'password': self.password,
                'session_cookies': json.dumps(self.session_cookies, ),
            })
            self.conn.commit()

        # Start method listening
        if self.listening == True:
            self.listen()

    ''' GET METHODS '''

    def getColor(self, thread_id):
        self.c.execute('''SELECT color FROM threads WHERE thread_id = ?''', (thread_id, ))
        color = self.c.fetchone()
        print(color)
        if color and color[0]:
            color = graphql_color_to_enum(" " + color[0])
            return color
        else:
            self.updateColor(thread_id, self.default_color)
            return self.default_color

    def getEmoji(self, thread_id):
        self.c.execute('''SELECT emoji FROM threads WHERE thread_id = ?''', (thread_id, ))
        emoji = self.c.fetchone()

        if emoji:
            emoji = emoji[0]
            return emoji
        else:
            self.updateEmoji(thread_id, self.default_emoji)
            return self.default_emoji

    def getNickname(self, thread_id, user_id):
        self.c.execute('SELECT nickname FROM nicknames WHERE thread_id = ? AND user_id = ?', (thread_id, user_id, ))
        nickname = self.c.fetchone()

        if nickname:
            nickname = nickname[0]
            return nickname
        else:
            self.updateNickname(thread_id, user_id, "")
            return ""

    ''' END GET METHODS '''
    ''' UPDATE METHODS '''

    def updateColor(self, thread_id, color):
        self.c.execute('''
            INSERT OR REPLACE INTO threads (
                id,
                thread_id,
                color, 
                emoji
            ) VALUES (
                (SELECT id FROM threads where thread_id = :thread_id),
                :thread_id,
                :color,
                (SELECT emoji FROM threads where thread_id = :thread_id)
            )
        ''', {
            'thread_id': thread_id,
            'color': color.value if color != ThreadColor.MESSENGER_BLUE else ''
        })
        self.conn.commit()

    def updateEmoji(self, thread_id, emoji):
        self.c.execute('''
            INSERT OR REPLACE INTO threads (
                id,
                thread_id,
                color,
                emoji
            ) VALUES (
                (SELECT id FROM threads where thread_id = :thread_id),
                :thread_id,
                (SELECT color FROM threads where thread_id = :thread_id),
                :emoji
            )
        ''', {
            'thread_id': thread_id,
            'emoji': emoji,
        })
        self.conn.commit()

    def updateNickname(self, thread_id, user_id, nickname):
        self.c.execute('''
            INSERT OR REPLACE INTO nicknames (
                id, 
                thread_id, user_id, nickname 
            ) VALUES (
                (SELECT id FROM nicknames WHERE thread_id = :thread_id AND user_id = :user_id),
                 :thread_id, :user_id, :nickname
            )
        ''', {
            'thread_id': thread_id,
            'user_id': user_id,
            'nickname': nickname
        })
        self.conn.commit()

    ''' END UPDATE METHODS '''
    ''' ON CHANGE METHODS '''

    def onColorChange(self, author_id, new_color, thread_id, thread_type, **kwargs):
        old_color = self.getColor(thread_id)
        if old_color != new_color and thread_type == ThreadType.USER:
            if author_id == self.uid:
                log.info("{} changed the thread color to {}".format(author_id, new_color))
                self.updateColor(thread_id, new_color)
            else:
                log.info("{} changed the thread color to {}. It will be changed back to {}".format(author_id, new_color, old_color))
                self.changeThreadColor(old_color, thread_id=thread_id)

    def onEmojiChange(self, author_id, new_emoji, thread_id, thread_type, **kwargs):
        old_emoji = self.getEmoji(thread_id)
        if old_emoji != new_emoji and thread_type == ThreadType.USER:
            if author_id == self.uid:
                log.info("{} changed the thread emoji to {}".format(author_id, new_emoji))
                self.updateEmoji(thread_id, new_emoji)
            else:
                log.info("{} changed the thread emoji to {}. It will be changed back to {}".format(author_id, new_emoji, old_emoji))
                self.changeThreadEmoji(old_emoji, thread_id=thread_id)

    def onNicknameChange(self, author_id, changed_for, new_nickname, thread_id, thread_type, **kwargs):
        old_nickname = self.getNickname(thread_id, changed_for)
        if old_nickname != new_nickname and (thread_type == ThreadType.USER or (thread_type == ThreadType.GROUP and changed_for == self.uid)):
            if author_id == self.uid:
                log.info("{} changed {}'s nickname to {}.".format(author_id, changed_for, new_nickname))
                self.updateNickname(thread_id, changed_for, new_nickname)
            else:
                log.info("{} changed {}'s nickname to {}.It will be changed back to {}.".format(author_id, changed_for, new_nickname, old_nickname))
                self.changeNickname(old_nickname, changed_for, thread_id=thread_id, thread_type=thread_type)

    ''' END ON CHANGE METHODS '''
