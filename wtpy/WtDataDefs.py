"""
数据定义模块

本模块定义了基于NumPy的数据结构，用于高效存储和操作K线、Tick、逐笔成交、逐笔委托等数据。
这些数据结构封装了C结构体到NumPy数组的转换，提供了便捷的数据访问接口。
支持与Pandas DataFrame的转换，方便进行数据分析和处理。

主要功能：
1. NumPy数据类型定义：定义K线、Tick、逐笔成交、逐笔委托、委托队列的NumPy数据类型
2. WtNpKline：K线数据容器类，提供K线数据的存储和访问
3. WtNpTicks：Tick数据容器类，提供Tick数据的存储和访问
4. WtNpTransactions：逐笔成交数据容器类
5. WtNpOrdDetails：逐笔委托数据容器类
6. WtNpOrdQueues：委托队列数据容器类
7. WtBarCache、WtTickCache：数据缓存辅助类，用于批量读取数据
"""

# 导入核心数据结构定义
from wtpy.WtCoreDefs import WTSBarStruct, WTSOrdDtlStruct, WTSOrdQueStruct, WTSTickStruct, WTSTransStruct
# 导入NumPy库，用于数组操作
import numpy as np
# 导入Pandas库，用于DataFrame转换
import pandas as pd

# 重复导入numpy（历史遗留，可忽略）
import numpy as np
# 导入ctypes模块，用于处理C结构体指针和地址
from ctypes import POINTER, addressof

# 重复导入核心数据结构（历史遗留，可忽略）
from wtpy.WtCoreDefs import WTSBarStruct, WTSTickStruct

# 定义K线数据的NumPy数据类型
# 字段包括：日期、保留字段、时间、开高低收、结算价、成交额、成交量、持仓量、持仓变化
NpTypeBar = np.dtype([('date','u4'),('reserve','u4'),('time','u8'),('open','d'),\
                ('high','d'),('low','d'),('close','d'),('settle','d'),\
                ('turnover','d'),('volume','d'),('open_interest','d'),('diff','d')])

# 定义Tick数据的NumPy数据类型
# 字段包括：交易所、合约代码、价格信息、买卖盘信息（10档）等
NpTypeTick = np.dtype([('exchg','S16'),('code','S32'),('price','d'),('open','d'),('high','d'),('low','d'),('settle_price','d'),\
                ('upper_limit','d'),('lower_limit','d'),('total_volume','d'),('volume','d'),('total_turnover','d'),('turn_over','d'),\
                ('open_interest','d'),('diff_interest','d'),('trading_date','u4'),('action_date','u4'),('action_time','u4'),\
                ('reserve','u4'),('pre_close','d'),('pre_settle','d'),('pre_interest','d'),\
                ('bid_price_0','d'),('bid_price_1','d'),('bid_price_2','d'),('bid_price_3','d'),('bid_price_4','d'),\
                ('bid_price_5','d'),('bid_price_6','d'),('bid_price_7','d'),('bid_price_8','d'),('bid_price_9','d'),\
                ('ask_price_0','d'),('ask_price_1','d'),('ask_price_2','d'),('ask_price_3','d'),('ask_price_4','d'),\
                ('ask_price_5','d'),('ask_price_6','d'),('ask_price_7','d'),('ask_price_8','d'),('ask_price_9','d'),\
                ('bid_qty_0','d'),('bid_qty_1','d'),('bid_qty_2','d'),('bid_qty_3','d'),('bid_qty_4','d'),\
                ('bid_qty_5','d'),('bid_qty_6','d'),('bid_qty_7','d'),('bid_qty_8','d'),('bid_qty_9','d'),\
                ('ask_qty_0','d'),('ask_qty_1','d'),('ask_qty_2','d'),('ask_qty_3','d'),('ask_qty_4','d'),\
                ('ask_qty_5','d'),('ask_qty_6','d'),('ask_qty_7','d'),('ask_qty_8','d'),('ask_qty_9','d')])

# 定义逐笔成交数据的NumPy数据类型
# 字段包括：交易所、合约代码、日期时间、成交索引、成交类型、方向、价格、数量、买卖订单号
NpTypeTrans = np.dtype([('exchg','S16'),('code','S32'),('trading_date','u4'),('action_date','u4'),('action_time','u4'),\
                ('index','i8'),('ttype','i4'),('side','i4'),('price','d'),('volume','u4'),('askorder', np.int64),('bidorder', np.int64)])

