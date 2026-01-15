"""
核心定义模块

本模块定义了与C++底层交互所需的核心数据结构、回调函数类型和常量。
这些定义是Python层与C++底层通信的桥梁，包括：
1. C结构体定义：Tick、K线、逐笔成交、逐笔委托、委托队列等数据结构
2. 回调函数类型定义：策略回调、引擎回调、HFT策略回调等
3. 事件常量定义：引擎事件、通道事件、日志级别等
4. 枚举类型定义：引擎类型枚举

这些结构体和回调函数类型必须与C++底层的定义完全一致，以确保数据传递的正确性。
"""

# 导入ctypes模块，用于定义C数据类型和结构体
from ctypes import c_void_p, CFUNCTYPE, POINTER, c_char_p, c_bool, c_ulong, c_double
# 导入ctypes的结构体和基本数据类型
from ctypes import Structure, c_char, c_int32, c_uint32,c_uint64,c_int64
# 导入copy模块，用于对象拷贝
from copy import copy
# 导入numpy模块，用于数值计算
import numpy as np

# 定义合约代码最大长度类型，32个字符
MAX_INSTRUMENT_LENGTH = c_char*32
# 定义交易所代码最大长度类型，16个字符
MAX_EXCHANGE_LENGTH = c_char*16
# 定义价格队列类型，10个double类型元素的数组
PriceQueueType = c_double*10
# 定义数量队列类型，10个double类型元素的数组
VolumeQueueType = c_double*10

class WTSStruct(Structure):
    """
    C结构体基类
    
    所有C结构体的基类，提供了通用的字段访问和转换方法。
    继承自ctypes的Structure类，用于定义与C++底层交互的数据结构。
    """
    
    @property
    def fields(self) -> list:
        """
        获取结构体字段列表属性
        
        返回结构体的字段定义列表，每个元素为(字段名, 字段类型)的元组。
        
        @return: 字段列表，包含所有字段的定义信息
        """
        return self._fields_

    @property
    def values(self) -> tuple:
        """
        获取结构体所有字段的值属性
        
        返回结构体所有字段的值组成的元组，按字段定义的顺序。
        
        @return: 字段值元组，包含所有字段的值
        """
        return tuple(getattr(self, i[0]) for i in self._fields_)

    @property
    def to_dict(self) -> dict:
        """
        将结构体转换为字典属性
        
        将结构体的所有字段转换为字典格式，键为字段名，值为字段值。
        
        @return: 字典对象，包含所有字段的键值对
        """
        return {i[0]:getattr(self, i[0]) for i in self._fields_}

