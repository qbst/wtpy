"""
数据组件包装器模块

本模块提供WonderTrader数据组件（datakit）的Python接口封装。数据组件负责：
1. 从各种数据源（交易所、数据供应商等）接收实时行情数据
2. 存储和管理历史数据
3. 支持扩展数据解析器（Parser）和数据导出器（Dumper）
4. 提供数据订阅和推送功能

主要功能：
1. 初始化数据组件
2. 创建和管理扩展数据解析器
3. 创建和管理扩展数据导出器
4. 推送行情数据
5. 注册回调函数处理解析器和导出器事件

使用单例模式确保全局只有一个数据组件包装器实例。
"""

# 导入ctypes库，用于调用C++动态库
from ctypes import cdll, c_char_p, c_bool, POINTER
# 导入平台辅助工具，用于获取动态库路径和编码转换
from .PlatformHelper import PlatformHelper as ph
# 导入单例装饰器，确保全局唯一实例
from wtpy.WtUtilDefs import singleton
# 导入核心定义：数据结构、回调函数类型、事件类型
from wtpy.WtCoreDefs import WTSTickStruct, WTSBarStruct, CB_PARSER_EVENT, CB_PARSER_SUBCMD, FUNC_DUMP_HISBARS, FUNC_DUMP_HISTICKS
# 导入解析器事件类型定义
from wtpy.WtCoreDefs import EVENT_PARSER_CONNECT, EVENT_PARSER_DISCONNECT, EVENT_PARSER_INIT, EVENT_PARSER_RELEASE
# 导入操作系统模块
import os