# 定义委托队列数据的NumPy数据类型
# 字段包括：交易所、合约代码、日期时间、方向、价格、委托笔数、队列大小、各档位委托量（50档）
NpTypeOrdQue = np.dtype([('exchg','S16'),('code','S32'),('trading_date','u4'),('action_date','u4'),('action_time','u4'),\
                ('side','u4'),('price','d'),('order_items','u4'),('qsize', np.int64),('volumes', np.uint32, 50)])

# 定义逐笔委托数据的NumPy数据类型
# 字段包括：交易所、合约代码、日期时间、委托索引、价格、数量、方向、委托类型
NpTypeOrdDtl = np.dtype([('exchg','S16'),('code','S32'),('trading_date','u4'),('action_date','u4'),('action_time','u4'),\
                ('index','i8'),('price','d'),('volume','u4'),('side','u4'),('otype','u4')])

class WtNpKline:
    """
    基于NumPy数组的K线数据容器类
    
    提供K线数据的存储和访问功能，封装了C结构体到NumPy数组的转换。
    支持日线和分钟线的不同时间格式处理，提供便捷的属性访问和DataFrame转换。
    """
    
    # 类属性：NumPy数据类型，用于定义K线数据的结构
    __type__:np.dtype = NpTypeBar
    
    def __init__(self, isDay:bool = False, forceCopy:bool = False):
        """
        构造函数
        
        初始化K线数据容器，设置数据类型和标志。
        
        @isDay: 是否是日线数据，主要用于控制bartimes的生成机制，True表示日线，False表示分钟线
        @forceCopy: 是否强制拷贝，如果为True，则会拷贝一份数据，否则会直接引用内存中的数据
                    强制拷贝主要用于WtDtHelper的read_dsb_bars和read_dmb_bars接口，
                    因为这两个接口返回的数据是临时的，调用结束就会释放
        """
        # K线数据数组，存储实际的K线数据
        self.__data__:np.ndarray = None
        # 是否为日线数据标志
        self.__isDay__:bool = isDay
        # 是否强制拷贝标志
        self.__force_copy__:bool = forceCopy
        # K线时间数组缓存，避免重复计算
        self.__bartimes__:np.ndarray = None
        # Pandas DataFrame缓存，避免重复转换
        self.__df__:pd.DataFrame = None

    def __len__(self):
        """
        获取K线数据长度
        
        实现len()函数支持，返回K线数据的条数。
        
        @return: K线数据条数，如果没有数据则返回0
        """
        # 如果数据数组为空，返回0
        if self.__data__ is None:
            return 0
        
        # 返回数据数组的长度
        return len(self.__data__)
    
    def __getitem__(self, index:int):
        """
        获取指定索引的K线数据
        
        实现索引访问支持，可以通过obj[index]的方式访问K线数据。
        
        @index: 索引位置，支持负数索引（从后往前）
        @return: 指定索引的K线数据（NumPy结构化数组元素）
        @raise IndexError: 如果数据为空或索引超出范围则抛出异常
        """
        # 如果数据数组为空，抛出索引错误异常
        if self.__data__ is None:
            raise IndexError("No data in WtNpKline")
        
        # 返回指定索引的K线数据
        return self.__data__[index]

    def set_day_flag(self, isDay:bool):
        """
        设置日线标志
        
        修改日线标志，如果标志改变则清除时间缓存和DataFrame缓存。
        
        @isDay: 是否为日线数据，True表示日线，False表示分钟线
        """
        # 如果标志发生变化
        if self.__isDay__ != isDay:
            # 更新标志
            self.__isDay__ = isDay
            # 清除时间缓存，因为时间格式会改变
            self.__bartimes__ = None
            # 清除DataFrame缓存，因为索引会改变
            self.__df__ = None

    def set_data(self, firstBar, count:int):
        """
        设置K线数据
        
        从C结构体指针设置K线数据，支持强制拷贝和直接引用两种模式。
        如果已有数据，会将新数据追加到现有数据后面。
        
        @firstBar: C结构体指针，指向WTSBarStruct数组的第一个元素
        @count: 数据条数，要转换的K线数量
        """
        # 创建C结构体数组类型，长度为count
        BarList = WTSBarStruct*count
        # 如果强制拷贝模式
        if self.__force_copy__:
            # 从指针地址创建数组的副本
            c_array = BarList.from_buffer_copy(BarList.from_address(addressof(firstBar.contents)))
        else:
            # 从指针地址直接引用数组（不拷贝）
            c_array = BarList.from_buffer(BarList.from_address(addressof(firstBar.contents)))
        # 将C数组转换为NumPy数组，使用预定义的数据类型
        npAy = np.frombuffer(c_array, dtype=self.__type__, count=count)

        # 这里有点不高效，需要拼接的地方，主要是WtDtServo的场景，这里慢点没关系
        # 如果已有数据，将新数据追加到现有数据后面
        if self.__data__ is not None:
            # 使用concatenate拼接数组
            self.__data__ = np.concatenate((self.__data__, npAy))
            # 设置数组的可写标志，根据forceCopy参数决定
            self.__data__.flags.writeable = self.__force_copy__
        else:
            # 如果没有已有数据，直接使用新数组
            self.__data__ = npAy
            # 设置数组为只读（除非forceCopy为True）
            self.__data__.flags.writeable = False

    @property
    def ndarray(self) -> np.ndarray:
        """
        获取NumPy数组属性
        
        返回底层的NumPy数组对象，用于直接访问数据。
        
        @return: NumPy数组对象
        """
        return self.__data__
    
    @property
    def opens(self) -> np.ndarray:
        """
        获取开盘价数组属性
        
        返回所有K线的开盘价数组。
        
        @return: 开盘价数组，NumPy数组类型
        """
        return self.__data__["open"]

    @property
    def highs(self) -> np.ndarray:
        """
        获取最高价数组属性
        
        返回所有K线的最高价数组。
        
        @return: 最高价数组，NumPy数组类型
        """
        return self.__data__["high"]

    @property
    def lows(self) -> np.ndarray:
        """
        获取最低价数组属性
        
        返回所有K线的最低价数组。
        
        @return: 最低价数组，NumPy数组类型
        """
        return self.__data__["low"]

    @property
    def closes(self) -> np.ndarray:
        """
        获取收盘价数组属性
        
        返回所有K线的收盘价数组。
        
        @return: 收盘价数组，NumPy数组类型
        """
        return self.__data__["close"]

    @property
    def volumes(self) -> np.ndarray:
        """
        获取成交量数组属性
        
        返回所有K线的成交量数组。
        
        @return: 成交量数组，NumPy数组类型
        """
        return self.__data__["volume"]

    @property
    def bartimes(self) -> np.ndarray:
        """
        获取K线时间数组属性
        
        返回所有K线的时间数组，日线和分钟线的时间格式不同。
        这里应该会构造一个副本，可以暂存一个以提高性能。
        
        @return: K线时间数组，日线返回日期（yyyymmdd），分钟线返回时间戳（yyyymmddHHMM）
        """
        # 如果时间缓存为空，需要计算时间数组
        if self.__bartimes__ is None:
            # 如果是日线数据
            if self.__isDay__:
                # 直接使用日期字段
                self.__bartimes__ = self.__data__["date"]
            else:
                # 分钟线数据：时间字段加上基准时间戳199000000000（1990-01-01 00:00:00）
                self.__bartimes__ = self.__data__["time"] + 199000000000
        # 返回时间数组
        return self.__bartimes__
    
    def get_bar(self, iLoc:int = -1) -> tuple:
        """
        获取指定位置的K线数据
        
        获取指定索引位置的K线数据，返回为元组格式。
        
        @iLoc: 索引位置，默认为-1（最后一条），支持负数索引
        @return: K线数据元组，包含所有字段的值
        """
        return self.__data__[iLoc]
    
    @property
    def is_day(self) -> bool:
        """
        获取是否为日线数据属性
        
        返回是否为日线数据的标志。
        
        @return: True表示日线数据，False表示分钟线数据
        """
        return self.__isDay__
    
    def to_df(self) -> pd.DataFrame:
        """
        转换为Pandas DataFrame
        
        将K线数据转换为Pandas DataFrame格式，方便进行数据分析和处理。
        DataFrame的索引为K线时间，列包含开高低收、成交量等字段。
        
        @return: Pandas DataFrame对象，包含K线数据
        """
        # 如果DataFrame缓存为空，需要转换
        if self.__df__ is None:
            # 创建DataFrame，使用时间数组作为索引
            self.__df__ = pd.DataFrame(self.__data__, index=self.bartimes)
            # 删除不需要的列（date、time、reserve）
            self.__df__.drop(columns=["date", "time", "reserve"], inplace=True)
            # 添加bartime列，值为索引（时间）
            self.__df__["bartime"] = self.__df__.index
        # 返回DataFrame对象
        return self.__df__
    