class WTSTickStruct(WTSStruct):
    """
    Tick数据结构类
    
    C接口传递的Tick数据结构，用于存储单笔行情数据。
    包含价格、成交量、买卖盘（10档）等完整的Tick信息。
    继承自WTSStruct基类。
    """
    
    # 定义结构体字段列表，每个元素为(字段名, 字段类型)的元组
    _fields_ = [("exchg", MAX_EXCHANGE_LENGTH),  # 交易所代码，最大16个字符
                ("code", MAX_INSTRUMENT_LENGTH),  # 合约代码，最大32个字符
                ("price", c_double),              # 最新价
                ("open", c_double),               # 开盘价
                ("high", c_double),               # 最高价
                ("low", c_double),                # 最低价
                ("settle_price", c_double),       # 结算价

                ("upper_limit", c_double),        # 涨停价
                ("lower_limit", c_double),        # 跌停价

                ("total_volume", c_double),       # 总成交量
                ("volume", c_double),             # 本笔成交量
                ("total_turnover", c_double),     # 总成交额
                ("turn_over", c_double),          # 本笔成交额
                ("open_interest", c_double),      # 持仓量
                ("diff_interest", c_double),      # 持仓变化量

                ("trading_date", c_uint32),       # 交易日，格式yyyymmdd
                ("action_date", c_uint32),        # 动作日期，格式yyyymmdd
                ("action_time", c_uint32),        # 动作时间，格式HHMMSSmmm
                ("reserve", c_uint32),            # 保留字段

                ("pre_close", c_double),         # 昨收盘价
                ("pre_settle", c_double),         # 昨结算价
                ("pre_interest", c_double),      # 昨持仓量

                ("bid_price_0", c_double),        # 买一价
                ("bid_price_1", c_double),        # 买二价
                ("bid_price_2", c_double),        # 买三价
                ("bid_price_3", c_double),        # 买四价
                ("bid_price_4", c_double),        # 买五价
                ("bid_price_5", c_double),        # 买六价
                ("bid_price_6", c_double),        # 买七价
                ("bid_price_7", c_double),        # 买八价
                ("bid_price_8", c_double),        # 买九价
                ("bid_price_9", c_double),        # 买十价
                
                ("ask_price_0", c_double),        # 卖一价
                ("ask_price_1", c_double),        # 卖二价
                ("ask_price_2", c_double),        # 卖三价
                ("ask_price_3", c_double),        # 卖四价
                ("ask_price_4", c_double),        # 卖五价
                ("ask_price_5", c_double),        # 卖六价
                ("ask_price_6", c_double),        # 卖七价
                ("ask_price_7", c_double),        # 卖八价
                ("ask_price_8", c_double),        # 卖九价
                ("ask_price_9", c_double),        # 卖十价
                
                ("bid_qty_0", c_double),          # 买一量
                ("bid_qty_1", c_double),          # 买二量
                ("bid_qty_2", c_double),          # 买三量
                ("bid_qty_3", c_double),          # 买四量
                ("bid_qty_4", c_double),          # 买五量
                ("bid_qty_5", c_double),          # 买六量
                ("bid_qty_6", c_double),          # 买七量
                ("bid_qty_7", c_double),          # 买八量
                ("bid_qty_8", c_double),          # 买九量
                ("bid_qty_9", c_double),          # 买十量
                
                ("ask_qty_0", c_double),          # 卖一量
                ("ask_qty_1", c_double),          # 卖二量
                ("ask_qty_2", c_double),          # 卖三量
                ("ask_qty_3", c_double),          # 卖四量
                ("ask_qty_4", c_double),          # 卖五量
                ("ask_qty_5", c_double),          # 卖六量
                ("ask_qty_6", c_double),          # 卖七量
                ("ask_qty_7", c_double),          # 卖八量
                ("ask_qty_8", c_double),          # 卖九量
                ("ask_qty_9", c_double)]          # 卖十量
    
    # 结构体对齐方式，8字节对齐
    _pack_ = 8

    @property
    def fields(self) -> list:
        """
        获取结构体字段列表属性（重写基类方法）
        
        返回结构体的字段定义列表，将字符串字段转换为NumPy字符串类型。
        
        @return: 字段列表，包含所有字段的定义信息，字符串字段转换为'S10'类型
        """
        # 复制字段列表
        fields = self._fields_.copy()
        # 将交易所代码字段转换为NumPy字符串类型
        fields[0] = ('exchg', 'S10')
        # 将合约代码字段转换为NumPy字符串类型
        fields[1] = ('code', 'S10')
        # 返回修改后的字段列表
        return fields

    @property
    def bid_prices(self) -> tuple:
        """
        获取买盘价格元组属性
        
        返回所有买盘价格（10档）组成的元组。
        
        @return: 买盘价格元组，包含bid_price_0到bid_price_9
        """
        return (self.bid_price_0,   # 买一价
                self.bid_price_1,   # 买二价
                self.bid_price_2,   # 买三价
                self.bid_price_3,   # 买四价
                self.bid_price_4,   # 买五价
                self.bid_price_5,   # 买六价
                self.bid_price_6,   # 买七价
                self.bid_price_7,   # 买八价
                self.bid_price_8,   # 买九价
                self.bid_price_9)   # 买十价

    @property
    def bid_qty(self) -> tuple:
        """
        获取买盘数量元组属性
        
        返回所有买盘数量（10档）组成的元组。
        
        @return: 买盘数量元组，包含bid_qty_0到bid_qty_9
        """
        return (self.bid_qty_0,     # 买一量
                self.bid_qty_1,     # 买二量
                self.bid_qty_2,     # 买三量
                self.bid_qty_3,     # 买四量
                self.bid_qty_4,     # 买五量
                self.bid_qty_5,     # 买六量
                self.bid_qty_6,     # 买七量
                self.bid_qty_7,     # 买八量
                self.bid_qty_8,     # 买九量
                self.bid_qty_9)     # 买十量
    
    @property
    def ask_prices(self) -> tuple:
        """
        获取卖盘价格元组属性
        
        返回所有卖盘价格（10档）组成的元组。
        
        @return: 卖盘价格元组，包含ask_price_0到ask_price_9
        """
        return (self.ask_price_0,   # 卖一价
                self.ask_price_1,   # 卖二价
                self.ask_price_2,   # 卖三价
                self.ask_price_3,   # 卖四价
                self.ask_price_4,   # 卖五价
                self.ask_price_5,   # 卖六价
                self.ask_price_6,   # 卖七价
                self.ask_price_7,   # 卖八价
                self.ask_price_8,   # 卖九价
                self.ask_price_9)   # 卖十价

    @property
    def ask_qty(self) -> tuple:
        """
        获取卖盘数量元组属性
        
        返回所有卖盘数量（10档）组成的元组。
        
        @return: 卖盘数量元组，包含ask_qty_0到ask_qty_9
        """
        return (self.ask_qty_0,     # 卖一量
                self.ask_qty_1,     # 卖二量
                self.ask_qty_2,     # 卖三量
                self.ask_qty_3,     # 卖四量
                self.ask_qty_4,     # 卖五量
                self.ask_qty_5,     # 卖六量
                self.ask_qty_6,     # 卖七量
                self.ask_qty_7,     # 卖八量
                self.ask_qty_8,     # 卖九量
                self.ask_qty_9)     # 卖十量

    def to_tuple(self) -> tuple:
        """
        将结构体转换为元组
        
        将Tick结构体的所有字段转换为元组格式，时间字段会转换为时间戳。
        
        @return: 元组对象，包含所有字段的值，第一个元素为时间戳（纳秒级）
        """
        return (
                # 计算时间戳：日期（yyyymmdd）* 1000000000 + 时间（HHMMSSmmm）
                np.uint64(self.action_date)*1000000000+self.action_time,
                self.exchg,         # 交易所代码
                self.code,          # 合约代码
                self.price,         # 最新价
                self.open,          # 开盘价
                self.high,          # 最高价
                self.low,           # 最低价
                self.settle_price,  # 结算价
                self.upper_limit,   # 涨停价
                self.lower_limit,   # 跌停价
                self.total_volume,  # 总成交量
                self.volume,        # 本笔成交量
                self.total_turnover,# 总成交额
                self.turn_over,     # 本笔成交额
                self.open_interest, # 持仓量
                self.diff_interest, # 持仓变化量
                self.trading_date,  # 交易日
                self.action_date,   # 动作日期
                self.action_time,   # 动作时间
                self.pre_close,     # 昨收盘价
                self.pre_settle,    # 昨结算价
                self.pre_interest, # 昨持仓量
                
                # 买盘价格（10档）
                self.bid_price_0,
                self.bid_price_1,
                self.bid_price_2,
                self.bid_price_3,
                self.bid_price_4,
                self.bid_price_5,
                self.bid_price_6,
                self.bid_price_7,
                self.bid_price_8,
                self.bid_price_9,
                
                # 卖盘价格（10档）
                self.ask_price_0,
                self.ask_price_1,
                self.ask_price_2,
                self.ask_price_3,
                self.ask_price_4,
                self.ask_price_5,
                self.ask_price_6,
                self.ask_price_7,
                self.ask_price_8,
                self.ask_price_9,
                
                # 买盘数量（10档）
                self.bid_qty_0,
                self.bid_qty_1,
                self.bid_qty_2,
                self.bid_qty_3,
                self.bid_qty_4,
                self.bid_qty_5,
                self.bid_qty_6,
                self.bid_qty_7,
                self.bid_qty_8,
                self.bid_qty_9,
                
                # 卖盘数量（10档）
                self.ask_qty_0,
                self.ask_qty_1,
                self.ask_qty_2,
                self.ask_qty_3,
                self.ask_qty_4,
                self.ask_qty_5,
                self.ask_qty_6,
                self.ask_qty_7,
                self.ask_qty_8,
                self.ask_qty_9
            )

