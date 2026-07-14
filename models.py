#models.py
import datetime
from sqlalchemy import Column, Integer, String, Boolean, JSON, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.mutable import MutableDict
from .database import Base

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, index=True)
    username      = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role          = Column(String, default="user")   # admin, moderator, user, guest etc.
    settings      = Column(JSON, default={})
    custom_theme  = Column(JSON, nullable=True)

class ModuleState(Base):
    __tablename__ = "modules"
    id      = Column(Integer, primary_key=True)
    name    = Column(String, unique=True)
    enabled = Column(Boolean, default=True)

class Notification(Base):
    __tablename__ = "notifications"
    id             = Column(Integer, primary_key=True, index=True)
    recipient      = Column(String, index=True, nullable=True)   # username or "all"
    recipient_role = Column(String, default="")
    title          = Column(String, default="")
    message        = Column(Text, default="")
    payload        = Column(Text, default="{}")
    sent           = Column(Boolean, default=False, index=True)
    created_at     = Column(DateTime, default=datetime.datetime.utcnow)

class Theme(Base):
    __tablename__ = "themes"
    id        = Column(Integer, primary_key=True)
    slug      = Column(String, unique=True, nullable=False)
    name      = Column(String)
    is_active = Column(Boolean, default=False)
    config    = Column(JSON)

class UIString(Base):
    __tablename__ = "ui_strings"
    id    = Column(Integer, primary_key = True)
    key   = Column(String, unique = True, nullable = False)
    value = Column(Text)

class UserState(Base):
    """Per-user persistent state. One row per user. Namespaced by module inside the JSON blob."""
    __tablename__ = "user_state"
    id      = Column(Integer, primary_key = True)
    user_id = Column(Integer, ForeignKey("users.id"), unique = True, nullable = False)
    state   = Column(MutableDict.as_mutable(JSON), default = dict, nullable = True)
    user    = relationship("User", backref="state")

class ServerState(Base):
    """
    Single shared state for the entire server (scope="single" in state.py).
    Always exactly one row. All authenticated users read/write the same dict.
    Namespaced by module name inside the JSON blob — same structure as UserState.

    Use only for genuinely shared state (server config, collaborative views).
    For per-user isolation use UserState (scope="user").
    """
    __tablename__ = "server_state"
    id    = Column(Integer, primary_key = True)
    state = Column(MutableDict.as_mutable(JSON), default = dict, nullable = False)