class WtNpTicks:
    """
    基于NumPy数组的Tick数据容器类
    
    提供Tick数据的存储和访问功能，封装了C结构体到NumPy数组的转换。
    支持强制拷贝和直接引用两种模式，提供便捷的属性访问和DataFrame转换。
    """
    
    # 类属性：NumPy数据类型，用于定义Tick数据的结构
    __type__:np.dtype = NpTypeTick
    
    def __init__(self, forceCopy:bool = False):
        """
        构造函数
        
        初始化Tick数据容器，设置数据类型和标志。
        
        @forceCopy: 是否强制拷贝，如果为True，则会拷贝一份数据，否则会直接引用内存中的数据
                    强制拷贝主要用于WtDtHelper的read_dsb_ticks和read_dmb_ticks接口，
                    因为这两个接口返回的数据是临时的，调用结束就会释放
        """
        # Tick数据数组，存储实际的Tick数据
        self.__data__:np.ndarray = None
        # Tick时间数组缓存，避免重复计算
        self.__times__:np.ndarray = None
        # 是否强制拷贝标志
        self.__force_copy__:bool = forceCopy
        # Pandas DataFrame缓存，避免重复转换
        self.__df__:pd.DataFrame = None

    def __len__(self):
        """
        获取Tick数据长度
        
        实现len()函数支持，返回Tick数据的条数。
        
        @return: Tick数据条数，如果没有数据则返回0
        """
        # 如果数据数组为空，返回0
        if self.__data__ is None:
            return 0
        
        # 返回数据数组的长度
        return len(self.__data__)
    
    def __getitem__(self, index:int):
        """
        获取指定索引的Tick数据
        
        实现索引访问支持，可以通过obj[index]的方式访问Tick数据。
        
        @index: 索引位置，支持负数索引（从后往前）
        @return: 指定索引的Tick数据（NumPy结构化数组元素）
        @raise IndexError: 如果数据为空或索引超出范围则抛出异常
        """
        # 如果数据数组为空，抛出索引错误异常
        if self.__data__ is None:
            raise IndexError("No data in WtNpTicks")
        
        # 返回指定索引的Tick数据
        return self.__data__[index]

    def set_data(self, firstTick, count:int):
        """
        设置Tick数据
        
        从C结构体指针设置Tick数据，支持强制拷贝和直接引用两种模式。
        如果已有数据，会将新数据追加到现有数据后面。
        
        @firstTick: C结构体指针，指向WTSTickStruct数组的第一个元素
        @count: 数据条数，要转换的Tick数量
        """
        # 创建C结构体数组类型，长度为count
        BarList = WTSTickStruct*count
        # 如果强制拷贝模式
        if self.__force_copy__:
            # 从指针地址创建数组的副本
            c_array = BarList.from_buffer_copy(BarList.from_address(addressof(firstTick.contents)))
        else:
            # 从指针地址直接引用数组（不拷贝）
            c_array = BarList.from_buffer(BarList.from_address(addressof(firstTick.contents)))

        # 将C数组转换为NumPy数组，使用预定义的数据类型
        npAy = np.frombuffer(c_array, dtype=self.__type__, count=count)
        # 这里有点不高效，需要拼接的地方主要是WtDtServo的场景，这里慢点没关系
        # 一旦触发拼接逻辑，都会拷贝一次
        # 如果已有数据，将新数据追加到现有数据后面
        if self.__data__ is not None:
            # 使用concatenate拼接数组
            self.__data__ = np.concatenate((self.__data__, npAy))
            # 设置数组的可写标志，根据forceCopy参数决定
            self.__data__.flags.writeable = self.__force_copy__
        else:
            # 如果没有已有数据，直接使用新数组
            self.__data__ = npAy
            # 设置数组为只读（除非forceCopy为True）
            self.__data__.flags.writeable = False

    @property
    def times(self) -> np.ndarray:
        """
        获取Tick时间数组属性
        
        返回所有Tick的时间数组，时间格式为时间戳（纳秒级）。
        这里应该会构造一个副本，可以暂存一个以提高性能。
        
        @return: Tick时间数组，格式为时间戳（纳秒级，从1970-01-01开始）
        """
        # 如果时间缓存为空，需要计算时间数组
        if self.__times__ is None:
            # 计算时间戳：日期（yyyymmdd）* 1000000000 + 时间（HHMMSSmmm）
            self.__times__ = np.uint64(self.__data__["action_date"])*1000000000 + self.__data__["action_time"]
        # 返回时间数组
        return self.__times__


    def to_df(self) -> pd.DataFrame:
        """
        转换为Pandas DataFrame
        
        将Tick数据转换为Pandas DataFrame格式，方便进行数据分析和处理。
        DataFrame的索引为Tick时间，列包含价格、成交量、买卖盘等字段。
        
        @return: Pandas DataFrame对象，包含Tick数据
        """
        # 如果DataFrame缓存为空，需要转换
        if self.__df__ is None:
            # 创建DataFrame，使用时间数组作为索引
            self.__df__ = pd.DataFrame(self.__data__, index=self.times)
            # 删除不需要的列（reserve）
            self.__df__.drop(columns=["reserve"], inplace=True)
            # 添加time列，值为索引（时间）
            self.__df__["time"] = self.__df__.index
        # 返回DataFrame对象
        return self.__df__

    @property
    def ndarray(self) -> np.ndarray:
        """
        获取NumPy数组属性
        
        返回底层的NumPy数组对象，用于直接访问数据。
        
        @return: NumPy数组对象
        """
        return self.__data__
    