class WTSBarStruct(WTSStruct):
    """
    K线数据结构类
    
    C接口传递的K线数据结构，用于存储单根K线数据。
    包含开高低收、成交量、成交额、持仓量等信息。
    继承自WTSStruct基类。
    """
    
    # 定义结构体字段列表，每个元素为(字段名, 字段类型)的元组
    _fields_ = [("date", c_uint32),      # 日期，格式yyyymmdd（日线使用）
                ("reserve", c_uint32),    # 保留字段
                ("time", c_uint64),       # 时间，格式HHMMSSmmm（分钟线使用）
                ("open", c_double),       # 开盘价
                ("high", c_double),       # 最高价
                ("low", c_double),        # 最低价
                ("close", c_double),      # 收盘价
                ("settle", c_double),     # 结算价
                ("money", c_double),      # 成交额
                ("vol", c_double),        # 成交量
                ("hold", c_double),       # 持仓量
                ("diff", c_double)]       # 持仓变化量
    
    # 结构体对齐方式，8字节对齐
    _pack_ = 8

    def to_tuple(self, flag:int=0) -> tuple:
        """
        将K线结构体转换为元组
        
        将K线结构体的所有字段转换为元组格式，根据flag参数决定时间字段的格式。
        
        @flag: 转换标记，0-分钟线（时间格式为yyyymmddHHMM），1-日线（时间格式为yyyymmdd），2-秒线（时间格式为HHMMSSmmm），默认为0
        @return: 元组对象，包含所有字段的值
        """
        # 根据flag参数计算时间字段
        if flag == 0:
            # 分钟线：时间字段加上基准时间戳199000000000（1990-01-01 00:00:00）
            time = self.time + 199000000000
        elif flag == 1:
            # 日线：直接使用日期字段
            time = self.date
        elif flag == 2:
            # 秒线：直接使用时间字段
            time = self.time
        
        # 返回包含所有字段的元组
        return (
                self.date,     # 日期
                time,          # 时间（根据flag转换）
                self.open,     # 开盘价
                self.high,     # 最高价
                self.low,      # 最低价
                self.close,    # 收盘价
                self.settle,   # 结算价
                self.money,    # 成交额
                self.vol,      # 成交量
                self.hold,     # 持仓量
                self.diff)     # 持仓变化量

