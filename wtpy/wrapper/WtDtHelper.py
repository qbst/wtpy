"""
数据辅助工具模块

本模块提供WonderTrader数据辅助功能的Python接口封装。数据辅助工具用于处理各种数据格式转换、
数据存储和读取、数据重采样等功能，包括：
1. 数据格式转换：.dsb格式与.csv格式之间的转换
2. 数据存储：将K线、Tick、委托明细、委托队列、逐笔成交等数据存储到.dsb文件
3. 数据读取：从.dsb和.dmb文件读取各种数据
4. K线重采样：将低周期K线重采样为高周期K线

主要功能：
1. 导出.dsb格式数据为.csv格式
2. 将.csv格式数据转换为.dsb格式
3. 存储各种数据到.dsb文件
4. 从.dsb和.dmb文件读取数据
5. K线重采样

使用单例模式确保全局只有一个数据辅助工具实例。
"""

# 导入ctypes库，用于调用C++动态库
from ctypes import cdll, CFUNCTYPE, c_char_p, c_void_p, c_bool, POINTER, c_uint32, c_uint64
# 导入核心数据结构定义
from wtpy.WtCoreDefs import WTSTickStruct, WTSBarStruct, WTSOrdDtlStruct, WTSOrdQueStruct, WTSTransStruct
# 导入数据定义：数据缓存类和NumPy数组封装类
from wtpy.WtDataDefs import WtTickCache, WtNpOrdDetails, WtNpOrdQueues, WtNpTransactions, WtNpKline, WtNpTicks, WtBarCache
# 导入交易时段信息类，用于K线重采样
from wtpy.SessionMgr import SessionInfo
# 导入平台辅助工具，用于获取动态库路径
from wtpy.wrapper.PlatformHelper import PlatformHelper as ph
# 导入单例装饰器，确保全局唯一实例
from wtpy.WtUtilDefs import singleton
# 导入操作系统和日志模块
import os,logging

# 定义日志回调函数类型：日志消息（字符串）
CB_DTHELPER_LOG = CFUNCTYPE(c_void_p,  c_char_p)
# 定义Tick数据回调函数类型：Tick数据指针、数据条数、是否最后一批
CB_DTHELPER_TICK = CFUNCTYPE(c_void_p,  POINTER(WTSTickStruct), c_uint32, c_bool)
# 定义委托队列数据回调函数类型：委托队列数据指针、数据条数、是否最后一批（注意：注释中写的是ORDDtl，但实际是OrdQue）
CB_DTHELPER_ORDQUE = CFUNCTYPE(c_void_p,  POINTER(WTSOrdDtlStruct), c_uint32, c_bool)
# 定义委托明细数据回调函数类型：委托明细数据指针、数据条数、是否最后一批（注意：注释中写的是ORDQue，但实际是OrdDtl）
CB_DTHELPER_ORDDTL = CFUNCTYPE(c_void_p,  POINTER(WTSOrdQueStruct), c_uint32, c_bool)
# 定义逐笔成交数据回调函数类型：逐笔成交数据指针、数据条数、是否最后一批
CB_DTHELPER_TRANS = CFUNCTYPE(c_void_p,  POINTER(WTSTransStruct), c_uint32, c_bool)
# 定义K线数据回调函数类型：K线数据指针、数据条数、是否最后一批
CB_DTHELPER_BAR = CFUNCTYPE(c_void_p,  POINTER(WTSBarStruct), c_uint32, c_bool)

# 定义数据计数回调函数类型：数据总条数
CB_DTHELPER_COUNT = CFUNCTYPE(c_void_p,  c_uint32)