class WtNpTransactions:
    """
    基于NumPy数组的逐笔成交数据容器类
    
    提供逐笔成交数据的存储和访问功能，封装了C结构体到NumPy数组的转换。
    支持强制拷贝和直接引用两种模式，提供便捷的数据访问接口。
    """
    
    # 类属性：NumPy数据类型，用于定义逐笔成交数据的结构
    __type__:np.dtype = NpTypeTrans
    
    def __init__(self, forceCopy:bool = False):
        """
        构造函数
        
        初始化逐笔成交数据容器，设置数据类型和标志。
        
        @forceCopy: 是否强制拷贝，如果为True，则会拷贝一份数据，否则会直接引用内存中的数据
                    强制拷贝主要用于WtDtHelper的read_dsb_trans和read_dmb_trans接口，
                    因为这两个接口返回的数据是临时的，调用结束就会释放
        """
        # 逐笔成交数据数组，存储实际的逐笔成交数据
        self.__data__:np.ndarray = None
        # 是否强制拷贝标志
        self.__force_copy__:bool = forceCopy

    def __len__(self):
        """
        获取逐笔成交数据长度
        
        实现len()函数支持，返回逐笔成交数据的条数。
        
        @return: 逐笔成交数据条数，如果没有数据则返回0
        """
        # 如果数据数组为空，返回0
        if self.__data__ is None:
            return 0
        
        # 返回数据数组的长度
        return len(self.__data__)
    
    def __getitem__(self, index:int):
        """
        获取指定索引的逐笔成交数据
        
        实现索引访问支持，可以通过obj[index]的方式访问逐笔成交数据。
        
        @index: 索引位置，支持负数索引（从后往前）
        @return: 指定索引的逐笔成交数据（NumPy结构化数组元素）
        @raise IndexError: 如果数据为空或索引超出范围则抛出异常
        """
        # 如果数据数组为空，抛出索引错误异常
        if self.__data__ is None:
            raise IndexError("No data in WtNpTransactions")
        
        # 返回指定索引的逐笔成交数据
        return self.__data__[index]

    def set_data(self, firstItem, count:int):
        """
        设置逐笔成交数据
        
        从C结构体指针设置逐笔成交数据，支持强制拷贝和直接引用两种模式。
        如果已有数据，会将新数据追加到现有数据后面。
        
        @firstItem: C结构体指针，指向WTSTransStruct数组的第一个元素
        @count: 数据条数，要转换的逐笔成交数量
        """
        # 创建C结构体数组类型，长度为count
        DataList = WTSTransStruct*count
        # 如果强制拷贝模式
        if self.__force_copy__:
            # 从指针地址创建数组的副本
            c_array = DataList.from_buffer_copy(DataList.from_address(addressof(firstItem.contents)))
        else:
            # 从指针地址直接引用数组（不拷贝）
            c_array = DataList.from_buffer(DataList.from_address(addressof(firstItem.contents)))
        
        # 将C数组转换为NumPy数组，使用预定义的数据类型
        npAy = np.frombuffer(c_array, dtype=self.__type__, count=count)
        # 这里有点不高效，需要拼接的地方主要是WtDtServo的场景，这里慢点没关系
        # 一旦触发拼接逻辑，都会拷贝一次
        # 如果已有数据，将新数据追加到现有数据后面
        if self.__data__ is not None:
            # 使用concatenate拼接数组
            self.__data__ = np.concatenate((self.__data__, npAy))
            # 设置数组的可写标志，根据forceCopy参数决定
            self.__data__.flags.writeable = self.__force_copy__
        else:
            # 如果没有已有数据，直接使用新数组
            self.__data__ = npAy
            # 设置数组为只读（除非forceCopy为True）
            self.__data__.flags.writeable = False

    @property
    def ndarray(self) -> np.ndarray:
        """
        获取NumPy数组属性
        
        返回底层的NumPy数组对象，用于直接访问数据。
        
        @return: NumPy数组对象
        """
        return self.__data__
    
