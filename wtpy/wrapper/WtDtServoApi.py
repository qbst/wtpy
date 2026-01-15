"""
数据服务API包装模块

本模块提供WonderTrader数据服务组件的Python接口封装。数据服务组件提供数据查询服务，
可以从数据存储中读取历史K线和Tick数据，支持多种查询方式：
1. 按时间范围查询
2. 按数据条数查询
3. 按日期查询

主要功能：
1. 初始化数据服务
2. 查询K线数据（支持分钟线、日线、秒线）
3. 查询Tick数据
4. 清除缓存

使用单例模式确保全局只有一个数据服务API实例。
"""

# 导入ctypes库，用于调用C++动态库
from ctypes import cdll, CFUNCTYPE, c_char_p, c_void_p, c_bool, POINTER, c_uint64, c_uint32
# 导入核心数据结构定义
from wtpy.WtCoreDefs import WTSBarStruct, WTSTickStruct
# 导入数据定义：NumPy数组封装类和数据缓存类
from wtpy.WtDataDefs import WtNpKline, WtNpTicks, WtBarCache, WtTickCache
# 导入平台辅助工具，用于获取动态库路径
from wtpy.wrapper.PlatformHelper import PlatformHelper as ph
# 导入单例装饰器，确保全局唯一实例
from wtpy.WtUtilDefs import singleton
# 导入操作系统模块
import os

# 定义K线数据回调函数类型：K线数据指针、数据条数、是否最后一批
CB_GET_BAR = CFUNCTYPE(c_void_p,  POINTER(WTSBarStruct), c_uint32, c_bool)
# 定义Tick数据回调函数类型：Tick数据指针、数据条数、是否最后一批
CB_GET_TICK = CFUNCTYPE(c_void_p,  POINTER(WTSTickStruct), c_uint32, c_bool)
# 定义数据计数回调函数类型：数据总条数
CB_DATA_COUNT = CFUNCTYPE(c_void_p,  c_uint32)