@singleton
class WtDataHelper:
    """
    WonderTrader数据辅助工具C接口底层对接模块
    
    提供数据格式转换、存储、读取和重采样等功能的Python封装。
    使用单例模式，确保全局只有一个实例。
    """

    # api可以作为公共变量，存储C++动态库的接口
    api = None
    # 版本信息
    ver = "Unknown"

    # 构造函数，初始化数据辅助工具
    def __init__(self):
        """
        初始化数据辅助工具包装器
        """
        # 获取当前文件所在目录
        paths = os.path.split(__file__)
        # 获取数据辅助工具动态库文件名（包含平台和架构信息）
        dllname = ph.getModule("WtDtHelper")
        # 拼接路径
        a = (paths[:-1] + (dllname,))
        # 生成完整的动态库路径
        _path = os.path.join(*a)
        # 加载C++动态库
        self.api = cdll.LoadLibrary(_path)
        
        # 创建日志回调函数
        self.cb_dthelper_log = CB_DTHELPER_LOG(self.on_log_output)
        # 设置resample_bars函数的参数类型：K线文件路径、K线回调、计数回调、开始时间、结束时间、周期、重采样倍数、交易时段信息、日志回调
        self.api.resample_bars.argtypes = [c_char_p, CB_DTHELPER_BAR, CB_DTHELPER_COUNT, c_uint64, c_uint64, c_char_p, c_uint32, c_char_p, CB_DTHELPER_LOG]

    def on_log_output(self, message:str):
        """
        日志输出回调函数
        
        当C++库产生日志时，会调用此函数。
        
        @param message: 日志消息（字节串）
        """
        # 将日志消息从字节串解码为UTF-8字符串
        message = bytes.decode(message, 'utf-8')
        # 使用logging模块记录日志信息
        logging.info(message)

    def dump_bars(self, binFolder:str, csvFolder:str, strFilter:str=""):
        """
        将目录下的.dsb格式的历史K线数据导出为.csv格式
        
        @param binFolder: .dsb文件存储目录
        @param csvFolder: .csv文件的输出目录
        @param strFilter: 代码过滤器（暂未启用），默认为空字符串
        """
        # 调用C++库导出K线数据，将.dsb格式转换为.csv格式
        self.api.dump_bars(bytes(binFolder, encoding="utf8"), bytes(csvFolder, encoding="utf8"), bytes(strFilter, encoding="utf8"), self.cb_dthelper_log)

    def dump_ticks(self, binFolder: str, csvFolder: str, strFilter: str=""):
        """
        将目录下的.dsb格式的历史Tick数据导出为.csv格式
        
        @param binFolder: .dsb文件存储目录
        @param csvFolder: .csv文件的输出目录
        @param strFilter: 代码过滤器（暂未启用），默认为空字符串
        """
        # 调用C++库导出Tick数据，将.dsb格式转换为.csv格式
        self.api.dump_ticks(bytes(binFolder, encoding="utf8"), bytes(csvFolder, encoding="utf8"), bytes(strFilter, encoding="utf8"), self.cb_dthelper_log)

    def trans_csv_bars(self, csvFolder: str, binFolder: str, period: str):
        """
        将目录下的.csv格式的历史K线数据转成.dsb格式
        
        @param csvFolder: .csv文件的输入目录
        @param binFolder: .dsb文件存储目录
        @param period: K线周期，m1-1分钟线，m5-5分钟线，d-日线
        """
        # 调用C++库转换K线数据，将.csv格式转换为.dsb格式
        self.api.trans_csv_bars(bytes(csvFolder, encoding="utf8"), bytes(binFolder, encoding="utf8"), bytes(period, encoding="utf8"), self.cb_dthelper_log)
    
    def trans_bars(self, barFile:str, getter, count:int, period:str) -> bool:
        """
        将K线转储到dsb文件中（已废弃）
        
        此方法已被移除，请使用store_bars方法代替。
        
        @param barFile: 要存储的文件路径
        @param getter: 获取bar的回调函数
        @param count: 一共要写入的数据条数
        @param period: 周期，m1/m5/d
        @return bool: 是否存储成功
        @raise Exception: 总是抛出异常，提示使用store_bars方法
        """
        # 抛出异常，提示使用新方法
        raise Exception("Method trans_bars is removed from core, use store_bars instead")
        # 以下代码已被注释，保留用于参考
        # cb = CB_DTHELPER_BAR_GETTER(getter)
        # return self.api.trans_bars(bytes(barFile, encoding="utf8"), cb, count, bytes(period, encoding="utf8"), self.cb_dthelper_log)

    def trans_ticks(self, tickFile:str, getter, count:int) -> bool:
        """
        将Tick数据转储到dsb文件中（已废弃）
        
        此方法已被移除，请使用store_ticks方法代替。
        
        @param tickFile: 要存储的文件路径
        @param getter: 获取tick的回调函数
        @param count: 一共要写入的数据条数
        @return bool: 是否存储成功
        @raise Exception: 总是抛出异常，提示使用store_ticks方法
        """
        # 抛出异常，提示使用新方法
        raise Exception("Method trans_ticks is removed from core, use store_ticks instead")
        # 以下代码已被注释，保留用于参考
        # cb = CB_DTHELPER_TICK_GETTER(getter)
        # return self.api.trans_ticks(bytes(tickFile, encoding="utf8"), cb, count, self.cb_dthelper_log)

    def store_bars(self, barFile:str, firstBar:POINTER(WTSBarStruct), count:int, period:str) -> bool:
        """
        将K线转储到dsb文件中
        
        @param barFile: 要存储的文件路径
        @param firstBar: 第一条bar的指针（指向K线数据数组）
        @param count: 一共要写入的数据条数
        @param period: 周期，m1/m5/d
        @return bool: 是否存储成功
        """
        # 调用C++库存储K线数据到.dsb文件
        return self.api.store_bars(bytes(barFile, encoding="utf8"), firstBar, count, bytes(period, encoding="utf8"), self.cb_dthelper_log)

    def store_ticks(self, tickFile:str, firstTick:POINTER(WTSTickStruct), count:int) -> bool:
        """
        将Tick数据转储到dsb文件中
        
        @param tickFile: 要存储的文件路径
        @param firstTick: 第一条tick的指针（指向Tick数据数组）
        @param count: 一共要写入的数据条数
        @return bool: 是否存储成功
        """
        # 调用C++库存储Tick数据到.dsb文件
        # 注意：注释中的getter参数已不再使用
        return self.api.store_ticks(bytes(tickFile, encoding="utf8"), firstTick, count, self.cb_dthelper_log)
    
    def store_order_details(self, targetFile:str, firstItem:POINTER(WTSOrdDtlStruct), count:int) -> bool:
        """
        将委托明细数据转储到dsb文件中
        
        @param targetFile: 要存储的文件路径
        @param firstItem: 第一条数据的指针（指向委托明细数据数组）
        @param count: 一共要写入的数据条数
        @return bool: 是否存储成功
        """
        # 调用C++库存储委托明细数据到.dsb文件
        return self.api.store_order_details(bytes(targetFile, encoding="utf8"), firstItem, count, self.cb_dthelper_log)
    
    def store_order_queues(self, targetFile:str, firstItem:POINTER(WTSOrdQueStruct), count:int) -> bool:
        """
        将委托队列数据转储到dsb文件中
        
        @param targetFile: 要存储的文件路径
        @param firstItem: 第一条数据的指针（指向委托队列数据数组）
        @param count: 一共要写入的数据条数
        @return bool: 是否存储成功
        """
        # 调用C++库存储委托队列数据到.dsb文件
        return self.api.store_order_queues(bytes(targetFile, encoding="utf8"), firstItem, count, self.cb_dthelper_log)
    
    def store_transactions(self, targetFile:str, firstItem:POINTER(WTSTransStruct), count:int) -> bool:
        """
        将逐笔成交数据转储到dsb文件中
        
        @param targetFile: 要存储的文件路径
        @param firstItem: 第一条数据的指针（指向逐笔成交数据数组）
        @param count: 一共要写入的数据条数
        @return bool: 是否存储成功
        """
        # 调用C++库存储逐笔成交数据到.dsb文件
        return self.api.store_transactions(bytes(targetFile, encoding="utf8"), firstItem, count, self.cb_dthelper_log)
    
    def read_dsb_bars(self, barFile: str) -> WtNpKline:
        """
        读取.dsb格式的K线数据
        
        @param barFile: .dsb的K线数据文件路径
        @return WtNpKline: K线数据对象（NumPy数组封装），可以通过WtNpKline.ndarray获取numpy的ndarray对象，如果读取失败返回None
        """        
        # 创建K线数据缓存对象，forceCopy=True表示强制复制数据（避免内存问题）
        bar_cache = WtBarCache(forceCopy=True)
        # 调用C++库读取.dsb格式的K线数据，返回0表示失败
        if 0 == self.api.read_dsb_bars(bytes(barFile, encoding="utf8"), CB_DTHELPER_BAR(bar_cache.on_read_bar), CB_DTHELPER_COUNT(bar_cache.on_data_count), self.cb_dthelper_log):
            return None
        else:
            # 返回缓存中的数据记录
            return bar_cache.records

    def read_dmb_ticks(self, tickFile: str) -> WtNpTicks:
        """
        读取.dmb格式的Tick数据
        
        @param tickFile: .dmb的Tick数据文件路径
        @return WtNpTicks: Tick数据对象（NumPy数组封装），如果读取失败返回None
        """        
        # 创建Tick数据缓存对象，forceCopy=True表示强制复制数据
        tick_cache = WtTickCache(forceCopy=True)
        # 调用C++库读取.dmb格式的Tick数据，返回0表示失败
        if 0 == self.api.read_dmb_ticks(bytes(tickFile, encoding="utf8"), CB_DTHELPER_TICK(tick_cache.on_read_tick), CB_DTHELPER_COUNT(tick_cache.on_data_count), self.cb_dthelper_log):
            return None
        else:
            # 返回缓存中的数据记录
            return tick_cache.records

    def read_dmb_bars(self, barFile: str) -> WtNpKline:
        """
        读取.dmb格式的K线数据
        
        @param barFile: .dmb的K线数据文件路径
        @return WtNpKline: K线数据对象（NumPy数组封装），如果读取失败返回None
        """        
        # 创建K线数据缓存对象，forceCopy=True表示强制复制数据
        bar_cache = WtBarCache(forceCopy=True)
        # 调用C++库读取.dmb格式的K线数据，返回0表示失败
        if 0 == self.api.read_dmb_bars(bytes(barFile, encoding="utf8"), CB_DTHELPER_BAR(bar_cache.on_read_bar), CB_DTHELPER_COUNT(bar_cache.on_data_count), self.cb_dthelper_log):
            return None
        else:
            # 返回缓存中的数据记录
            return bar_cache.records

    def read_dsb_ticks(self, tickFile: str) -> WtNpTicks:
        """
        读取.dsb格式的Tick数据
        
        @param tickFile: .dsb的Tick数据文件路径
        @return WtNpTicks: Tick数据对象（NumPy数组封装），可以通过WtNpTicks.ndarray获取numpy的ndarray对象，如果读取失败返回None
        """         
        # 创建Tick数据缓存对象，forceCopy=True表示强制复制数据
        tick_cache = WtTickCache(forceCopy=True)
        # 调用C++库读取.dsb格式的Tick数据，返回0表示失败
        if 0 == self.api.read_dsb_ticks(bytes(tickFile, encoding="utf8"), CB_DTHELPER_TICK(tick_cache.on_read_tick), CB_DTHELPER_COUNT(tick_cache.on_data_count), self.cb_dthelper_log):
            return None
        else:
            # 返回缓存中的数据记录
            return tick_cache.records

    def read_dsb_order_details(self, dataFile: str) -> WtNpOrdDetails:
        """
        读取.dsb格式的委托明细数据
        
        @param dataFile: .dsb的数据文件路径
        @return WtNpOrdDetails: 委托明细数据对象（NumPy数组封装），如果读取失败返回None
        """
        # 定义内部数据缓存类，用于接收C++库返回的数据
        class DataCache:
            def __init__(self):
                # 初始化数据记录为None
                self.records:WtNpOrdDetails = None

            def on_read_data(self, firstItem:POINTER(WTSOrdDtlStruct), count:int, isLast:bool):
                """
                数据读取回调函数
                
                @param firstItem: 第一条数据的指针
                @param count: 数据条数
                @param isLast: 是否最后一批
                """
                # 创建委托明细数据对象，forceCopy=True表示强制复制数据
                self.records = WtNpOrdDetails(forceCopy=True)
                # 设置数据内容
                self.records.set_data(firstItem, count)

            def on_data_count(self, count:int):
                """
                数据计数回调函数
                
                @param count: 数据总条数
                """
                pass
        
        # 创建数据缓存对象
        data_cache = DataCache()
        # 调用C++库读取.dsb格式的委托明细数据，返回0表示失败
        if 0 == self.api.read_dsb_order_details(bytes(dataFile, encoding="utf8"), CB_DTHELPER_ORDDTL(data_cache.on_read_data), CB_DTHELPER_COUNT(data_cache.on_data_count), self.cb_dthelper_log):
            return None
        else:
            # 返回缓存中的数据记录
            return data_cache.records
        
    def read_dsb_order_queues(self, dataFile: str) -> WtNpOrdQueues:
        """
        读取.dsb格式的委托队列数据
        
        @param dataFile: .dsb的数据文件路径
        @return WtNpOrdQueues: 委托队列数据对象（NumPy数组封装），如果读取失败返回None
        """
        # 定义内部数据缓存类，用于接收C++库返回的数据
        class DataCache:
            def __init__(self):
                # 初始化数据记录为None
                self.records:WtNpOrdQueues = None

            def on_read_data(self, firstItem:POINTER(WTSOrdQueStruct), count:int, isLast:bool):
                """
                数据读取回调函数
                
                @param firstItem: 第一条数据的指针
                @param count: 数据条数
                @param isLast: 是否最后一批
                """
                # 创建委托队列数据对象，forceCopy=True表示强制复制数据
                self.records = WtNpOrdQueues(forceCopy=True)
                # 设置数据内容
                self.records.set_data(firstItem, count)

            def on_data_count(self, count:int):
                """
                数据计数回调函数
                
                @param count: 数据总条数
                """
                pass
        
        # 创建数据缓存对象
        data_cache = DataCache()
        # 调用C++库读取.dsb格式的委托队列数据，返回0表示失败
        if 0 == self.api.read_dsb_order_queues(bytes(dataFile, encoding="utf8"), CB_DTHELPER_ORDQUE(data_cache.on_read_data), CB_DTHELPER_COUNT(data_cache.on_data_count), self.cb_dthelper_log):
            return None
        else:
            # 返回缓存中的数据记录
            return data_cache.records
        
    def read_dsb_transactions(self, dataFile: str) -> WtNpTransactions:
        """
        读取.dsb格式的逐笔成交数据
        
        @param dataFile: .dsb的数据文件路径
        @return WtNpTransactions: 逐笔成交数据对象（NumPy数组封装），如果读取失败返回None
        """
        # 定义内部数据缓存类，用于接收C++库返回的数据
        class DataCache:
            def __init__(self):
                # 初始化数据记录为None
                self.records:WtNpTransactions = None

            def on_read_data(self, firstItem:POINTER(WTSTransStruct), count:int, isLast:bool):
                """
                数据读取回调函数
                
                @param firstItem: 第一条数据的指针
                @param count: 数据条数
                @param isLast: 是否最后一批
                """
                # 创建逐笔成交数据对象，forceCopy=True表示强制复制数据
                self.records = WtNpTransactions(forceCopy=True)
                # 设置数据内容
                self.records.set_data(firstItem, count)

            def on_data_count(self, count:int):
                """
                数据计数回调函数
                
                @param count: 数据总条数
                """
                pass
        
        # 创建数据缓存对象
        data_cache = DataCache()
        # 调用C++库读取.dsb格式的逐笔成交数据，返回0表示失败
        if 0 == self.api.read_dsb_transactions(bytes(dataFile, encoding="utf8"), CB_DTHELPER_TRANS(data_cache.on_read_data), CB_DTHELPER_COUNT(data_cache.on_data_count), self.cb_dthelper_log):
            return None
        else:
            # 返回缓存中的数据记录
            return data_cache.records
    
    def resample_bars(self, barFile:str, period:str, times:int, fromTime:int, endTime:int, sessInfo:SessionInfo, alignSection:bool = False) -> WtNpKline:
        """
        重采样K线
        
        将低周期K线重采样为高周期K线。例如：将1分钟K线重采样为3分钟K线时，times=3。
        
        @param barFile: dsb格式的K线数据文件路径
        @param period: 基础K线周期，m1/m5/d
        @param times: 重采样倍数，如利用m1生成m3数据时，times为3
        @param fromTime: 开始时间，日线数据格式yyyymmdd，分钟线数据格式yyyymmddHHMMSS
        @param endTime: 结束时间，日线数据格式yyyymmdd，分钟线数据格式yyyymmddHHMMSS
        @param sessInfo: 交易时间模板，用于确定交易时段
        @param alignSection: 是否对齐交易时段，默认为False
        @return WtNpKline: 重采样后的K线数据对象（NumPy数组封装），如果重采样失败返回None
        """        
        # 创建K线数据缓存对象，forceCopy=True表示强制复制数据
        bar_cache = WtBarCache(forceCopy=True)
        # 调用C++库进行K线重采样，返回0表示失败
        if 0 == self.api.resample_bars(bytes(barFile, encoding="utf8"), CB_DTHELPER_BAR(bar_cache.on_read_bar), CB_DTHELPER_COUNT(bar_cache.on_data_count), 
                fromTime, endTime, bytes(period,'utf8'), times, bytes(sessInfo.toString(),'utf8'), self.cb_dthelper_log, alignSection):
            return None
        else:
            # 返回缓存中的数据记录
            return bar_cache.records