class WtNpOrdDetails:
    """
    基于NumPy数组的逐笔委托数据容器类
    
    提供逐笔委托数据的存储和访问功能，封装了C结构体到NumPy数组的转换。
    支持强制拷贝和直接引用两种模式，提供便捷的数据访问接口。
    """
    
    # 类属性：NumPy数据类型，用于定义逐笔委托数据的结构
    __type__:np.dtype = NpTypeOrdDtl
    
    def __init__(self, forceCopy:bool = False):
        """
        构造函数
        
        初始化逐笔委托数据容器，设置数据类型和标志。
        
        @forceCopy: 是否强制拷贝，如果为True，则会拷贝一份数据，否则会直接引用内存中的数据
                    强制拷贝主要用于WtDtHelper的read_dsb_trans和read_dmb_trans接口，
                    因为这两个接口返回的数据是临时的，调用结束就会释放
        """
        # 逐笔委托数据数组，存储实际的逐笔委托数据
        self.__data__:np.ndarray = None
        # 是否强制拷贝标志
        self.__force_copy__:bool = forceCopy

    def __len__(self):
        """
        获取逐笔委托数据长度
        
        实现len()函数支持，返回逐笔委托数据的条数。
        
        @return: 逐笔委托数据条数，如果没有数据则返回0
        """
        # 如果数据数组为空，返回0
        if self.__data__ is None:
            return 0
        
        # 返回数据数组的长度
        return len(self.__data__)
    
    def __getitem__(self, index:int):
        """
        获取指定索引的逐笔委托数据
        
        实现索引访问支持，可以通过obj[index]的方式访问逐笔委托数据。
        
        @index: 索引位置，支持负数索引（从后往前）
        @return: 指定索引的逐笔委托数据（NumPy结构化数组元素）
        @raise IndexError: 如果数据为空或索引超出范围则抛出异常
        """
        # 如果数据数组为空，抛出索引错误异常
        if self.__data__ is None:
            raise IndexError("No data in WtNpOrdDetails")
        
        # 返回指定索引的逐笔委托数据
        return self.__data__[index]

    def set_data(self, firstItem, count:int):
        """
        设置逐笔委托数据
        
        从C结构体指针设置逐笔委托数据，支持强制拷贝和直接引用两种模式。
        如果已有数据，会将新数据追加到现有数据后面。
        
        @firstItem: C结构体指针，指向WTSOrdDtlStruct数组的第一个元素
        @count: 数据条数，要转换的逐笔委托数量
        """
        # 创建C结构体数组类型，长度为count
        DataList = WTSOrdDtlStruct*count
        # 如果强制拷贝模式
        if self.__force_copy__:
            # 从指针地址创建数组的副本
            c_array = DataList.from_buffer_copy(DataList.from_address(addressof(firstItem.contents)))
        else:
            # 从指针地址直接引用数组（不拷贝）
            c_array = DataList.from_buffer(DataList.from_address(addressof(firstItem.contents)))

        # 将C数组转换为NumPy数组，使用预定义的数据类型
        npAy = np.frombuffer(c_array, dtype=self.__type__, count=count)
        # 这里有点不高效，需要拼接的地方主要是WtDtServo的场景，这里慢点没关系
        # 一旦触发拼接逻辑，都会拷贝一次
        # 如果已有数据，将新数据追加到现有数据后面
        if self.__data__ is not None:
            # 使用concatenate拼接数组
            self.__data__ = np.concatenate((self.__data__, npAy))
            # 设置数组的可写标志，根据forceCopy参数决定
            self.__data__.flags.writeable = self.__force_copy__
        else:
            # 如果没有已有数据，直接使用新数组
            self.__data__ = npAy
            # 设置数组为只读（除非forceCopy为True）
            self.__data__.flags.writeable = False

    @property
    def ndarray(self) -> np.ndarray:
        """
        获取NumPy数组属性
        
        返回底层的NumPy数组对象，用于直接访问数据。
        
        @return: NumPy数组对象
        """
        return self.__data__
    
