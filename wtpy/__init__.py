"""
wtpy模块初始化文件

本文件是wtpy量化交易框架的入口模块，负责导出框架的核心类和接口。
wtpy是基于WonderTrader C++量化框架的Python封装层，提供了完整的量化交易功能，
包括策略开发、回测、实盘交易、数据管理等核心功能。

主要功能模块：
1. 策略基类：BaseCtaStrategy（CTA策略）、BaseSelStrategy（选股策略）、BaseHftStrategy（高频策略）
2. 策略上下文：CtaContext、SelContext、HftContext，提供策略运行环境和接口
3. 引擎类：WtEngine（实盘引擎）、WtBtEngine（回测引擎）、WtDtEngine（数据引擎）
4. 数据结构：WTSTickStruct（Tick数据）、WTSBarStruct（K线数据）、EngineType（引擎类型枚举）
5. 扩展工具：BaseDataReporter（数据报告器）、BaseIndexWriter（指标输出器）
6. 扩展模块：BaseExtExecuter（扩展执行器）、BaseExtParser（扩展行情解析器）
7. 消息队列：WtMsgQue、WtMQClient、WtMQServer（消息队列相关类）
8. 数据服务：WtDtServo（数据服务端）
9. 其他工具：WtExecApi（执行API）、ContractLoader（合约加载器）、TraderDumper（交易数据导出器）
"""

# 导入策略基类定义
from .StrategyDefs import BaseCtaStrategy, BaseSelStrategy, BaseHftStrategy
# 导入策略上下文类，提供策略运行环境和接口
from .CtaContext import CtaContext
from .SelContext import SelContext
from .HftContext import HftContext
# 导入引擎类，包括实盘引擎、回测引擎和数据引擎
from .WtEngine import WtEngine
from .WtBtEngine import WtBtEngine
from .WtDtEngine import WtDtEngine
# 导入核心数据结构定义和引擎类型枚举
from .WtCoreDefs import WTSTickStruct,WTSBarStruct,EngineType
# 导入扩展工具基类，用于数据报告和指标输出
from .ExtToolDefs import BaseDataReporter, BaseIndexWriter
# 导入扩展模块基类，用于扩展执行器和行情解析器
from .ExtModuleDefs import BaseExtExecuter, BaseExtParser
# 导入消息队列相关类
from .WtMsgQue import WtMsgQue, WtMQClient, WtMQServer
# 导入数据服务端类
from .WtDtServo import WtDtServo

# 从wrapper子模块导入执行API、合约加载器和交易数据导出器
from wtpy.wrapper.WtExecApi import WtExecApi
from wtpy.wrapper.ContractLoader import ContractLoader,LoaderType
from wtpy.wrapper.TraderDumper import TraderDumper, DumperSink

# 定义模块的公共接口，控制from wtpy import *时导入的内容
__all__ = ["BaseCtaStrategy", "BaseSelStrategy", "BaseHftStrategy", 
            "CtaContext", "SelContext", "HftContext",
            "WtEngine",  "WtBtEngine", "WtDtEngine", "EngineType", 
            "WtExecApi", "WtDtServo", 
            "WTSTickStruct","WTSBarStruct",
            "BaseIndexWriter", "BaseDataReporter", 
            "ContractLoader", "LoaderType",
            "BaseExtParser", "BaseExtExecuter",
            "WtMsgQue", "WtMQClient", "WtMQServer", 
            "TraderDumper", "DumperSink"]
