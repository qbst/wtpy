"""
选股策略上下文模块

本模块提供了选股策略的上下文类（SelContext），是策略可以直接访问的唯一对象。
策略通过Context对象调用框架提供的所有接口，包括数据查询、下单、持仓管理等。
Context类封装了底层接口的调用细节，为策略提供了简洁易用的API。

主要功能：
1. 时间接口：获取当前日期、时间、交易日等
2. 数据接口：获取K线、Tick、持仓、资金等数据
3. 交易接口：设置仓位、查询持仓等
4. 工具接口：日志输出、用户数据存储、品种信息查询等
"""

# 导入ctypes模块的POINTER类型，用于处理C结构体指针
from ctypes import POINTER
# 导入核心数据结构定义
from wtpy.WtCoreDefs import WTSBarStruct, WTSTickStruct
# 导入数据定义模块中的K线和Tick数据结构
from wtpy.WtDataDefs import WtNpKline, WtNpTicks

class SelContext:
    """
    选股策略上下文类
    
    Context是策略可以直接访问的唯一对象，策略所有的接口都通过Context对象调用。
    Context类包括以下几类接口：
    1、时间接口（日期、时间等），接口格式如：stra_xxx
    2、数据接口（K线、财务等），接口格式如：stra_xxx
    3、下单接口（设置目标仓位、直接下单等），接口格式如：stra_xxx
    """

    def __init__(self, id:int, stra, wrapper, engine):
        """
        构造函数
        
        初始化选股策略上下文，设置策略对象、底层包装器、引擎等引用。
        
        @id: 策略ID，由引擎分配的唯一标识符
        @stra: 策略对象，继承自BaseSelStrategy的策略实例
        @wrapper: 底层接口转换器，用于调用C++底层接口
        @engine: 交易引擎对象，提供引擎级别的功能
        """
        # 策略对象引用，用于调用策略的回调函数
        self.__stra_info__ = stra
        # 底层接口转换器，用于调用C++底层接口
        self.__wrapper__ = wrapper
        # 策略ID，由引擎分配的唯一标识符
        self.__id__ = id
        # K线数据缓存字典，键为"合约代码#周期"，值为WtNpKline对象
        self.__bar_cache__ = dict()
        # Tick数据缓存字典，键为合约代码，值为WtNpTicks对象
        # 注意：Tick缓存每次都重新拉取，这个只做中转用，不在python里维护副本
        self.__tick_cache__ = dict()
        # 策略名称，从策略对象获取
        self.__sname__ = stra.name()
        # 交易引擎对象引用，提供引擎级别的功能
        self.__engine__ = engine
        # 持仓缓存字典，键为合约代码，值为持仓数量
        self.__pos_cache__ = None

        # 是否为回测模式标志，从引擎获取
        self.is_backtest = self.__engine__.is_backtest

        # 设置接口函数别名，提供更简洁的调用方式
        self.__alias__()
        
    @property
    def id(self):
        """
        获取策略ID属性
        
        @return: 返回策略ID
        """
        return self.__id__
    
    def __alias__(self):
        """
        设置接口函数别名
        
        为常用的接口函数设置简短的别名，方便策略调用。
        例如：context.get_bars() 等价于 context.stra_get_bars()
        """
        # 设置获取全部持仓的别名
        self.get_all_position = self.stra_get_all_position
        # 设置获取K线的别名
        self.get_bars = self.stra_get_bars
        # 设置获取品种信息的别名
        self.get_comminfo = self.stra_get_comminfo
        # 设置获取日期的别名
        self.get_date = self.stra_get_date
        # 设置获取当日价格的别名
        self.get_day_price = self.stra_get_day_price
        # 设置获取持仓成本的别名
        self.get_detail_cost = self.stra_get_detail_cost
        # 设置获取持仓进场时间的别名
        self.get_detail_entertime = self.stra_get_detail_entertime
        # 设置获取持仓盈亏的别名
        self.get_detail_profit = self.stra_get_detail_profit
        # 设置获取首次进场时间的别名
        self.get_first_entertime = self.stra_get_first_entrytime
        # 设置获取资金数据的别名
        self.get_fund_data = self.stra_get_fund_data
        # 设置获取最后进场标记的别名
        self.get_last_entrytag = self.stra_get_last_entrytag
        # 设置获取最后进场时间的别名
        self.get_last_entrytime = self.stra_get_last_entrytime
        # 设置获取最后出场时间的别名
        self.get_last_exittime = self.stra_get_last_exittime
        # 设置获取持仓的别名
        self.get_position = self.stra_get_position
        # 设置获取持仓均价的别名
        self.get_position_avgpx = self.stra_get_position_avgpx
        # 设置获取持仓盈亏的别名
        self.get_position_profit = self.stra_get_position_profit
        # 设置获取最新价格的别名
        self.get_price = self.stra_get_price
        # 设置获取原始合约代码的别名
        self.get_rawcode = self.stra_get_rawcode
        # 设置获取交易时段信息的别名
        self.get_sessinfo = self.stra_get_sessioninfo
        # 设置获取交易日的别名
        self.get_tdate = self.stra_get_tdate
        # 设置获取Tick数据的别名
        self.get_ticks = self.stra_get_ticks
        # 设置获取时间的别名
        self.get_time = self.stra_get_time
        # 设置输出日志的别名
        self.log_text = self.stra_log_text
        # 设置准备K线的别名
        self.prepare_bars = self.stra_prepare_bars
        # 设置设置仓位的别名
        self.set_position = self.stra_set_position
        # 设置订阅Tick的别名
        self.sub_ticks = self.stra_sub_ticks
        pass

    def write_indicator(self, tag, time, data):
        """
        输出指标数据
        
        将策略计算的指标数据输出到外部存储或显示系统。
        指标数据会被转换为JSON格式保存。
        
        @tag: 指标标签，用于区分不同的指标，例如：m5、d等
        @time: 输出时间，格式如yyyymmddHHMM
        @data: 输出的指标数据，dict类型，会转成json以后保存
        """
        # 调用引擎的指标输出方法，传入策略名称、标签、时间和数据
        self.__engine__.write_indicator(self.__stra_info__.name(), tag, time, data)

    def on_init(self):
        """
        初始化回调函数
        
        在策略启动时调用，一般用于系统启动的时候。
        此函数会调用策略对象的on_init方法。
        """
        # 调用策略对象的初始化方法，传入self作为上下文
        self.__stra_info__.on_init(self)

    def on_session_begin(self, curTDate:int):
        """
        交易日开始事件回调函数
        
        在每个交易日开始时调用，通知策略新的交易日开始。
        
        @curTDate: 当前交易日，格式为yyyymmdd，例如：20210220
        """
        # 调用策略对象的交易日开始方法，传入self和交易日
        self.__stra_info__.on_session_begin(self, curTDate)

    def on_session_end(self, curTDate:int):
        """
        交易日结束事件回调函数
        
        在每个交易日结束时调用，通知策略当前交易日结束。
        
        @curTDate: 当前交易日，格式为yyyymmdd，例如：20210220
        """
        # 调用策略对象的交易日结束方法，传入self和交易日
        self.__stra_info__.on_session_end(self, curTDate)

    def on_backtest_end(self):
        """
        回测结束事件回调函数
        
        在回测结束时调用，通知策略回测已完成。
        """
        # 调用策略对象的回测结束方法，传入self作为上下文
        self.__stra_info__.on_backtest_end(self)

    def on_getticks(self, stdCode:str, newTicks:WtNpTicks):
        """
        Tick数据获取回调函数（由底层调用）
        
        当底层返回Tick数据时，会调用此函数将数据存储到缓存中。
        
        @stdCode: 合约代码，例如：SSE.000001
        @newTicks: Tick数据对象，包含多个Tick数据
        """
        # 使用合约代码作为键
        key = stdCode

        # 将Tick数据存储到缓存字典中
        self.__tick_cache__[key] = newTicks

    def on_getpositions(self, stdCode:str, qty:float, frozen:float):
        """
        持仓数据获取回调函数（由底层调用）
        
        当底层返回持仓数据时，会调用此函数将数据存储到缓存中。
        
        @stdCode: 合约代码，空字符串表示全部持仓
        @qty: 持仓数量，正数表示多头，负数表示空头
        @frozen: 冻结数量，暂时未使用
        """
        # 如果合约代码为空，直接返回
        if len(stdCode) == 0:
            return
        # 将持仓数量存储到缓存字典中
        self.__pos_cache__[stdCode] = qty

    def on_getbars(self, stdCode:str, period:str, npBars:WtNpKline):
        """
        K线数据获取回调函数（由底层调用）
        
        当底层返回K线数据时，会调用此函数将数据存储到缓存中。
        
        @stdCode: 合约代码，例如：SSE.000001
        @period: K线周期，例如：m5、d
        @npBars: K线数据对象，包含多个K线数据
        """
        # 构造缓存键：合约代码#周期
        key = "%s#%s" % (stdCode, period)

        # 将K线数据存储到缓存字典中
        self.__bar_cache__[key] = npBars

    def on_tick(self, stdCode:str, newTick:POINTER(WTSTickStruct)):
        """
        Tick数据回调函数（由底层调用）
        
        当订阅的合约有新的Tick数据时，底层会调用此函数。
        此函数会将C结构体转换为Python字典，然后调用策略对象的on_tick方法。
        
        @stdCode: 合约代码，例如：SSE.000001
        @newTick: Tick数据指针，指向WTSTickStruct结构体
        """
        # 调用策略对象的on_tick方法，将C结构体转换为字典
        self.__stra_info__.on_tick(self, stdCode, newTick.contents.to_dict)

    def on_bar(self, stdCode:str, period:str, newBar:POINTER(WTSBarStruct)):
        """
        K线闭合事件响应函数（由底层调用）
        
        当订阅的K线闭合时，底层会调用此函数。
        此函数会将C结构体转换为Python字典，然后调用策略对象的on_bar方法。
        
        @stdCode: 品种代码，例如：SSE.000001
        @period: K线基础周期，例如：m5、d
        @newBar: 最新K线数据指针，指向WTSBarStruct结构体
        """        
        # 构造缓存键：合约代码#周期
        key = "%s#%s" % (stdCode, period)

        # 如果该键不在缓存中，说明策略未订阅此K线，直接返回
        if key not in self.__bar_cache__:
            return
        
        try:
            # 调用策略对象的on_bar方法，将C结构体转换为字典
            self.__stra_info__.on_bar(self, stdCode, period, newBar.contents.to_dict)
        except ValueError as ve:
            # 如果发生值错误，打印错误信息
            print(ve)
        else:
            # 如果没有异常，正常返回
            return

    def on_calculate(self):
        """
        策略计算回调函数（由底层调用）
        
        在定时触发时调用，通知策略进行核心计算。
        此函数会调用策略对象的on_calculate方法。
        """
        # 调用策略对象的计算方法，传入self作为上下文
        self.__stra_info__.on_calculate(self)

    def on_calculate_done(self):
        """
        策略计算完成回调函数（由底层调用）
        
        在策略计算完成后调用，主要用于异步场景。
        此函数会调用策略对象的on_calculate_done方法。
        """
        # 调用策略对象的计算完成方法，传入self作为上下文
        self.__stra_info__.on_calculate_done(self)

    def stra_log_text(self, message:str, level:int = 1):
        """
        输出日志
        
        向日志系统输出一条日志消息。
        
        @level: 日志级别，0-debug，1-info，2-warn，3-error，默认为1（info）
        @message: 消息内容，最大242字符，超出部分会被截断
        """
        # 调用底层包装器的日志输出方法，传入策略ID、日志级别和消息内容（截断到242字符）
        self.__wrapper__.sel_log_text(self.__id__, level, message[:242])
    
    def stra_get_tdate(self) -> int:
        """
        获取当前交易日
        
        @return: 返回当前交易日，格式如20180513（yyyymmdd）
        """
        # 调用底层包装器获取交易日
        return self.__wrapper__.sel_get_tdate()
    
    def stra_get_date(self):
        """
        获取当前日期
        
        @return: 返回当前日期，格式如20180513（yyyymmdd）
        """
        # 调用底层包装器获取日期
        return self.__wrapper__.sel_get_date()
    
    def stra_get_position_avgpx(self, stdCode:str = "") -> float:
        """
        获取当前持仓均价
        
        获取指定合约的持仓均价，如果stdCode为空则返回全部持仓的加权平均价。
        
        @stdCode: 合约代码，为空时返回全部持仓的加权平均价
        @return: 持仓均价，如果没有持仓则返回0
        """
        # 调用底层包装器获取持仓均价
        return self.__wrapper__.sel_get_position_avgpx(self.__id__, stdCode)

    def stra_get_position_profit(self, stdCode:str = "") -> float:
        """
        获取持仓浮动盈亏
        
        获取指定合约的持仓浮动盈亏，如果stdCode为空则返回全部持仓的总浮动盈亏。
        
        @stdCode: 合约代码，为空时返回全部品种的浮动盈亏
        @return: 浮动盈亏，正数表示盈利，负数表示亏损
        """
        # 调用底层包装器获取持仓浮动盈亏
        return self.__wrapper__.sel_get_position_profit(self.__id__, stdCode)

    def stra_get_fund_data(self, flag:int = 0) -> float:
        """
        获取资金数据
        
        获取策略的资金相关信息。
        
        @flag: 资金数据类型标志，0-动态权益，1-总平仓盈亏，2-总浮动盈亏，3-总手续费
        @return: 资金数据，根据flag返回对应的资金信息
        """
        # 调用底层包装器获取资金数据
        return self.__wrapper__.sel_get_fund_data(self.__id__, flag)

    def stra_get_time(self):
        """
        获取当前时间
        
        获取当前时间，24小时制，精确到分钟。
        
        @return: 返回当前时间，格式如1231（HHMM）
        """
        # 调用底层包装器获取时间
        return self.__wrapper__.sel_get_time()

    def stra_get_price(self, stdCode):
        """
        获取最新价格
        
        获取指定合约的最新价格，一般在获取了K线以后再获取该价格。
        
        @stdCode: 合约代码，例如：SSE.000001
        @return: 最新价格，如果合约不存在则返回0
        """
        # 调用底层包装器获取最新价格
        return self.__wrapper__.sel_get_price(stdCode)
    
    def stra_get_day_price(self, stdCode:str, flag:int = 0) -> float:
        """
        获取当日价格
        
        获取指定合约当日的各种价格信息。
        
        @stdCode: 合约代码，例如：SSE.000001
        @flag: 价格标记，0-开盘价，1-最高价，2-最低价，3-最新价，默认为0
        @return: 对应的价格，根据flag返回不同的价格
        """
        # 调用底层包装器获取当日价格
        return self.__wrapper__.sel_get_day_price(stdCode, flag)

    def stra_get_all_position(self):
        """
        获取全部持仓
        
        获取策略的所有持仓信息，返回一个字典，键为合约代码，值为持仓数量。
        
        @return: 持仓字典，键为合约代码，值为持仓数量（正数表示多头，负数表示空头）
        """
        # 初始化持仓缓存字典
        self.__pos_cache__ = dict()
        # 调用底层包装器获取全部持仓，数据会通过on_getpositions回调存储到缓存中
        self.__wrapper__.sel_get_all_position(self.__id__)
        # 返回持仓缓存字典
        return self.__pos_cache__
    
    def stra_prepare_bars(self, stdCode:str, period:str, count:int):
        """
        准备历史K线数据
        
        在策略初始化时调用，用于预先加载历史K线数据到缓存中。
        一般在on_init中调用，确保后续获取K线时数据已经准备好。
        
        @stdCode: 合约代码，例如：SSE.000001
        @period: K线周期，例如：m3（3分钟）、d7（7日）
        @count: 要拉取的K线条数，从最新数据往前取
        """
        # 调用底层包装器获取K线数据，数据会通过on_getbars回调存储到缓存中
        self.__wrapper__.sel_get_bars(self.__id__, stdCode, period, count)

    def stra_get_bars(self, stdCode:str, period:str, count:int) -> WtNpKline:
        """
        获取历史K线数据
        
        获取指定合约和周期的历史K线数据。
        注意：每次调用都会重新从底层获取数据，确保数据的实时性。
        
        @stdCode: 合约代码，例如：SSE.000001
        @period: K线周期，例如：m3（3分钟）、d7（7日）
        @count: 要拉取的K线条数，从最新数据往前取
        @return: 返回WtNpKline对象，包含K线数据，如果获取失败则返回None
        """
        # 构造缓存键：合约代码#周期
        key = "%s#%s" % (stdCode, period)

        # 每次都重新构造，不然onbar处理会更麻烦
        # 调用底层包装器获取K线数据，返回数据条数
        cnt =  self.__wrapper__.sel_get_bars(self.__id__, stdCode, period, count)
        # 如果数据条数为0，返回None
        if cnt == 0:
            return None

        # 从缓存中获取K线数据对象
        npBars = self.__bar_cache__[key]

        # 返回K线数据对象
        return npBars
    
    def stra_get_ticks(self, stdCode:str, count:int) -> WtNpTicks:
        """
        获取Tick数据
        
        获取指定合约的历史Tick数据。
        
        @stdCode: 合约代码，例如：SSE.000001
        @count: 要拉取的Tick数量，从最新数据往前取
        @return: 返回WtNpTicks对象，包含Tick数据，如果获取失败则返回None
        """
        # 初始化Tick缓存，创建一个空的WtNpTicks对象
        self.__tick_cache__[stdCode] = WtNpTicks()
        # 调用底层包装器获取Tick数据，返回数据条数
        cnt = self.__wrapper__.sel_get_ticks(self.__id__, stdCode, count)
        # 如果数据条数为0，返回None
        if cnt == 0:
            return None
        
        # 从缓存中获取Tick数据对象
        np_ticks = self.__tick_cache__[stdCode]
        # 返回Tick数据对象
        return np_ticks

    def stra_sub_ticks(self, stdCode:str):
        """
        订阅实时行情
        
        订阅指定合约的实时Tick行情数据。
        订阅后，当有新的Tick数据时，会触发策略的on_tick回调。
        
        @stdCode: 合约代码，例如：SSE.000001
        """
        # 调用底层包装器订阅Tick行情
        self.__wrapper__.sel_sub_ticks(stdCode)

    def stra_get_position(self, stdCode:str, bonlyvalid:bool = False, usertag:str = "") -> float:
        """
        读取当前仓位
        
        获取指定合约的当前持仓数量。
        
        @stdCode: 合约/股票代码，例如：SSE.000001
        @bonlyvalid: 是否只读取可用持仓，默认为False（读取全部持仓）
        @usertag: 入场标记，用于区分不同标记的持仓，默认为空字符串
        @return: 持仓数量，正数表示多仓，负数表示空仓，如果没有持仓则返回0
        """
        # 调用底层包装器获取持仓
        return self.__wrapper__.sel_get_position(self.__id__, stdCode, bonlyvalid, usertag)

    def stra_set_position(self, stdCode:str, qty:float, usertag:str = ""):
        """
        设置仓位
        
        设置指定合约的目标仓位，框架会自动计算需要开仓或平仓的数量。
        
        @stdCode: 合约/股票代码，例如：SSE.000001
        @qty: 目标仓位，正数表示多仓，负数表示空仓，0表示平仓
        @usertag: 用户标记，用于标识该仓位的来源或用途，默认为空字符串
        """
        # 调用底层包装器设置仓位
        self.__wrapper__.sel_set_position(self.__id__, stdCode, qty, usertag)

    def stra_get_last_entrytime(self, stdCode:str) -> int:
        """
        获取当前持仓最后一次进场时间
        
        获取指定合约当前持仓的最后一次开仓时间。
        
        @stdCode: 品种代码，例如：SSE.000001
        @return: 返回最后一次开仓的时间，格式如201903121047（yyyymmddHHMM），如果没有持仓则返回0
        """
        # 调用底层包装器获取最后进场时间
        return self.__wrapper__.sel_get_last_entertime(self.__id__, stdCode)

    def stra_get_last_entrytag(self, stdCode:str) -> str:
        """
        获取当前持仓最后一次进场标记
        
        获取指定合约当前持仓的最后一次开仓标记。
        
        @stdCode: 品种代码，例如：SSE.000001
        @return: 返回最后一次开仓标记，如果没有持仓则返回空字符串
        """
        # 调用底层包装器获取最后进场标记
        return self.__wrapper__.sel_get_last_entertag(self.__id__, stdCode)

    def stra_get_last_exittime(self, stdCode:str) -> int:
        """
        获取当前持仓最后一次出场时间
        
        获取指定合约当前持仓的最后一次平仓时间。
        
        @stdCode: 品种代码，例如：SSE.000001
        @return: 返回最后一次平仓的时间，格式如201903121047（yyyymmddHHMM），如果没有平仓记录则返回0
        """
        # 调用底层包装器获取最后出场时间
        return self.__wrapper__.sel_get_last_exittime(self.__id__, stdCode)

    def stra_get_first_entrytime(self, stdCode:str) -> int:
        """
        获取当前持仓第一次进场时间
        
        获取指定合约当前持仓的第一次开仓时间。
        
        @stdCode: 品种代码，例如：SSE.000001
        @return: 返回第一次开仓的时间，格式如201903121047（yyyymmddHHMM），如果没有持仓则返回0
        """
        # 调用底层包装器获取首次进场时间
        return self.__wrapper__.sel_get_first_entertime(self.__id__, stdCode)
        
    def user_save_data(self, key:str, val):
        """
        保存用户数据
        
        保存策略的自定义数据，数据会被持久化存储，在策略重启后可以读取。
        
        @key: 数据ID，用于标识不同的数据项
        @val: 数据值，可以直接转换成str的数据均可（如int、float、str等）
        """
        # 调用底层包装器保存用户数据，将值转换为字符串
        self.__wrapper__.sel_save_user_data(self.__id__, key, str(val))

    def user_load_data(self, key:str, defVal = None, vType = float):
        """
        读取用户数据
        
        读取之前保存的用户自定义数据。
        
        @key: 数据ID，用于标识要读取的数据项
        @defVal: 默认数据，如果找不到则返回该数据，默认为None
        @vType: 数据类型转换函数，默认为float，用于将字符串转换为指定类型
        @return: 返回值，根据vType转换为指定类型的数据
        """
        # 调用底层包装器读取用户数据，如果不存在则返回空字符串
        ret = self.__wrapper__.sel_load_user_data(self.__id__, key, "")
        # 如果返回值为空字符串，返回默认值
        if ret == "":
            return defVal

        # 使用指定的类型转换函数转换返回值
        return vType(ret)
    
    def stra_get_detail_profit(self, stdCode:str, usertag:str, flag:int = 0) -> float:
        """
        获取指定标记的持仓的盈亏
        
        获取指定合约和标记的持仓的盈亏信息。
        
        @stdCode: 合约代码，例如：SSE.000001
        @usertag: 进场标记，用于区分不同标记的持仓
        @flag: 盈亏记号，0-浮动盈亏，1-最大浮盈，-1-最大亏损（负数），2-最高浮动价格，-2-最低浮动价格，默认为0
        @return: 盈亏数值，根据flag返回不同的盈亏信息
        """
        # 调用底层包装器获取详细盈亏
        return self.__wrapper__.sel_get_detail_profit(self.__id__, stdCode, usertag, flag)

    def stra_get_detail_cost(self, stdCode:str, usertag:str) -> float:
        """
        获取指定标记的持仓的开仓价
        
        获取指定合约和标记的持仓的平均开仓价。
        
        @stdCode: 合约代码，例如：SSE.000001
        @usertag: 进场标记，用于区分不同标记的持仓
        @return: 开仓价，如果没有持仓则返回0
        """
        # 调用底层包装器获取详细成本
        return self.__wrapper__.sel_get_detail_cost(self.__id__, stdCode, usertag)

    def stra_get_detail_entertime(self, stdCode:str, usertag:str) -> int:
        """
        获取指定标记的持仓的进场时间
        
        获取指定合约和标记的持仓的进场时间。
        
        @stdCode: 合约代码，例如：SSE.000001
        @usertag: 进场标记，用于区分不同标记的持仓
        @return: 进场时间，格式如201907260932（yyyymmddHHMM），如果没有持仓则返回0
        """
        # 调用底层包装器获取详细进场时间
        return self.__wrapper__.sel_get_detail_entertime(self.__id__, stdCode, usertag)
    
    def stra_get_comminfo(self, stdCode:str):
        """
        获取品种详情
        
        获取指定合约或品种的详细信息，包括品种代码、名称、交易时段等。
        
        @stdCode: 合约代码如SHFE.ag.HOT，或者品种代码如SHFE.ag
        @return: 品种信息对象（ProductInfo），如果不存在则返回None，结构请参考ProductMgr中的ProductInfo
        """
        # 如果引擎对象不存在，返回None
        if self.__engine__ is None:
            return None
        # 调用引擎的getProductInfo方法获取品种信息
        return self.__engine__.getProductInfo(stdCode)

    def stra_get_rawcode(self, stdCode:str):
        """
        获取分月合约代码
        
        根据连续合约代码获取当前对应的分月合约代码。
        例如：SHFE.rb.HOT可能对应SHFE.rb.2305。
        
        @stdCode: 连续合约代码，例如：SHFE.ag.HOT
        @return: 分月合约代码，例如：SHFE.ag.2305，如果不存在则返回空字符串
        """
        # 如果引擎对象不存在，返回空字符串
        if self.__engine__ is None:
            return ""
        # 调用引擎的getRawStdCode方法获取原始合约代码
        return self.__engine__.getRawStdCode(stdCode)

    def stra_get_sessioninfo(self, stdCode:str):
        """
        获取交易时段信息
        
        获取指定合约或品种的交易时段信息，包括交易时间段、集合竞价时间等。
        
        @stdCode: 合约代码如SHFE.ag.HOT，或者品种代码如SHFE.ag
        @return: 交易时段信息对象（SessionInfo），如果不存在则返回None，结构请参考SessionMgr中的SessionInfo
        """
        # 如果引擎对象不存在，返回None
        if self.__engine__ is None:
            return None
        # 调用引擎的getSessionByCode方法获取交易时段信息
        return self.__engine__.getSessionByCode(stdCode)

    def stra_get_contract(self, stdCode:str):
        """
        获取合约详情
        
        获取指定合约的详细信息，包括合约代码、名称、上市日期、到期日等。
        
        @stdCode: 合约代码如SHFE.ag.HOT，或者品种代码如SHFE.ag
        @return: 合约信息对象（ContractInfo），如果不存在则返回None，结构请参考ContractMgr中的ContractInfo
        """
        # 如果引擎对象不存在，返回None
        if self.__engine__ is None:
            return None
        # 调用引擎的getContractInfo方法获取合约信息
        return self.__engine__.getContractInfo(stdCode)

    def stra_get_all_codes(self) -> list:
        """
        获取全部合约代码列表
        
        获取引擎中所有可用的合约代码列表。
        
        @return: 合约代码列表，如果引擎不存在则返回空列表
        """
        # 如果引擎对象不存在，返回空列表
        if self.__engine__ is None:
            return []
        # 调用引擎的getAllCodes方法获取全部合约代码
        return self.__engine__.getAllCodes()
    
    def stra_get_codes_by_product(self, stdPID:str) -> list:
        """
        根据品种代码读取合约列表
        
        获取指定品种下的所有合约代码列表。
        
        @stdPID: 品种代码，格式如SHFE.rb
        @return: 合约代码列表，如果引擎不存在则返回空列表
        """
        # 如果引擎对象不存在，返回空列表
        if self.__engine__ is None:
            return []
        # 调用引擎的getCodesByProduct方法获取合约列表
        return self.__engine__.getCodesByProduct(stdPID)
    
    def stra_get_codes_by_underlying(self, underlying:str) -> list:
        """
        根据标的资产读取合约列表（期权专用）
        
        获取指定标的资产下的所有期权合约代码列表。
        
        @underlying: 标的资产代码，格式如CFFEX.IM2304
        @return: 合约代码列表，如果引擎不存在则返回空列表
        """
        # 如果引擎对象不存在，返回空列表
        if self.__engine__ is None:
            return []
        # 调用引擎的getCodesByUnderlying方法获取合约列表
        return self.__engine__.getCodesByUnderlying(underlying)
