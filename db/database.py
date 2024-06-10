import os
import logging
import pytz
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, Index, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.exc import IntegrityError, OperationalError, InvalidRequestError
from datetime import datetime
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

# Load environment variables from .env file
load_dotenv()

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database URL for SQLite
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./kywins.db')

Base = declarative_base()

# Define the timezone for Eastern Standard Time
eastern = pytz.timezone('US/Eastern')

def current_time_est():
    """Get the current time in EST."""
    return datetime.now(eastern)

class Guild(Base):
    __tablename__ = 'guilds'
    id = Column(BigInteger, primary_key=True)
    members = relationship('Member', back_populates='guild')

class Member(Base):
    __tablename__ = 'members'
    id = Column(BigInteger, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey('guilds.id'))
    guild = relationship('Guild', back_populates='members')

class Attachment(Base):
    __tablename__ = 'attachments'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False)
    channel_name = Column(String, nullable=False)
    post_dir_name = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        Index('idx_attachments_username_channel', 'username', 'channel_name'),
    )

class UserCurrency(Base):
    __tablename__ = 'user_currency'
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=False)
    balance = Column(Integer, nullable=False)

class County(Base):
    __tablename__ = 'counties'
    name = Column(String, primary_key=True)
    folder_count = Column(Integer, nullable=False)

class RecentPurchase(Base):
    __tablename__ = 'recent_purchases'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False)
    county_name = Column(String, ForeignKey('counties.name'), nullable=False)
    price = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user1 = Column(String, nullable=False)
    user2 = Column(String, nullable=False)
    item1 = Column(String, nullable=False)
    item2 = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    feedback1 = Column(String)
    feedback2 = Column(String)
    rating1 = Column(Integer)
    rating2 = Column(Integer)

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('user_currency.user_id'), nullable=False)
    username = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    description = Column(String)

class MessageCount(Base):
    __tablename__ = 'message_counts'
    guild_id = Column(BigInteger, ForeignKey('guilds.id'), primary_key=True)
    member_id = Column(BigInteger, ForeignKey('members.id'), primary_key=True)
    username = Column(String, nullable=False)
    count = Column(Integer, nullable=False)

# Create the async engine with pool_pre_ping enabled
async_engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True  # Enables checking connections before use
)

# Create a session maker
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Initialize the database
async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema created successfully.")

@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=10))
async def safe_commit(session):
    try:
        await session.commit()
        logger.info("Session committed successfully.")
    except IntegrityError as e:
        logger.error(f"IntegrityError during commit: {e}")
        await session.rollback()
        raise
    except OperationalError as e:
        logger.error(f"OperationalError during commit: {e}")
        await session.rollback()
        raise
    except InvalidRequestError as e:
        logger.error(f"InvalidRequestError during commit: {e}")
        await session.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error during commit: {e}")
        await session.rollback()
        raise

# Function to handle database operations
async def handle_database_operations(client):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            try:
                for guild in client.guilds:
                    # Check if the guild exists before adding
                    existing_guild = await session.get(Guild, guild.id)
                    if not existing_guild:
                        new_guild = Guild(id=guild.id)
                        session.add(new_guild)

                    # Add members to the database, checking for duplicates
                    for member in guild.members:
                        existing_member = await session.get(Member, member.id)
                        if not existing_member:
                            new_member = Member(id=member.id, guild_id=guild.id)
                            session.add(new_member)

                await safe_commit(session)
            except Exception as e:
                await session.rollback()
                logger.error(f"An error occurred during database operations: {e}")