class WTSTransStruct(WTSStruct):
    """
    逐笔成交数据结构类
    
    C接口传递的逐笔成交数据结构，用于存储单笔成交数据。
    包含成交价格、数量、方向、买卖订单号等信息。
    继承自WTSStruct基类。
    """
    
    # 定义结构体字段列表，每个元素为(字段名, 字段类型)的元组
    _fields_ = [("exchg", MAX_EXCHANGE_LENGTH),  # 交易所代码，最大16个字符
                ("code", MAX_INSTRUMENT_LENGTH),  # 合约代码，最大32个字符

                ("trading_date", c_uint32),       # 交易日，格式yyyymmdd
                ("action_date", c_uint32),        # 动作日期，格式yyyymmdd
                ("action_time", c_uint32),        # 动作时间，格式HHMMSSmmm

                ("index", c_int64),               # 成交索引，唯一标识一笔成交
                ("ttype", c_int32),               # 成交类型
                ("side", c_int32),                # 成交方向，0-买入，1-卖出

                ("price", c_double),              # 成交价格
                ("volume", c_uint32),             # 成交数量
                ("askorder", c_int64),            # 卖单订单号
                ("bidorder", c_int64)]            # 买单订单号
    
    # 结构体对齐方式，8字节对齐
    _pack_ = 8

    def to_tuple(self) -> tuple:
        """
        将逐笔成交结构体转换为元组
        
        将逐笔成交结构体的所有字段转换为元组格式，时间字段会转换为时间戳。
        
        @return: 元组对象，包含所有字段的值，第一个元素为时间戳（纳秒级）
        """
        return (
                # 计算时间戳：日期（yyyymmdd）* 1000000000 + 时间（HHMMSSmmm）
                np.uint64(self.action_date)*1000000000+self.action_time,
                self.exchg,         # 交易所代码
                self.code,          # 合约代码
                self.trading_date,  # 交易日
                self.action_date,   # 动作日期
                self.action_time,   # 动作时间
                self.index,         # 成交索引
                self.ttype,         # 成交类型
                self.side,          # 成交方向
                self.price,         # 成交价格
                self.volume,        # 成交数量
                self.askorder,      # 卖单订单号
                self.bidorder       # 买单订单号
            )

