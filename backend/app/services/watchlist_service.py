"""临时观察指数 900002 — CRUD 服务

提供对 index_constituents / index_info 的增删改查，供 watchlist API 调用。
使用 Core 级别查询（select(Model.__table__)），遵循项目规范。
"""

from datetime import date as date_type

from sqlalchemy import select, text, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.index_tables import IndexInfo, IndexConstituent
from ..models.stock_tables import Stock

INDEX_CODE = "900002"
INDEX_NAME = "临时观察"
FULL_NAME = "临时观察指数"
PUBLISHER = "自定义"
DATA_SOURCE = "custom.manual_watchlist"


async def ensure_index_info(db: AsyncSession) -> None:
    """幂等注册 900002 元数据到 index_info（INSERT ON CONFLICT DO NOTHING）"""
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
            "code": INDEX_CODE,
            "name": INDEX_NAME,
            "full_name": FULL_NAME,
            "publisher": PUBLISHER,
            "source": DATA_SOURCE,
            "today": str(date_type.today()),
        },
    )
    await db.commit()


async def get_stocks(db: AsyncSession) -> dict:
    """读取 900002 所有成分股（JOIN stocks 获取完整 ts_code 和 name）

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
        {"index_code": INDEX_CODE},
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
        select(IndexInfo.__table__).where(IndexInfo.__table__.c.index_code == INDEX_CODE)
    )
    info_row = info_result.first()
    index_info = dict(info_row._mapping) if info_row else None

    return {"stocks": stocks, "index_info": index_info}


async def add_stocks(db: AsyncSession, ts_codes: list[str]) -> dict:
    """批量添加股票到 900002

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
            {"code": INDEX_CODE, "raw": raw_code},
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
                "code": INDEX_CODE,
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
        text(
            "SELECT COUNT(*) FROM index_constituents WHERE index_code = :code"
        ),
        {"code": INDEX_CODE},
    )
    count = count_result.scalar() or 0
    await db.execute(
        text(
            "UPDATE index_info SET constituent_count = :cnt, last_sync_date = :today, "
            "updated_at = NOW() AT TIME ZONE 'Asia/Shanghai' WHERE index_code = :code"
        ),
        {"cnt": count, "today": today, "code": INDEX_CODE},
    )
    await db.commit()

    return {"added": added, "ts_codes": added_codes}


async def remove_stock(db: AsyncSession, ts_code: str) -> dict:
    """从 900002 删除单只股票

    ts_code 可以是完整格式（000001.SZ）或原始代码（000001）。

    Returns:
        {"removed": bool, "ts_code": str}
    """
    raw_code = ts_code.split(".")[0] if "." in ts_code else ts_code

    result = await db.execute(
        text(
            "DELETE FROM index_constituents WHERE index_code = :code AND ts_code = :raw"
        ),
        {"code": INDEX_CODE, "raw": raw_code},
    )
    removed = result.rowcount > 0
    await db.commit()

    # 更新 index_info 的 constituent_count
    count_result = await db.execute(
        text(
            "SELECT COUNT(*) FROM index_constituents WHERE index_code = :code"
        ),
        {"code": INDEX_CODE},
    )
    count = count_result.scalar() or 0
    today = str(date_type.today())
    await db.execute(
        text(
            "UPDATE index_info SET constituent_count = :cnt, last_sync_date = :today, "
            "updated_at = NOW() AT TIME ZONE 'Asia/Shanghai' WHERE index_code = :code"
        ),
        {"cnt": count, "today": today, "code": INDEX_CODE},
    )
    await db.commit()

    return {"removed": removed, "ts_code": ts_code}
