"""
数据引擎模块

本模块提供了数据引擎（Data Engine）的Python封装，用于管理数据采集、存储和分发。
数据引擎负责从各种数据源（如行情接口、数据文件等）采集数据，并进行存储和分发。
支持扩展的行情解析器（Parser）和数据导出器（Dumper），可以灵活接入不同的数据源。

主要功能：
1. 引擎初始化：配置数据引擎的运行参数和日志配置
2. 扩展Parser管理：添加和管理扩展的行情解析器
3. 扩展Dumper管理：添加和管理扩展的数据导出器
4. 数据推送：将扩展Parser接收的行情数据推送到底层
"""

# 导入数据引擎的底层包装器
from wtpy.wrapper import WtDtWrapper
# 导入扩展模块基类
from wtpy.ExtModuleDefs import BaseExtParser, BaseExtDataDumper
# 导入单例装饰器
from wtpy.WtUtilDefs import singleton
# 导入JSON处理模块
import json

@singleton
class WtDtEngine:
    """
    数据引擎类（单例模式）
    
    负责管理数据采集、存储和分发。
    采用单例模式确保整个应用中只有一个引擎实例。
    """

    def __init__(self):
        """
        构造函数
        
        初始化数据引擎，创建底层包装器和扩展模块字典。
        """
        # 底层API接口转换器，用于调用C++底层接口
        self.__wrapper__ = WtDtWrapper(self)
        # 存储扩展行情解析器的字典，键为解析器ID，值为BaseExtParser对象
        self.__ext_parsers__ = dict()
        # 存储扩展数据导出器的字典，键为导出器ID，值为BaseExtDataDumper对象
        self.__ext_dumpers__ = dict()

    def initialize(self, cfgfile:str = "dtcfg.yaml", logprofile:str = "logcfgdt.yaml", bCfgFile:bool = True, bLogCfgFile:bool = True):
        """
        数据引擎初始化
        
        从配置文件初始化数据引擎，设置运行参数和日志配置。
        
        @cfgfile: 配置文件路径，默认为dtcfg.yaml
        @logprofile: 日志模块配置文件路径，默认为logcfgdt.yaml
        @bCfgFile: 配置文件是否为文件路径，True表示文件路径，False表示配置内容字符串
        @bLogCfgFile: 日志配置是否为文件路径，True表示文件路径，False表示配置内容字符串
        """
        # 调用底层包装器初始化数据引擎
        self.__wrapper__.initialize(cfgfile, logprofile, bCfgFile, bLogCfgFile)

    def init_with_config(self, cfgfile:dict, logprofile:dict):
        """
        使用配置字典初始化数据引擎
        
        直接使用Python字典对象初始化数据引擎，无需配置文件。
        
        @cfgfile: 配置字典对象
        @logprofile: 日志配置字典对象
        """
        # 将配置字典转换为JSON字符串，并调用底层接口初始化
        self.__wrapper__.initialize(json.dumps(cfgfile), json.dumps(logprofile), False, False)
    
    def run(self, bAsync:bool = False):
        """
        运行数据引擎
        
        启动数据引擎，开始数据采集和处理。
        
        @bAsync: 是否异步运行，True表示异步运行（立即返回），False表示同步运行（阻塞直到停止），默认False
        """
        # 调用底层包装器运行数据引擎
        self.__wrapper__.run_datakit(bAsync)

    def add_exetended_parser(self, parser:BaseExtParser):
        """
        添加扩展行情解析器
        
        注册一个扩展的行情解析器，用于从外部数据源接收行情数据。
        解析器必须实现BaseExtParser接口。
        
        @parser: 扩展行情解析器对象，必须继承自BaseExtParser
        """
        # 获取解析器ID
        id = parser.id()
        # 如果解析器尚未注册
        if id not in self.__ext_parsers__:
            # 先添加到字典中
            self.__ext_parsers__[id] = parser
            # 尝试在底层创建解析器，如果失败则从字典中移除
            if not self.__wrapper__.create_extended_parser(id):
                self.__ext_parsers__.pop(id)

    def get_extended_parser(self, id:str)->BaseExtParser:
        """
        根据ID获取扩展行情解析器
        
        @id: 解析器ID
        @return: 返回对应的BaseExtParser对象，如果不存在则返回None
        """
        # 检查解析器是否存在
        if id not in self.__ext_parsers__:
            return None
        # 返回解析器对象
        return self.__ext_parsers__[id]

    def push_quote_from_extended_parser(self, id:str, newTick, uProcFlag:int):
        """
        从扩展解析器推送Tick数据到底层
        
        当扩展解析器接收到新的Tick数据时，调用此方法将数据推送到底层引擎。
        
        @id: 解析器ID，标识数据来源
        @newTick: Tick数据指针，类型为POINTER(WTSTickStruct)
        @uProcFlag: 预处理标记，0-不处理，1-切片处理，2-累加处理
        """
        # 调用底层包装器推送Tick数据
        self.__wrapper__.push_quote_from_exetended_parser(id, newTick, uProcFlag)

    def add_extended_data_dumper(self, dumper:BaseExtDataDumper):
        """
        添加扩展数据导出器
        
        注册一个扩展的数据导出器，用于将数据导出到外部存储。
        导出器必须实现BaseExtDataDumper接口。
        
        @dumper: 扩展数据导出器对象，必须继承自BaseExtDataDumper
        """
        # 获取导出器ID
        id = dumper.id()
        # 如果导出器尚未注册
        if id not in self.__ext_dumpers__:
            # 先添加到字典中
            self.__ext_dumpers__[id] = dumper
            # 尝试在底层创建导出器，如果失败则从字典中移除
            if not self.__wrapper__.create_extended_dumper(id):
                self.__ext_dumpers__.pop(id)
        # 注册扩展数据导出器到底层
        self.__wrapper__.register_extended_data_dumper()
    
    def get_extended_data_dumper(self, id:str) -> BaseExtDataDumper:
        """
        根据ID获取扩展数据导出器
        
        @id: 导出器ID
        @return: 返回对应的BaseExtDataDumper对象，如果不存在则返回None
        """
        # 检查导出器是否存在
        if id not in self.__ext_dumpers__:
            return None
        # 返回导出器对象
        return self.__ext_dumpers__[id]
