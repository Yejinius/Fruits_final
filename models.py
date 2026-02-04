"""
데이터베이스 모델 정의
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from config import DB_PATH

Base = declarative_base()


class Category(Base):
    """상품 카테고리"""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), unique=True, nullable=False)  # A, B, C, D, E, F, G
    name = Column(String(100), nullable=False)  # 곡류, 과일 등
    created_at = Column(DateTime, default=datetime.now)

    products = relationship("Product", back_populates="category")

    def __repr__(self):
        return f"<Category(code={self.code}, name={self.name})>"


class Product(Base):
    """상품 정보"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_idx = Column(Integer, unique=True, nullable=False)  # 사이트 상품 ID

    # 기본 정보
    name = Column(String(500), nullable=False)
    price = Column(Integer, default=0)  # 가격 (원)
    original_price = Column(Integer, default=0)  # 원래 가격 (할인 전)

    # 상세 정보
    description = Column(Text)  # 상품 설명
    origin = Column(String(200))  # 원산지
    unit = Column(String(100))  # 단위 (kg, 개 등)

    # 재고/배송
    stock = Column(Integer, default=0)  # 재고 수량
    is_available = Column(Boolean, default=True)  # 판매 가능 여부
    delivery_fee = Column(Integer, default=0)  # 배송비

    # 이미지
    main_image_url = Column(String(1000))  # 메인 이미지 원본 URL
    main_image_local = Column(String(500))  # 로컬 저장 경로
    detail_images = Column(Text)  # 상세 이미지 URL들 (JSON)

    # 상세 콘텐츠 (텍스트+이미지 순서 유지, JSON)
    detail_content = Column(Text)  # [{"type": "text", "content": "..."}, {"type": "image", "url": "..."}]

    # 옵션 정보
    options = Column(Text)  # 옵션 정보 (JSON)

    # 카테고리
    category_id = Column(Integer, ForeignKey("categories.id"))
    category = relationship("Category", back_populates="products")

    # 메타 정보
    source_url = Column(String(1000))  # 원본 페이지 URL
    crawled_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<Product(id={self.article_idx}, name={self.name[:30]}...)>"


class ProductImage(Base):
    """상품 이미지 (상세 이미지 별도 관리)"""
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    image_url = Column(String(1000), nullable=False)  # 원본 URL
    local_path = Column(String(500))  # 로컬 저장 경로
    image_type = Column(String(50), default="detail")  # main, detail, etc.
    order = Column(Integer, default=0)  # 이미지 순서

    created_at = Column(DateTime, default=datetime.now)


class CrawlLog(Base):
    """크롤링 로그"""
    __tablename__ = "crawl_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_code = Column(String(10))
    total_products = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime)
    status = Column(String(50), default="running")  # running, completed, failed
    error_message = Column(Text)


# 데이터베이스 초기화
def init_db():
    """데이터베이스 및 테이블 생성"""
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session():
    """데이터베이스 세션 반환"""
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    # 테이블 생성 테스트
    engine = init_db()
    print(f"Database created at: {DB_PATH}")
