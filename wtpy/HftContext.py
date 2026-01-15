"""
高频策略上下文模块

本模块提供了高频交易（HFT）策略的上下文类（HftContext），是策略可以直接访问的唯一对象。
策略通过Context对象调用框架提供的所有接口，包括数据查询、下单、持仓管理等。
HFT策略需要处理Tick级别的数据，包括逐笔委托、逐笔成交、委托队列等高频数据。

主要功能：
1. 时间接口：获取当前日期、时间、秒数等
2. 数据接口：获取K线、Tick、委托队列、逐笔委托、逐笔成交等数据
3. 交易接口：买入、卖出、撤单等操作
4. 工具接口：日志输出、用户数据存储、品种信息查询等
"""

# 导入ctypes模块的POINTER类型，用于处理C结构体指针
from ctypes import POINTER
# 导入交易时段信息类
from wtpy.SessionMgr import SessionInfo
# 导入核心数据结构定义
from wtpy.WtCoreDefs import WTSBarStruct, WTSOrdDtlStruct, WTSOrdQueStruct, WTSTickStruct, WTSTransStruct
# 导入数据定义模块中的各种数据结构
from wtpy.WtDataDefs import WtNpKline, WtNpOrdDetails, WtNpOrdQueues, WtNpTicks, WtNpTransactions