class WtNpOrdQueues:
    """
    基于NumPy数组的委托队列数据容器类
    
    提供委托队列数据的存储和访问功能，封装了C结构体到NumPy数组的转换。
    支持强制拷贝和直接引用两种模式，提供便捷的数据访问接口。
    """
    
    # 类属性：NumPy数据类型，用于定义委托队列数据的结构
    __type__:np.dtype = NpTypeOrdQue
    
    def __init__(self, forceCopy:bool = False):
        """
        构造函数
        
        初始化委托队列数据容器，设置数据类型和标志。
        
        @forceCopy: 是否强制拷贝，如果为True，则会拷贝一份数据，否则会直接引用内存中的数据
                    强制拷贝主要用于WtDtHelper的read_dsb_trans和read_dmb_trans接口，
                    因为这两个接口返回的数据是临时的，调用结束就会释放
        """
        # 委托队列数据数组，存储实际的委托队列数据
        self.__data__:np.ndarray = None
        # 是否强制拷贝标志
        self.__force_copy__:bool = forceCopy

    def __len__(self):
        """
        获取委托队列数据长度
        
        实现len()函数支持，返回委托队列数据的条数。
        
        @return: 委托队列数据条数，如果没有数据则返回0
        """
        # 如果数据数组为空，返回0
        if self.__data__ is None:
            return 0
        
        # 返回数据数组的长度
        return len(self.__data__)
    
    def __getitem__(self, index:int):
        """
        获取指定索引的委托队列数据
        
        实现索引访问支持，可以通过obj[index]的方式访问委托队列数据。
        
        @index: 索引位置，支持负数索引（从后往前）
        @return: 指定索引的委托队列数据（NumPy结构化数组元素）
        @raise IndexError: 如果数据为空或索引超出范围则抛出异常
        """
        # 如果数据数组为空，抛出索引错误异常
        if self.__data__ is None:
            raise IndexError("No data in WtNpOrdQueues")
        
        # 返回指定索引的委托队列数据
        return self.__data__[index]

    def set_data(self, firstItem, count:int):
        """
        设置委托队列数据
        
        从C结构体指针设置委托队列数据，支持强制拷贝和直接引用两种模式。
        如果已有数据，会将新数据追加到现有数据后面。
        
        @firstItem: C结构体指针，指向WTSOrdQueStruct数组的第一个元素
        @count: 数据条数，要转换的委托队列数量
        """
        # 创建C结构体数组类型，长度为count
        DataList = WTSOrdQueStruct*count
        # 如果强制拷贝模式
        if self.__force_copy__:
            # 从指针地址创建数组的副本
            c_array = DataList.from_buffer_copy(DataList.from_address(addressof(firstItem.contents)))
        else:
            # 从指针地址直接引用数组（不拷贝）
            c_array = DataList.from_buffer(DataList.from_address(addressof(firstItem.contents)))

        # 将C数组转换为NumPy数组，使用预定义的数据类型
        npAy = np.frombuffer(c_array, dtype=self.__type__, count=count)
        # 这里有点不高效，需要拼接的地方主要是WtDtServo的场景，这里慢点没关系
        # 一旦触发拼接逻辑，都会拷贝一次
        # 如果已有数据，将新数据追加到现有数据后面
        if self.__data__ is not None:
            # 使用concatenate拼接数组
            self.__data__ = np.concatenate((self.__data__, npAy))
            # 设置数组的可写标志，根据forceCopy参数决定
            self.__data__.flags.writeable = self.__force_copy__
        else:
            # 如果没有已有数据，直接使用新数组
            self.__data__ = npAy
            # 设置数组为只读（除非forceCopy为True）
            self.__data__.flags.writeable = False

    @property
    def ndarray(self) -> np.ndarray:
        """
        获取NumPy数组属性
        
        返回底层的NumPy数组对象，用于直接访问数据。
        
        @return: NumPy数组对象
        """
        return self.__data__
    
