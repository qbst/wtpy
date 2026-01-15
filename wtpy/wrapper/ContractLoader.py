"""
合约加载器模块

本模块提供从交易所加载合约信息的功能，支持多种交易接口：
1. CTP接口（CTPLoader）- 用于期货交易
2. CTP期权接口（CTPOptLoader）- 用于期权交易

合约加载器会连接到交易所，下载并保存合约的基本信息（合约代码、名称、交易时间等），
这些信息是后续交易和数据处理的基础。
"""

# 导入平台辅助工具，用于获取动态库路径
from .PlatformHelper import PlatformHelper as ph
# 导入操作系统和JSON处理模块
import os, json
# 导入ctypes库，用于调用C++动态库
from ctypes import cdll,c_char_p, c_bool, c_bool

# 导入枚举类型
from enum import Enum

class LoaderType(Enum):
    """
    加载器类型枚举
    
    定义支持的合约加载器类型，每种类型对应不同的交易接口。
    """
    LT_CTP      = 1  # CTP期货接口加载器
    LT_CTPOpt   = 2  # CTP期权接口加载器

def getModuleName(lType:LoaderType)->str:
    """
    根据加载器类型获取对应的动态库文件名
    
    @param lType: 加载器类型枚举值
    @return str: 动态库文件的完整路径
    @raise Exception: 当加载器类型无效时抛出异常
    """
    # 根据加载器类型选择对应的文件名
    if lType == LoaderType.LT_CTP:
        filename = "CTPLoader"  # CTP期货接口加载器
    elif lType == LoaderType.LT_CTPOpt:
        filename = "CTPOptLoader"  # CTP期权接口加载器
    else:
        # 无效的加载器类型，抛出异常
        raise Exception('Invalid loader type')
        return
    
    # 获取当前文件所在目录
    paths = os.path.split(__file__)
    # 使用平台辅助工具生成动态库文件名（包含平台和架构信息）
    exename = ph.getModule(filename)
    # 拼接路径：当前目录 + 动态库文件名
    a = (paths[:-1] + (exename,))
    # 使用os.path.join拼接路径，确保跨平台兼容性
    return os.path.join(*a)


class ContractLoader:
    """
    合约加载器类
    
    用于从交易所加载合约信息。支持通过配置文件或配置字典两种方式启动。
    加载器会连接到指定的交易接口，下载合约信息并保存到本地。
    """

    def __init__(self, lType:LoaderType = LoaderType.LT_CTP):
        """
        初始化合约加载器
        
        @param lType: 加载器类型，默认为CTP期货接口
        """
        # 打印动态库路径，便于调试
        print(getModuleName(lType))
        # 加载对应的C++动态库
        self.api = cdll.LoadLibrary(getModuleName(lType))
        # 设置run函数的参数类型：配置文件内容（字符串）、是否异步（布尔）、是否为文件路径（布尔）
        self.api.run.argtypes = [ c_char_p, c_bool, c_bool]

    def start(self, cfgfile:str = 'config.ini', bAsync:bool = False):
        """
        通过配置文件启动合约加载器
        
        @param cfgfile: 配置文件名，默认为'config.ini'
        @param bAsync: 是否异步执行，True表示立即返回，False表示等待加载完成，默认为False
        """
        # 调用C++库的run函数，第三个参数True表示cfgfile是文件路径
        self.api.run(bytes(cfgfile, encoding = "utf8"), bAsync, True)

    def start_with_config(self, config:dict, bAsync:bool = False):
        """
        通过配置字典启动合约加载器
        
        @param config: 配置字典，包含连接参数等信息
        @param bAsync: 是否异步执行，True表示立即返回，False表示等待加载完成，默认为False
        """
        # 将配置字典转换为JSON字符串，第三个参数False表示传入的是配置内容而非文件路径
        self.api.run(bytes(json.dumps(config), encoding = "utf8"), bAsync, False)