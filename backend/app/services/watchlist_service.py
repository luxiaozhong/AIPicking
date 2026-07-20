"""临时观察指数 — CRUD 服务（组件化，支持多个观察指数）

提供对 index_constituents / index_info 的增删改查，供 watchlist API 调用。
使用 Core 级别查询（select(Model.__table__)），遵循项目规范。

默认观察指数为 900002（临时观察），同时可被语音播报功能复用：
通过传入不同的 index_code（如 900099 语音播报关注）实现独立列表。
"""

from datetime import date as date_type

from sqlalchemy import select, text, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.index_tables import IndexInfo, IndexConstituent
from ..models.stock_tables import Stock

# 默认观察指数（保留原有 900002 行为）
DEFAULT_INDEX_CODE = "900002"
DEFAULT_INDEX_NAME = "临时观察"
DEFAULT_FULL_NAME = "临时观察指数"
DEFAULT_PUBLISHER = "自定义"
DEFAULT_DATA_SOURCE = "custom.manual_watchlist"


async def ensure_index_info(
    db: AsyncSession,
    index_code: str = DEFAULT_INDEX_CODE,
    index_name: str = DEFAULT_INDEX_NAME,
    full_name: str = DEFAULT_FULL_NAME,
    publisher: str = DEFAULT_PUBLISHER,
    data_source: str = DEFAULT_DATA_SOURCE,
) -> None:
    """幂等注册指数元数据到 index_info（INSERT ON CONFLICT DO NOTHING）"""
    await db.execute(
        text(
            """
            INSERT INTO index_info (index_code, index_name, full_name, publisher,
                                    constituent_count, data_source, last_sync_date)
            VALUES (:code, :name, :full_name, :publisher, 0, :source, :today)
            ON CONFLICT (index_code) DO NOTHING
            """
        ),
        {
            "code": index_code,
            "name": index_name,
            "full_name": full_name,
            "publisher": publisher,
            "source": data_source,
            "today": str(date_type.today()),
        },
    )
    await db.commit()


async def get_stocks(db: AsyncSession, index_code: str = DEFAULT_INDEX_CODE) -> dict:
    """读取指定指数所有成分股（JOIN stocks 获取完整 ts_code 和 name）

    Returns:
        {"stocks": [...], "index_info": {...}}
    """
    # 查询成分股
    result = await db.execute(
        text(
            """
            SELECT ic.ts_code AS raw_code, ic.stock_name,
                   COALESCE(s.ts_code, ic.ts_code) AS full_ts_code,
                   COALESCE(s.symbol, ic.ts_code) AS symbol,
                   ic.eff_date, ic.weight
            FROM index_constituents ic
            LEFT JOIN stocks s ON (
                s.ts_code LIKE ic.ts_code || '.%%' OR s.ts_code = ic.ts_code
            )
            WHERE ic.index_code = :index_code
            ORDER BY ic.created_at DESC
            """
        ),
        {"index_code": index_code},
    )
    rows = result.all()

    stocks = [
        {
            "raw_code": r.raw_code,
            "stock_name": r.stock_name,
            "ts_code": r.full_ts_code,
            "symbol": r.symbol,
            "eff_date": r.eff_date,
            "weight": r.weight,
        }
        for r in rows
    ]

    # 查询指数元数据
    info_result = await db.execute(
        select(IndexInfo.__table__).where(IndexInfo.__table__.c.index_code == index_code)
    )
    info_row = info_result.first()
    index_info = dict(info_row._mapping) if info_row else None

    return {"stocks": stocks, "index_info": index_info}


async def add_stocks(
    db: AsyncSession, ts_codes: list[str], index_code: str = DEFAULT_INDEX_CODE
) -> dict:
    """批量添加股票到指定指数

    对每只股票：先 DELETE 旧记录（同 index_code + 同 raw_code），再 INSERT。
    raw_code 从 ts_code 提取（去掉 .SZ/.SH 后缀）。
    stock_name 从 stocks 表查询，查不到则用 ts_code 本身。

    Returns:
        {"added": int, "ts_codes": [...]}
    """
    today = str(date_type.today())
    added = 0
    added_codes = []

    for ts_code in ts_codes:
        # 提取原始代码（去掉交易所后缀）
        raw_code = ts_code.split(".")[0] if "." in ts_code else ts_code

        # 查询股票名称
        name_result = await db.execute(
            select(Stock.__table__.c.name).where(
                (Stock.__table__.c.ts_code == ts_code)
                | (Stock.__table__.c.ts_code.like(raw_code + ".%"))
            )
        )
        name_row = name_result.first()
        stock_name = name_row.name if name_row else raw_code

        # 删除旧记录
        await db.execute(
            text(
                "DELETE FROM index_constituents WHERE index_code = :code AND ts_code = :raw"
            ),
            {"code": index_code, "raw": raw_code},
        )

        # 插入新记录
        await db.execute(
            text(
                """
                INSERT INTO index_constituents (index_code, ts_code, stock_name,
                                                industry, market_cap, weight, eff_date)
                VALUES (:code, :raw, :name, '', NULL, 0, :today)
                """
            ),
            {
                "code": index_code,
                "raw": raw_code,
                "name": stock_name,
                "today": today,
            },
        )

        added += 1
        added_codes.append(ts_code)

    await db.commit()

    # 更新 index_info 的 constituent_count
    count_result = await db.execute(
        text("SELECT COUNT(*) FROM index_constituents WHERE index_code = :code"),
        {"code": index_code},
    )
    count = count_result.scalar() or 0
    await db.execute(
        text(
            "UPDATE index_info SET constituent_count = :cnt, last_sync_date = :today, "
            "updated_at = NOW() AT TIME ZONE 'Asia/Shanghai' WHERE index_code = :code"
        ),
        {"cnt": count, "today": today, "code": index_code},
    )
    await db.commit()

    return {"added": added, "ts_codes": added_codes}


async def remove_stock(
    db: AsyncSession, ts_code: str, index_code: str = DEFAULT_INDEX_CODE
) -> dict:
    """从指定指数删除单只股票

    ts_code 可以是完整格式（000001.SZ）或原始代码（000001）。

    同时尝试原始代码和完整 ts_code，兼容 index_constituents 中两种格式并存的情况。

    Returns:
        {"removed": bool, "ts_code": str}
    """
    raw_code = ts_code.split(".")[0] if "." in ts_code else ts_code

    result = await db.execute(
        text(
            "DELETE FROM index_constituents "
            "WHERE index_code = :code AND (ts_code = :raw OR ts_code = :full)"
        ),
        {"code": index_code, "raw": raw_code, "full": ts_code},
    )
    removed = result.rowcount > 0
    await db.commit()

    # 更新 index_info 的 constituent_count
    count_result = await db.execute(
        text("SELECT COUNT(*) FROM index_constituents WHERE index_code = :code"),
        {"code": index_code},
    )
    count = count_result.scalar() or 0
    today = str(date_type.today())
    await db.execute(
        text(
            "UPDATE index_info SET constituent_count = :cnt, last_sync_date = :today, "
            "updated_at = NOW() AT TIME ZONE 'Asia/Shanghai' WHERE index_code = :code"
        ),
        {"cnt": count, "today": today, "code": index_code},
    )
    await db.commit()

    return {"removed": removed, "ts_code": ts_code}
