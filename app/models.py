import bcrypt
from datetime import datetime
from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, get_db_session
from app.extensions import cache


# ── SQLAlchemy ORM Models ──────────────────────────────────────────────

class DBUser(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rullenummer: Mapped[int] = mapped_column(String(10), nullable=True)
    name = Column(String(255), nullable=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_auth: Mapped[int] = mapped_column(Integer, default=0)
    email = Column(String(255), nullable=True)
    email_verified: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    verification_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    has_seen_turnusliste_tour: Mapped[int] = mapped_column(Integer, default=0)
    is_stub: Mapped[int] = mapped_column(Integer, default=0)
    stasjoneringssted = Column(String(100), nullable=True)
    ans_dato = Column(String(20), nullable=True)   # stored as DD.MM.YYYY string
    fodt_dato = Column(String(20), nullable=True)  # stored as DD.MM.YYYY string
    seniority_nr = Column(Integer, nullable=True)


class AuthorizedEmails(Base):
    __tablename__ = 'authorized_emails'
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=True)
    rullenummer = Column(String(50), nullable=True)
    added_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    added_at = Column(DateTime, default=func.now())
    notes = Column(String(500))
    __table_args__ = (UniqueConstraint('rullenummer', name='unique_rullenummer'),)


class EmailVerificationToken(Base):
    __tablename__ = 'email_verification_tokens'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[int] = mapped_column(Integer, default=0)
    token_type = Column(String(50), default='verification')


class TurnusSet(Base):
    __tablename__ = 'turnus_sets'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    year_identifier = Column(String(10), nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    turnus_file_path = Column(String(500), nullable=True)
    df_file_path = Column(String(500), nullable=True)
    __table_args__ = (UniqueConstraint('year_identifier'),)


class Favorites(Base):
    __tablename__ = 'favorites'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    shift_title = Column(String(255), nullable=False)
    turnus_set_id = Column(Integer, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint('user_id', 'shift_title', 'turnus_set_id'),)


class Shifts(Base):
    __tablename__ = 'shifts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    turnus_set_id = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint('title', 'turnus_set_id'),)


class SoknadsskjemaChoice(Base):
    __tablename__ = "soknadsskjema_choices"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(Integer, nullable=False)
    turnus_set_id   = Column(Integer, nullable=False)
    shift_title     = Column(String(255), nullable=False)
    linje_135       = Column(Integer, default=0)   # 1 = X marked
    linje_246       = Column(Integer, default=0)   # 1 = X marked
    linjeprioritering = Column(String(255), nullable=True)  # future: from turnusnøkkel
    h_dag           = Column(Integer, default=0)   # 1 = J marked
    __table_args__ = (
        UniqueConstraint("user_id", "turnus_set_id", "shift_title",
                         name="uq_soknadsskjema_choices"),
    )


class Innplassering(Base):
    __tablename__ = "innplassering"
    id = Column(Integer, primary_key=True, autoincrement=True)
    turnus_set_id = Column(Integer, ForeignKey("turnus_sets.id"), nullable=False)
    rullenummer = Column(String(20), nullable=False)
    shift_title = Column(String(255), nullable=False)
    linjenummer = Column(Integer, nullable=True)   # position 1–6 within the shift
    ans_nr = Column(Integer, nullable=True)        # seniority/"Ans" column
    is_7th_driver = Column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("turnus_set_id", "rullenummer", name="uq_innplassering_turnus_rullenr"),
    )


# ── Flask-Login User Wrapper ───────────────────────────────────────────

class User(UserMixin):
    def __init__(self, username, user_id, is_admin):
        self.id = user_id
        self.username = username
        self.is_admin = is_admin

    def get_id(self):
        return str(self.id)

    def get_username(self):
        return self.username

    @staticmethod
    def get(username):
        """Get user by username - used by Flask-Login"""
        user = cache.get(f'user_{username}')
        if not user:
            from app.services.user_service import get_user_data
            db_user_data = get_user_data(username)
            if db_user_data:
                user = User(username, db_user_data['id'], db_user_data['is_auth'])
                cache.set(f'user_{username}', user, timeout=60)
        return user

    @staticmethod
    def get_by_username(username):
        """Get user by username"""
        return User.get(username)

    @staticmethod
    def get_by_id(user_id):
        """Get user by ID (required for Flask-Login)"""
        db_session = get_db_session()
        try:
            db_user = db_session.query(DBUser).filter_by(id=user_id).first()
            if db_user:
                return User(db_user.username, db_user.id, db_user.is_auth)
            return None
        finally:
            db_session.close()

    @staticmethod
    def verify_password(stored_password, provided_password):
        """Verify a password against the stored hash"""
        return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password.encode('utf-8'))

    def set_password(self, password):
        """Hash and set the password"""
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return hashed

    def verify_password_instance(self, password):
        """Verify a password for this user instance"""
        from app.services.user_service import get_user_password
        stored_password = get_user_password(self.username)
        if stored_password:
            return User.verify_password(stored_password, password)
        return False