class WTSOrdQueStruct(WTSStruct):
    """
    委托队列数据结构类
    
    C接口传递的委托队列数据结构，用于存储某个价格档位的委托队列信息。
    包含价格、方向、委托笔数、队列大小、各档位委托量等信息。
    继承自WTSStruct基类。
    """
    
    # 定义结构体字段列表，每个元素为(字段名, 字段类型)的元组
    _fields_ = [("exchg", MAX_EXCHANGE_LENGTH),  # 交易所代码，最大16个字符
                ("code", MAX_INSTRUMENT_LENGTH),  # 合约代码，最大32个字符

                ("trading_date", c_uint32),       # 交易日，格式yyyymmdd
                ("action_date", c_uint32),        # 动作日期，格式yyyymmdd
                ("action_time", c_uint32),        # 动作时间，格式HHMMSSmmm

                ("side", c_int32),                # 方向，0-买，1-卖
                ("price", c_double),              # 价格档位
                ("order_items", c_uint32),        # 委托笔数
                ("qsize", c_uint32),              # 队列大小
                ("volumes", c_uint32*50)]         # 各档位委托量数组，最多50档
    
    # 结构体对齐方式，8字节对齐
    _pack_ = 8

    def to_tuple(self) -> tuple:
        """
        将委托队列结构体转换为元组
        
        将委托队列结构体的所有字段转换为元组格式，时间字段会转换为时间戳。
        注意：此方法中bidorder字段引用错误，应该使用volumes字段。
        
        @return: 元组对象，包含所有字段的值，第一个元素为时间戳（纳秒级）
        """
        return (
                # 计算时间戳：日期（yyyymmdd）* 1000000000 + 时间（HHMMSSmmm）
                np.uint64(self.action_date)*1000000000+self.action_time,
                self.exchg,         # 交易所代码
                self.code,          # 合约代码
                self.trading_date,  # 交易日
                self.action_date,   # 动作日期
                self.action_time,   # 动作时间
                self.side,          # 方向
                self.price,         # 价格档位
                self.order_items,   # 委托笔数
                self.qsize          # 队列大小
            ) + tuple(self.bidorder)  # 注意：这里应该是self.volumes，但代码中使用了self.bidorder

class WTSOrdDtlStruct(WTSStruct):
    """
    逐笔委托数据结构类
    
    C接口传递的逐笔委托数据结构，用于存储单笔委托数据。
    包含委托价格、数量、方向、委托类型等信息。
    继承自WTSStruct基类。
    """
    
    # 定义结构体字段列表，每个元素为(字段名, 字段类型)的元组
    _fields_ = [("exchg", MAX_EXCHANGE_LENGTH),  # 交易所代码，最大16个字符
                ("code", MAX_INSTRUMENT_LENGTH),  # 合约代码，最大32个字符

                ("trading_date", c_uint32),       # 交易日，格式yyyymmdd
                ("action_date", c_uint32),        # 动作日期，格式yyyymmdd
                ("action_time", c_uint32),        # 动作时间，格式HHMMSSmmm

                ("index", c_uint64),              # 委托索引，唯一标识一笔委托
                ("price", c_double),              # 委托价格
                ("volume", c_uint32),             # 委托数量
                ("side", c_uint32),               # 委托方向，0-买，1-卖
                ("otype", c_uint32)]              # 委托类型
    
    # 结构体对齐方式，8字节对齐
    _pack_ = 8

    def to_tuple(self) -> tuple:
        """
        将逐笔委托结构体转换为元组
        
        将逐笔委托结构体的所有字段转换为元组格式，时间字段会转换为时间戳。
        
        @return: 元组对象，包含所有字段的值，第一个元素为时间戳（纳秒级）
        """
        return (
                # 计算时间戳：日期（yyyymmdd）* 1000000000 + 时间（HHMMSSmmm）
                np.uint64(self.action_date)*1000000000+self.action_time,
                self.exchg,         # 交易所代码
                self.code,          # 合约代码
                self.trading_date,  # 交易日
                self.action_date,   # 动作日期
                self.action_time,   # 动作时间
                self.index,         # 委托索引
                self.side,          # 委托方向
                self.price,         # 委托价格
                self.volume,        # 委托数量
                self.otype          # 委托类型
            )