class HftContext:
    """
    高频策略上下文类
    
    Context是策略可以直接访问的唯一对象，策略所有的接口都通过Context对象调用。
    Context类包括以下几类接口：
    1、时间接口（日期、时间等），接口格式如：stra_xxx
    2、数据接口（K线、财务等），接口格式如：stra_xxx
    3、下单接口（设置目标仓位、直接下单等），接口格式如：stra_xxx
    """

    def __init__(self, id:int, stra, wrapper, engine):
        """
        构造函数
        
        初始化高频策略上下文，设置策略对象、底层包装器、引擎等引用。
        
        @id: 策略ID，由引擎分配的唯一标识符
        @stra: 策略对象，继承自BaseHftStrategy的策略实例
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
        self.__tick_cache__ = dict()
        # 委托队列数据缓存字典，键为合约代码，值为WtNpOrdQueues对象
        self.__ordque_cache__ = dict()
        # 逐笔委托数据缓存字典，键为合约代码，值为WtNpOrdDetails对象
        self.__orddtl_cache__ = dict()
        # 逐笔成交数据缓存字典，键为合约代码，值为WtNpTransactions对象
        self.__trans_cache__ = dict()
        # 策略名称，从策略对象获取
        self.__sname__ = stra.name()
        # 交易引擎对象引用，提供引擎级别的功能
        self.__engine__ = engine

        # 是否为回测模式标志，从引擎获取
        self.is_backtest = self.__engine__.is_backtest

    @property
    def id(self):
        """
        获取策略ID属性
        
        @return: 返回策略ID
        """
        return self.__id__

    def on_init(self):
        """
        初始化回调函数（由底层调用）
        
        在策略启动时调用，一般用于系统启动的时候。
        此函数会调用策略对象的on_init方法。
        """
        # 调用策略对象的初始化方法，传入self作为上下文
        self.__stra_info__.on_init(self)

    def on_session_begin(self, curTDate:int):
        """
        交易日开始事件回调函数（由底层调用）
        
        在每个交易日开始时调用，通知策略新的交易日开始。
        
        @curTDate: 当前交易日，格式为yyyymmdd，例如：20210220
        """
        # 调用策略对象的交易日开始方法，传入self和交易日
        self.__stra_info__.on_session_begin(self, curTDate)

    def on_session_end(self, curTDate:int):
        """
        交易日结束事件回调函数（由底层调用）
        
        在每个交易日结束时调用，通知策略当前交易日结束。
        
        @curTDate: 当前交易日，格式为yyyymmdd，例如：20210220
        """
        # 调用策略对象的交易日结束方法，传入self和交易日
        self.__stra_info__.on_session_end(self, curTDate)

    def on_backtest_end(self):
        """
        回测结束事件回调函数（由底层调用）
        
        在回测结束时调用，通知策略回测已完成。
        """
        # 调用策略对象的回测结束方法，传入self作为上下文
        self.__stra_info__.on_backtest_end(self)

    def on_getticks(self, stdCode:str, newTicks:WtNpTicks):
        """
        Tick数据获取回调函数（由底层调用）
        
        当底层返回Tick数据时，会调用此函数将数据存储到缓存中。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newTicks: Tick数据对象，包含多个Tick数据
        """
        # 将Tick数据存储到缓存字典中，使用合约代码作为键
        self.__tick_cache__[stdCode] = newTicks

    def on_getbars(self, stdCode:str, period:str, npBars:WtNpKline):
        """
        K线数据获取回调函数（由底层调用）
        
        当底层返回K线数据时，会调用此函数将数据存储到缓存中。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
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
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newTick: Tick数据指针，指向WTSTickStruct结构体
        """
        # 调用策略对象的on_tick方法，将C结构体转换为字典
        self.__stra_info__.on_tick(self, stdCode, newTick.contents.to_dict)

    def on_order_queue(self, stdCode:str, newOrdQue:POINTER(WTSOrdQueStruct)):
        """
        委托队列数据回调函数（由底层调用）
        
        当订阅的合约有新的委托队列数据时，底层会调用此函数。
        此函数会将C结构体转换为Python元组，然后调用策略对象的on_order_queue方法。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newOrdQue: 委托队列数据指针，指向WTSOrdQueStruct结构体
        """
        # 调用策略对象的on_order_queue方法，将C结构体转换为元组
        self.__stra_info__.on_order_queue(self, stdCode, newOrdQue.contents.to_tuple())

    def on_get_order_queue(self, stdCode:str, newOdrQues:WtNpOrdQueues):
        """
        委托队列数据获取回调函数（由底层调用）
        
        当底层返回委托队列数据时，会调用此函数将数据存储到缓存中。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newOdrQues: 委托队列数据对象，包含多个委托队列数据
        """
        # 将委托队列数据存储到缓存字典中，使用合约代码作为键
        self.__ordque_cache__[stdCode] = newOdrQues

    def on_order_detail(self, stdCode:str, newOrdDtl:POINTER(WTSOrdDtlStruct)):
        """
        逐笔委托数据回调函数（由底层调用）
        
        当订阅的合约有新的逐笔委托数据时，底层会调用此函数。
        此函数会将C结构体转换为Python元组，然后调用策略对象的on_order_detail方法。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newOrdDtl: 逐笔委托数据指针，指向WTSOrdDtlStruct结构体
        """
        # 调用策略对象的on_order_detail方法，将C结构体转换为元组
        self.__stra_info__.on_order_detail(self, stdCode, newOrdDtl.contents.to_tuple())

    def on_get_order_detail(self, stdCode:str, newOrdDtls:WtNpOrdDetails):
        """
        逐笔委托数据获取回调函数（由底层调用）
        
        当底层返回逐笔委托数据时，会调用此函数将数据存储到缓存中。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newOrdDtls: 逐笔委托数据对象，包含多个逐笔委托数据
        """
        # 将逐笔委托数据存储到缓存字典中，使用合约代码作为键
        self.__orddtl_cache__[stdCode] = newOrdDtls

    def on_transaction(self, stdCode:str, newTrans:POINTER(WTSTransStruct)):
        """
        逐笔成交数据回调函数（由底层调用）
        
        当订阅的合约有新的逐笔成交数据时，底层会调用此函数。
        此函数会将C结构体转换为Python元组，然后调用策略对象的on_transaction方法。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newTrans: 逐笔成交数据指针，指向WTSTransStruct结构体
        """
        # 调用策略对象的on_transaction方法，将C结构体转换为元组
        self.__stra_info__.on_transaction(self, stdCode, newTrans.contents.to_tuple())

    def on_get_transaction(self, stdCode:str, newTranses:WtNpTransactions):
        """
        逐笔成交数据获取回调函数（由底层调用）
        
        当底层返回逐笔成交数据时，会调用此函数将数据存储到缓存中。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newTranses: 逐笔成交数据对象，包含多个逐笔成交数据
        """
        # 使用合约代码作为键
        key = stdCode
        # 将逐笔成交数据存储到缓存字典中
        self.__trans_cache__[key] = newTranses

    def on_channel_ready(self):
        """
        交易通道就绪回调函数（由底层调用）
        
        当交易通道连接成功并准备就绪时调用，通知策略可以开始下单。
        """
        # 调用策略对象的交易通道就绪方法
        self.__stra_info__.on_channel_ready(self)

    def on_channel_lost(self):
        """
        交易通道丢失回调函数（由底层调用）
        
        当交易通道断开连接时调用，通知策略无法进行下单操作。
        """
        # 调用策略对象的交易通道丢失方法
        self.__stra_info__.on_channel_lost(self)

    def on_entrust(self, localid:int, stdCode:str, bSucc:bool, msg:str, userTag:str):
        """
        下单结果回报回调函数（由底层调用）
        
        当策略下单后，会收到下单结果的回报。
        此函数会调用策略对象的on_entrust方法，通知策略下单是否成功。
        
        @localid: 本地订单ID，下单时返回的订单标识
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @bSucc: 下单是否成功，True表示成功，False表示失败
        @msg: 下单结果描述信息，如果失败则包含失败原因
        @userTag: 用户标记，下单时传入的自定义标记
        """
        # 调用策略对象的下单结果回报方法
        self.__stra_info__.on_entrust(self, localid, stdCode, bSucc, msg, userTag)

    def on_position(self, stdCode:str, isLong:bool, prevol:float, preavail:float, newvol:float, newavail:float):
        """
        初始持仓回报回调函数（由底层调用）
        
        在策略启动时调用，用于通知策略当前的持仓情况。
        注意：此回调只在实盘环境中有效，回测时初始仓位都是空。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @isLong: 是否为多头持仓，True表示多头，False表示空头
        @prevol: 昨日持仓数量
        @preavail: 可用昨日持仓数量
        @newvol: 今日持仓数量
        @newavail: 可用今日持仓数量
        """
        # 调用策略对象的初始持仓回报方法
        self.__stra_info__.on_position(self, stdCode, isLong, prevol, preavail, newvol, newavail)

    def on_order(self, localid:int, stdCode:str, isBuy:bool, totalQty:float, leftQty:float, price:float, isCanceled:bool, userTag:str):
        """
        订单回报回调函数（由底层调用）
        
        当订单状态发生变化时调用，如订单被部分成交、全部成交、被撤销等。
        此函数会调用策略对象的on_order方法，通知策略订单状态变化。
        
        @localid: 本地订单ID，下单时返回的订单标识
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @isBuy: 是否为买入订单，True表示买入，False表示卖出
        @totalQty: 订单总数量
        @leftQty: 剩余未成交数量
        @price: 订单价格
        @isCanceled: 订单是否已被撤销，True表示已撤销，False表示未撤销
        @userTag: 用户标记，下单时传入的自定义标记
        """
        # 调用策略对象的订单回报方法
        self.__stra_info__.on_order(self, localid, stdCode, isBuy, totalQty, leftQty, price, isCanceled, userTag)

    def on_trade(self, localid:int, stdCode:str, isBuy:bool, qty:float, price:float, userTag:str):
        """
        成交回报回调函数（由底层调用）
        
        当订单有成交时调用，每次成交都会触发一次此回调。
        此函数会调用策略对象的on_trade方法，通知策略订单成交情况。
        
        @localid: 本地订单ID，下单时返回的订单标识
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @isBuy: 是否为买入成交，True表示买入，False表示卖出
        @qty: 成交数量
        @price: 成交价格
        @userTag: 用户标记，下单时传入的自定义标记
        """
        # 调用策略对象的成交回报方法
        self.__stra_info__.on_trade(self, localid, stdCode, isBuy, qty, price, userTag)
        
    def on_bar(self, stdCode:str, period:str, newBar:POINTER(WTSBarStruct)):
        """
        K线闭合事件响应函数（由底层调用）
        
        当订阅的K线闭合时，底层会调用此函数。
        此函数会将C结构体转换为Python字典，然后调用策略对象的on_bar方法。
        
        @stdCode: 品种代码，例如：SHFE.rb.2305
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

    def stra_log_text(self, message:str, level:int = 1):
        """
        输出日志
        
        向日志系统输出一条日志消息。
        
        @level: 日志级别，0-debug，1-info，2-warn，3-error，默认为1（info）
        @message: 消息内容，最大242字符，超出部分会被截断
        """
        # 调用底层包装器的日志输出方法，传入策略ID、日志级别和消息内容（截断到242字符）
        self.__wrapper__.hft_log_text(self.__id__, level, message[:242])
        
    def stra_get_date(self):
        """
        获取当前日期
        
        获取当前日期，用于判断交易日等。
        
        @return: 返回当前日期，格式如20180513（yyyymmdd）
        """
        # 调用底层包装器获取日期
        return self.__wrapper__.hft_get_date()

    def stra_get_time(self):
        """
        获取当前时间
        
        获取当前时间，24小时制，精确到分钟。
        
        @return: 返回当前时间，格式如1231（HHMM）
        """
        # 调用底层包装器获取时间
        return self.__wrapper__.hft_get_time()

    def stra_get_secs(self):
        """
        获取当前秒数
        
        获取当前时间，精确到毫秒。
        用于高频交易中需要精确时间戳的场景。
        
        @return: 返回当前秒数（包含毫秒），格式如1234567890（时间戳）
        """
        # 调用底层包装器获取秒数（精确到毫秒）
        return self.__wrapper__.hft_get_secs()

    def stra_get_price(self, stdCode):
        """
        获取最新价格
        
        获取指定合约的最新价格，一般在获取了K线以后再获取该价格。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @return: 最新价格，如果合约不存在则返回0
        """
        # 调用底层包装器获取最新价格
        return self.__wrapper__.hft_get_price(stdCode)
    
    def stra_prepare_bars(self, stdCode:str, period:str, count:int):
        """
        准备历史K线数据
        
        在策略初始化时调用，用于预先加载历史K线数据到缓存中。
        一般在on_init中调用，确保后续获取K线时数据已经准备好。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @period: K线周期，例如：m3（3分钟）、d7（7日）
        @count: 要拉取的K线条数，从最新数据往前取
        """
        # 调用底层包装器获取K线数据，数据会通过on_getbars回调存储到缓存中
        self.__wrapper__.hft_get_bars(self.__id__, stdCode, period, count)

    def stra_get_bars(self, stdCode:str, period:str, count:int) -> WtNpKline:
        """
        获取历史K线数据
        
        获取指定合约和周期的历史K线数据。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @period: K线周期，例如：m3（3分钟）、d7（7日）
        @count: 要拉取的K线条数，从最新数据往前取
        @return: 返回WtNpKline对象，包含K线数据，如果获取失败则返回None
        """
        # 构造缓存键：合约代码#周期
        key = "%s#%s" % (stdCode, period)

        # 调用底层包装器获取K线数据，返回数据条数
        cnt =  self.__wrapper__.hft_get_bars(self.__id__, stdCode, period, count)
        # 如果数据条数为0，返回None
        if cnt == 0:
            return None

        # 从缓存中获取K线数据对象并返回
        return self.__bar_cache__[key]

    def stra_get_ticks(self, stdCode:str, count:int) -> WtNpTicks:
        """
        获取Tick数据
        
        获取指定合约的历史Tick数据。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @count: 要拉取的Tick数量，从最新数据往前取
        @return: 返回WtNpTicks对象，包含Tick数据，如果获取失败则返回None
        """
        # 调用底层包装器获取Tick数据，返回数据条数
        cnt = self.__wrapper__.hft_get_ticks(self.__id__, stdCode, count)
        # 如果数据条数为0，返回None
        if cnt == 0:
            return None
        
        # 从缓存中获取Tick数据对象并返回
        return self.__tick_cache__[stdCode]

    def stra_get_order_queue(self, stdCode:str, count:int) -> WtNpOrdQueues:
        """
        获取委托队列数据
        
        获取指定合约的历史委托队列数据。
        委托队列数据包含某个价格档位的委托队列信息。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @count: 要拉取的委托队列数量，从最新数据往前取
        @return: 返回WtNpOrdQueues对象，包含委托队列数据，如果获取失败则返回None
        """
        # 调用底层包装器获取委托队列数据，返回数据条数
        cnt = self.__wrapper__.hft_get_ordque(self.__id__, stdCode, count)
        # 如果数据条数为0，返回None
        if cnt == 0:
            return None
        
        # 从缓存中获取委托队列数据对象并返回
        return  self.__ordque_cache__[stdCode]

    def stra_get_order_detail(self, stdCode:str, count:int) -> WtNpOrdDetails:
        """
        获取逐笔委托数据
        
        获取指定合约的历史逐笔委托数据。
        逐笔委托数据包含每笔委托的详细信息。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @count: 要拉取的逐笔委托数量，从最新数据往前取
        @return: 返回WtNpOrdDetails对象，包含逐笔委托数据，如果获取失败则返回None
        """
        # 如果缓存中已有数据，直接返回（这里做一个数据长度处理）
        if stdCode in self.__orddtl_cache__:
            return self.__orddtl_cache__[stdCode]

        # 调用底层包装器获取逐笔委托数据，返回数据条数
        cnt = self.__wrapper__.hft_get_orddtl(self.__id__, stdCode, count)
        # 如果数据条数为0，返回None
        if cnt == 0:
            return None
        
        # 从缓存中获取逐笔委托数据对象并返回
        return self.__orddtl_cache__[stdCode]

    def stra_get_transaction(self, stdCode:str, count:int) -> WtNpTransactions:
        """
        获取逐笔成交数据
        
        获取指定合约的历史逐笔成交数据。
        逐笔成交数据包含每笔成交的详细信息。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @count: 要拉取的逐笔成交数量，从最新数据往前取
        @return: 返回WtNpTransactions对象，包含逐笔成交数据，如果获取失败则返回None
        """
        # 调用底层包装器获取逐笔成交数据，返回数据条数
        cnt = self.__wrapper__.hft_get_trans(self.__id__, stdCode, count)
        # 如果数据条数为0，返回None
        if cnt == 0:
            return None
        
        # 从缓存中获取逐笔成交数据对象并返回
        return self.__trans_cache__[stdCode]

    def stra_get_position(self, stdCode:str, bonlyvalid:bool = False):
        """
        读取当前仓位
        
        获取指定合约的当前持仓数量。
        
        @stdCode: 合约/股票代码，例如：SHFE.rb.2305
        @bonlyvalid: 是否只读取可用持仓，默认为False（读取全部持仓）
        @return: 持仓数量，正数表示多仓，负数表示空仓，如果没有持仓则返回0
        """
        # 调用底层包装器获取持仓
        return self.__wrapper__.hft_get_position(self.__id__, stdCode, bonlyvalid)

    def stra_get_position_profit(self, stdCode:str = ""):
        """
        读取指定持仓的浮动盈亏
        
        获取指定合约的持仓浮动盈亏，如果stdCode为空则返回全部持仓的总浮动盈亏。
        
        @stdCode: 合约/股票代码，为空时返回全部持仓的总浮动盈亏
        @return: 浮动盈亏，正数表示盈利，负数表示亏损
        """
        # 调用底层包装器获取持仓浮动盈亏
        return self.__wrapper__.hft_get_position_profit(self.__id__, stdCode)

    def stra_get_position_avgpx(self, stdCode:str = ""):
        """
        读取指定持仓的持仓均价
        
        获取指定合约的持仓均价，如果stdCode为空则返回全部持仓的加权平均价。
        
        @stdCode: 合约/股票代码，为空时返回全部持仓的加权平均价
        @return: 持仓均价，如果没有持仓则返回0
        """
        # 调用底层包装器获取持仓均价
        return self.__wrapper__.hft_get_position_avgpx(self.__id__, stdCode)

    def stra_get_undone(self, stdCode:str):
        """
        获取未完成订单数量
        
        获取指定合约的未完成订单（未成交且未撤销）数量。
        
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @return: 未完成订单数量
        """
        # 调用底层包装器获取未完成订单数量
        return self.__wrapper__.hft_get_undone(self.__id__, stdCode)


    def user_save_data(self, key:str, val):
        """
        保存用户数据
        
        保存策略的自定义数据，数据会被持久化存储，在策略重启后可以读取。
        
        @key: 数据ID，用于标识不同的数据项
        @val: 数据值，可以直接转换成str的数据均可（如int、float、str等）
        """
        # 调用底层包装器保存用户数据，将值转换为字符串
        self.__wrapper__.hft_save_user_data(self.__id__, key, str(val))

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
        ret = self.__wrapper__.hft_load_user_data(self.__id__, key, "")
        # 如果返回值为空字符串，返回默认值
        if ret == "":
            return defVal

        # 使用指定的类型转换函数转换返回值
        return vType(ret)

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
        
    def stra_get_sessinfo(self, stdCode:str) -> SessionInfo:
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

    def stra_sub_ticks(self, stdCode:str):
        """
        订阅实时行情数据
        
        订阅指定合约的实时Tick行情数据。
        注意：获取K线和tick数据的时候会自动订阅，这里只需要订阅额外要检测的品种即可。
        
        @stdCode: 品种代码，例如：SHFE.rb.2305
        """
        # 调用底层包装器订阅Tick行情
        self.__wrapper__.hft_sub_ticks(self.__id__, stdCode)

    def stra_cancel(self, localid:int):
        """
        撤销指定订单
        
        撤销指定的订单，订单必须处于未完全成交状态。
        
        @localid: 下单时返回的本地订单号
        @return: 撤销是否成功，True表示成功，False表示失败
        """
        # 调用底层包装器撤销订单
        return self.__wrapper__.hft_cancel(self.__id__, localid)

    def stra_cancel_all(self, stdCode:str, isBuy:bool):
        """
        撤销指定品种的全部买入订单或卖出订单
        
        撤销指定合约的所有买入订单或卖出订单。
        
        @stdCode: 品种代码，例如：SHFE.rb.2305
        @isBuy: 是否撤销买入订单，True表示撤销买入订单，False表示撤销卖出订单
        @return: 返回被撤销的订单ID列表
        """
        # 调用底层包装器撤销全部订单，返回订单ID字符串（逗号分隔）
        idstr = self.__wrapper__.hft_cancel_all(self.__id__, stdCode, isBuy)
        # 如果返回值为空字符串，返回空列表
        if len(idstr) == 0:
            return list()

        # 将订单ID字符串按逗号分割成列表
        ids = idstr.split(",")
        # 创建订单ID整数列表
        localids = list()
        # 遍历订单ID字符串列表，转换为整数
        for localid in ids:
            localids.append(int(localid))
        # 返回订单ID整数列表
        return localids

    def stra_buy(self, stdCode:str, price:float, qty:float, userTag:str = "", flag:int = 0):
        """
        买入指令
        
        下达买入订单，支持限价、市价、FAK、FOK等多种订单类型。
        
        @stdCode: 品种代码，例如：SHFE.rb.2305
        @price: 买入价格，0为市价
        @qty: 买入数量
        @userTag: 用户标记，用于标识订单的来源或用途，默认为空字符串
        @flag: 下单标志，0-normal（普通订单），1-fak（立即成交剩余撤销），2-fok（全部成交否则撤销），默认为0
        @return: 返回订单ID列表，如果下单失败则返回空列表
        """
        # 调用底层包装器买入订单，返回订单ID字符串（逗号分隔）
        idstr = self.__wrapper__.hft_buy(self.__id__, stdCode, price, qty, userTag, flag)
        # 如果返回值为空字符串，返回空列表
        if len(idstr) == 0:
            return list()
            
        # 将订单ID字符串按逗号分割成列表
        ids = idstr.split(",")
        # 创建订单ID整数列表
        localids = list()
        # 遍历订单ID字符串列表，转换为整数
        for localid in ids:
            localids.append(int(localid))
        # 返回订单ID整数列表
        return localids

    def stra_sell(self, stdCode:str, price:float, qty:float, userTag:str = "", flag:int = 0):
        """
        卖出指令
        
        下达卖出订单，支持限价、市价、FAK、FOK等多种订单类型。
        
        @stdCode: 品种代码，例如：SHFE.rb.2305
        @price: 卖出价格，0为市价
        @qty: 卖出数量
        @userTag: 用户标记，用于标识订单的来源或用途，默认为空字符串
        @flag: 下单标志，0-normal（普通订单），1-fak（立即成交剩余撤销），2-fok（全部成交否则撤销），默认为0
        @return: 返回订单ID列表，如果下单失败则返回空列表
        """
        # 调用底层包装器卖出订单，返回订单ID字符串（逗号分隔）
        idstr = self.__wrapper__.hft_sell(self.__id__, stdCode, price, qty, userTag, flag)
        # 如果返回值为空字符串，返回空列表
        if len(idstr) == 0:
            return list()
            
        # 将订单ID字符串按逗号分割成列表
        ids = idstr.split(",")
        # 创建订单ID整数列表
        localids = list()
        # 遍历订单ID字符串列表，转换为整数
        for localid in ids:
            localids.append(int(localid))
        # 返回订单ID整数列表
        return localids
    
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
