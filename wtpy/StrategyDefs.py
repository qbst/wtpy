"""
策略定义模块

本模块定义了所有策略的基类，包括CTA策略、HFT策略和选股策略。
这些基类提供了策略开发的标准接口和回调函数框架，所有自定义策略都需要继承这些基类。
策略开发者只需要重写感兴趣的回调函数，实现自己的交易逻辑即可。

主要功能：
1. BaseCtaStrategy：CTA（Commodity Trading Advisor）策略基类，用于中低频交易策略
2. BaseHftStrategy：HFT（High Frequency Trading）策略基类，用于高频交易策略
3. BaseSelStrategy：选股策略基类，用于多因子选股策略
"""

# 导入策略上下文类，用于在策略中访问框架功能
from wtpy import CtaContext, SelContext, HftContext

class BaseCtaStrategy:
    """
    CTA策略基础类
    
    所有CTA策略的基类，提供了CTA策略开发的标准接口。
    CTA策略主要用于中低频交易，通常基于K线数据进行决策。
    策略开发者需要继承此类，并重写感兴趣的回调函数来实现交易逻辑。
    """
    
    def __init__(self, name:str):
        """
        构造函数
        
        初始化CTA策略，设置策略名称。
        
        @name: 策略名称，用于标识该策略，必须唯一
        """
        # 保存策略名称，使用双下划线前缀表示私有属性
        self.__name__ = name
        
    
    def name(self) -> str:
        """
        获取策略名称
        
        @return: 返回策略名称字符串
        """
        return self.__name__


    def on_init(self, context:CtaContext):
        """
        策略初始化回调函数
        
        在策略启动时调用，用于加载自定义数据、初始化指标等准备工作。
        这是策略的第一个回调函数，通常在这里订阅行情、准备历史数据等。
        
        @context: 策略运行上下文对象，提供数据查询、下单等接口
        """
        return

    def on_session_begin(self, context:CtaContext, curTDate:int):
        """
        交易日开始事件回调函数
        
        在每个交易日开始时调用，用于执行每日的初始化工作。
        例如：重置每日计数器、加载当日数据等。
        
        @context: 策略运行上下文对象
        @curTDate: 当前交易日，格式为yyyymmdd，例如：20210220
        """
        return

    def on_session_end(self, context:CtaContext, curTDate:int):
        """
        交易日结束事件回调函数
        
        在每个交易日结束时调用，用于执行每日的清理工作。
        例如：保存数据、计算每日统计等。
        
        @context: 策略运行上下文对象
        @curTDate: 当前交易日，格式为yyyymmdd，例如：20210220
        """
        return
    
    def on_calculate(self, context:CtaContext):
        """
        策略计算回调函数
        
        在主K线闭合时调用，这是策略的核心计算模块。
        通常在这里进行技术指标计算、信号生成、仓位管理等逻辑。
        只有订阅的主K线闭合时才会触发此回调。
        
        @context: 策略运行上下文对象
        """
        return

    def on_calculate_done(self, context:CtaContext):
        """
        策略计算完成回调函数
        
        在策略计算完成后调用，主要用于异步场景。
        在异步模式下，此回调在on_calculate之后触发，用于将计算完成的信号传递给底层。
        目前主要用于强化学习的训练场景。
        
        @context: 策略运行上下文对象
        """
        return


    def on_tick(self, context:CtaContext, stdCode:str, newTick:dict):
        """
        Tick数据回调函数
        
        当订阅的合约有新的Tick数据时调用。
        在实盘环境中，每笔行情进来就会立即调用此函数。
        在回测环境中，是模拟的逐笔数据。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newTick: 最新Tick数据字典，包含价格、成交量、买卖盘等信息
        """
        return

    def on_bar(self, context:CtaContext, stdCode:str, period:str, newBar:dict):
        """
        K线闭合回调函数
        
        当订阅的K线闭合时调用，可以获取到最新闭合的K线数据。
        注意：此回调在on_calculate之前触发，可以在这里进行K线级别的数据处理。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @period: K线周期，例如：m5（5分钟）、d（日线）
        @newBar: 最新闭合的K线数据字典，包含开高低收、成交量等信息
        """
        return

    def on_backtest_end(self, context:CtaContext):
        """
        回测结束回调函数
        
        在回测结束时调用，只在回测框架下会触发。
        可以在这里进行回测结果的统计、保存等操作。
        
        @context: 策略运行上下文对象
        """
        return

    def on_condition_triggered(self, context:CtaContext, stdCode:str, target:float, price:float, usertag:str):
        """
        条件单触发回调函数
        
        当设置的条件单被触发时调用。
        条件单是一种特殊的订单类型，当价格达到指定条件时自动触发。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @target: 触发后的最终目标仓位，正数表示多头，负数表示空头
        @price: 触发价格，即条件单被触发时的价格
        @usertag: 用户标记，用于标识该条件单的来源或用途
        """
        return

