from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базальная модель."""
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    items: Mapped[list["Item"]] = relationship("Item", back_populates="category", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Category {self.id}: {self.name}>"


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    category: Mapped[Category] = relationship("Category", back_populates="items")

    is_booked: Mapped[bool] = mapped_column(Boolean, default=False)
    serial: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Поля для брони и продажи
    booking_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    booking_prepayment: Mapped[Optional[float]] = mapped_column(nullable=True)
    booking_platform: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    booking_full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    booking_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    booking_payment_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    booking_bonus: Mapped[Optional[float]] = mapped_column(nullable=True)
    booking_bonus_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    sale_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    sale_prepayment: Mapped[Optional[float]] = mapped_column(nullable=True)
    sale_payment_amount: Mapped[Optional[float]] = mapped_column(nullable=True)
    sale_payment_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sale_platform: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sale_full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sale_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sale_bonus: Mapped[Optional[float]] = mapped_column(nullable=True)
    sale_bonus_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sale_change: Mapped[Optional[float]] = mapped_column(nullable=True)
    sale_change_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_sold: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self):
        return f"<Item {self.id}: {self.text[:50]}>"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    phones: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    social_network: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    referral_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    birth_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    purchases: Mapped[list["Purchase"]] = relationship("Purchase", back_populates="client", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Client {self.id}: {self.full_name}>"


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    client: Mapped[Client] = relationship("Client", back_populates="purchases")
    total_amount: Mapped[float] = mapped_column(nullable=False)
    purchase_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payment_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    items_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DeletedItem(Base):
    __tablename__ = "deleted_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    serial: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(String(50), default="manual")
    deleted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    restored: Mapped[bool] = mapped_column(Boolean, default=False)
    sale_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)   # ← ИЗМЕНЕНО


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    cash: Mapped[float] = mapped_column(default=0)
    terminal: Mapped[float] = mapped_column(default=0)
    qr: Mapped[float] = mapped_column(default=0)
    transfer: Mapped[float] = mapped_column(default=0)
    invoice: Mapped[float] = mapped_column(default=0)
    installment: Mapped[float] = mapped_column(default=0)
    is_accessory: Mapped[bool] = mapped_column(Boolean, default=False)
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)        # ← ИЗМЕНЕНО
    sold_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Preorder(Base):
    __tablename__ = "preorders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cash: Mapped[float] = mapped_column(default=0)
    terminal: Mapped[float] = mapped_column(default=0)
    qr: Mapped[float] = mapped_column(default=0)
    transfer: Mapped[float] = mapped_column(default=0)
    invoice: Mapped[float] = mapped_column(default=0)
    installment: Mapped[float] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_amount: Mapped[float] = mapped_column(default=0)
    booked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DailyPayment(Base):
    __tablename__ = "daily_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(default=0)
    sale_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)   # ← ИЗМЕНЕНО
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Seller(Base):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SellerDay(Base):
    __tablename__ = "seller_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"))
    date: Mapped[datetime] = mapped_column(Date, nullable=False, index=True)
    seller: Mapped[Seller] = relationship("Seller", back_populates="days")


Seller.days = relationship("SellerDay", back_populates="seller", cascade="all, delete-orphan")


class DailyStats(Base):
    __tablename__ = "daily_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(Date, unique=True, nullable=False, index=True)

    sales_count: Mapped[int] = mapped_column(Integer, default=0)
    preorders_count: Mapped[int] = mapped_column(Integer, default=0)
    bookings_count: Mapped[int] = mapped_column(Integer, default=0)

    cash: Mapped[float] = mapped_column(default=0)
    terminal: Mapped[float] = mapped_column(default=0)
    qr: Mapped[float] = mapped_column(default=0)
    transfer: Mapped[float] = mapped_column(default=0)
    invoice: Mapped[float] = mapped_column(default=0)
    installment: Mapped[float] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())