# 回调函数定义
# 策略初始化回调函数类型定义
# 参数：策略ID（c_ulong）
# 返回值：void指针
CB_STRATEGY_INIT = CFUNCTYPE(c_void_p, c_ulong)

# 策略Tick数据推送回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、Tick数据指针（POINTER(WTSTickStruct)）
# 返回值：void指针
CB_STRATEGY_TICK = CFUNCTYPE(c_void_p, c_ulong, c_char_p, POINTER(WTSTickStruct))

# 策略获取Tick数据的单条Tick同步回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、Tick数据指针（POINTER(WTSTickStruct)）、索引（c_uint32）、是否最后一条（c_bool）
# 返回值：void指针
CB_STRATEGY_GET_TICK = CFUNCTYPE(c_void_p, c_ulong, c_char_p, POINTER(WTSTickStruct), c_uint32, c_bool)

# 策略重算回调函数类型定义（CTA/SEL策略）
# 参数：策略ID（c_ulong）、时间戳1（c_ulong）、时间戳2（c_ulong）
# 返回值：void指针
CB_STRATEGY_CALC = CFUNCTYPE(c_void_p, c_ulong, c_ulong, c_ulong)

# 策略订阅的K线闭合事件回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、周期（c_char_p）、K线数据指针（POINTER(WTSBarStruct)）
# 返回值：void指针
CB_STRATEGY_BAR = CFUNCTYPE(c_void_p, c_ulong, c_char_p, c_char_p, POINTER(WTSBarStruct))

# 策略获取K线数据的单条K线同步回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、周期（c_char_p）、K线数据指针（POINTER(WTSBarStruct)）、索引（c_uint32）、是否最后一条（c_bool）
# 返回值：void指针
CB_STRATEGY_GET_BAR = CFUNCTYPE(c_void_p, c_ulong, c_char_p, c_char_p, POINTER(WTSBarStruct), c_uint32, c_bool)

# 策略获取全部持仓的同步回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、持仓数量（c_double）、是否冻结（c_bool）
# 返回值：void指针
CB_STRATEGY_GET_POSITION = CFUNCTYPE(c_void_p, c_ulong, c_char_p, c_double, c_bool)

# 交易日开始结束事件回调函数类型定义
# 参数：策略ID（c_ulong）、交易日（c_ulong）、是否开始（c_bool）
# 返回值：void指针
CB_SESSION_EVENT = CFUNCTYPE(c_void_p, c_ulong, c_ulong, c_bool)

# 条件单触发回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、目标仓位（c_double）、触发价格（c_double）、用户标记（c_char_p）
# 返回值：void指针
CB_STRATEGY_COND_TRIGGER = CFUNCTYPE(c_void_p, c_ulong, c_char_p, c_double, c_double, c_char_p)

# 引擎事件回调函数类型定义（交易日开启结束等）
# 参数：事件类型（c_ulong）、时间戳1（c_ulong）、时间戳2（c_ulong）
# 返回值：void指针
CB_ENGINE_EVENT = CFUNCTYPE(c_void_p, c_ulong, c_ulong, c_ulong)

# HFT策略交易通道事件回调函数类型定义
# 参数：策略ID（c_ulong）、通道名称（c_char_p）、事件类型（c_ulong）
# 返回值：void指针
CB_HFTSTRA_CHNL_EVT = CFUNCTYPE(c_void_p, c_ulong, c_char_p, c_ulong)

# HFT策略订单推送回报回调函数类型定义
# 参数：策略ID（c_ulong）、本地订单ID（c_ulong）、合约代码（c_char_p）、是否买入（c_bool）、总数量（c_double）、剩余数量（c_double）、价格（c_double）、是否已撤销（c_bool）、用户标记（c_char_p）
# 返回值：void指针
CB_HFTSTRA_ORD = CFUNCTYPE(c_void_p, c_ulong, c_ulong, c_char_p, c_bool, c_double, c_double, c_double, c_bool, c_char_p)