class WtBarCache:
    """
    K线数据缓存辅助类
    
    用于批量读取K线数据时的缓存管理。
    当数据分多次返回时，会自动将数据拼接在一起。
    """
    
    def __init__(self, isDay:bool = False, forceCopy:bool = False):
        """
        构造函数
        
        初始化K线数据缓存，设置标志和计数器。
        
        @isDay: 是否是日线数据，True表示日线，False表示分钟线
        @forceCopy: 是否强制拷贝数据
        """
        # K线数据记录对象，存储实际的K线数据
        self.records:WtNpKline = None
        # 是否为日线数据标志
        self.__is_day__ = isDay
        # 是否强制拷贝标志
        self.__force_copy__ = forceCopy
        # 总数据条数计数器
        self.__total_count__ = 0

    def on_read_bar(self, firstItem:POINTER(WTSBarStruct), count:int, isLast:bool):
        """
        K线数据读取回调函数（由底层调用）
        
        当底层返回K线数据时调用，将数据添加到缓存中。
        
        @firstItem: C结构体指针，指向WTSBarStruct数组的第一个元素
        @count: 本次返回的数据条数
        @isLast: 是否是最后一批数据，True表示这是最后一批
        """
        # 如果记录对象未初始化，创建新的WtNpKline对象
        if self.records is None:
            self.records = WtNpKline(isDay=self.__is_day__, forceCopy=self.__force_copy__)

        # 多次set_data，会在内部自动concatenate（拼接）
        # 将本次数据添加到记录对象中
        self.records.set_data(firstItem, count)

    def on_data_count(self, count:int):
        """
        数据总数回调函数（由底层调用）
        
        在开始读取数据前调用，通知总数据条数。
        其实这里最好的处理方式是能够直接将底层的内存块拷贝，拼接成一块大的内存块
        但是暂时没想好怎么处理，所以只能多次set_data了，会损失一些性能，但是比以前快
        
        @count: 总数据条数
        """
        # 保存总数据条数
        self.__total_count__ = count
        pass