class BaseHftStrategy:
    """
    HFT策略基础类
    
    所有HFT（高频交易）策略的基类，提供了HFT策略开发的标准接口。
    HFT策略主要用于高频交易，需要处理Tick级别的数据，包括逐笔委托、逐笔成交等。
    策略开发者需要继承此类，并重写感兴趣的回调函数来实现交易逻辑。
    """
    
    def __init__(self, name:str):
        """
        构造函数
        
        初始化HFT策略，设置策略名称。
        
        @name: 策略名称，用于标识该策略，必须唯一
        """
        # 保存策略名称，使用双下划线前缀表示私有属性
        self.__name__ = name
        
    
    def name(self) -> str:
        """
        获取策略名称
        
        @return: 返回策略名称字符串
        """
        return self.__name__


    def on_init(self, context:HftContext):
        """
        策略初始化回调函数
        
        在策略启动时调用，用于加载自定义数据、初始化指标等准备工作。
        这是策略的第一个回调函数，通常在这里订阅行情、准备历史数据等。
        
        @context: 策略运行上下文对象，提供数据查询、下单等接口
        """
        return
    
    def on_session_begin(self, context:HftContext, curTDate:int):
        """
        交易日开始事件回调函数
        
        在每个交易日开始时调用，用于执行每日的初始化工作。
        例如：重置每日计数器、加载当日数据等。
        
        @context: 策略运行上下文对象
        @curTDate: 当前交易日，格式为yyyymmdd，例如：20210220
        """
        return

    def on_session_end(self, context:HftContext, curTDate:int):
        """
        交易日结束事件回调函数
        
        在每个交易日结束时调用，用于执行每日的清理工作。
        例如：保存数据、计算每日统计等。
        
        @context: 策略运行上下文对象
        @curTDate: 当前交易日，格式为yyyymmdd，例如：20210220
        """
        return

    def on_backtest_end(self, context:CtaContext):
        """
        回测结束回调函数
        
        在回测结束时调用，只在回测框架下会触发。
        注意：参数类型标注为CtaContext，但实际传入的是HftContext，这是历史遗留问题。
        
        @context: 策略运行上下文对象
        """
        return

    def on_tick(self, context:HftContext, stdCode:str, newTick:dict):
        """
        Tick数据回调函数
        
        当订阅的合约有新的Tick数据时调用。
        Tick数据包含最新的价格、成交量、买卖盘等信息。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newTick: 最新Tick数据字典，包含价格、成交量、买卖盘等信息
        """
        return

    def on_order_detail(self, context:HftContext, stdCode:str, newOrdQue:dict):
        """
        逐笔委托数据回调函数
        
        当订阅的合约有新的逐笔委托数据时调用。
        逐笔委托数据包含每笔委托的详细信息，如委托价格、数量、方向等。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newOrdQue: 最新逐笔委托数据字典，包含委托的详细信息
        """
        return

    def on_order_queue(self, context:HftContext, stdCode:str, newOrdQue:dict):
        """
        委托队列数据回调函数
        
        当订阅的合约有新的委托队列数据时调用。
        委托队列数据包含某个价格档位的委托队列信息，如该价格档位的总委托量等。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newOrdQue: 最新委托队列数据字典，包含委托队列的详细信息
        """
        return

    def on_transaction(self, context:HftContext, stdCode:str, newTrans:dict):
        """
        逐笔成交数据回调函数
        
        当订阅的合约有新的逐笔成交数据时调用。
        逐笔成交数据包含每笔成交的详细信息，如成交价格、数量、方向等。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @newTrans: 最新逐笔成交数据字典，包含成交的详细信息
        """
        return

    def on_bar(self, context:HftContext, stdCode:str, period:str, newBar:dict):
        """
        K线闭合回调函数
        
        当订阅的K线闭合时调用，可以获取到最新闭合的K线数据。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @period: K线周期，例如：m5（5分钟）、d（日线）
        @newBar: 最新闭合的K线数据字典，包含开高低收、成交量等信息
        """
        return

    def on_channel_ready(self, context:HftContext):
        """
        交易通道就绪回调函数
        
        当交易通道连接成功并准备就绪时调用。
        此时可以开始下单操作。
        
        @context: 策略运行上下文对象
        """
        return

    def on_channel_lost(self, context:HftContext):
        """
        交易通道丢失回调函数
        
        当交易通道断开连接时调用。
        此时无法进行下单操作，需要等待通道重新连接。
        
        @context: 策略运行上下文对象
        """
        return

    def on_entrust(self, context:HftContext, localid:int, stdCode:str, bSucc:bool, msg:str, userTag:str):
        """
        下单结果回报回调函数
        
        当策略下单后，会收到下单结果的回报。
        此回调用于通知策略下单是否成功，以及失败的原因。
        
        @context: 策略运行上下文对象
        @localid: 本地订单ID，下单时返回的订单标识
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @bSucc: 下单是否成功，True表示成功，False表示失败
        @msg: 下单结果描述信息，如果失败则包含失败原因
        @userTag: 用户标记，下单时传入的自定义标记
        """
        return

    def on_order(self, context:HftContext, localid:int, stdCode:str, isBuy:bool, totalQty:float, leftQty:float, price:float, isCanceled:bool, userTag:str):
        """
        订单回报回调函数
        
        当订单状态发生变化时调用，如订单被部分成交、全部成交、被撤销等。
        此回调用于跟踪订单的执行状态。
        
        @context: 策略运行上下文对象
        @localid: 本地订单ID，下单时返回的订单标识
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @isBuy: 是否为买入订单，True表示买入，False表示卖出
        @totalQty: 订单总数量
        @leftQty: 剩余未成交数量
        @price: 订单价格
        @isCanceled: 订单是否已被撤销，True表示已撤销，False表示未撤销
        @userTag: 用户标记，下单时传入的自定义标记
        """
        return

    def on_trade(self, context:HftContext, localid:int, stdCode:str, isBuy:bool, qty:float, price:float, userTag:str):
        """
        成交回报回调函数
        
        当订单有成交时调用，每次成交都会触发一次此回调。
        此回调用于跟踪订单的成交情况。
        
        @context: 策略运行上下文对象
        @localid: 本地订单ID，下单时返回的订单标识
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @isBuy: 是否为买入成交，True表示买入，False表示卖出
        @qty: 成交数量
        @price: 成交价格
        @userTag: 用户标记，下单时传入的自定义标记
        """
        return

    def on_position(self, context:HftContext, stdCode:str, isLong:bool, prevol:float, preavail:float, newvol:float, newavail:float):
        """
        初始持仓回报回调函数
        
        在策略启动时调用，用于通知策略当前的持仓情况。
        注意：此回调只在实盘环境中有效，回测时初始仓位都是空，所以不会触发。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SHFE.rb.2305
        @isLong: 是否为多头持仓，True表示多头，False表示空头
        @prevol: 昨日持仓数量
        @preavail: 可用昨日持仓数量
        @newvol: 今日持仓数量
        @newavail: 可用今日持仓数量
        """
        return

