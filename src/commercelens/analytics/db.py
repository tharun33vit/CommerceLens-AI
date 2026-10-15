"""
Database Engine & Connection Management for CommerceLens AI.

Provides secure SQLAlchemy engine creation, credential masking, environment-driven
connection resolution, connection health checks, and transactional SQL file execution.
"""

import os
import re
from pathlib import Path
from typing import Optional, Tuple, Union
from dotenv import load_dotenv
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

# Automatically load environment variables from .env if present
load_dotenv()


def mask_connection_url(url: str) -> str:
    """
    Mask password in a database connection URL for safe logging and reporting.

    Example:
        'postgresql+psycopg2://user:secret@localhost:5432/db' ->
        'postgresql+psycopg2://user:***@localhost:5432/db'
    """
    if not url:
        return ""
    # Matches :password@ in URL
    return re.sub(r":([^/@:]+)@", ":***@", url)


def get_database_url() -> str:
    """
    Construct database connection URL from environment variables.
    Prioritizes DATABASE_URL if explicitly set, otherwise constructs from POSTGRES_* vars.
    """
    explicit_url = os.environ.get("DATABASE_URL")
    if explicit_url:
        return explicit_url

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db_name = os.environ.get("POSTGRES_DB", "commercelens_db")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "")

    if password:
        encoded_password = quote_plus(password)
        return f"postgresql+psycopg2://{user}:{encoded_password}@{host}:{port}/{db_name}"
    return f"postgresql+psycopg2://{user}@{host}:{port}/{db_name}"


def ensure_database_exists(db_name: str = "commercelens_db") -> Tuple[bool, str]:
    """
    Ensure the target database exists without dropping or altering anything.
    Connects to the maintenance 'postgres' database to check pg_database and create if needed.
    """
    db_url = get_database_url()
    if db_url.startswith("sqlite"):
        return True, "SQLite database is auto-managed."

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "")

    if password:
        encoded_password = quote_plus(password)
        admin_url = f"postgresql+psycopg2://{user}:{encoded_password}@{host}:{port}/postgres"
    else:
        admin_url = f"postgresql+psycopg2://{user}@{host}:{port}/postgres"

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            check_sql = text("SELECT 1 FROM pg_database WHERE datname = :dbname")
            exists = conn.execute(check_sql, {"dbname": db_name}).scalar()
            if exists:
                return True, f"Database '{db_name}' already exists."

            if not re.match(r"^[a-zA-Z0-9_]+$", db_name):
                raise ValueError(f"Invalid database name: {db_name}")
            conn.execute(text(f"CREATE DATABASE {db_name};"))
            return True, f"Database '{db_name}' created successfully."
    except Exception as e:
        return False, f"Failed to verify/create database '{db_name}': {str(e)}"


def create_db_engine(
    url: Optional[str] = None,
    echo: bool = False,
    pool_pre_ping: bool = True,
    **kwargs,
) -> Engine:
    """
    Create a SQLAlchemy Engine with pre-ping validation and safe defaults.

    Args:
        url: Database connection URL (defaults to get_database_url()).
        echo: Whether to log SQL statements.
        pool_pre_ping: Checks connection liveness before checking out from pool.

    Returns:
        SQLAlchemy Engine instance.
    """
    db_url = url or get_database_url()
    
    # SQLite connections do not use pool_pre_ping or server-side pooling
    if db_url.startswith("sqlite"):
        return create_engine(db_url, echo=echo, **kwargs)

    return create_engine(
        db_url,
        echo=echo,
        pool_pre_ping=pool_pre_ping,
        **kwargs,
    )


def check_connection(target: Union[Engine, str]) -> Tuple[bool, str]:
    """
    Safely probe database connectivity with a simple SELECT 1.
    Accepts either an active SQLAlchemy Engine or a connection URL string.

    Returns:
        (is_connected, status_message)
    """
    if isinstance(target, str):
        masked_url = mask_connection_url(target)
        try:
            engine = create_db_engine(target)
        except (ModuleNotFoundError, ImportError) as ie:
            return False, f"Database driver not installed for {masked_url}: {str(ie)}"
        except Exception as e:
            return False, f"Engine initialization failed for {masked_url}: {type(e).__name__} - {str(e)}"
    else:
        engine = target
        masked_url = mask_connection_url(str(engine.url))

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        return True, f"Successfully connected to database at {masked_url}"
    except OperationalError as oe:
        clean_msg = str(oe.orig) if hasattr(oe, "orig") and oe.orig else str(oe)
        return False, f"Connection failed to {masked_url}: {clean_msg}"
    except Exception as e:
        return False, f"Unexpected error connecting to {masked_url}: {type(e).__name__} - {str(e)}"


def execute_sql_file(engine: Engine, sql_file_path: Path) -> int:
    """
    Execute a multi-statement SQL script file inside a single transaction.

    Args:
        engine: SQLAlchemy Engine
        sql_file_path: Path to the .sql file

    Returns:
        Number of statements executed.
    """
    path = Path(sql_file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SQL file not found at: {path}")

    sql_content = path.read_text(encoding="utf-8")
    
    # Split by semicolon while respecting comments and blocks
    # For robust execution across dialects, strip comments and split by ';'
    statements = []
    current_stmt = []
    
    for line in sql_content.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("--"):
            continue
        if trimmed:
            current_stmt.append(line)
        if ";" in line:
            stmt_text = "\n".join(current_stmt).strip()
            if stmt_text:
                statements.append(stmt_text)
            current_stmt = []
            
    if current_stmt:
        remainder = "\n".join(current_stmt).strip()
        if remainder:
            statements.append(remainder)

    executed_count = 0
    with engine.begin() as conn:
        for stmt in statements:
            cleaned = stmt.strip()
            if cleaned:
                conn.execute(text(cleaned))
                executed_count += 1

    return executed_count
