"""全部业务表共用一个元数据及表级配置。"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class Base(DeclarativeBase):
    """所有模型共用的 Base。"""

    # 约束和索引在模型中显式命名，与已执行的冻结基线保持一致。
    metadata = MetaData()