class BaseSelStrategy:
    """
    选股策略基础类
    
    所有选股策略的基类，提供了选股策略开发的标准接口。
    选股策略主要用于多因子选股，通常基于多个股票的数据进行筛选和排序。
    策略开发者需要继承此类，并重写感兴趣的回调函数来实现选股逻辑。
    """
    
    def __init__(self, name:str):
        """
        构造函数
        
        初始化选股策略，设置策略名称。
        
        @name: 策略名称，用于标识该策略，必须唯一
        """
        # 保存策略名称，使用双下划线前缀表示私有属性
        self.__name__ = name
        
    
    def name(self) -> str:
        """
        获取策略名称
        
        @return: 返回策略名称字符串
        """
        return self.__name__


    def on_init(self, context:SelContext):
        """
        策略初始化回调函数
        
        在策略启动时调用，用于加载自定义数据、初始化指标等准备工作。
        这是策略的第一个回调函数，通常在这里订阅行情、准备历史数据等。
        
        @context: 策略运行上下文对象，提供数据查询、下单等接口
        """
        return
    
    def on_session_begin(self, context:SelContext, curTDate:int):
        """
        交易日开始事件回调函数
        
        在每个交易日开始时调用，用于执行每日的初始化工作。
        例如：重置每日计数器、加载当日数据等。
        
        @context: 策略运行上下文对象
        @curTDate: 当前交易日，格式为yyyymmdd，例如：20210220
        """
        return

    def on_session_end(self, context:SelContext, curTDate:int):
        """
        交易日结束事件回调函数
        
        在每个交易日结束时调用，用于执行每日的清理工作。
        例如：保存数据、计算每日统计等。
        
        @context: 策略运行上下文对象
        @curTDate: 当前交易日，格式为yyyymmdd，例如：20210220
        """
        return
    
    def on_calculate(self, context:SelContext):
        """
        策略计算回调函数
        
        在定时触发时调用，这是策略的核心计算模块。
        通常在这里进行因子计算、股票筛选、仓位调整等逻辑。
        
        @context: 策略运行上下文对象
        """
        return

    def on_calculate_done(self, context:SelContext):
        """
        策略计算完成回调函数
        
        在策略计算完成后调用，主要用于异步场景。
        在异步模式下，此回调在on_calculate之后触发。
        
        @context: 策略运行上下文对象
        """
        return

    def on_backtest_end(self, context:CtaContext):
        """
        回测结束回调函数
        
        在回测结束时调用，只在回测框架下会触发。
        注意：参数类型标注为CtaContext，但实际传入的是SelContext，这是历史遗留问题。
        
        @context: 策略运行上下文对象
        """
        return

    def on_tick(self, context:SelContext, stdCode:str, newTick:dict):
        """
        Tick数据回调函数
        
        当订阅的合约有新的Tick数据时调用。
        在实盘环境中，每笔行情进来就会立即调用此函数。
        在回测环境中，是模拟的逐笔数据。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SSE.000001
        @newTick: 最新Tick数据字典，包含价格、成交量、买卖盘等信息
        """
        return

    def on_bar(self, context:SelContext, stdCode:str, period:str, newBar:dict):
        """
        K线闭合回调函数
        
        当订阅的K线闭合时调用，可以获取到最新闭合的K线数据。
        
        @context: 策略运行上下文对象
        @stdCode: 合约代码，例如：SSE.000001
        @period: K线周期，例如：m5（5分钟）、d（日线）
        @newBar: 最新闭合的K线数据字典，包含开高低收、成交量等信息
        """
        return