# HFT策略成交推送回报回调函数类型定义
# 参数：策略ID（c_ulong）、本地订单ID（c_ulong）、合约代码（c_char_p）、是否买入（c_bool）、成交数量（c_double）、成交价格（c_double）、用户标记（c_char_p）
# 返回值：void指针
CB_HFTSTRA_TRD = CFUNCTYPE(c_void_p, c_ulong, c_ulong, c_char_p, c_bool, c_double, c_double, c_char_p)

# HFT策略下单结果回报回调函数类型定义
# 参数：策略ID（c_ulong）、本地订单ID（c_ulong）、合约代码（c_char_p）、是否成功（c_bool）、消息（c_char_p）、用户标记（c_char_p）
# 返回值：void指针
CB_HFTSTRA_ENTRUST = CFUNCTYPE(c_void_p, c_ulong, c_ulong, c_char_p, c_bool, c_char_p, c_char_p)

# HFT策略持仓推送回报回调函数类型定义（实盘有效）
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、是否多头（c_bool）、昨日持仓（c_double）、昨日可用（c_double）、今日持仓（c_double）、今日可用（c_double）
# 返回值：void指针
CB_HFTSTRA_POSITION = CFUNCTYPE(c_void_p, c_ulong, c_char_p, c_bool, c_double, c_double, c_double, c_double)

# 策略委托队列推送回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、委托队列数据指针（POINTER(WTSOrdQueStruct)）
# 返回值：void指针
CB_HFTSTRA_ORDQUE = CFUNCTYPE(c_void_p, c_ulong, c_char_p, POINTER(WTSOrdQueStruct))

# 策略获取委托队列数据的单条数据同步回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、委托队列数据指针（POINTER(WTSOrdQueStruct)）、索引（c_uint32）、是否最后一条（c_bool）
# 返回值：void指针
CB_HFTSTRA_GET_ORDQUE = CFUNCTYPE(c_void_p, c_ulong, c_char_p, POINTER(WTSOrdQueStruct), c_uint32, c_bool)

# 策略委托明细推送回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、委托明细数据指针（POINTER(WTSOrdDtlStruct)）
# 返回值：void指针
CB_HFTSTRA_ORDDTL = CFUNCTYPE(c_void_p, c_ulong, c_char_p, POINTER(WTSOrdDtlStruct))

# 策略获取委托明细数据的单条数据同步回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、委托明细数据指针（POINTER(WTSOrdDtlStruct)）、索引（c_uint32）、是否最后一条（c_bool）
# 返回值：void指针
CB_HFTSTRA_GET_ORDDTL = CFUNCTYPE(c_void_p, c_ulong, c_char_p, POINTER(WTSOrdDtlStruct), c_uint32, c_bool)

# 策略成交明细推送回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、成交明细数据指针（POINTER(WTSTransStruct)）
# 返回值：void指针
CB_HFTSTRA_TRANS = CFUNCTYPE(c_void_p, c_ulong, c_char_p, POINTER(WTSTransStruct))

# 策略获取成交明细数据的单条数据同步回调函数类型定义
# 参数：策略ID（c_ulong）、合约代码（c_char_p）、成交明细数据指针（POINTER(WTSTransStruct)）、索引（c_uint32）、是否最后一条（c_bool）
# 返回值：void指针
CB_HFTSTRA_GET_TRANS = CFUNCTYPE(c_void_p, c_ulong, c_char_p, POINTER(WTSTransStruct), c_uint32, c_bool)


# 引擎事件常量定义
EVENT_ENGINE_INIT       = 1     # 框架初始化事件
EVENT_SESSION_BEGIN     = 2     # 交易日开始事件
EVENT_SESSION_END       = 3     # 交易日结束事件
EVENT_ENGINE_SCHDL      = 4     # 框架调度事件
EVENT_BACKTEST_END      = 5     # 回测结束事件

# 通道事件常量定义
CHNL_EVENT_READY        = 1000  # 通道就绪事件
CHNL_EVENT_LOST         = 1001  # 通道断开事件