@singleton
class WtDtServoApi:
    """
    WonderTrader数据服务组件C接口底层对接模块
    
    提供数据查询服务的Python封装，支持多种查询方式获取历史数据。
    使用单例模式，确保全局只有一个实例。
    """

    # api可以作为公共变量，存储C++动态库的接口
    api = None
    # 版本信息
    ver = "Unknown"

    # 构造函数，初始化数据服务API
    def __init__(self):
        """
        初始化数据服务API包装器
        """
        # 获取当前文件所在目录
        paths = os.path.split(__file__)
        # 获取数据服务动态库文件名（包含平台和架构信息）
        dllname = ph.getModule("WtDtServo")
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

        # 设置get_bars_by_range函数的参数类型：合约代码、周期、开始时间、结束时间、K线回调、计数回调
        self.api.get_bars_by_range.argtypes = [c_char_p, c_char_p, c_uint64, c_uint64, CB_GET_BAR, CB_DATA_COUNT]
        # 设置get_ticks_by_range函数的参数类型：合约代码、开始时间、结束时间、Tick回调、计数回调
        self.api.get_ticks_by_range.argtypes = [c_char_p, c_uint64, c_uint64, CB_GET_TICK, CB_DATA_COUNT]

        # 设置get_bars_by_count函数的参数类型：合约代码、周期、数据条数、结束时间、K线回调、计数回调
        self.api.get_bars_by_count.argtypes = [c_char_p, c_char_p, c_uint32, c_uint64, CB_GET_BAR, CB_DATA_COUNT]
        # 设置get_ticks_by_count函数的参数类型：合约代码、数据条数、结束时间、Tick回调、计数回调
        self.api.get_ticks_by_count.argtypes = [c_char_p, c_uint32, c_uint64, CB_GET_TICK, CB_DATA_COUNT]

        # 设置get_ticks_by_date函数的参数类型：合约代码、日期、Tick回调、计数回调
        self.api.get_ticks_by_date.argtypes = [c_char_p, c_uint32, CB_GET_TICK, CB_DATA_COUNT]
        # 设置get_sbars_by_date函数的参数类型：合约代码、秒数周期、日期、K线回调、计数回调
        self.api.get_sbars_by_date.argtypes = [c_char_p, c_uint32, c_uint32, CB_GET_BAR, CB_DATA_COUNT]
        # 设置get_bars_by_date函数的参数类型：合约代码、周期、日期、K线回调、计数回调
        self.api.get_bars_by_date.argtypes = [c_char_p, c_char_p, c_uint32, CB_GET_BAR, CB_DATA_COUNT]

    def initialize(self, cfgfile:str, isFile:bool, logcfg:str = 'logcfg.yaml'):
        """
        初始化数据服务
        
        @param cfgfile: 配置文件路径或配置内容
        @param isFile: 是否为文件路径，True表示文件路径，False表示配置内容
        @param logcfg: 日志配置文件路径，默认为'logcfg.yaml'
        """
        # 调用C++库初始化数据服务
        self.api.initialize(bytes(cfgfile, encoding = "utf8"), isFile, bytes(logcfg, encoding = "utf8"))

    def clear_cache(self):
        """
        清除数据缓存
        
        清除内存中的数据缓存，释放内存空间。
        """
        # 调用C++库清除缓存
        self.api.clear_cache()

    def get_bars(self, stdCode:str, period:str, fromTime:int = None, dataCount:int = None, endTime:int = 0) -> WtNpKline:
        """
        获取K线数据
        
        支持两种查询方式：
        1. 按时间范围查询：指定fromTime和endTime
        2. 按数据条数查询：指定dataCount和endTime
        
        @param stdCode: 标准合约代码
        @param period: 基础K线周期，如m1（1分钟）、m5（5分钟）、d（日线）
        @param fromTime: 开始时间，日线数据格式yyyymmdd，分钟线数据格式yyyymmddHHMM，默认为None
        @param dataCount: 数据条数，当fromTime为None时使用，默认为None
        @param endTime: 结束时间，日线数据格式yyyymmdd，分钟线数据格式yyyymmddHHMM，为0则读取到最后一条，默认为0
        @return WtNpKline: K线数据对象（NumPy数组封装），如果查询失败返回None
        """        
        # 创建K线数据缓存对象，用于接收C++库返回的数据
        bar_cache = WtBarCache()
        # 判断查询方式
        if fromTime is not None:
            # 按时间范围查询：调用C++库的get_bars_by_range函数
            ret = self.api.get_bars_by_range(bytes(stdCode, encoding="utf8"), bytes(period,'utf8'), fromTime, endTime, CB_GET_BAR(bar_cache.on_read_bar), CB_DATA_COUNT(bar_cache.on_data_count))
        else:
            # 按数据条数查询：调用C++库的get_bars_by_count函数
            ret = self.api.get_bars_by_count(bytes(stdCode, encoding="utf8"), bytes(period,'utf8'), dataCount, endTime, CB_GET_BAR(bar_cache.on_read_bar), CB_DATA_COUNT(bar_cache.on_data_count))

        # 判断查询是否成功（返回0表示失败）
        if ret == 0:
            return None
        else:
            # 返回缓存中的数据记录
            return bar_cache.records

    def get_ticks(self, stdCode:str, fromTime:int = None, dataCount:int = None, endTime:int = 0) -> WtNpTicks:
        """
        获取Tick数据
        
        支持两种查询方式：
        1. 按时间范围查询：指定fromTime和endTime
        2. 按数据条数查询：指定dataCount和endTime
        
        @param stdCode: 标准合约代码
        @param fromTime: 开始时间，格式为yyyymmddHHMM，默认为None
        @param dataCount: 数据条数，当fromTime为None时使用，默认为None
        @param endTime: 结束时间，格式为yyyymmddHHMM，为0则读取到最后一条，默认为0
        @return WtNpTicks: Tick数据对象（NumPy数组封装），如果查询失败返回None
        """        
        # 创建Tick数据缓存对象，用于接收C++库返回的数据
        tick_cache = WtTickCache()
        # 判断查询方式
        if fromTime is not None:
            # 按时间范围查询：调用C++库的get_ticks_by_range函数
            ret = self.api.get_ticks_by_range(bytes(stdCode, encoding="utf8"), fromTime, endTime, CB_GET_TICK(tick_cache.on_read_tick), CB_DATA_COUNT(tick_cache.on_data_count))
        else:
            # 按数据条数查询：调用C++库的get_ticks_by_count函数
            ret = self.api.get_ticks_by_count(bytes(stdCode, encoding="utf8"), dataCount, endTime, CB_GET_TICK(tick_cache.on_read_tick), CB_DATA_COUNT(tick_cache.on_data_count))

        # 判断查询是否成功（返回0表示失败）
        if ret == 0:
            return None
        else:
            # 返回缓存中的数据记录
            return tick_cache.records

    def get_ticks_by_date(self, stdCode:str, iDate:int) -> WtNpTicks:
        """
        按天读取Tick数据
        
        读取指定日期的所有Tick数据。
        
        @param stdCode: 标准合约代码
        @param iDate: 数据日期，格式为yyyymmdd
        @return WtNpTicks: Tick数据对象（NumPy数组封装），如果查询失败返回None
        """        
        # 创建Tick数据缓存对象，用于接收C++库返回的数据
        tick_cache = WtTickCache()
        # 调用C++库的get_ticks_by_date函数查询指定日期的Tick数据
        ret = self.api.get_ticks_by_date(bytes(stdCode, encoding="utf8"), iDate, CB_GET_TICK(tick_cache.on_read_tick), CB_DATA_COUNT(tick_cache.on_data_count))   

        # 判断查询是否成功（返回0表示失败）
        if ret == 0:
            return None
        else:
            # 返回缓存中的数据记录
            return tick_cache.records

    def get_sbars_by_date(self, stdCode:str, iSec:int, iDate:int) -> WtNpKline:
        """
        按天读取秒线数据
        
        读取指定日期的秒线K线数据。
        
        @param stdCode: 标准合约代码
        @param iSec: 周期，单位秒（s）
        @param iDate: 数据日期，格式为yyyymmdd
        @return WtNpKline: K线数据对象（NumPy数组封装），如果查询失败返回None
        """        
        # 创建K线数据缓存对象，用于接收C++库返回的数据
        bar_cache = WtBarCache()
        # 调用C++库的get_sbars_by_date函数查询指定日期的秒线数据
        ret = self.api.get_sbars_by_date(bytes(stdCode, encoding="utf8"), iSec, iDate, CB_GET_BAR(bar_cache.on_read_bar), CB_DATA_COUNT(bar_cache.on_data_count))

        # 判断查询是否成功（返回0表示失败）
        if ret == 0:
            return None
        else:
            # 返回缓存中的数据记录
            return bar_cache.records

    def get_bars_by_date(self, stdCode:str, period:str, iDate:int) -> WtNpKline:
        """
        按天读取分钟线数据
        
        读取指定日期的分钟线K线数据。注意：此方法仅支持分钟线（周期以'm'开头）。
        
        @param stdCode: 标准合约代码
        @param period: 周期，分钟线（如m1、m5等）
        @param iDate: 数据日期，格式为yyyymmdd
        @return WtNpKline: K线数据对象（NumPy数组封装），如果查询失败或周期不是分钟线返回None
        """
        # 检查周期是否为分钟线（分钟线周期以'm'开头）
        if period[0] != 'm':
            return None

        # 创建K线数据缓存对象，用于接收C++库返回的数据
        bar_cache = WtBarCache()
        # 调用C++库的get_bars_by_date函数查询指定日期的分钟线数据
        ret = self.api.get_bars_by_date(bytes(stdCode, encoding="utf8"), bytes(period, encoding="utf8"), iDate, CB_GET_BAR(bar_cache.on_read_bar), CB_DATA_COUNT(bar_cache.on_data_count))

        # 判断查询是否成功（返回0表示失败）
        if ret == 0:
            return None
        else:
            # 返回缓存中的数据记录
            return bar_cache.records
