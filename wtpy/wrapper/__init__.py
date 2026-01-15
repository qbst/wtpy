"""
wrapper模块初始化文件

本模块是wtpy框架中与C++底层库交互的包装层，提供了Python与WonderTrader C++核心库之间的接口封装。
主要功能包括：
1. 实盘交易引擎包装（WtWrapper）
2. 回测引擎包装（WtBtWrapper）
3. 数据组件包装（WtDtWrapper, WtDtServoApi, WtDataHelper）
4. 执行器API（WtExecApi）
5. 消息队列包装（WtMQWrapper）
6. 合约加载器（ContractLoader）
7. 交易数据导出器（TraderDumper）

所有包装类都通过ctypes库调用对应的C++动态链接库，实现Python层与C++层的无缝对接。
"""

# 导入实盘交易引擎包装类，用于连接WonderTrader的实盘交易引擎
from .WtWrapper import WtWrapper
# 导入执行器API包装类，用于独立执行器功能
from .WtExecApi import WtExecApi
# 导入回测引擎包装类，用于连接WonderTrader的回测引擎
from .WtBtWrapper import WtBtWrapper
# 导入数据组件包装类，用于连接WonderTrader的数据组件
from .WtDtWrapper import WtDtWrapper
# 导入合约加载器类及其类型枚举，用于从交易所加载合约信息
from .ContractLoader import ContractLoader,LoaderType
# 导入数据辅助工具类，提供数据转换、存储等功能
from .WtDtHelper import WtDataHelper
# 导入数据服务API包装类，提供数据查询服务
from .WtDtServoApi import WtDtServoApi
# 导入交易数据导出器类，用于导出交易相关数据
from .TraderDumper import TraderDumper

# 定义模块对外导出的公共接口，控制from wrapper import *时的导入内容
__all__ = ["WtWrapper", "WtExecApi", "WtDtWrapper", "WtBtWrapper", "ContractLoader","LoaderType","WtDataHelper","WtDtServoApi","TraderDumper"]