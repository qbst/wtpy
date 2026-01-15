"""
数据服务端模块

本模块提供了数据服务端（Data Servo）的Python封装，用于提供历史数据查询服务。
数据服务端是一个独立的服务进程，可以响应客户端的K线和Tick数据查询请求。
支持按时间范围、按日期、按数据条数等多种方式查询历史数据。

主要功能：
1. 配置管理：设置基础文件路径、数据存储路径等
2. K线数据查询：支持分钟线、日线、秒线等多种周期的K线数据查询
3. Tick数据查询：支持按时间范围或按日期查询Tick数据
4. 缓存管理：提供缓存清除功能，提高查询性能
"""

# 导入数据定义模块中的K线和Tick数据结构
from wtpy.WtDataDefs import WtNpKline, WtNpTicks
# 导入单例装饰器
from wtpy.WtUtilDefs import singleton
# 导入数据服务端API包装器
from wtpy.wrapper import WtDtServoApi
# 导入JSON处理模块
import json
# 导入操作系统接口模块
import os

@singleton
class WtDtServo:
    """
    数据服务端类（单例模式）
    
    提供历史数据查询服务，支持K线和Tick数据的查询。
    采用单例模式确保整个应用中只有一个服务端实例。
    """

    # 构造函数, 传入动态库名
    def __init__(self, logcfg:str="logcfg.yaml"):
        """
        构造函数
        
        初始化数据服务端，设置日志配置和内部状态。
        
        @logcfg: 日志配置文件路径，默认为logcfg.yaml
        """
        # 配置字典，存储所有配置项
        self.__config__ = None
        # 配置是否已提交标志，防止重复提交
        self.__cfg_commited__ = False
        # 本地API对象，用于调用底层接口
        self.local_api = None
        # 日志配置文件路径
        self.logCfg = logcfg

    def __check_config__(self):
        """
        检查并初始化配置项
        
        主要会补充一些默认设置项，确保配置字典结构完整。
        如果配置字典或API对象未初始化，则进行初始化。
        """
        # 如果API对象未初始化，则创建新对象
        if self.local_api is None:
            self.local_api = WtDtServoApi()

        # 如果配置字典未初始化，则创建空字典
        if self.__config__ is None:
            self.__config__ = dict()

        # 如果配置中没有basefiles字段，则创建空字典
        if "basefiles" not in self.__config__:
            self.__config__["basefiles"] = dict()

        # 如果配置中没有data字段，则创建默认的数据存储配置
        if "data" not in self.__config__:
            self.__config__["data"] = {
                "store":{
                    "path":"./storage/"  # 默认数据存储路径
                }
            }

    def setBasefiles(self, folder:str="./common/", commfile:str="commodities.json", contractfile:str="contracts.json", 
                holidayfile:str="holidays.json", sessionfile:str="sessions.json", hotfile:str="hots.json"):
        """
        设置基础文件路径
        
        配置各种基础配置文件的路径，包括品种文件、合约文件、节假日文件等。
        支持单个文件路径或文件路径列表。
        
        @folder: 基础文件目录，默认为./common/
        @commfile: 品种文件路径或路径列表，支持str或list类型
        @contractfile: 合约文件路径或路径列表，支持str或list类型
        @holidayfile: 节假日文件路径
        @sessionfile: 交易时间模板文件路径
        @hotfile: 主力合约配置文件路径
        """
        # 检查并初始化配置
        self.__check_config__()

        # 处理品种文件路径
        if type(commfile) == str:
            # 单个文件路径，直接拼接
            self.__config__["basefiles"]["commodity"] = os.path.join(folder, commfile)
        elif type(commfile) == list:
            # 多个文件路径，拼接后用逗号分隔
            absList = []
            for filename in commfile:
                absList.append(os.path.join(folder, filename))
            self.__config__["basefiles"]["commodity"] = ','.join(absList)

        # 处理合约文件路径
        if type(contractfile) == str:
            # 单个文件路径，直接拼接
            self.__config__["basefiles"]["contract"] = os.path.join(folder, contractfile)
        elif type(contractfile) == list:
            # 多个文件路径，拼接后用逗号分隔
            absList = []
            for filename in contractfile:
                absList.append(os.path.join(folder, filename))
            self.__config__["basefiles"]["contract"] = ','.join(absList)

        # 设置节假日文件路径
        self.__config__["basefiles"]["holiday"] = os.path.join(folder, holidayfile)
        # 设置交易时间模板文件路径
        self.__config__["basefiles"]["session"] = os.path.join(folder, sessionfile)
        # 设置主力合约配置文件路径
        self.__config__["basefiles"]["hot"] = os.path.join(folder, hotfile)

    def setStorage(self, path:str = "./storage/", adjfactor:str = "adjfactors.json"):
        """
        设置数据存储路径
        
        配置数据存储的路径和复权因子文件路径。
        
        @path: 数据存储路径，默认为./storage/
        @adjfactor: 复权因子文件名，默认为adjfactors.json
        """
        # 设置数据存储路径
        self.__config__["data"]["store"]["path"] = path
        # 设置复权因子文件路径
        self.__config__["data"]["store"]["adjfactor"] = adjfactor
    
    def commitConfig(self):
        """
        提交配置到底层
        
        将配置字典转换为JSON字符串并提交到底层API进行初始化。
        只有第一次调用会生效，防止重复初始化。
        """
        # 如果配置已提交，直接返回
        if self.__cfg_commited__:
            return

        # 将配置字典转换为格式化的JSON字符串
        cfgfile = json.dumps(self.__config__, indent=4, sort_keys=True)
        try:
            # 调用底层API初始化，传入配置JSON字符串、非文件标志和日志配置
            self.local_api.initialize(cfgfile, False, self.logCfg)
            # 标记配置已提交
            self.__cfg_commited__ = True
        except OSError as oe:
            # 如果初始化失败，打印错误信息
            print(oe)

    def clear_cache(self):
        """
        清除缓存数据
        
        清除数据服务端的缓存，释放内存。
        在数据更新后调用此方法可以确保查询到最新数据。
        """        
        # 调用底层API清除缓存
        self.local_api.clear_cache()

    def get_bars(self, stdCode:str, period:str, fromTime:int = None, dataCount:int = None, endTime:int = 0) -> WtNpKline:
        """
        获取K线数据
        
        根据指定的合约代码、周期、时间范围或数据条数查询K线数据。
        fromTime和dataCount必须且只能指定其中一个。
        
        @stdCode: 标准合约代码，例如：SHFE.rb.2305
        @period: 基础K线周期，例如：m1（1分钟）、m5（5分钟）、d（日线）
        @fromTime: 开始时间，日线数据格式yyyymmdd，分钟线数据格式yyyymmddHHMM
        @dataCount: 要获取的数据条数，如果指定此参数则从最新数据往前取
        @endTime: 结束时间，日线数据格式yyyymmdd，分钟线数据格式yyyymmddHHMM，为0则读取到最后一条
        @return: 返回WtNpKline对象，包含K线数据
        @raise Exception: 如果fromTime和dataCount同时指定或都不指定则抛出异常
        """        
        # 确保配置已提交
        self.commitConfig()

        # 检查参数：fromTime和dataCount必须且只能指定其中一个
        if (fromTime is None and dataCount is None) or (fromTime is not None and dataCount is not None):
            raise Exception('Only one of fromTime and dataCount must be valid at the same time')

        # 调用底层API获取K线数据
        return self.local_api.get_bars(stdCode=stdCode, period=period, fromTime=fromTime, dataCount=dataCount, endTime=endTime)

    def get_ticks(self, stdCode:str, fromTime:int = None, dataCount:int = None, endTime:int = 0) -> WtNpTicks:
        """
        获取Tick数据
        
        根据指定的合约代码、时间范围或数据条数查询Tick数据。
        fromTime和dataCount必须且只能指定其中一个。
        
        @stdCode: 标准合约代码，例如：SHFE.rb.2305
        @fromTime: 开始时间，格式为yyyymmddHHMM
        @dataCount: 要获取的数据条数，如果指定此参数则从最新数据往前取
        @endTime: 结束时间，格式为yyyymmddHHMM，为0则读取到最后一条
        @return: 返回WtNpTicks对象，包含Tick数据
        @raise Exception: 如果fromTime和dataCount同时指定或都不指定则抛出异常
        """
        # 确保配置已提交
        self.commitConfig()

        # 检查参数：fromTime和dataCount必须且只能指定其中一个
        if (fromTime is None and dataCount is None) or (fromTime is not None and dataCount is not None):
            raise Exception('Only one of fromTime and dataCount must be valid at the same time')

        # 调用底层API获取Tick数据
        return self.local_api.get_ticks(stdCode=stdCode, fromTime=fromTime, dataCount=dataCount, endTime=endTime)

    def get_ticks_by_date(self, stdCode:str, iDate:int) -> WtNpTicks:
        """
        按日期获取Tick数据
        
        获取指定合约在指定日期的所有Tick数据。
        
        @stdCode: 标准合约代码，例如：SHFE.rb.2305
        @iDate: 日期，格式为yyyymmdd，例如：20230101
        @return: 返回WtNpTicks对象，包含该日期的所有Tick数据
        """
        # 确保配置已提交
        self.commitConfig()

        # 调用底层API按日期获取Tick数据
        return self.local_api.get_ticks_by_date(stdCode=stdCode, iDate=iDate)

    def get_sbars_by_date(self, stdCode:str, iSec:int, iDate:int) -> WtNpKline:
        """
        按日期获取秒线数据
        
        获取指定合约在指定日期的秒线数据。
        
        @stdCode: 标准合约代码，例如：SHFE.rb.2305
        @iSec: 周期，单位秒，例如：5表示5秒线
        @iDate: 日期，格式为yyyymmdd，例如：20230101
        @return: 返回WtNpKline对象，包含该日期的秒线数据
        """
        # 确保配置已提交
        self.commitConfig()

        # 调用底层API按日期获取秒线数据
        return self.local_api.get_sbars_by_date(stdCode=stdCode, iSec=iSec, iDate=iDate)

    def get_bars_by_date(self, stdCode:str, period:str, iDate:int) -> WtNpKline:
        """
        按日期获取K线数据
        
        获取指定合约在指定日期的K线数据。
        注意：此方法只支持分钟线，不支持日线。
        
        @stdCode: 标准合约代码，例如：SHFE.rb.2305
        @period: 周期，只支持分钟线，例如：m1、m5
        @iDate: 日期，格式为yyyymmdd，例如：20230101
        @return: 返回WtNpKline对象，包含该日期的K线数据
        """
        # 确保配置已提交
        self.commitConfig()

        # 调用底层API按日期获取K线数据
        return self.local_api.get_bars_by_date(stdCode=stdCode, period=period, iDate=iDate)
