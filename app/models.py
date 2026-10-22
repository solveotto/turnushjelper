import bcrypt
from datetime import datetime
from flask_login import UserMixin
from sqlalchemy import (
    JSON, Column, Integer, String, DateTime, LargeBinary, UniqueConstraint, func, ForeignKey, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, get_db_session
from app.extensions import cache


# ── SQLAlchemy ORM Models ──────────────────────────────────────────────

class DBUser(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rullenummer: Mapped[str | None] = mapped_column(String(10), nullable=True, unique=True, index=True)
    medlemsnummer = Column(String(20), nullable=True, unique=True, index=True)
    name = Column(String(255), nullable=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_auth: Mapped[int] = mapped_column(Integer, default=0)
    email = Column(String(255), nullable=True)
    email_verified: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    verification_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    has_seen_turnusliste_tour: Mapped[int] = mapped_column(Integer, default=0)
    has_seen_favorites_tour: Mapped[int] = mapped_column(Integer, default=0)
    has_seen_mintur_tour: Mapped[int] = mapped_column(Integer, default=0)
    has_seen_compare_tour: Mapped[int] = mapped_column(Integer, default=0)
    has_seen_welcome: Mapped[int] = mapped_column(Integer, default=0)
    has_seen_soknadsskjema_tour: Mapped[int] = mapped_column(Integer, default=0)
    is_stub: Mapped[int] = mapped_column(Integer, default=0)
    stasjoneringssted = Column(String(100), nullable=True)
    ans_dato = Column(String(20), nullable=True)   # stored as DD.MM.YYYY string
    fodt_dato = Column(String(20), nullable=True)  # stored as DD.MM.YYYY string
    seniority_nr = Column(Integer, nullable=True)
    not_on_nlf_list = Column(Integer, nullable=True, default=0)


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
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    shift_title = Column(String(255), nullable=False)
    turnus_set_id = Column(Integer, ForeignKey('turnus_sets.id', ondelete='CASCADE'), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint('user_id', 'shift_title', 'turnus_set_id'),)


class Shifts(Base):
    __tablename__ = 'shifts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    turnus_set_id = Column(Integer, ForeignKey('turnus_sets.id', ondelete='CASCADE'), nullable=False)
    __table_args__ = (UniqueConstraint('title', 'turnus_set_id'),)


class SoknadsskjemaChoice(Base):
    __tablename__ = "soknadsskjema_choices"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    turnus_set_id   = Column(Integer, ForeignKey('turnus_sets.id', ondelete='CASCADE'), nullable=False)
    shift_title     = Column(String(255), nullable=False)
    linje_135       = Column(Integer, default=0)   # 1 = X marked
    linje_246       = Column(Integer, default=0)   # 1 = X marked
    linjeprioritering = Column(String(255), nullable=True)  # future: from turnusnøkkel
    h_dag           = Column(Integer, default=0)   # 1 = J marked
    __table_args__ = (
        UniqueConstraint("user_id", "turnus_set_id", "shift_title",
                         name="uq_soknadsskjema_choices"),
    )


class UserActivity(Base):
    __tablename__ = 'user_activity'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    event_type = Column(String(50), nullable=False)  # 'login', 'logout', 'favorite_add', 'favorite_remove'
    timestamp = Column(DateTime, default=func.now(), nullable=False)
    details = Column(String(255), nullable=True)       # e.g. shift title for favorite events
    session_duration_seconds = Column(Integer, nullable=True)  # only for 'logout' events


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


class StreklisteDagsverk(Base):
    """One duty as the strekliste PDF draws it: a number, the weekdays it
    runs, and (below) its activities. Plan data for a rutetermin, not a
    record of anything that happened — a re-parse replaces it wholesale.

    ``nr`` is the number as printed ("1203-Mod_1", "1313-N05_5"); ``nr_base``
    its leading digits, which is all the roster export carries. The same
    number recurs with different ``kjoredager`` (1310 on days 2+5 and on
    days 3+4), so the key includes the days.
    """
    __tablename__ = "strekliste_dagsverk"
    id = Column(Integer, primary_key=True, autoincrement=True)
    turnus_set_id = Column(Integer, ForeignKey("turnus_sets.id", ondelete="CASCADE"), nullable=False)
    stasjoneringssted = Column(String(10), nullable=True)
    nr = Column(String(60), nullable=False)       # R27 prints up to 22 chars ("1208-mod_1___N05_13_17")
    nr_base = Column(String(10), nullable=False)
    kjoredager = Column(String(7), nullable=False, default="")
    dobbelt_tur = Column(String(130), nullable=True)  # "3006<<3007" when the row held two duties; two nr + "<<"
    materiell = Column(String(120), nullable=True)
    start = Column(String(5), nullable=True)      # "HH:MM"
    slutt = Column(String(5), nullable=True)
    slutt_neste_dag = Column(Integer, nullable=False, default=0)
    side = Column(Integer, nullable=True)
    beregninger = Column(JSON, nullable=True)     # the Timer columns, when the file has them
    kommentar = Column(String(300), nullable=True)
    advarsler = Column(JSON, nullable=True)       # what the parser could not settle
    created_at = Column(DateTime, default=func.now())
    aktiviteter = relationship(
        "StreklisteAktivitet", back_populates="dagsverk",
        cascade="all, delete-orphan", order_by="StreklisteAktivitet.radnr",
    )
    __table_args__ = (
        UniqueConstraint("turnus_set_id", "stasjoneringssted", "nr", "kjoredager",
                         name="uq_strekliste_dagsverk_nokkel"),
        Index("ix_strekliste_dagsverk_base", "turnus_set_id", "nr_base"),
    )


class StreklisteAktivitet(Base):
    """One segment of a duty's bar, in order. Times are clock times ("HH:MM"),
    with ``*_neste_dag`` set on the far side of midnight."""
    __tablename__ = "strekliste_aktivitet"
    id = Column(Integer, primary_key=True, autoincrement=True)
    dagsverk_id = Column(Integer, ForeignKey("strekliste_dagsverk.id", ondelete="CASCADE"),
                         nullable=False)
    radnr = Column(Integer, nullable=False)
    fra_tid = Column(String(5), nullable=True)
    til_tid = Column(String(5), nullable=True)
    fra_neste_dag = Column(Integer, nullable=False, default=0)
    til_neste_dag = Column(Integer, nullable=False, default=0)
    fra_stasjon = Column(String(10), nullable=True)
    til_stasjon = Column(String(10), nullable=True)
    type = Column(String(30), nullable=False)      # label keyword, else the pattern's legend name
    monster = Column(String(30), nullable=True)    # the pattern the segment is drawn with
    tognumre = Column(String(120), nullable=True)  # comma-separated, as printed
    tekst = Column(String(300), nullable=True)     # every label on the segment, verbatim
    dagsverk = relationship("StreklisteDagsverk", back_populates="aktiviteter")
    __table_args__ = (
        UniqueConstraint("dagsverk_id", "radnr", name="uq_strekliste_aktivitet_rad"),
    )


class FlaskSessionModel(Base):
    __tablename__ = 'flask_sessions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    data = Column(LargeBinary(16_777_215), nullable=False)
    expiry = Column(DateTime, nullable=False, index=True)


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