class WtTickCache:
    """
    Tick数据缓存辅助类
    
    用于批量读取Tick数据时的缓存管理。
    当数据分多次返回时，会自动将数据拼接在一起。
    """
    
    def __init__(self, forceCopy:bool = False):
        """
        构造函数
        
        初始化Tick数据缓存，设置标志和计数器。
        
        @forceCopy: 是否强制拷贝数据
        """
        # Tick数据记录对象，存储实际的Tick数据
        self.records:WtNpTicks = None
        # 是否强制拷贝标志
        self.__force_copy__ = forceCopy
        # 总数据条数计数器
        self.__total_count__ = 0

    def on_read_tick(self, firstItem:POINTER(WTSTickStruct), count:int, isLast:bool):
        """
        Tick数据读取回调函数（由底层调用）
        
        当底层返回Tick数据时调用，将数据添加到缓存中。
        
        @firstItem: C结构体指针，指向WTSTickStruct数组的第一个元素
        @count: 本次返回的数据条数
        @isLast: 是否是最后一批数据，True表示这是最后一批
        """
        # 如果记录对象未初始化，创建新的WtNpTicks对象
        if self.records is None:
            self.records = WtNpTicks(forceCopy=self.__force_copy__)

        # 多次set_data，会在内部自动concatenate（拼接）
        # 将本次数据添加到记录对象中
        self.records.set_data(firstItem, count)

    def on_data_count(self, count:int):
        """
        数据总数回调函数（由底层调用）
        
        在开始读取数据前调用，通知总数据条数。
        其实这里最好的处理方式是能够直接将底层的内存块拷贝，拼接成一块大的内存块
        但是暂时没想好怎么处理，所以只能多次set_data了，会损失一些性能，但是比以前快
        
        @count: 总数据条数
        """
        # 保存总数据条数
        self.__total_count__ = count
        pass
