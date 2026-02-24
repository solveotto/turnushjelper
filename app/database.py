import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import AppConfig, get_database_uri

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

Base = declarative_base()

DATABASE_URL = get_database_uri()

_mysql_kwargs = (
    {
        "pool_size": 10,
        "max_overflow": 20,
        "connect_args": {
            "connect_timeout": 20,
            "read_timeout": 20,
            "write_timeout": 20,
        },
    }
    if AppConfig.DB_TYPE == "mysql"
    else {}
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    **_mysql_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session():
    return SessionLocal()