# 日志级别常量定义
LOG_LEVEL_DEBUG         = 0     # 调试级别日志
LOG_LEVEL_INFO          = 1     # 信息级别日志
LOG_LEVEL_WARN          = 2     # 警告级别日志
LOG_LEVEL_ERROR         = 3     # 错误级别日志

# 导入枚举模块
from enum import Enum

class EngineType(Enum):
    """
    引擎类型枚举类
    
    定义引擎类型的枚举值，用于区分不同类型的交易引擎。
    """
    
    ET_CTA = 999   # CTA引擎类型，用于中低频交易策略
    ET_HFT = 1000  # HFT引擎类型，用于高频交易策略
    ET_SEL = 1001  # SEL引擎类型，用于选股策略

        
"""
Parser外接实现相关定义

用于扩展行情解析器的回调函数和事件常量定义。
"""
# Parser初始化事件
EVENT_PARSER_INIT       = 1
# Parser连接事件
EVENT_PARSER_CONNECT    = 2
# Parser断开连接事件
EVENT_PARSER_DISCONNECT = 3
# Parser释放事件
EVENT_PARSER_RELEASE    = 4

# Parser事件回调函数类型定义
# 参数：Parser ID（c_ulong）、事件数据（c_char_p）
# 返回值：void指针
CB_PARSER_EVENT = CFUNCTYPE(c_void_p, c_ulong, c_char_p)

# Parser订阅命令回调函数类型定义
# 参数：合约代码（c_char_p）、命令（c_char_p）、是否订阅（c_bool）
# 返回值：void指针
CB_PARSER_SUBCMD = CFUNCTYPE(c_void_p, c_char_p, c_char_p, c_bool)

"""
Executer外接实现相关定义

用于扩展执行器的回调函数类型定义。
"""
# Executer初始化回调函数类型定义
# 参数：执行器ID（c_char_p）
# 返回值：void指针
CB_EXECUTER_INIT = CFUNCTYPE(c_void_p, c_char_p)

# Executer命令回调函数类型定义
# 参数：执行器ID（c_char_p）、合约代码（c_char_p）、目标仓位（c_double）
# 返回值：void指针
CB_EXECUTER_CMD = CFUNCTYPE(c_void_p, c_char_p, c_char_p, c_double)


"""
DataLoader外接实现相关定义

用于扩展历史数据加载器的回调函数类型定义。
"""
# 加载K线数据回调函数类型定义
# 参数：合约代码（c_char_p）、周期（c_char_p）
# 返回值：是否成功（c_bool）
FUNC_LOAD_HISBARS = CFUNCTYPE(c_bool, c_char_p, c_char_p)

# 加载复权因子回调函数类型定义
# 参数：合约代码（c_char_p）
# 返回值：是否成功（c_bool）
FUNC_LOAD_ADJFACTS = CFUNCTYPE(c_bool, c_char_p)

# 加载Tick数据回调函数类型定义
# 参数：合约代码（c_char_p）、日期（c_ulong）
# 返回值：是否成功（c_bool）
FUNC_LOAD_HISTICKS = CFUNCTYPE(c_bool, c_char_p, c_ulong)

"""
DataDumper外接实现相关定义

用于扩展历史数据Dumper的回调函数类型定义。
"""
# 转储K线数据回调函数类型定义
# 参数：合约代码（c_char_p）、周期（c_char_p）、日期（c_char_p）、K线数据指针（POINTER(WTSBarStruct)）、数量（c_uint32）
# 返回值：是否成功（c_bool）
FUNC_DUMP_HISBARS = CFUNCTYPE(c_bool, c_char_p, c_char_p, c_char_p, POINTER(WTSBarStruct), c_uint32)

# 转储Tick数据回调函数类型定义
# 参数：合约代码（c_char_p）、日期（c_char_p）、时间戳（c_ulong）、Tick数据指针（POINTER(WTSTickStruct)）、数量（c_uint32）
# 返回值：是否成功（c_bool）
FUNC_DUMP_HISTICKS = CFUNCTYPE(c_bool, c_char_p, c_char_p, c_ulong, POINTER(WTSTickStruct), c_uint32)
