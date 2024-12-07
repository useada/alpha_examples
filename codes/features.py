# this code is auto generated by the expr_codegen
# https://github.com/wukan1986/expr_codegen
# 此段代码由 expr_codegen 自动生成，欢迎提交 issue 或 pull request
from typing import TypeVar

import polars as pl  # noqa
import polars.selectors as cs  # noqa

# from loguru import logger  # noqa
from polars import DataFrame as _pl_DataFrame
from polars import LazyFrame as _pl_LazyFrame

# ===================================
# 导入优先级，例如：ts_RSI在ta与talib中都出现了，优先使用ta
# 运行时，后导入覆盖前导入，但IDE智能提示是显示先导入的
_ = 0  # 只要之前出现了语句，之后的import位置不参与调整
# from polars_ta.prefix.talib import *  # noqa
from polars_ta.prefix.tdx import *  # noqa
from polars_ta.prefix.ta import *  # noqa
from polars_ta.prefix.wq import *  # noqa
from polars_ta.prefix.cdl import *  # noqa

DataFrame = TypeVar("DataFrame", _pl_LazyFrame, _pl_DataFrame)
# ===================================

_ = ["CLOSE"]
[CLOSE] = [pl.col(i) for i in _]

_ = ["_x_0", "ROCP_020", "ROCP_040", "ROCP_060", "SMA_020", "SMA_040", "SMA_060", "VR_020", "VR_040", "VR_060"]
[_x_0, ROCP_020, ROCP_040, ROCP_060, SMA_020, SMA_040, SMA_060, VR_020, VR_040, VR_060] = [pl.col(i) for i in _]

_DATE_ = "date"
_ASSET_ = "asset"
_NONE_ = None
_TRUE_ = True
_FALSE_ = False


def unpack(x: Expr, idx: int = 0) -> Expr:
    return x.struct[idx]


CS_SW_L1 = r"^sw_l1_\d+$"


def func_0_ts__asset(df: DataFrame) -> DataFrame:
    # ========================================
    df = df.with_columns(
        _x_0=(ts_log_diff(CLOSE, 1)).over(_ASSET_, order_by=_DATE_),
        ROCP_020=(ts_returns(CLOSE, 20)).over(_ASSET_, order_by=_DATE_),
        ROCP_040=(ts_returns(CLOSE, 40)).over(_ASSET_, order_by=_DATE_),
        ROCP_060=(ts_returns(CLOSE, 60)).over(_ASSET_, order_by=_DATE_),
        SMA_020=(ts_mean(CLOSE, 20)).over(_ASSET_, order_by=_DATE_),
        SMA_040=(ts_mean(CLOSE, 40)).over(_ASSET_, order_by=_DATE_),
        SMA_060=(ts_mean(CLOSE, 60)).over(_ASSET_, order_by=_DATE_),
    )
    # ========================================
    df = df.with_columns(
        VR_020=(ts_std_dev(_x_0, 20)).over(_ASSET_, order_by=_DATE_),
        VR_040=(ts_std_dev(_x_0, 40)).over(_ASSET_, order_by=_DATE_),
        VR_060=(ts_std_dev(_x_0, 60)).over(_ASSET_, order_by=_DATE_),
    )
    return df


"""
#========================================func_0_ts__asset
_x_0 = ts_log_diff(CLOSE, 1)
ROCP_020 = ts_returns(CLOSE, 20)
ROCP_040 = ts_returns(CLOSE, 40)
ROCP_060 = ts_returns(CLOSE, 60)
SMA_020 = ts_mean(CLOSE, 20)
SMA_040 = ts_mean(CLOSE, 40)
SMA_060 = ts_mean(CLOSE, 60)
#========================================func_0_ts__asset
VR_020 = ts_std_dev(_x_0, 20)
VR_040 = ts_std_dev(_x_0, 40)
VR_060 = ts_std_dev(_x_0, 60)
"""

"""
ROCP_020 = ts_returns(CLOSE, 20)
ROCP_040 = ts_returns(CLOSE, 40)
ROCP_060 = ts_returns(CLOSE, 60)
VR_020 = ts_std_dev(ts_log_diff(CLOSE, 1), 20)
VR_040 = ts_std_dev(ts_log_diff(CLOSE, 1), 40)
VR_060 = ts_std_dev(ts_log_diff(CLOSE, 1), 60)
SMA_020 = ts_mean(CLOSE, 20)
SMA_040 = ts_mean(CLOSE, 40)
SMA_060 = ts_mean(CLOSE, 60)
"""


def main(df: DataFrame) -> DataFrame:
    # logger.info("start...")

    df = func_0_ts__asset(df.sort(_ASSET_, _DATE_)).drop(*["_x_0"])

    # drop intermediate columns
    # df = df.select(pl.exclude(r'^_x_\d+$'))
    df = df.select(~cs.starts_with("_"))

    # shrink
    df = df.select(cs.all().shrink_dtype())
    # df = df.shrink_to_fit()

    # logger.info('done')

    # save
    # df.write_parquet('output.parquet')

    return df


if __name__ in ("__main__", "builtins"):
    # TODO: 数据加载或外部传入
    df_output = main(df_input)