# Python对接C接口的库
@singleton
class WtDtWrapper:
    """
    WonderTrader数据组件C接口底层对接模块
    
    提供数据组件功能的Python封装，支持数据接收、存储、解析和导出。
    使用单例模式，确保全局只有一个实例。
    """

    # api可以作为公共变量，存储C++动态库的接口
    api = None
    # 版本信息
    ver = "Unknown"
    
    # 构造函数，传入数据引擎对象
    def __init__(self, engine):
        """
        初始化数据组件包装器
        
        @param engine: 数据引擎对象，用于管理扩展模块
        """
        # 保存数据引擎引用
        self._engine = engine
        # 获取当前文件所在目录
        paths = os.path.split(__file__)
        # 获取数据组件动态库文件名（包含平台和架构信息）
        dllname = ph.getModule("WtDtPorter")
        # 拼接路径
        a = (paths[:-1] + (dllname,))
        # 生成完整的动态库路径
        _path = os.path.join(*a)
        # 加载C++动态库
        self.api = cdll.LoadLibrary(_path)
        # 设置get_version函数的返回类型：版本字符串（字符指针）
        self.api.get_version.restype = c_char_p
        # 获取并解码版本信息
        self.ver = bytes.decode(self.api.get_version())

        # 设置create_ext_parser函数的返回类型：是否创建成功（布尔）
        self.api.create_ext_parser.restype = c_bool
        # 设置create_ext_parser函数的参数类型：解析器ID（字符串）
        self.api.create_ext_parser.argtypes = [c_char_p]

        # 设置create_ext_dumper函数的返回类型：是否创建成功（布尔）
        self.api.create_ext_dumper.restype = c_bool
        # 设置create_ext_dumper函数的参数类型：导出器ID（字符串）
        self.api.create_ext_dumper.argtypes = [c_char_p]

    def run_datakit(self, bAsync:bool = False):
        """
        启动数据组件
        
        启动数据组件主循环，开始接收和处理数据。
        
        @param bAsync: 是否异步运行，True表示在后台线程运行，False表示阻塞运行，默认为False
        """
        # 调用C++库启动数据组件
        self.api.start(bAsync)

    def write_log(self, level, message:str, catName:str = ""):
        """
        向组件输出日志
        
        @param level: 日志级别（整数）
        @param message: 日志消息内容
        @param catName: 日志分类名称，默认为空字符串
        """
        # 调用C++库写入日志，Windows平台需要转换为GBK编码
        self.api.write_log(level, bytes(message, encoding = "utf8").decode('utf-8').encode('gbk'), bytes(catName, encoding = "utf8"))

    def initialize(self, cfgfile:str = "dtcfg.yaml", logprofile:str = "logcfgdt.jsyamlon", bCfgFile:bool = True, bLogCfgFile:bool = True):
        """
        C接口初始化
        
        初始化数据组件，加载配置文件和日志配置。
        
        @param cfgfile: 配置文件路径或配置内容，默认为"dtcfg.yaml"
        @param logprofile: 日志配置文件路径或配置内容，默认为"logcfgdt.jsyamlon"
        @param bCfgFile: 配置文件参数是否为文件路径，True表示文件路径，False表示配置内容，默认为True
        @param bLogCfgFile: 日志配置文件参数是否为文件路径，True表示文件路径，False表示配置内容，默认为True
        """
        try:
            # 调用C++库初始化数据组件
            self.api.initialize(bytes(cfgfile, encoding = "utf8"), bytes(logprofile, encoding = "utf8"), bCfgFile, bLogCfgFile)
            # 注册扩展模块的回调函数
            self.register_extended_module_callbacks()
        except OSError as oe:
            # 如果加载动态库失败，打印错误信息
            print(oe)

        # 写入初始化成功日志
        self.write_log(102, "WonderTrader datakit initialzied，version: %s" % (self.ver))

    def create_extended_parser(self, id:str) -> bool:
        """
        创建扩展数据解析器
        
        扩展数据解析器用于从自定义数据源接收数据并推送到数据组件。
        
        @param id: 解析器ID，用于标识不同的解析器实例
        @return bool: 是否创建成功
        """
        # 调用C++库创建扩展解析器
        return self.api.create_ext_parser(bytes(id, encoding = "utf8"))

    def push_quote_from_exetended_parser(self, id:str, newTick:POINTER(WTSTickStruct), uProcFlag:int = 1):
        """
        从扩展解析器推送行情数据
        
        将扩展解析器接收到的行情数据推送到数据组件进行处理和存储。
        
        @param id: 解析器ID
        @param newTick: 新的Tick数据指针
        @param uProcFlag: 处理标志，默认为1
        @return bool: 是否推送成功
        """
        # 调用C++库推送行情数据
        return self.api.parser_push_quote(bytes(id, encoding = "utf8"), newTick, uProcFlag)

    def register_extended_module_callbacks(self,):
        """
        注册扩展模块的回调函数
        
        注册解析器事件回调和订阅命令回调，用于处理解析器的生命周期事件和数据订阅请求。
        """
        # 创建解析器事件回调函数
        self.cb_parser_event = CB_PARSER_EVENT(self.on_parser_event)
        # 创建解析器订阅命令回调函数
        self.cb_parser_subcmd = CB_PARSER_SUBCMD(self.on_parser_sub)

        # 向C++库注册回调函数
        self.api.register_parser_callbacks(self.cb_parser_event, self.cb_parser_subcmd)

    def create_extended_dumper(self, id:str) -> bool:
        """
        创建扩展数据导出器
        
        扩展数据导出器用于将数据组件的数据导出到自定义存储位置。
        
        @param id: 导出器ID，用于标识不同的导出器实例
        @return bool: 是否创建成功
        """
        # 调用C++库创建扩展导出器
        return self.api.create_ext_dumper(bytes(id, encoding = "utf8"))

    def register_extended_data_dumper(self):
        """
        注册扩展数据导出器的回调函数
        
        注册K线和Tick数据的导出回调函数，当需要导出数据时会调用这些回调。
        """
        # 创建K线导出回调函数
        self.cb_bars_dumper = FUNC_DUMP_HISBARS(self.dump_his_bars)
        # 创建Tick导出回调函数
        self.cb_ticks_dumper = FUNC_DUMP_HISTICKS(self.dump_his_ticks)

        # 向C++库注册导出器回调函数
        self.api.register_extended_dumper(self.cb_bars_dumper, self.cb_ticks_dumper)

    def on_parser_event(self, evtId:int, id:str):
        """
        解析器事件回调函数
        
        当解析器发生生命周期事件时（初始化、连接、断开连接、释放），C++库会调用此函数。
        
        @param evtId: 事件ID，标识事件类型
        @param id: 解析器ID（字节串）
        """
        # 将解析器ID从字节串解码为字符串
        id = bytes.decode(id)
        # 获取数据引擎对象
        engine = self._engine
        # 从引擎获取对应的扩展解析器对象
        parser = engine.get_extended_parser(id)
        # 如果解析器不存在，直接返回
        if parser is None:
            return
        
        # 根据事件类型调用解析器的相应方法
        if evtId == EVENT_PARSER_INIT:
            # 初始化事件：调用解析器的初始化方法
            parser.init(engine)
        elif evtId == EVENT_PARSER_CONNECT:
            # 连接事件：调用解析器的连接方法
            parser.connect()
        elif evtId == EVENT_PARSER_DISCONNECT:
            # 断开连接事件：调用解析器的断开连接方法
            parser.disconnect()
        elif evtId == EVENT_PARSER_RELEASE:
            # 释放事件：调用解析器的释放方法
            parser.release()

    def on_parser_sub(self, id:str, fullCode:str, isForSub:bool):
        """
        解析器订阅命令回调函数
        
        当需要订阅或取消订阅某个合约的数据时，C++库会调用此函数。
        
        @param id: 解析器ID（字节串）
        @param fullCode: 完整合约代码（字节串）
        @param isForSub: 是否为订阅操作，True表示订阅，False表示取消订阅
        """
        # 将解析器ID从字节串解码为字符串
        id = bytes.decode(id)
        # 获取数据引擎对象
        engine = self._engine
        # 从引擎获取对应的扩展解析器对象
        parser = engine.get_extended_parser(id)
        # 如果解析器不存在，直接返回
        if parser is None:
            return
        # 将合约代码从字节串解码为字符串
        fullCode = bytes.decode(fullCode)
        # 根据操作类型调用解析器的相应方法
        if isForSub:
            # 订阅操作：调用解析器的订阅方法
            parser.subscribe(fullCode)
        else:
            # 取消订阅操作：调用解析器的取消订阅方法
            parser.unsubscribe(fullCode)

    def dump_his_bars(self, id:str, fullCode:str, period:str, bars:POINTER(WTSBarStruct), count:int) -> bool:
        """
        导出历史K线数据回调函数
        
        当扩展数据导出器需要导出K线数据时，C++库会调用此函数。
        
        @param id: 导出器ID（字节串）
        @param fullCode: 完整合约代码（字节串）
        @param period: K线周期（字节串）
        @param bars: K线数据指针数组
        @param count: K线数据条数
        @return bool: 是否导出成功
        """
        # 将导出器ID从字节串解码为字符串
        id = bytes.decode(id)
        # 获取数据引擎对象
        engine = self._engine
        # 从引擎获取对应的扩展数据导出器对象
        dumper = engine.get_extended_data_dumper(id)
        # 如果导出器不存在，返回False
        if dumper is None:
            return False

        # 将合约代码从字节串解码为字符串
        fullCode = bytes.decode(fullCode)
        # 将K线周期从字节串解码为字符串
        period = bytes.decode(period)

        # 调用导出器的K线导出方法
        return dumper.dump_his_bars(fullCode, period, bars, count)

    def dump_his_ticks(self, id:str, fullCode:str, uDate:int, ticks:POINTER(WTSTickStruct), count:int) -> bool:
        """
        导出历史Tick数据回调函数
        
        当扩展数据导出器需要导出Tick数据时，C++库会调用此函数。
        
        @param id: 导出器ID（字节串）
        @param fullCode: 完整合约代码（字节串）
        @param uDate: 数据日期（整数，格式yyyymmdd）
        @param ticks: Tick数据指针数组
        @param count: Tick数据条数
        @return bool: 是否导出成功
        """
        # 将导出器ID从字节串解码为字符串
        id = bytes.decode(id)
        # 获取数据引擎对象
        engine = self._engine
        # 从引擎获取对应的扩展数据导出器对象
        dumper = engine.get_extended_data_dumper(id)
        # 如果导出器不存在，返回False
        if dumper is None:
            return False

        # 将合约代码从字节串解码为字符串
        fullCode = bytes.decode(fullCode)

        # 调用导出器的Tick导出方法
        return dumper.dump_his_ticks(fullCode, uDate, ticks, count)
