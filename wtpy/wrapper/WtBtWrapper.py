"""
回测引擎包装器模块

本模块提供WonderTrader回测引擎的Python接口封装。回测引擎用于在历史数据上测试策略的表现，
支持CTA、SEL、HFT三种策略类型的回测。

主要功能：
1. 支持三种策略类型：CTA（商品交易顾问）、SEL（选股策略）、HFT（高频交易）
2. 策略生命周期管理：初始化、计算、行情推送、会话事件、回测结束等
3. 交易指令接口：开多、开空、平多、平空、设置目标仓位等
4. 数据查询接口：获取K线、Tick、持仓、资金等信息
5. 回测控制：设置回测时间范围、启用Tick回测、单步执行等
6. 扩展模块支持：扩展数据加载器等
7. 用户数据存储：保存和加载策略的用户自定义数据
8. 图表功能：支持K线图表、指标、标记等可视化功能

与实盘引擎（WtWrapper）的主要区别：
- 回测引擎使用历史数据进行回测，实盘引擎使用实时数据
- 回测引擎支持单步执行和回测控制，实盘引擎不支持
- 回测引擎有回测结束事件，实盘引擎没有

使用单例模式确保全局只有一个回测引擎包装器实例。
"""

# 导入ctypes库，用于调用C++动态库
from ctypes import c_uint32, cdll, c_char_p, c_bool, c_ulong, c_uint64, c_double, c_int, POINTER
# 导入策略回调函数类型定义
from wtpy.WtCoreDefs import CB_STRATEGY_INIT, CB_STRATEGY_TICK, CB_STRATEGY_CALC, CB_STRATEGY_BAR, CB_STRATEGY_GET_BAR, CB_STRATEGY_GET_TICK, CB_STRATEGY_GET_POSITION, CB_STRATEGY_COND_TRIGGER
# 导入HFT策略回调函数类型定义
from wtpy.WtCoreDefs import CB_HFTSTRA_CHNL_EVT, CB_HFTSTRA_ENTRUST, CB_HFTSTRA_ORD, CB_HFTSTRA_TRD, CB_SESSION_EVENT
# 导入HFT策略数据回调函数类型定义
from wtpy.WtCoreDefs import CB_HFTSTRA_ORDQUE, CB_HFTSTRA_ORDDTL, CB_HFTSTRA_TRANS, CB_HFTSTRA_GET_ORDQUE, CB_HFTSTRA_GET_ORDDTL, CB_HFTSTRA_GET_TRANS
# 导入通道事件和引擎事件类型定义
from wtpy.WtCoreDefs import CHNL_EVENT_READY, CHNL_EVENT_LOST, CB_ENGINE_EVENT
# 导入历史数据加载函数类型定义
from wtpy.WtCoreDefs import FUNC_LOAD_HISBARS, FUNC_LOAD_HISTICKS, FUNC_LOAD_ADJFACTS
# 导入引擎事件类型定义（包括回测结束事件）
from wtpy.WtCoreDefs import EVENT_ENGINE_INIT, EVENT_SESSION_BEGIN, EVENT_SESSION_END, EVENT_ENGINE_SCHDL, EVENT_BACKTEST_END
# 导入数据结构定义
from wtpy.WtCoreDefs import WTSTickStruct, WTSBarStruct, WTSOrdQueStruct, WTSOrdDtlStruct, WTSTransStruct
# 导入平台辅助工具，用于获取动态库路径和编码转换
from .PlatformHelper import PlatformHelper as ph
# 导入单例装饰器，确保全局唯一实例
from wtpy.WtUtilDefs import singleton
# 导入NumPy数组封装类
from wtpy.WtDataDefs import WtNpKline, WtNpOrdDetails, WtNpOrdQueues, WtNpTicks, WtNpTransactions
# 导入操作系统模块
import os

# Python对接C接口的库
@singleton
class WtBtWrapper:
    """
    WonderTrader回测引擎C接口底层对接模块
    
    提供回测引擎功能的Python封装，支持CTA、SEL、HFT三种策略类型的回测。
    负责管理策略的回测执行、交易指令的模拟、历史数据的回放等。
    使用单例模式，确保全局只有一个实例。
    """

    # ========== 类成员变量 ==========
    # api可以作为公共变量，存储C++动态库的接口
    api = None
    # 版本信息
    ver = "Unknown"
    # 交易引擎对象引用，用于管理策略上下文
    _engine = None
    
    def __init__(self, engine):
        """
        初始化回测引擎包装器
        
        初始化回测引擎包装器，加载C++动态库，设置函数签名，获取版本信息。
        
        @param engine: 回测引擎对象，用于管理策略上下文
        """
        # 保存回测引擎引用
        self._engine = engine
        # 获取当前文件所在目录
        paths = os.path.split(__file__)
        # 获取回测引擎动态库文件名（包含平台和架构信息）
        dllname = ph.getModule("WtBtPorter")
        # 拼接路径
        a = (paths[:-1] + (dllname,))
        # 生成完整的动态库路径
        _path = os.path.join(*a)
        # 加载C++动态库
        self.api = cdll.LoadLibrary(_path)
            
        # ========== 基础接口函数返回类型设置 ==========
        # 设置get_version函数的返回类型：版本字符串（字符指针）
        self.api.get_version.restype = c_char_p
        # 设置cta_get_last_entertime函数的返回类型：最后进场时间（64位无符号整数）
        self.api.cta_get_last_entertime.restype = c_uint64
        # 设置cta_get_first_entertime函数的返回类型：首次进场时间（64位无符号整数）
        self.api.cta_get_first_entertime.restype = c_uint64
        # 设置cta_get_last_exittime函数的返回类型：最后出场时间（64位无符号整数）
        self.api.cta_get_last_exittime.restype = c_uint64
        # 设置cta_get_detail_entertime函数的返回类型：指定标记的进场时间（64位无符号整数）
        self.api.cta_get_detail_entertime.restype = c_uint64
        # 设置cta_get_last_entertag函数的返回类型：最后进场标记（字符指针）
        self.api.cta_get_last_entertag.restype = c_char_p
        # ========== CTA策略交易接口函数参数类型设置 ==========
        # 设置cta_enter_long函数的参数类型：策略ID、合约代码、数量、用户标记、限价、止损价
        self.api.cta_enter_long.argtypes = [c_ulong, c_char_p, c_double, c_char_p, c_double, c_double]
        # 设置cta_enter_short函数的参数类型：策略ID、合约代码、数量、用户标记、限价、止损价
        self.api.cta_enter_short.argtypes = [c_ulong, c_char_p, c_double, c_char_p, c_double, c_double]
        # 设置cta_exit_long函数的参数类型：策略ID、合约代码、数量、用户标记、限价、止损价
        self.api.cta_exit_long.argtypes = [c_ulong, c_char_p, c_double, c_char_p, c_double, c_double]
        # 设置cta_exit_short函数的参数类型：策略ID、合约代码、数量、用户标记、限价、止损价
        self.api.cta_exit_short.argtypes = [c_ulong, c_char_p, c_double, c_char_p, c_double, c_double]
        # 设置cta_set_position函数的参数类型：策略ID、合约代码、目标仓位、用户标记、限价、止损价
        self.api.cta_set_position.argtypes = [c_ulong, c_char_p, c_double, c_char_p, c_double, c_double]
        # 获取并解码版本信息
        self.ver = bytes.decode(self.api.get_version())

        # ========== CTA策略用户数据接口函数签名设置 ==========
        # 设置cta_save_userdata函数的参数类型：策略ID、数据键名、数据值
        self.api.cta_save_userdata.argtypes = [c_ulong, c_char_p, c_char_p]
        # 设置cta_load_userdata函数的参数类型：策略ID、数据键名、默认值
        self.api.cta_load_userdata.argtypes = [c_ulong, c_char_p, c_char_p]
        # 设置cta_load_userdata函数的返回类型：用户数据字符串（字符指针）
        self.api.cta_load_userdata.restype = c_char_p

        # ========== CTA策略数据查询接口函数返回类型设置 ==========
        # 设置cta_get_position函数的返回类型：持仓数量（双精度浮点数）
        self.api.cta_get_position.restype = c_double
        # 设置cta_get_position_profit函数的返回类型：持仓盈亏（双精度浮点数）
        self.api.cta_get_position_profit.restype = c_double
        # 设置cta_get_position_avgpx函数的返回类型：持仓均价（双精度浮点数）
        self.api.cta_get_position_avgpx.restype = c_double
        # 设置cta_get_detail_cost函数的返回类型：指定标记持仓的开仓价（双精度浮点数）
        self.api.cta_get_detail_cost.restype = c_double
        # 设置cta_get_detail_profit函数的返回类型：指定标记持仓的盈亏（双精度浮点数）
        self.api.cta_get_detail_profit.restype = c_double
        # 设置cta_get_price函数的返回类型：最新价格（双精度浮点数）
        self.api.cta_get_price.restype = c_double
        # 设置cta_get_day_price函数的返回类型：当日价格（双精度浮点数）
        self.api.cta_get_day_price.restype = c_double
        # 设置cta_get_fund_data函数的返回类型：资金数据（双精度浮点数）
        self.api.cta_get_fund_data.restype = c_double

        # ========== SEL策略用户数据接口函数签名设置 ==========
        # 设置sel_save_userdata函数的参数类型：策略ID、数据键名、数据值
        self.api.sel_save_userdata.argtypes = [c_ulong, c_char_p, c_char_p]
        # 设置sel_load_userdata函数的参数类型：策略ID、数据键名、默认值
        self.api.sel_load_userdata.argtypes = [c_ulong, c_char_p, c_char_p]
        # 设置sel_load_userdata函数的返回类型：用户数据字符串（字符指针）
        self.api.sel_load_userdata.restype = c_char_p
        # 设置sel_get_position函数的返回类型：持仓数量（双精度浮点数）
        self.api.sel_get_position.restype = c_double
        # 设置sel_set_position函数的参数类型：策略ID、合约代码、目标仓位、用户标记
        self.api.sel_set_position.argtypes = [c_ulong, c_char_p, c_double, c_char_p]
        # 设置sel_get_position_profit函数的返回类型：持仓盈亏（双精度浮点数）
        self.api.sel_get_position_profit.restype = c_double
        # 设置sel_get_position_avgpx函数的返回类型：持仓均价（双精度浮点数）
        self.api.sel_get_position_avgpx.restype = c_double
        # 设置sel_get_detail_cost函数的返回类型：指定标记持仓的开仓价（双精度浮点数）
        self.api.sel_get_detail_cost.restype = c_double
        # 设置sel_get_detail_profit函数的返回类型：指定标记持仓的盈亏（双精度浮点数）
        self.api.sel_get_detail_profit.restype = c_double
        # 设置sel_get_price函数的返回类型：最新价格（双精度浮点数）
        self.api.sel_get_price.restype = c_double
        # 设置sel_get_day_price函数的返回类型：当日价格（双精度浮点数）
        self.api.sel_get_day_price.restype = c_double
        # 设置sel_get_fund_data函数的返回类型：资金数据（双精度浮点数）
        self.api.sel_get_fund_data.restype = c_double
        # 设置sel_get_last_entertime函数的返回类型：最后进场时间（64位无符号整数）
        self.api.sel_get_last_entertime.restype = c_uint64
        # 设置sel_get_first_entertime函数的返回类型：首次进场时间（64位无符号整数）
        self.api.sel_get_first_entertime.restype = c_uint64
        # 设置sel_get_last_exittime函数的返回类型：最后出场时间（64位无符号整数）
        self.api.sel_get_last_exittime.restype = c_uint64
        # 设置sel_get_detail_entertime函数的返回类型：指定标记的进场时间（64位无符号整数）
        self.api.sel_get_detail_entertime.restype = c_uint64
        # 设置sel_get_last_entertag函数的返回类型：最后进场标记（字符指针）
        self.api.sel_get_last_entertag.restype = c_char_p

        # ========== HFT策略用户数据接口函数签名设置 ==========
        # 设置hft_save_userdata函数的参数类型：策略ID、数据键名、数据值
        self.api.hft_save_userdata.argtypes = [c_ulong, c_char_p, c_char_p]
        # 设置hft_load_userdata函数的参数类型：策略ID、数据键名、默认值
        self.api.hft_load_userdata.argtypes = [c_ulong, c_char_p, c_char_p]
        # 设置hft_load_userdata函数的返回类型：用户数据字符串（字符指针）
        self.api.hft_load_userdata.restype = c_char_p
        # 设置hft_get_position函数的返回类型：持仓数量（双精度浮点数）
        self.api.hft_get_position.restype = c_double
        # 设置hft_get_position_profit函数的返回类型：持仓盈亏（双精度浮点数）
        self.api.hft_get_position_profit.restype = c_double
        # 设置hft_get_position_avgpx函数的返回类型：持仓均价（双精度浮点数）
        self.api.hft_get_position_avgpx.restype = c_double
        # 设置hft_get_undone函数的返回类型：未完成订单数量（双精度浮点数）
        self.api.hft_get_undone.restype = c_double
        # 设置hft_get_price函数的返回类型：最新价格（双精度浮点数）
        self.api.hft_get_price.restype = c_double
        
        # ========== HFT策略交易接口函数签名设置 ==========
        # 设置hft_buy函数的返回类型：本地订单号（字符指针）
        self.api.hft_buy.restype = c_char_p
        # 设置hft_buy函数的参数类型：策略ID、合约代码、价格、数量、用户标记、下单标志
        self.api.hft_buy.argtypes = [c_ulong, c_char_p, c_double, c_double, c_char_p, c_int]
        # 设置hft_sell函数的返回类型：本地订单号（字符指针）
        self.api.hft_sell.restype = c_char_p
        # 设置hft_sell函数的参数类型：策略ID、合约代码、价格、数量、用户标记、下单标志
        self.api.hft_sell.argtypes = [c_ulong, c_char_p, c_double, c_double, c_char_p, c_int]
        # 设置hft_cancel_all函数的返回类型：撤销结果消息（字符指针）
        self.api.hft_cancel_all.restype = c_char_p

        # ========== CTA策略图表功能接口函数签名设置 ==========
        # 设置cta_set_chart_kline函数的参数类型：策略ID、合约代码、K线周期
        self.api.cta_set_chart_kline.argtypes = [c_ulong, c_char_p, c_char_p]
        # 设置cta_add_chart_mark函数的参数类型：策略ID、价格、图标ID、标签
        self.api.cta_add_chart_mark.argtypes = [c_ulong, c_double, c_char_p, c_char_p]
        # 设置cta_register_index函数的参数类型：策略ID、指标名称、指标类型
        self.api.cta_register_index.argtypes = [c_ulong, c_char_p, c_uint32]
        # 设置cta_register_index_line函数的参数类型：策略ID、指标名称、线名称、线型
        self.api.cta_register_index_line.argtypes = [c_ulong, c_char_p, c_char_p, c_uint32]
        # 设置cta_add_index_baseline函数的参数类型：策略ID、指标名称、线名称、基准值
        self.api.cta_add_index_baseline.argtypes = [c_ulong, c_char_p, c_char_p, c_double]
        # 设置cta_set_index_value函数的参数类型：策略ID、指标名称、线名称、指标值
        self.api.cta_set_index_value.argtypes = [c_ulong, c_char_p, c_char_p, c_double]

        # ========== 回测控制接口函数签名设置（回测引擎专用） ==========
        # 设置set_time_range函数的参数类型：开始时间、结束时间（64位无符号整数）
        self.api.set_time_range.argtypes = [c_uint64, c_uint64]
        # 设置enable_tick函数的参数类型：是否启用（布尔值）
        self.api.enable_tick.argtypes = [c_bool]

        # ========== 工具函数返回类型设置 ==========
        # 设置get_raw_stdcode函数的返回类型：原始标准化代码（字符指针）
        self.api.get_raw_stdcode.restype = c_char_p

    def on_engine_event(self, evtid:int, evtDate:int, evtTime:int):
        """
        引擎事件回调函数
        
        当引擎发生生命周期事件时（初始化、定时调度、会话开始、会话结束、回测结束），
        C++库会调用此函数。回测引擎比实盘引擎多了一个回测结束事件。
        
        @param evtid: 事件ID，标识事件类型
        @param evtDate: 事件日期（整数，格式yyyymmdd）
        @param evtTime: 事件时间（整数，格式HHMM）
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 根据事件类型调用引擎的相应方法
        if evtid == EVENT_ENGINE_INIT:
            # 引擎初始化事件：调用引擎的初始化方法
            engine.on_init()
        elif evtid == EVENT_ENGINE_SCHDL:
            # 引擎定时调度事件：调用引擎的定时调度方法
            engine.on_schedule(evtDate, evtTime)
        elif evtid == EVENT_SESSION_BEGIN:
            # 会话开始事件：调用引擎的会话开始方法
            engine.on_session_begin(evtDate)
        elif evtid == EVENT_SESSION_END:
            # 会话结束事件：调用引擎的会话结束方法
            engine.on_session_end(evtDate)
        elif evtid == EVENT_BACKTEST_END:
            # 回测结束事件（回测引擎特有）：调用引擎的回测结束方法
            engine.on_backtest_end()
        return

    def on_stra_init(self, id:int):
        """
        策略初始化回调函数
        
        当策略需要初始化时，C++库会调用此函数。此函数由C++引擎在策略创建后自动调用，
        用于触发策略的初始化逻辑。
        
        @param id: 策略ID，唯一标识一个策略实例
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象，上下文对象封装了策略的运行时环境
        ctx = engine.get_context(id)
        # 如果上下文存在，调用其初始化方法，触发策略的on_init回调
        if ctx is not None:
            ctx.on_init()
        return

    def on_session_event(self, id:int, udate:int, isBegin:bool):
        """
        交易会话事件回调函数
        
        当交易会话开始或结束时，C++库会调用此函数。交易会话通常对应一个交易日，
        会话开始表示交易日开始，会话结束表示交易日结束。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param udate: 交易日期（整数格式，如20230101）
        @param isBegin: 是否为会话开始事件，True表示会话开始，False表示会话结束
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，根据事件类型调用相应的会话事件处理方法
        if ctx is not None:
            if isBegin:
                # 会话开始：调用策略的会话开始回调，通常用于初始化交易日相关数据
                ctx.on_session_begin(udate)
            else:
                # 会话结束：调用策略的会话结束回调，通常用于清理和保存数据
                ctx.on_session_end(udate)
        return

    def on_stra_calc(self, id:int, curDate:int, curTime:int):
        """
        策略计算回调函数
        
        当策略需要执行计算逻辑时，C++库会调用此函数。通常在主K线闭合时触发，
        用于执行策略的主要交易逻辑。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param curDate: 当前日期（整数格式，如20230101）
        @param curTime: 当前时间（整数格式，如93000表示09:30:00）
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，调用策略的计算方法，触发策略的on_calculate回调
        if ctx is not None:
            ctx.on_calculate()
        return

    def on_stra_calc_done(self, id:int, curDate:int, curTime:int):
        """
        策略计算完成回调函数
        
        当策略计算完成后，C++库会调用此函数。此函数在on_calculate之后调用，
        用于执行计算后的清理工作。此函数是回测引擎特有的，实盘引擎没有。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param curDate: 当前日期（整数格式，如20230101）
        @param curTime: 当前时间（整数格式，如93000表示09:30:00）
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，调用策略的计算完成方法，触发策略的on_calculate_done回调
        if ctx is not None:
            ctx.on_calculate_done()
        return

    def on_stra_tick(self, id:int, stdCode:str, newTick:POINTER(WTSTickStruct)):
        """
        Tick数据回调函数
        
        当接收到新的Tick行情数据时，C++库会调用此函数。Tick数据是最细粒度的行情数据，
        包含每一笔成交的价格、成交量等信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param newTick: 新的Tick数据指针（指向WTSTickStruct结构体）
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)

        # 如果上下文存在，将Tick数据传递给策略，触发策略的on_tick回调
        if ctx is not None:
            # 将合约代码从字节字符串解码为Python字符串，Tick指针直接传递
            ctx.on_tick(bytes.decode(stdCode), newTick)
        return
    
    def on_stra_bar(self, id:int, stdCode:str, period:str, newBar:POINTER(WTSBarStruct)):
        """
        K线闭合回调函数
        
        当K线闭合时，C++库会调用此函数。K线闭合表示一个时间周期的K线数据已经完成，
        此时可以基于完整的K线数据进行策略计算。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param period: K线周期（字节字符串，如"m5"表示5分钟K线，需要解码）
        @param newBar: 新的K线数据指针（指向WTSBarStruct结构体）
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，将K线数据传递给策略，触发策略的on_bar回调
        if ctx is not None:
            # 将合约代码和周期从字节字符串解码为Python字符串，K线指针直接传递
            ctx.on_bar(bytes.decode(stdCode), bytes.decode(period), newBar)
        return

    def on_stra_get_bar(self, id:int, stdCode:str, period:str, curBar:POINTER(WTSBarStruct), count:int, isLast:bool):
        """
        获取K线数据回调函数
        
        该回调函数由Python主动发起的数据查询触发，需要同步执行，因此不走事件推送机制。
        当策略调用get_bars接口查询K线数据时，C++库会通过此回调函数返回数据。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param period: K线周期（字节字符串，如"m5"表示5分钟K线，需要解码）
        @param curBar: K线数据数组指针（指向WTSBarStruct结构体数组的起始位置）
        @param count: K线数据条数
        @param isLast: 是否为最后一批数据，True表示数据已全部返回
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 将周期字符串从字节字符串解码为Python字符串
        period = bytes.decode(period)
        # 判断是否为日线周期（日线周期以'd'开头）
        isDay = period[0]=='d'

        # 创建NumPy封装的K线数据容器（回测引擎默认使用拷贝模式）
        npBars = WtNpKline(isDay)
        # 将C++传递的K线数据数组设置到NumPy容器中
        npBars.set_data(curBar, count)

        # 如果上下文存在，将K线数据传递给策略，触发策略的on_getbars回调
        if ctx is not None:
            ctx.on_getbars(bytes.decode(stdCode), period, npBars)

    def on_stra_get_tick(self, id:int, stdCode:str, curTick:POINTER(WTSTickStruct), count:int, isLast:bool):
        """
        获取Tick数据回调函数
        
        该回调函数由Python主动发起的数据查询触发，需要同步执行，因此不走事件推送机制。
        当策略调用get_ticks接口查询Tick数据时，C++库会通过此回调函数返回数据。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param curTick: Tick数据数组指针（指向WTSTickStruct结构体数组的起始位置）
        @param count: Tick数据条数
        @param isLast: 是否为最后一批数据，True表示数据已全部返回
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)

        # 创建NumPy封装的Tick数据容器，使用零拷贝模式提高性能
        npTicks = WtNpTicks(forceCopy=False)
        # 将C++传递的Tick数据数组设置到NumPy容器中
        npTicks.set_data(curTick, count)

        # 如果上下文存在，将Tick数据传递给策略，触发策略的on_getticks回调
        if ctx is not None:
            ctx.on_getticks(bytes.decode(stdCode), npTicks)
        return

    def on_stra_get_position(self, id:int, stdCode:str, qty:float, isLast:bool):
        """
        获取持仓数据回调函数
        
        该回调函数由Python主动发起的持仓查询触发，需要同步执行，因此不走事件推送机制。
        当策略调用get_all_position接口查询所有持仓时，C++库会通过此回调函数返回每个合约的持仓数据。
        注意：回测引擎的持仓回调函数参数与实盘引擎不同，没有frozen参数，但有isLast参数。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param qty: 持仓数量（浮点数），正数表示多仓，负数表示空仓
        @param isLast: 是否为最后一条持仓数据（布尔值），True表示数据已全部返回
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，将持仓数据传递给策略，触发策略的on_getpositions回调
        if ctx is not None:
            ctx.on_getpositions(bytes.decode(stdCode), qty, isLast)

    def on_stra_cond_triggerd(self, id:int, stdCode:str, target:float, price:float, usertag:str):
        """
        条件单触发回调函数
        
        当条件单被触发时，C++库会调用此函数。条件单是一种特殊的订单类型，
        当市场价格达到预设条件时自动触发。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param target: 目标价格（浮点数），条件单触发时的目标价格
        @param price: 触发价格（浮点数），实际触发时的市场价格
        @param usertag: 用户标记（字节字符串，需要解码），用于标识条件单
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，将条件单触发信息传递给策略，触发策略的on_condition_triggered回调
        if ctx is not None:
            ctx.on_condition_triggered(bytes.decode(stdCode), target, price, bytes.decode(usertag))

    def on_hftstra_channel_evt(self, id:int, trader:str, evtid:int):
        """
        HFT策略交易通道事件回调函数
        
        当HFT策略的交易通道状态发生变化时，C++库会调用此函数。交易通道事件包括
        通道就绪（可以交易）和通道丢失（无法交易）两种情况。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param trader: 交易通道名称（字符串，标识交易接口）
        @param evtid: 事件ID，CHNL_EVENT_READY表示通道就绪，CHNL_EVENT_LOST表示通道丢失
        """
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文不存在，直接返回
        if ctx is None:
            return
        # 根据事件类型调用相应的处理方法
        if evtid == CHNL_EVENT_READY:
            # 通道就绪事件：调用策略的通道就绪回调，表示可以开始交易
            ctx.on_channel_ready()
        elif evtid == CHNL_EVENT_LOST:
            # 通道丢失事件：调用策略的通道丢失回调，表示交易通道断开
            ctx.on_channel_lost()

    def on_hftstra_order(self, id:int, localid:int, stdCode:str, isBuy:bool, totalQty:float, leftQty:float, price:float, isCanceled:bool, userTag:str):
        """
        HFT策略订单回报回调函数
        
        当订单状态发生变化时，C++库会调用此函数。订单回报包括订单提交、部分成交、
        全部成交、撤单等状态变化。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param localid: 本地订单号（整数），策略下单时返回的订单标识
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param isBuy: 是否为买入订单（布尔值），True表示买入，False表示卖出
        @param totalQty: 订单总数量（浮点数）
        @param leftQty: 剩余未成交数量（浮点数）
        @param price: 订单价格（浮点数）
        @param isCanceled: 是否已撤销（布尔值），True表示订单已撤销
        @param userTag: 用户标记（字节字符串，GBK编码，需要解码），用于标识订单
        """
        # 将合约代码从字节字符串解码为Python字符串
        stdCode = bytes.decode(stdCode)
        # 将用户标记从字节字符串解码为Python字符串（回测引擎使用GBK编码）
        userTag = bytes.decode(userTag,"gbk")
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，将订单回报信息传递给策略，触发策略的on_order回调
        if ctx is not None:
            ctx.on_order(localid, stdCode, isBuy, totalQty, leftQty, price, isCanceled, userTag)

    def on_hftstra_trade(self, id:int, localid:int, stdCode:str, isBuy:bool, qty:float, price:float, userTag:str):
        """
        HFT策略成交通知回调函数
        
        当订单成交时，C++库会调用此函数。成交通知包含成交的详细信息，包括成交价格、
        成交数量等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param localid: 本地订单号（整数），策略下单时返回的订单标识
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param isBuy: 是否为买入成交（布尔值），True表示买入，False表示卖出
        @param qty: 成交数量（浮点数）
        @param price: 成交价格（浮点数）
        @param userTag: 用户标记（字节字符串，GBK编码，需要解码），用于标识订单
        """
        # 将合约代码从字节字符串解码为Python字符串
        stdCode = bytes.decode(stdCode)
        # 将用户标记从字节字符串解码为Python字符串（回测引擎使用GBK编码）
        userTag = bytes.decode(userTag,"gbk")
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，将成交通知信息传递给策略，触发策略的on_trade回调
        if ctx is not None:
            ctx.on_trade(localid, stdCode, isBuy, qty, price, userTag)

    def on_hftstra_entrust(self, id:int, localid:int, stdCode:str, bSucc:bool, message:str, userTag:str):
        """
        HFT策略委托回报回调函数
        
        当下单请求被交易所接受或拒绝时，C++库会调用此函数。委托回报表示订单是否
        成功提交到交易所。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param localid: 本地订单号（整数），策略下单时返回的订单标识
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param bSucc: 是否成功（布尔值），True表示委托成功，False表示委托失败
        @param message: 委托结果消息（字节字符串，GBK编码，需要解码），包含成功或失败的原因
        @param userTag: 用户标记（字节字符串，GBK编码，需要解码），用于标识订单
        """
        # 将合约代码从字节字符串解码为Python字符串
        stdCode = bytes.decode(stdCode)
        # 将消息从字节字符串解码为Python字符串（回测引擎使用GBK编码）
        message = bytes.decode(message, "gbk")
        # 将用户标记从字节字符串解码为Python字符串（回测引擎使用GBK编码）
        userTag = bytes.decode(userTag, "gbk")
        # 获取回测引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，将委托回报信息传递给策略，触发策略的on_entrust回调
        if ctx is not None:
            ctx.on_entrust(localid, stdCode, bSucc, message, userTag)

    def on_hftstra_order_queue(self, id:int, stdCode:str, newOrdQue:POINTER(WTSOrdQueStruct)):
        stdCode = bytes.decode(stdCode)
        engine = self._engine
        ctx = engine.get_context(id)

        newOrdQue = newOrdQue.contents        
        if ctx is not None:
            ctx.on_order_queue(stdCode, newOrdQue.to_tuple())

    def on_hftstra_get_order_queue(self, id:int, stdCode:str, newOrdQue:POINTER(WTSOrdQueStruct), count:int, isLast:bool):
        engine = self._engine
        ctx = engine.get_context(id)
        
        npHftData = WtNpOrdQueues(forceCopy=False)
        npHftData.set_data(newOrdQue, count)

        if ctx is not None:
            ctx.on_get_order_queue(bytes.decode(stdCode), npHftData)

    def on_hftstra_order_detail(self, id:int, stdCode:str, newOrdDtl:POINTER(WTSOrdDtlStruct)):
        stdCode = bytes.decode(stdCode)
        engine = self._engine
        ctx = engine.get_context(id)

        newOrdDtl = newOrdDtl.contents
        
        if ctx is not None:
            ctx.on_order_detail(stdCode, newOrdDtl.to_tuple())

    def on_hftstra_get_order_detail(self, id:int, stdCode:str, newOrdDtl:POINTER(WTSOrdDtlStruct), count:int, isLast:bool):
        engine = self._engine
        ctx = engine.get_context(id)
        
        npHftData = WtNpOrdDetails(forceCopy=False)
        npHftData.set_data(newOrdDtl, count)
            
        if ctx is not None:
            ctx.on_get_order_detail(bytes.decode(stdCode), npHftData)

    def on_hftstra_transaction(self, id:int, stdCode:str, newTrans:POINTER(WTSTransStruct)):
        stdCode = bytes.decode(stdCode)
        engine = self._engine
        ctx = engine.get_context(id)
        newTrans = newTrans.contents
        
        if ctx is not None:
            ctx.on_transaction(stdCode, newTrans.to_tuple())
        
    def on_hftstra_get_transaction(self, id:int, stdCode:str, newTrans:POINTER(WTSTransStruct), count:int, isLast:bool):
        engine = self._engine
        ctx = engine.get_context(id)

        npHftData = WtNpTransactions(forceCopy=False)
        npHftData.set_data(newTrans, count)
            
        if ctx is not None:
            ctx.on_get_transaction(bytes.decode(stdCode), npHftData)

    def on_load_fnl_his_bars(self, stdCode:str, period:str) -> bool:
        engine = self._engine
        loader = engine.get_extended_data_loader()
        if loader is None:
            return False

        return loader.load_final_his_bars(bytes.decode(stdCode), bytes.decode(period), self.api.feed_raw_bars)

    def on_load_raw_his_bars(self, stdCode:str, period:str) -> bool:
        engine = self._engine
        loader = engine.get_extended_data_loader()
        if loader is None:
            return False

        return loader.load_raw_his_bars(bytes.decode(stdCode), bytes.decode(period), self.api.feed_raw_bars)

    def feed_adj_factors(self, stdCode:str, dates:list, factors:list):
        stdCode = bytes(stdCode, encoding="utf8")
        '''
        TODO 这里类型要转一下! 底层接口是传数组的
        feed_adj_factors(WtString stdCode, WtUInt32* dates, double* factors, WtUInt32 count)
        '''
        self.api.feed_adj_factors(stdCode, dates, factors, len(dates))

    def on_load_adj_factors(self, stdCode:str) -> bool:
        engine = self._engine
        loader = engine.get_extended_data_loader()
        if loader is None:
            return False

        stdCode = bytes.decode(stdCode)
        return loader.load_adj_factors(stdCode, self.feed_adj_factors)

    def on_load_his_ticks(self, stdCode:str, uDate:int) -> bool:
        engine = self._engine
        loader = engine.get_extended_data_loader()
        if loader is None:
            return False
        
        # feed_raw_ticks(WTSTickStruct* ticks, WtUInt32 count);
        return loader.load_his_ticks(bytes.decode(stdCode), uDate, self.api.feed_raw_ticks)

    def write_log(self, level, message:str, catName:str = ""):
        """
        写入日志函数
        
        将日志消息写入日志系统。日志用于记录系统运行状态、错误信息等。
        
        @param level: 日志级别（整数），数值越大表示日志级别越高
        @param message: 日志消息内容（字符串，需要根据平台自动编码）
        @param catName: 日志分类名称（字符串，默认为空，需要编码为UTF-8字节字符串）
        """
        # 调用C++接口函数，将日志消息写入日志系统
        # 使用PlatformHelper自动处理消息编码（Windows→GBK，Linux→UTF-8）
        self.api.write_log(level, ph.auto_encode(message), bytes(catName, encoding = "utf8"))

    def set_time_range(self, beginTime:int, endTime:int):
        """
        设置回测时间区间接口
        
        设置回测的时间范围。回测引擎只会在指定的时间范围内回放历史数据。
        此函数必须在运行回测之前调用。
        
        @param beginTime: 开始时间（整数），格式如202301010930表示2023年1月1日09:30
        @param endTime: 结束时间（整数），格式如202301311500表示2023年1月31日15:00
        """
        # 调用C++接口函数，设置回测时间区间
        self.api.set_time_range(beginTime, endTime)

    def enable_tick(self, bEnabled:bool = True):
        """
        启用Tick回测接口
        
        启用或禁用Tick级别的回测。如果启用，回测引擎会推送Tick数据；
        如果禁用，回测引擎只推送K线数据。
        
        @param bEnabled: 是否启用（布尔值，默认True），True表示启用Tick回测，False表示禁用
        """
        # 调用C++接口函数，启用或禁用Tick回测
        self.api.enable_tick(bEnabled)

    # ========== 回测引擎控制接口（与实盘引擎有差异） ==========
    def run_backtest(self, bNeedDump:bool = False, bAsync:bool = False):
        """
        运行回测接口
        
        启动回测引擎，开始回放历史数据并执行策略。回测引擎会按照时间顺序
        回放历史数据，触发策略的各种回调函数。
        
        @param bNeedDump: 是否需要转储数据（布尔值，默认False），True表示转储回测数据到文件
        @param bAsync: 是否异步运行（布尔值，默认False），True表示异步运行（非阻塞），False表示同步运行（阻塞）
        """
        # 调用C++接口函数，运行回测
        self.api.run_backtest(bNeedDump, bAsync)

    def stop_backtest(self):
        """
        停止回测接口
        
        停止正在运行的回测。回测引擎会停止数据回放，但不会释放资源。
        """
        # 调用C++接口函数，停止回测
        self.api.stop_backtest()

    def release_backtest(self):
        """
        释放回测引擎资源接口
        
        释放回测引擎占用的资源，包括关闭连接、清理内存等。
        在程序退出前应调用此函数以确保资源正确释放。
        """
        # 调用C++接口函数，释放回测引擎资源
        self.api.release_backtest()

    def clear_cache(self):
        """
        清理缓存接口
        
        清理回测引擎的数据缓存。缓存用于提高数据查询性能，清理后需要重新加载数据。
        """
        # 调用C++接口函数，清理缓存
        self.api.clear_cache()

    def get_raw_stdcode(self, stdCode:str):
        """
        获取原始标准化代码接口
        
        将标准化代码转换为原始代码格式。标准化代码是wtpy内部使用的统一代码格式，
        原始代码是交易所使用的代码格式。
        
        @param stdCode: 标准化代码（字符串，需要编码为UTF-8字节字符串）
        @return: 原始代码（字符串），从字节字符串解码得到
        """
        # 调用C++接口函数，获取原始代码，并解码为Python字符串
        return bytes.decode(self.api.get_raw_stdcode(bytes(stdCode, encoding = "utf8")))

    def config_backtest(self, cfgfile:str = 'config.yaml', isFile:bool = True):
        """
        配置回测引擎接口
        
        加载配置文件，配置回测引擎的参数，包括数据源、策略、回测参数等。
        
        @param cfgfile: 配置文件路径或配置内容（字符串，默认'config.yaml'）
        @param isFile: 是否为文件路径（布尔值，默认True），True表示cfgfile是文件路径，False表示cfgfile是配置内容
        """
        # 调用C++接口函数，配置回测引擎
        self.api.config_backtest(bytes(cfgfile, encoding = "utf8"), isFile)

    def initialize_cta(self, logCfg:str = "logcfgbt.yaml", isFile:bool = True, outDir:str = "./outputs_bt"):
        """
        初始化CTA策略回测引擎
        
        初始化CTA（商品交易顾问）策略回测引擎，注册所有CTA策略相关的回调函数，
        并启动C++回测引擎。此函数必须在添加策略之前调用。
        
        @param logCfg: 日志配置文件路径或配置内容（字符串，默认"logcfgbt.yaml"）
        @param isFile: 是否为文件路径（布尔值，默认True），True表示logCfg是文件路径，False表示logCfg是配置内容
        @param outDir: 输出目录（字符串，默认"./outputs_bt"），用于存储回测结果文件
        """
        # ========== 创建CTA策略回调函数对象 ==========
        # 创建策略初始化回调函数对象，用于接收策略初始化事件
        self.cb_stra_init = CB_STRATEGY_INIT(self.on_stra_init)
        # 创建Tick数据回调函数对象，用于接收Tick行情数据
        self.cb_stra_tick = CB_STRATEGY_TICK(self.on_stra_tick)
        # 创建策略计算回调函数对象，用于接收策略计算事件
        self.cb_stra_calc = CB_STRATEGY_CALC(self.on_stra_calc)
        # 创建策略计算完成回调函数对象（回测引擎特有），用于接收策略计算完成事件
        self.cb_stra_calc_done = CB_STRATEGY_CALC(self.on_stra_calc_done)
        # 创建K线闭合回调函数对象，用于接收K线闭合事件
        self.cb_stra_bar = CB_STRATEGY_BAR(self.on_stra_bar)
        # 创建会话事件回调函数对象，用于接收交易会话开始/结束事件
        self.cb_session_event = CB_SESSION_EVENT(self.on_session_event)
        # 创建条件单触发回调函数对象，用于接收条件单触发事件
        self.cb_stra_cond_trigger = CB_STRATEGY_COND_TRIGGER(self.on_stra_cond_triggerd)

        # ========== 创建引擎事件回调函数对象 ==========
        # 创建引擎事件回调函数对象，用于接收引擎生命周期事件（包括回测结束事件）
        self.cb_engine_event = CB_ENGINE_EVENT(self.on_engine_event)
        
        # ========== 注册回调函数并初始化回测引擎 ==========
        try:
            # 注册引擎事件回调函数到C++引擎
            self.api.register_evt_callback(self.cb_engine_event)
            # 注册CTA策略回调函数到C++引擎，包括基础回调和计算完成回调（回测引擎特有）
            self.api.register_cta_callbacks(self.cb_stra_init, self.cb_stra_tick, 
                self.cb_stra_calc, self.cb_stra_bar, self.cb_session_event, self.cb_stra_calc_done, self.cb_stra_cond_trigger)
            # 初始化C++回测引擎，加载日志配置和输出目录
            self.api.init_backtest(bytes(logCfg, encoding = "utf8"), isFile, bytes(outDir, encoding = "utf8"))
        except OSError as oe:
            # 如果发生操作系统错误（如动态库加载失败），打印错误信息
            print(oe)

        # 写入初始化成功日志
        self.write_log(102, "WonderTrader CTA backtest framework initialzied, version: %s" % (self.ver))

    def initialize_hft(self, logCfg:str = "logcfgbt.yaml", isFile:bool = True, outDir:str = "./outputs_bt"):
        """
        初始化HFT策略回测引擎
        
        初始化HFT（高频交易）策略回测引擎，注册所有HFT策略相关的回调函数，
        并启动C++回测引擎。HFT策略支持更细粒度的行情数据和交易回报。
        此函数必须在添加策略之前调用。
        
        @param logCfg: 日志配置文件路径或配置内容（字符串，默认"logcfgbt.yaml"）
        @param isFile: 是否为文件路径（布尔值，默认True），True表示logCfg是文件路径，False表示logCfg是配置内容
        @param outDir: 输出目录（字符串，默认"./outputs_bt"），用于存储回测结果文件
        """
        # ========== 创建HFT策略基础回调函数对象 ==========
        # 创建策略初始化回调函数对象，用于接收策略初始化事件
        self.cb_stra_init = CB_STRATEGY_INIT(self.on_stra_init)
        # 创建Tick数据回调函数对象，用于接收Tick行情数据
        self.cb_stra_tick = CB_STRATEGY_TICK(self.on_stra_tick)
        # 创建K线闭合回调函数对象，用于接收K线闭合事件
        self.cb_stra_bar = CB_STRATEGY_BAR(self.on_stra_bar)
        # 创建会话事件回调函数对象，用于接收交易会话开始/结束事件
        self.cb_session_event = CB_SESSION_EVENT(self.on_session_event)

        # ========== 创建HFT策略专用回调函数对象 ==========
        # 创建交易通道事件回调函数对象，用于接收交易通道状态变化事件
        self.cb_hftstra_channel_evt = CB_HFTSTRA_CHNL_EVT(self.on_hftstra_channel_evt)
        # 创建订单回报回调函数对象，用于接收订单状态变化事件
        self.cb_hftstra_order = CB_HFTSTRA_ORD(self.on_hftstra_order)
        # 创建成交通知回调函数对象，用于接收订单成交事件
        self.cb_hftstra_trade = CB_HFTSTRA_TRD(self.on_hftstra_trade)
        # 创建委托回报回调函数对象，用于接收委托提交结果事件
        self.cb_hftstra_entrust = CB_HFTSTRA_ENTRUST(self.on_hftstra_entrust)
        # 创建逐笔委托回调函数对象，用于接收逐笔委托数据
        self.cb_hftstra_order_detail = CB_HFTSTRA_ORDDTL(self.on_hftstra_order_detail)
        # 创建委托队列回调函数对象，用于接收委托队列数据
        self.cb_hftstra_order_queue = CB_HFTSTRA_ORDQUE(self.on_hftstra_order_queue)
        # 创建逐笔成交回调函数对象，用于接收逐笔成交数据
        self.cb_hftstra_transaction = CB_HFTSTRA_TRANS(self.on_hftstra_transaction)

        # ========== 创建引擎事件回调函数对象 ==========
        # 创建引擎事件回调函数对象，用于接收引擎生命周期事件（包括回测结束事件）
        self.cb_engine_event = CB_ENGINE_EVENT(self.on_engine_event)

        # ========== 注册回调函数并初始化回测引擎 ==========
        try:
            # 注册引擎事件回调函数到C++引擎
            self.api.register_evt_callback(self.cb_engine_event)
            # 注册HFT策略回调函数到C++引擎，包括基础回调和HFT专用回调
            self.api.register_hft_callbacks(self.cb_stra_init, self.cb_stra_tick, self.cb_stra_bar, 
                self.cb_hftstra_channel_evt, self.cb_hftstra_order, self.cb_hftstra_trade, 
                self.cb_hftstra_entrust, self.cb_hftstra_order_detail, self.cb_hftstra_order_queue, 
                self.cb_hftstra_transaction, self.cb_session_event)
            # 初始化C++回测引擎，加载日志配置和输出目录
            self.api.init_backtest(bytes(logCfg, encoding = "utf8"), isFile, bytes(outDir, encoding = "utf8"))
        except OSError as oe:
            # 如果发生操作系统错误（如动态库加载失败），打印错误信息
            print(oe)

        # 写入初始化成功日志
        self.write_log(102, "WonderTrader HFT backtest framework initialzied, version: %s" % (self.ver))

    def initialize_sel(self, logCfg:str = "logcfgbt.yaml", isFile:bool = True, outDir:str = "./outputs_bt"):
        """
        初始化SEL策略回测引擎
        
        初始化SEL（选股）策略回测引擎，注册所有SEL策略相关的回调函数，
        并启动C++回测引擎。SEL策略主要用于多标的选择和组合管理。
        此函数必须在添加策略之前调用。
        
        @param logCfg: 日志配置文件路径或配置内容（字符串，默认"logcfgbt.yaml"）
        @param isFile: 是否为文件路径（布尔值，默认True），True表示logCfg是文件路径，False表示logCfg是配置内容
        @param outDir: 输出目录（字符串，默认"./outputs_bt"），用于存储回测结果文件
        """
        # ========== 创建SEL策略回调函数对象 ==========
        # 创建策略初始化回调函数对象，用于接收策略初始化事件
        self.cb_stra_init = CB_STRATEGY_INIT(self.on_stra_init)
        # 创建Tick数据回调函数对象，用于接收Tick行情数据
        self.cb_stra_tick = CB_STRATEGY_TICK(self.on_stra_tick)
        # 创建策略计算回调函数对象，用于接收策略计算事件
        self.cb_stra_calc = CB_STRATEGY_CALC(self.on_stra_calc)
        # 创建策略计算完成回调函数对象（回测引擎特有），用于接收策略计算完成事件
        self.cb_stra_calc_done = CB_STRATEGY_CALC(self.on_stra_calc_done)
        # 创建K线闭合回调函数对象，用于接收K线闭合事件
        self.cb_stra_bar = CB_STRATEGY_BAR(self.on_stra_bar)
        # 创建会话事件回调函数对象，用于接收交易会话开始/结束事件
        self.cb_session_event = CB_SESSION_EVENT(self.on_session_event)

        # ========== 创建引擎事件回调函数对象 ==========
        # 创建引擎事件回调函数对象，用于接收引擎生命周期事件（包括回测结束事件）
        self.cb_engine_event = CB_ENGINE_EVENT(self.on_engine_event)

        # ========== 注册回调函数并初始化回测引擎 ==========
        try:
            # 注册引擎事件回调函数到C++引擎
            self.api.register_evt_callback(self.cb_engine_event)
            # 注册SEL策略回调函数到C++引擎，包括基础回调和计算完成回调（回测引擎特有）
            self.api.register_sel_callbacks(self.cb_stra_init, self.cb_stra_tick, 
                self.cb_stra_calc, self.cb_stra_bar, self.cb_session_event, self.cb_stra_calc_done)
            # 初始化C++回测引擎，加载日志配置和输出目录
            self.api.init_backtest(bytes(logCfg, encoding = "utf8"), isFile, bytes(outDir, encoding = "utf8"))
        except OSError as oe:
            # 如果发生操作系统错误（如动态库加载失败），打印错误信息
            print(oe)

        # 写入初始化成功日志
        self.write_log(102, "WonderTrader SEL backtest framework initialzied, version: %s" % (self.ver))

    def register_extended_data_loader(self, bAutoTrans:bool = True):
        """
        注册扩展历史数据加载器回调函数
        
        将扩展历史数据加载器的回调函数注册到C++回测引擎。注册后，C++引擎在需要加载
        历史数据时会调用这些回调函数，由Python端的扩展数据加载器负责实现数据加载逻辑。
        
        @param bAutoTrans: 是否自动转储（布尔值，默认True），True表示自动将加载的数据转储到文件，False表示不转储
        """
        # 创建加载最终K线数据回调函数对象
        self.cb_load_fnlbars = FUNC_LOAD_HISBARS(self.on_load_fnl_his_bars)
        # 创建加载原始K线数据回调函数对象
        self.cb_load_rawbars = FUNC_LOAD_HISBARS(self.on_load_raw_his_bars)
        # 创建加载Tick历史数据回调函数对象
        self.cb_load_histicks = FUNC_LOAD_HISTICKS(self.on_load_his_ticks)
        # 创建加载复权因子数据回调函数对象
        self.cb_load_adjfacts = FUNC_LOAD_ADJFACTS(self.on_load_adj_factors)
        # 将所有数据加载回调函数注册到C++回测引擎，并设置自动转储选项
        self.api.register_ext_data_loader(self.cb_load_fnlbars, self.cb_load_rawbars, self.cb_load_adjfacts, self.cb_load_histicks, bAutoTrans)

    def cta_enter_long(self, id:int, stdCode:str, qty:float, usertag:str, limitprice:float = 0.0, stopprice:float = 0.0):
        """
        CTA策略开多仓接口（回测引擎）
        
        下达开多仓指令，增加多仓持仓。如果当前没有持仓，则新建多仓；
        如果当前有空仓，则先平空仓再开多仓。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param qty: 开仓数量（浮点数，大于等于0），单位为手
        @param usertag: 用户标记（字符串，需要编码为UTF-8字节字符串），用于标识此笔交易
        @param limitprice: 限价（浮点数，默认0.0），0表示市价单，非0表示限价单
        @param stopprice: 止损价（浮点数，默认0.0），0表示不设置止损
        """
        # 调用C++接口函数，下达开多仓指令
        self.api.cta_enter_long(id, bytes(stdCode, encoding = "utf8"), qty, bytes(usertag, encoding = "utf8"), limitprice, stopprice)

    def cta_exit_long(self, id:int, stdCode:str, qty:float, usertag:str, limitprice:float = 0.0, stopprice:float = 0.0):
        """
        CTA策略平多仓接口（回测引擎）
        
        下达平多仓指令，减少多仓持仓。如果当前没有多仓，则指令无效。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param qty: 平仓数量（浮点数，大于等于0），单位为手
        @param usertag: 用户标记（字符串，需要编码为UTF-8字节字符串），用于标识此笔交易
        @param limitprice: 限价（浮点数，默认0.0），0表示市价单，非0表示限价单
        @param stopprice: 止损价（浮点数，默认0.0），0表示不设置止损
        """
        # 调用C++接口函数，下达平多仓指令
        self.api.cta_exit_long(id, bytes(stdCode, encoding = "utf8"), qty, bytes(usertag, encoding = "utf8"), limitprice, stopprice)

    def cta_enter_short(self, id:int, stdCode:str, qty:float, usertag:str, limitprice:float = 0.0, stopprice:float = 0.0):
        """
        CTA策略开空仓接口（回测引擎）
        
        下达开空仓指令，增加空仓持仓。如果当前没有持仓，则新建空仓；
        如果当前有多仓，则先平多仓再开空仓。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param qty: 开仓数量（浮点数，大于等于0），单位为手
        @param usertag: 用户标记（字符串，需要编码为UTF-8字节字符串），用于标识此笔交易
        @param limitprice: 限价（浮点数，默认0.0），0表示市价单，非0表示限价单
        @param stopprice: 止损价（浮点数，默认0.0），0表示不设置止损
        """
        # 调用C++接口函数，下达开空仓指令
        self.api.cta_enter_short(id, bytes(stdCode, encoding = "utf8"), qty, bytes(usertag, encoding = "utf8"), limitprice, stopprice)

    def cta_exit_short(self, id:int, stdCode:str, qty:float, usertag:str, limitprice:float = 0.0, stopprice:float = 0.0):
        """
        CTA策略平空仓接口（回测引擎）
        
        下达平空仓指令，减少空仓持仓。如果当前没有空仓，则指令无效。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param qty: 平仓数量（浮点数，大于等于0），单位为手
        @param usertag: 用户标记（字符串，需要编码为UTF-8字节字符串），用于标识此笔交易
        @param limitprice: 限价（浮点数，默认0.0），0表示市价单，非0表示限价单
        @param stopprice: 止损价（浮点数，默认0.0），0表示不设置止损
        """
        # 调用C++接口函数，下达平空仓指令
        self.api.cta_exit_short(id, bytes(stdCode, encoding = "utf8"), qty, bytes(usertag, encoding = "utf8"), limitprice, stopprice)
    
    def cta_get_bars(self, id:int, stdCode:str, period:str, count:int, isMain:bool):
        """
        CTA策略获取K线数据接口（回测引擎）
        
        查询指定合约的K线历史数据。K线数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_stra_get_bar回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param period: K线周期（字符串，如"m1"表示1分钟，"m5"表示5分钟，"d1"表示日线，需要编码为UTF-8字节字符串）
        @param count: 查询条数（整数），表示需要获取多少根K线
        @param isMain: 是否主K线（布尔值），True表示主K线，False表示非主K线
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询K线数据
        # 数据通过on_stra_get_bar回调函数异步返回
        return self.api.cta_get_bars(id, bytes(stdCode, encoding = "utf8"), bytes(period, encoding = "utf8"), count, isMain, CB_STRATEGY_GET_BAR(self.on_stra_get_bar))
    
    def cta_get_ticks(self, id:int, stdCode:str, count:int):
        """
        CTA策略获取Tick数据接口（回测引擎）
        
        查询指定合约的Tick历史数据。Tick数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_stra_get_tick回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param count: 查询条数（整数），表示需要获取多少笔Tick数据
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询Tick数据
        # 数据通过on_stra_get_tick回调函数异步返回
        return self.api.cta_get_ticks(id, bytes(stdCode, encoding = "utf8"), count, CB_STRATEGY_GET_TICK(self.on_stra_get_tick))

    def cta_get_position_profit(self, id:int, stdCode:str):
        """
        CTA策略获取持仓浮动盈亏接口（回测引擎）
        
        获取指定合约的持仓浮动盈亏。浮动盈亏是根据当前市场价格计算的未实现盈亏。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的持仓浮动盈亏（浮点数），正数表示盈利，负数表示亏损
        """
        # 调用C++接口函数，获取持仓浮动盈亏
        return self.api.cta_get_position_profit(id, bytes(stdCode, encoding = "utf8"))

    def cta_get_position_avgpx(self, id:int, stdCode:str):
        """
        CTA策略获取持仓均价接口（回测引擎）
        
        获取指定合约的持仓均价。持仓均价是所有持仓的平均开仓价格。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的持仓均价（浮点数）
        """
        # 调用C++接口函数，获取持仓均价
        return self.api.cta_get_position_avgpx(id, bytes(stdCode, encoding = "utf8"))

    def cta_get_all_position(self, id:int):
        """
        CTA策略获取全部持仓接口（回测引擎）
        
        获取策略的所有持仓信息。持仓信息通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_stra_get_position回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询所有持仓
        # 持仓数据通过on_stra_get_position回调函数异步返回
        return self.api.cta_get_all_position(id, CB_STRATEGY_GET_POSITION(self.on_stra_get_position))
    
    def cta_get_position(self, id:int, stdCode:str, bonlyvalid:bool = False, usertag:str = ""):
        """
        CTA策略获取持仓接口（回测引擎）
        
        获取指定合约的持仓数量。可以获取全部持仓或指定标记的持仓。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param bonlyvalid: 是否只读可用持仓（布尔值，默认False），True表示只返回可用持仓，False表示返回全部持仓
        @param usertag: 进场标记（字符串，默认空字符串，需要编码为UTF-8字节字符串），如果为空则获取该合约全部持仓，否则只获取指定标记的持仓
        @return: 指定合约的持仓手数（浮点数），正数表示多仓，负数表示空仓，0表示无持仓
        """
        # 调用C++接口函数，获取持仓数量
        return self.api.cta_get_position(id, bytes(stdCode, encoding = "utf8"), bonlyvalid, bytes(usertag, encoding = "utf8"))

    def cta_get_fund_data(self, id:int, flag:int) -> float:
        """
        CTA策略获取资金数据接口（回测引擎）
        
        获取策略的资金数据，包括动态权益、盈亏、手续费等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param flag: 资金数据标志（整数），0-动态权益，1-总平仓盈亏，2-总浮动盈亏，3-总手续费
        @return: 资金数据（浮点数），根据flag返回相应的资金数据
        """
        # 调用C++接口函数，获取资金数据
        return self.api.cta_get_fund_data(id, flag)

    def cta_get_price(self, stdCode:str) -> float:
        """
        CTA策略获取最新价格接口（回测引擎）
        
        获取指定合约的最新价格。最新价格是最近一笔成交的价格。
        
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的最新价格（浮点数）
        """
        # 调用C++接口函数，获取最新价格
        return self.api.cta_get_price(bytes(stdCode, encoding = "utf8"))

    def cta_get_day_price(self, stdCode:str, flag:int = 0) -> float:
        """
        CTA策略获取当日价格接口（回测引擎）
        
        获取指定合约的当日价格，包括开盘价、最高价、最低价、最新价等。
        
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param flag: 价格标记（整数，默认0），0-开盘价，1-最高价，2-最低价，3-最新价
        @return: 指定合约的价格（浮点数），根据flag返回相应的价格
        """
        # 调用C++接口函数，获取当日价格
        return self.api.cta_get_day_price(bytes(stdCode, encoding = "utf8"), flag)

    def cta_set_position(self, id:int, stdCode:str, qty:float, usertag:str = "", limitprice:float = 0.0, stopprice:float = 0.0):
        """
        CTA策略设置目标仓位接口（回测引擎）
        
        设置指定合约的目标仓位。系统会自动计算需要开仓或平仓的数量，并执行相应的交易指令。
        如果目标仓位大于当前持仓，则开仓；如果目标仓位小于当前持仓，则平仓。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param qty: 目标仓位（浮点数），正数表示多仓，负数表示空仓，0表示平仓
        @param usertag: 用户标记（字符串，默认空字符串，需要编码为UTF-8字节字符串），用于标识此笔交易
        @param limitprice: 限价（浮点数，默认0.0），0表示市价单，非0表示限价单
        @param stopprice: 止损价（浮点数，默认0.0），0表示不设置止损
        """
        # 调用C++接口函数，设置目标仓位
        self.api.cta_set_position(id, bytes(stdCode, encoding = "utf8"), qty, bytes(usertag, encoding = "utf8"), limitprice, stopprice)

    def cta_get_tdate(self) -> int:
        """
        CTA策略获取当前交易日接口（回测引擎）
        
        获取当前交易日。交易日是交易所规定的交易日期，可能与自然日不同。
        在回测中，当前交易日是回测引擎正在回放的交易日。
        
        @return: 当前交易日（整数），格式如20230101
        """
        # 调用C++接口函数，获取当前交易日
        return self.api.cta_get_tdate()

    def cta_get_date(self) -> int:
        """
        CTA策略获取当前日期接口（回测引擎）
        
        获取当前日期。当前日期是系统日期，可能与交易日不同。
        在回测中，当前日期是回测引擎正在回放的日期。
        
        @return: 当前日期（整数），格式如20230101
        """
        # 调用C++接口函数，获取当前日期
        return self.api.cta_get_date()

    def cta_get_time(self) -> int:
        """
        CTA策略获取当前时间接口（回测引擎）
        
        获取当前时间。当前时间是系统时间，格式为HHMMSS（时分秒）。
        在回测中，当前时间是回测引擎正在回放的时间。
        
        @return: 当前时间（整数），格式如93000表示09:30:00
        """
        # 调用C++接口函数，获取当前时间
        return self.api.cta_get_time()

    def cta_get_first_entertime(self, id:int, stdCode:str) -> int:
        """
        CTA策略获取首次进场时间接口（回测引擎）
        
        获取当前持仓的首次进场时间。首次进场时间是最早一笔持仓的开仓时间。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 首次进场时间（整数），格式如201907260932表示2019年7月26日09:32:00
        """
        # 调用C++接口函数，获取首次进场时间
        return self.api.cta_get_first_entertime(id, bytes(stdCode, encoding = "utf8"))

    def cta_get_last_entertime(self, id:int, stdCode:str) -> int:
        """
        CTA策略获取最后进场时间接口（回测引擎）
        
        获取当前持仓的最后进场时间。最后进场时间是最近一笔持仓的开仓时间。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 最后进场时间（整数），格式如201907260932表示2019年7月26日09:32:00
        """
        # 调用C++接口函数，获取最后进场时间
        return self.api.cta_get_last_entertime(id, bytes(stdCode, encoding = "utf8"))

    def cta_get_last_entertag(self, id:int, stdCode:str) -> str:
        """
        CTA策略获取最后进场标记接口（回测引擎）
        
        获取当前持仓的最后进场标记。最后进场标记是最近一笔持仓的用户标记。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 最后进场标记（字符串），从字节字符串解码得到
        """
        # 调用C++接口函数，获取最后进场标记，并解码为Python字符串
        return bytes.decode(self.api.cta_get_last_entertag(id, bytes(stdCode, encoding = "utf8")))

    def cta_get_last_exittime(self, id:int, stdCode:str) -> int:
        """
        CTA策略获取最后出场时间接口（回测引擎）
        
        获取当前持仓的最后出场时间。最后出场时间是最近一笔平仓的时间。
        如果当前没有持仓，则返回0。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 最后出场时间（整数），格式如201907260932表示2019年7月26日09:32:00，0表示没有出场记录
        """
        # 调用C++接口函数，获取最后出场时间
        return self.api.cta_get_last_exittime(id, bytes(stdCode, encoding = "utf8"))

    def cta_log_text(self, id:int, level:int, message:str):
        """
        CTA策略日志输出接口（回测引擎）
        
        输出策略日志。日志用于记录策略运行状态、交易决策等信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param level: 日志级别（整数），数值越大表示日志级别越高
        @param message: 日志内容（字符串），需要根据平台自动编码（Windows使用GBK，Linux使用UTF-8）
        """
        # 调用C++接口函数，输出策略日志
        # 使用PlatformHelper自动处理编码（Windows→GBK，Linux→UTF-8）
        self.api.cta_log_text(id, level, ph.auto_encode(message))

    def cta_get_detail_entertime(self, id:int, stdCode:str, usertag:str) -> int:
        """
        CTA策略获取指定标记持仓的进场时间接口（回测引擎）
        
        获取指定用户标记的持仓的进场时间。用于查询特定交易的详细信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param usertag: 进场标记（字符串，需要编码为UTF-8字节字符串），用于标识特定的持仓
        @return: 进场时间（整数），格式如201907260932表示2019年7月26日09:32:00，0表示未找到
        """
        # 调用C++接口函数，获取指定标记持仓的进场时间
        return self.api.cta_get_detail_entertime(id, bytes(stdCode, encoding = "utf8"), bytes(usertag, encoding = "utf8")) 

    def cta_get_detail_cost(self, id:int, stdCode:str, usertag:str) -> float:
        """
        CTA策略获取指定标记持仓的开仓价接口（回测引擎）
        
        获取指定用户标记的持仓的开仓价。用于查询特定交易的开仓成本。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param usertag: 进场标记（字符串，需要编码为UTF-8字节字符串），用于标识特定的持仓
        @return: 开仓价（浮点数），0表示未找到
        """
        # 调用C++接口函数，获取指定标记持仓的开仓价
        return self.api.cta_get_detail_cost(id, bytes(stdCode, encoding = "utf8"), bytes(usertag, encoding = "utf8")) 

    def cta_get_detail_profit(self, id:int, stdCode:str, usertag:str, flag:int):
        """
        CTA策略获取指定标记持仓的盈亏接口（回测引擎）
        
        获取指定用户标记的持仓的盈亏信息。可以查询浮动盈亏、最大浮盈、最大亏损等。
        回测引擎支持更多的盈亏查询选项，包括最大浮盈价格和最大浮亏价格。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param usertag: 进场标记（字符串，需要编码为UTF-8字节字符串），用于标识特定的持仓
        @param flag: 盈亏记号（整数），0-浮动盈亏，1-最大浮盈，-1-最大亏损（负数），2-最大浮盈价格，-2-最大浮亏价格
        @return: 盈亏（浮点数），根据flag返回相应的盈亏数据
        """
        # 调用C++接口函数，获取指定标记持仓的盈亏
        return self.api.cta_get_detail_profit(id, bytes(stdCode, encoding = "utf8"), bytes(usertag, encoding = "utf8"), flag) 

    def cta_save_user_data(self, id:int, key:str, val:str):
        """
        CTA策略保存用户数据接口（回测引擎）
        
        保存策略的用户自定义数据。用户数据可以用于存储策略的状态、参数等信息，
        数据会持久化保存，程序重启后可以加载。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param key: 数据键名（字符串，需要编码为UTF-8字节字符串），用于标识数据
        @param val: 数据值（字符串，需要编码为UTF-8字节字符串），要保存的数据内容
        """
        # 调用C++接口函数，保存用户数据
        self.api.cta_save_userdata(id, bytes(key, encoding = "utf8"), bytes(val, encoding = "utf8"))

    def cta_load_user_data(self, id:int, key:str, defVal:str  = ""):
        """
        CTA策略加载用户数据接口（回测引擎）
        
        加载策略的用户自定义数据。如果数据不存在，则返回默认值。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param key: 数据键名（字符串，需要编码为UTF-8字节字符串），用于标识数据
        @param defVal: 默认值（字符串，默认空字符串，需要编码为UTF-8字节字符串），当数据不存在时返回此值
        @return: 用户数据（字符串），从字节字符串解码得到，如果数据不存在则返回默认值
        """
        # 调用C++接口函数，加载用户数据，并解码为Python字符串
        ret = self.api.cta_load_userdata(id, bytes(key, encoding = "utf8"), bytes(defVal, encoding = "utf8"))
        return bytes.decode(ret)

    def cta_sub_ticks(self, id:int, stdCode:str):
        """
        CTA策略订阅Tick行情接口（回测引擎）
        
        订阅指定品种的Tick行情数据。订阅后，策略会收到该品种的所有Tick数据回调。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串），可以是具体合约或品种代码
        """
        # 调用C++接口函数，订阅Tick行情
        self.api.cta_sub_ticks(id, bytes(stdCode, encoding = "utf8"))

    def cta_sub_bar_events(self, id:int, stdCode:str, period:str):
        """
        CTA策略订阅K线事件接口（回测引擎）
        
        订阅指定品种和周期的K线闭合事件。订阅后，当K线闭合时，策略会收到K线数据回调。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串），可以是具体合约或品种代码
        @param period: K线周期（字符串，需要编码为UTF-8字节字符串），如"m5"表示5分钟K线
        """
        # 调用C++接口函数，订阅K线事件
        self.api.cta_sub_bar_events(id, bytes(stdCode, encoding = "utf8"), bytes(period, encoding = "utf8"))

    def cta_step(self, id:int) -> bool:
        """
        CTA策略单步执行接口（回测引擎特有）
        
        单步执行策略。此函数用于调试和精确控制回测进度，每次调用会执行一步回测。
        此函数是回测引擎特有的，实盘引擎没有。
        
        @param id: 策略ID，唯一标识一个策略实例
        @return: 是否还有数据需要执行，True表示还有数据，False表示回测已完成
        """
        # 调用C++接口函数，单步执行回测
        return self.api.cta_step(id)

    def cta_set_chart_kline(self, id:int, stdCode:str, period:str):
        """
        CTA策略设置图表K线接口（回测引擎）
        
        设置策略图表的K线数据源。图表用于可视化显示K线数据和指标。
        此函数应在策略初始化时调用。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param period: K线周期（字符串，需要编码为UTF-8字节字符串），如"m5"表示5分钟K线
        """
        # 调用C++接口函数，设置图表K线
        self.api.cta_set_chart_kline(id, bytes(stdCode, encoding = "utf8"), bytes(period, encoding = "utf8"))

    def cta_add_chart_mark(self, id:int, price:float, icon:str, tag:str = 'Notag'):
        """
        CTA策略添加图表标记接口（回测引擎）
        
        在图表上添加标记。标记用于标识重要的价格点，如开仓点、平仓点等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param price: 价格（浮点数），决定图标在图表上出现的位置
        @param icon: 图标ID（字符串，需要编码为UTF-8字节字符串），系统预定义的图标标识
        @param tag: 标签（字符串，默认'Notag'，需要编码为UTF-8字节字符串），自定义的标记说明
        """
        # 调用C++接口函数，添加图表标记
        self.api.cta_add_chart_mark(id, price, bytes(icon, encoding = "utf8"), bytes(tag, encoding = "utf8"))

    def cta_register_index(self, id:int, idxName:str, idxType:int = 1):
        """
        CTA策略注册指标接口（回测引擎）
        
        注册一个指标。指标用于在图表上显示技术分析数据，如均线、MACD等。
        此函数应在策略初始化时（on_init）调用。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param idxName: 指标名称（字符串，需要编码为UTF-8字节字符串），用于标识指标
        @param idxType: 指标类型（整数，默认1），0-主图指标（显示在K线图上），1-副图指标（显示在独立图表上）
        """
        # 调用C++接口函数，注册指标
        self.api.cta_register_index(id, bytes(idxName, encoding = "utf8"), idxType)

    def cta_register_index_line(self, id:int, idxName:str, lineName:str, lineType:int = 0) -> bool:
        """
        CTA策略注册指标线接口（回测引擎）
        
        为指标注册一条数据线。一个指标可以有多条数据线，如MACD有MACD线、信号线、柱状图等。
        此函数应在策略初始化时（on_init）调用。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param idxName: 指标名称（字符串，需要编码为UTF-8字节字符串），已注册的指标名称
        @param lineName: 线名称（字符串，需要编码为UTF-8字节字符串），用于标识数据线
        @param lineType: 线型（整数，默认0），0-曲线，1-柱子
        @return: 是否注册成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，注册指标线
        return self.api.cta_register_index_line(id, bytes(idxName, encoding = "utf8"), bytes(lineName, encoding = "utf8"), lineType)

    def cta_add_index_baseline(self, id:int, idxName:str, lineName:str, value:float) -> bool:
        """
        CTA策略添加指标基准线接口（回测引擎）
        
        为指标线添加基准线。基准线是一条水平参考线，用于辅助分析。
        此函数应在策略初始化时（on_init）调用。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param idxName: 指标名称（字符串，需要编码为UTF-8字节字符串），已注册的指标名称
        @param lineName: 线名称（字符串，需要编码为UTF-8字节字符串），已注册的线名称
        @param value: 基准值（浮点数），基准线的数值
        @return: 是否添加成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，添加指标基准线
        return self.api.cta_add_index_baseline(id, bytes(idxName, encoding = "utf8"), bytes(lineName, encoding = "utf8"), value)

    def cta_set_index_value(self, id:int, idxName:str, lineName:str, val:float) -> bool:
        """
        CTA策略设置指标值接口（回测引擎）
        
        设置指标线的数值。此函数用于更新指标的计算结果，应在策略计算时（on_calculate）调用。
        只有在on_calculate的时候调用此函数才会生效。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param idxName: 指标名称（字符串，需要编码为UTF-8字节字符串），已注册的指标名称
        @param lineName: 线名称（字符串，需要编码为UTF-8字节字符串），已注册的线名称
        @param val: 指标值（浮点数），要设置的指标数值
        @return: 是否设置成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，设置指标值
        return self.api.cta_set_index_value(id, bytes(idxName, encoding = "utf8"), bytes(lineName, encoding = "utf8"), val)

    # ========== SEL策略接口（回测引擎） ==========
    def sel_get_bars(self, id:int, stdCode:str, period:str, count:int):
        """
        SEL策略获取K线数据接口（回测引擎）
        
        查询指定合约的K线历史数据。K线数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_stra_get_bar回调函数返回。
        注意：回测引擎的sel_get_bars接口没有isMain参数。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param period: K线周期（字符串，如"m1"表示1分钟，"m5"表示5分钟，"d1"表示日线，需要编码为UTF-8字节字符串）
        @param count: 查询条数（整数），表示需要获取多少根K线
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询K线数据
        # 数据通过on_stra_get_bar回调函数异步返回
        return self.api.sel_get_bars(id, bytes(stdCode, encoding = "utf8"), bytes(period, encoding = "utf8"), count, CB_STRATEGY_GET_BAR(self.on_stra_get_bar))
    
    def sel_get_ticks(self, id:int, stdCode:str, count:int):
        """
        SEL策略获取Tick数据接口（回测引擎）
        
        查询指定合约的Tick历史数据。Tick数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_stra_get_tick回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param count: 查询条数（整数），表示需要获取多少笔Tick数据
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询Tick数据
        # 数据通过on_stra_get_tick回调函数异步返回
        return self.api.sel_get_ticks(id, bytes(stdCode, encoding = "utf8"), count, CB_STRATEGY_GET_TICK(self.on_stra_get_tick))

    def sel_save_user_data(self, id:int, key:str, val:str):
        """
        SEL策略保存用户数据接口（回测引擎）
        
        保存策略的自定义数据。这些数据可以在策略的不同运行周期之间持久化保存，
        用于存储策略的状态、参数等信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param key: 数据键名（字符串，需要编码为UTF-8字节字符串），用于标识数据
        @param val: 数据值（字符串，需要编码为UTF-8字节字符串），要保存的数据内容
        """
        # 调用C++接口函数，保存用户数据
        self.api.sel_save_userdata(id, bytes(key, encoding = "utf8"), bytes(val, encoding = "utf8"))

    def sel_load_user_data(self, id:int, key:str, defVal:str  = ""):
        """
        SEL策略加载用户数据接口（回测引擎）
        
        加载策略的自定义数据。如果数据不存在，返回默认值。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param key: 数据键名（字符串，需要编码为UTF-8字节字符串），用于标识数据
        @param defVal: 默认值（字符串，默认空字符串，需要编码为UTF-8字节字符串），当数据不存在时返回此值
        @return: 数据值（字符串），如果数据存在则返回保存的值，否则返回默认值
        """
        # 调用C++接口函数，加载用户数据
        ret = self.api.sel_load_userdata(id, bytes(key, encoding = "utf8"), bytes(defVal, encoding = "utf8"))
        # 将返回的字节字符串解码为Python字符串
        return bytes.decode(ret)

    def sel_get_all_position(self, id:int):
        """
        SEL策略获取全部持仓接口（回测引擎）
        
        获取策略的所有持仓信息。持仓信息通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_stra_get_position回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询全部持仓
        # 持仓信息通过on_stra_get_position回调函数异步返回
        return self.api.sel_get_all_position(id, CB_STRATEGY_GET_POSITION(self.on_stra_get_position))

    def sel_get_position(self, id:int, stdCode:str, bonlyvalid:bool = False, usertag:str = ""):
        """
        SEL策略获取持仓接口（回测引擎）
        
        获取指定合约的持仓数量。如果指定了usertag，则获取该标记的持仓；如果usertag为空，
        则获取该合约的全部持仓。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param bonlyvalid: 是否仅获取有效持仓（布尔值，默认False），True表示仅获取有效持仓
        @param usertag: 进场标记（字符串，默认空字符串，需要编码为UTF-8字节字符串），如果为空则获取该合约全部持仓
        @return: 持仓数量（浮点数），正数表示多头持仓，负数表示空头持仓
        """
        # 调用C++接口函数，查询持仓
        return self.api.sel_get_position(id, bytes(stdCode, encoding = "utf8"), bonlyvalid, bytes(usertag, encoding = "utf8"))

    def sel_get_price(self, stdCode:str):
        """
        SEL策略获取最新价格接口（回测引擎）
        
        获取指定合约的最新价格。这是回测引擎中当前时刻该合约的最新成交价。
        
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 最新价格（浮点数），指定合约的最新成交价
        """
        # 调用C++接口函数，查询最新价格
        return self.api.sel_get_price(bytes(stdCode, encoding = "utf8"))

    def sel_set_position(self, id:int, stdCode:str, qty:float, usertag:str = ""):
        """
        SEL策略设置目标仓位接口（回测引擎）
        
        设置指定合约的目标持仓数量。回测引擎会根据目标仓位自动进行交易，调整实际持仓
        以达到目标仓位。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param qty: 目标仓位（浮点数），正数表示目标多头持仓，负数表示目标空头持仓
        @param usertag: 进场标记（字符串，默认空字符串，需要编码为UTF-8字节字符串），用于标识持仓
        """
        # 调用C++接口函数，设置目标仓位
        self.api.sel_set_position(id, bytes(stdCode, encoding = "utf8"), qty, bytes(usertag, encoding = "utf8"))
    
    def sel_get_tdate(self) -> int:
        """
        SEL策略获取当前交易日接口（回测引擎）
        
        获取回测引擎当前模拟的交易日。交易日格式为YYYYMMDD的整数形式。
        
        @return: 当前交易日（整数），格式如20190726
        """
        # 调用C++接口函数，获取当前交易日
        return self.api.sel_get_tdate()
    
    def sel_get_date(self):
        """
        SEL策略获取当前日期接口（回测引擎）
        
        获取回测引擎当前模拟的日期。日期格式为YYYYMMDD的整数形式。
        
        @return: 当前日期（整数），格式如20190726
        """
        # 调用C++接口函数，获取当前日期
        return self.api.sel_get_date()

    def sel_get_time(self):
        """
        SEL策略获取当前时间接口（回测引擎）
        
        获取回测引擎当前模拟的时间。时间格式为HHMMSS的整数形式。
        
        @return: 当前时间（整数），格式如093200（表示9点32分0秒）
        """
        # 调用C++接口函数，获取当前时间
        return self.api.sel_get_time()

    def sel_log_text(self, id:int, level:int, message:str):
        """
        SEL策略日志输出接口（回测引擎）
        
        输出策略日志。日志会被记录到回测引擎的日志系统中，用于策略调试和运行监控。
        
        @param id: 策略ID（整数），唯一标识一个策略实例
        @param level: 日志级别（整数），用于标识日志的重要性
        @param message: 日志内容（字符串），需要编码为平台特定的编码（Windows为GBK，Linux为UTF-8）
        """
        # 调用C++接口函数，输出日志
        # 使用PlatformHelper的auto_encode方法进行编码转换
        self.api.sel_log_text(id, level, ph.auto_encode(message))

    def sel_sub_ticks(self, id:int, stdCode:str):
        """
        SEL策略订阅行情接口（回测引擎）
        
        订阅指定合约的Tick行情数据。订阅后，当该合约有新的Tick数据时，会触发策略的
        on_tick回调函数。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串），要订阅的合约
        """
        # 调用C++接口函数，订阅行情
        self.api.sel_sub_ticks(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_day_price(self, stdCode:str, flag:int = 0) -> float:
        """
        SEL策略获取当日价格接口（回测引擎）
        
        获取指定合约当日的特定价格，如开盘价、最高价、最低价、最新价等。
        
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param flag: 价格标记（整数，默认0），0-开盘价，1-最高价，2-最低价，3-最新价
        @return: 价格（浮点数），指定合约的指定价格
        """
        # 调用C++接口函数，查询当日价格
        return self.api.sel_get_day_price(bytes(stdCode, encoding = "utf8"), flag)

    def sel_get_fund_data(self, id:int, flag:int) -> float:
        """
        SEL策略获取资金数据接口（回测引擎）
        
        获取策略的资金相关数据，如动态权益、平仓盈亏、浮动盈亏、手续费等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param flag: 数据标记（整数），0-动态权益，1-总平仓盈亏，2-总浮动盈亏，3-总手续费
        @return: 资金数据（浮点数），指定类型的资金数据
        """
        # 调用C++接口函数，查询资金数据
        return self.api.sel_get_fund_data(id, flag)

    def sel_get_position_profit(self, id:int, stdCode:str):
        """
        SEL策略获取持仓浮动盈亏接口（回测引擎）
        
        获取指定合约的持仓浮动盈亏。浮动盈亏是根据当前价格和持仓成本价计算的未实现盈亏。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 浮动盈亏（浮点数），指定合约的持仓浮动盈亏
        """
        # 调用C++接口函数，查询持仓浮动盈亏
        return self.api.sel_get_position_profit(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_position_avgpx(self, id:int, stdCode:str):
        """
        SEL策略获取持仓均价接口（回测引擎）
        
        获取指定合约的持仓平均成本价。持仓均价是所有持仓的平均开仓价格。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 持仓均价（浮点数），指定合约的持仓平均成本价
        """
        # 调用C++接口函数，查询持仓均价
        return self.api.sel_get_position_avgpx(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_first_entertime(self, id:int, stdCode:str) -> int:
        """
        SEL策略获取首次进场时间接口（回测引擎）
        
        获取指定合约当前持仓的首次进场时间。首次进场时间是指该合约持仓中最早的开仓时间。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 进场时间（整数），格式如201907260932（表示2019年7月26日9点32分）
        """
        # 调用C++接口函数，查询首次进场时间
        return self.api.sel_get_first_entertime(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_last_entertime(self, id:int, stdCode:str) -> int:
        """
        SEL策略获取最后进场时间接口（回测引擎）
        
        获取指定合约当前持仓的最后进场时间。最后进场时间是指该合约持仓中最近的开仓时间。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 进场时间（整数），格式如201907260932（表示2019年7月26日9点32分）
        """
        # 调用C++接口函数，查询最后进场时间
        return self.api.sel_get_last_entertime(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_last_entertag(self, id:int, stdCode:str) -> str:
        """
        SEL策略获取最后进场标记接口（回测引擎）
        
        获取指定合约当前持仓的最后进场标记。进场标记是策略在开仓时设置的标识符。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 进场标记（字符串），最后进场的标记
        """
        # 调用C++接口函数，查询最后进场标记
        # 将返回的字节字符串解码为Python字符串
        return bytes.decode(self.api.sel_get_last_entertag(id, bytes(stdCode, encoding = "utf8")))

    def sel_get_last_exittime(self, id:int, stdCode:str) -> int:
        """
        SEL策略获取最后出场时间接口（回测引擎）
        
        获取指定合约当前持仓的最后出场时间。出场时间是指该合约持仓中最近的平仓时间。
        如果持仓从未平仓，则返回0或无效值。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 出场时间（整数），格式如201907260932（表示2019年7月26日9点32分）
        """
        # 调用C++接口函数，查询最后出场时间
        return self.api.sel_get_last_exittime(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_detail_entertime(self, id:int, stdCode:str, usertag:str) -> int:
        """
        SEL策略获取指定标记持仓的进场时间接口（回测引擎）
        
        获取指定合约、指定标记的持仓的进场时间。此函数用于查询特定标记持仓的详细信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param usertag: 进场标记（字符串，需要编码为UTF-8字节字符串），用于标识持仓
        @return: 进场时间（整数），格式如201907260932（表示2019年7月26日9点32分）
        """
        # 调用C++接口函数，查询指定标记持仓的进场时间
        return self.api.sel_get_detail_entertime(id, bytes(stdCode, encoding = "utf8"), bytes(usertag, encoding = "utf8")) 

    def sel_get_detail_cost(self, id:int, stdCode:str, usertag:str) -> float:
        """
        SEL策略获取指定标记持仓的开仓价接口（回测引擎）
        
        获取指定合约、指定标记的持仓的开仓价格。开仓价是该标记持仓的平均成本价。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param usertag: 进场标记（字符串，需要编码为UTF-8字节字符串），用于标识持仓
        @return: 开仓价（浮点数），指定标记持仓的平均成本价
        """
        # 调用C++接口函数，查询指定标记持仓的开仓价
        return self.api.sel_get_detail_cost(id, bytes(stdCode, encoding = "utf8"), bytes(usertag, encoding = "utf8")) 

    def sel_get_detail_profit(self, id:int, stdCode:str, usertag:str, flag:int):
        """
        SEL策略获取指定标记持仓的盈亏接口（回测引擎）
        
        获取指定合约、指定标记的持仓的盈亏信息。可以查询浮动盈亏、最大浮盈、最大浮亏、
        最大浮盈价格、最大浮亏价格等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param usertag: 进场标记（字符串，需要编码为UTF-8字节字符串），用于标识持仓
        @param flag: 盈亏标记（整数），0-浮动盈亏，1-最大浮盈，-1-最大亏损（负数），2-最大浮盈价格，-2-最大浮亏价格
        @return: 盈亏数据（浮点数），指定类型的盈亏数据
        """
        # 调用C++接口函数，查询指定标记持仓的盈亏
        return self.api.sel_get_detail_profit(id, bytes(stdCode, encoding = "utf8"), bytes(usertag, encoding = "utf8"), flag) 


    # ========== HFT策略接口（回测引擎） ==========
    def hft_get_bars(self, id:int, stdCode:str, period:str, count:int):
        """
        HFT策略获取K线数据接口（回测引擎）
        
        查询指定合约的K线历史数据。K线数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_stra_get_bar回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param period: K线周期（字符串，如"m1"表示1分钟，"m5"表示5分钟，"d1"表示日线，需要编码为UTF-8字节字符串）
        @param count: 查询条数（整数），表示需要获取多少根K线
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询K线数据
        # 数据通过on_stra_get_bar回调函数异步返回
        return self.api.hft_get_bars(id, bytes(stdCode, encoding = "utf8"), bytes(period, encoding = "utf8"), count, CB_STRATEGY_GET_BAR(self.on_stra_get_bar))
    
    def hft_get_ticks(self, id:int, stdCode:str, count:int):
        """
        HFT策略获取Tick数据接口（回测引擎）
        
        查询指定合约的Tick历史数据。Tick数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_stra_get_tick回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param count: 查询条数（整数），表示需要获取多少笔Tick数据
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询Tick数据
        # 数据通过on_stra_get_tick回调函数异步返回
        return self.api.hft_get_ticks(id, bytes(stdCode, encoding = "utf8"), count, CB_STRATEGY_GET_TICK(self.on_stra_get_tick))

    def hft_get_ordque(self, id:int, stdCode:str, count:int):
        """
        HFT策略获取委托队列数据接口（回测引擎）
        
        查询指定合约的委托队列历史数据。委托队列数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_hftstra_get_order_queue回调函数返回。
        委托队列数据包含买卖盘口的挂单信息，用于分析市场深度。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param count: 查询条数（整数），表示需要获取多少条委托队列数据
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询委托队列数据
        # 数据通过on_hftstra_get_order_queue回调函数异步返回
        return self.api.hft_get_ordque(id, bytes(stdCode, encoding = "utf8"), count, CB_HFTSTRA_GET_ORDQUE(self.on_hftstra_get_order_queue))

    def hft_get_orddtl(self, id:int, stdCode:str, count:int):
        """
        HFT策略获取逐笔委托数据接口（回测引擎）
        
        查询指定合约的逐笔委托历史数据。逐笔委托数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_hftstra_get_order_detail回调函数返回。
        逐笔委托数据包含每一笔委托的详细信息，用于分析市场微观结构。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param count: 查询条数（整数），表示需要获取多少条逐笔委托数据
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询逐笔委托数据
        # 数据通过on_hftstra_get_order_detail回调函数异步返回
        return self.api.hft_get_orddtl(id, bytes(stdCode, encoding = "utf8"), count, CB_HFTSTRA_GET_ORDDTL(self.on_hftstra_get_order_detail))

    def hft_get_trans(self, id:int, stdCode:str, count:int):
        """
        HFT策略获取逐笔成交数据接口（回测引擎）
        
        查询指定合约的逐笔成交历史数据。逐笔成交数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_hftstra_get_transaction回调函数返回。
        逐笔成交数据包含每一笔成交的详细信息，用于分析市场成交情况。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param count: 查询条数（整数），表示需要获取多少条逐笔成交数据
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询逐笔成交数据
        # 数据通过on_hftstra_get_transaction回调函数异步返回
        return self.api.hft_get_trans(id, bytes(stdCode, encoding = "utf8"), count, CB_HFTSTRA_GET_TRANS(self.on_hftstra_get_transaction))

    def hft_save_user_data(self, id:int, key:str, val:str):
        """
        HFT策略保存用户数据接口（回测引擎）
        
        保存策略的自定义数据。这些数据可以在策略的不同运行周期之间持久化保存，
        用于存储策略的状态、参数等信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param key: 数据键名（字符串，需要编码为UTF-8字节字符串），用于标识数据
        @param val: 数据值（字符串，需要编码为UTF-8字节字符串），要保存的数据内容
        """
        # 调用C++接口函数，保存用户数据
        self.api.hft_save_userdata(id, bytes(key, encoding = "utf8"), bytes(val, encoding = "utf8"))

    def hft_load_user_data(self, id:int, key:str, defVal:str  = ""):
        """
        HFT策略加载用户数据接口（回测引擎）
        
        加载策略的自定义数据。如果数据不存在，返回默认值。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param key: 数据键名（字符串，需要编码为UTF-8字节字符串），用于标识数据
        @param defVal: 默认值（字符串，默认空字符串，需要编码为UTF-8字节字符串），当数据不存在时返回此值
        @return: 数据值（字符串），如果数据存在则返回保存的值，否则返回默认值
        """
        # 调用C++接口函数，加载用户数据
        ret = self.api.hft_load_userdata(id, bytes(key, encoding = "utf8"), bytes(defVal, encoding = "utf8"))
        # 将返回的字节字符串解码为Python字符串
        return bytes.decode(ret)

    def hft_get_position(self, id:int, stdCode:str, bonlyvalid:bool = False):
        """
        HFT策略获取持仓接口（回测引擎）
        
        获取指定合约的持仓数量。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param bonlyvalid: 是否仅获取有效持仓（布尔值，默认False），True表示仅获取有效持仓
        @return: 持仓数量（浮点数），正数表示多头持仓，负数表示空头持仓
        """
        # 调用C++接口函数，查询持仓
        return self.api.hft_get_position(id, bytes(stdCode, encoding = "utf8"), bonlyvalid)

    def hft_get_position_profit(self, id:int, stdCode:str):
        """
        HFT策略获取持仓浮动盈亏接口（回测引擎）
        
        获取指定合约的持仓浮动盈亏。浮动盈亏是根据当前价格和持仓成本价计算的未实现盈亏。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 浮动盈亏（浮点数），指定合约的持仓浮动盈亏
        """
        # 调用C++接口函数，查询持仓浮动盈亏
        return self.api.hft_get_position_profit(id, bytes(stdCode, encoding = "utf8"))

    def hft_get_position_avgpx(self, id:int, stdCode:str):
        """
        HFT策略获取持仓均价接口（回测引擎）
        
        获取指定合约的持仓平均成本价。持仓均价是所有持仓的平均开仓价格。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 持仓均价（浮点数），指定合约的持仓平均成本价
        """
        # 调用C++接口函数，查询持仓均价
        return self.api.hft_get_position_avgpx(id, bytes(stdCode, encoding = "utf8"))

    def hft_get_undone(self, id:int, stdCode:str):
        """
        HFT策略获取未成交订单数量接口（回测引擎）
        
        获取指定合约的未成交订单数量。未成交订单是指已提交但尚未完全成交的订单。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 未成交订单数量（浮点数），正数表示买入未成交，负数表示卖出未成交
        """
        # 调用C++接口函数，查询未成交订单数量
        return self.api.hft_get_undone(id, bytes(stdCode, encoding = "utf8"))

    def hft_get_price(self, stdCode:str):
        """
        HFT策略获取最新价格接口（回测引擎）
        
        获取指定合约的最新价格。这是回测引擎中当前时刻该合约的最新成交价。
        
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 最新价格（浮点数），指定合约的最新成交价
        """
        # 调用C++接口函数，查询最新价格
        return self.api.hft_get_price(bytes(stdCode, encoding = "utf8"))

    def hft_get_date(self):
        """
        HFT策略获取当前日期接口（回测引擎）
        
        获取回测引擎当前模拟的日期。日期格式为YYYYMMDD的整数形式。
        
        @return: 当前日期（整数），格式如20190726
        """
        # 调用C++接口函数，获取当前日期
        return self.api.hft_get_date()

    def hft_get_time(self):
        """
        HFT策略获取当前时间接口（回测引擎）
        
        获取回测引擎当前模拟的时间。时间格式为HHMMSS的整数形式。
        
        @return: 当前时间（整数），格式如093200（表示9点32分0秒）
        """
        # 调用C++接口函数，获取当前时间
        return self.api.hft_get_time()

    def hft_get_secs(self):
        """
        HFT策略获取当前秒数接口（回测引擎）
        
        获取回测引擎当前模拟的时间（从当日0点开始的秒数）。此函数返回从当日0点开始
        到当前时刻的秒数，用于精确的时间计算。
        
        @return: 当前秒数（整数），从当日0点开始到当前时刻的秒数
        """
        # 调用C++接口函数，获取当前秒数
        return self.api.hft_get_secs()

    def hft_log_text(self, id:int, level:int, message:str):
        """
        HFT策略日志输出接口（回测引擎）
        
        输出策略日志。日志会被记录到回测引擎的日志系统中，用于策略调试和运行监控。
        
        @param id: 策略ID（整数），唯一标识一个策略实例
        @param level: 日志级别（整数），用于标识日志的重要性
        @param message: 日志内容（字符串），需要编码为平台特定的编码（Windows为GBK，Linux为UTF-8）
        """
        # 调用C++接口函数，输出日志
        # 使用PlatformHelper的auto_encode方法进行编码转换
        self.api.hft_log_text(id, level, ph.auto_encode(message))

    def hft_sub_ticks(self, id:int, stdCode:str):
        """
        HFT策略订阅Tick行情接口（回测引擎）
        
        订阅指定合约的Tick行情数据。订阅后，当该合约有新的Tick数据时，会触发策略的
        on_tick回调函数。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串），要订阅的合约
        """
        # 调用C++接口函数，订阅Tick行情
        self.api.hft_sub_ticks(id, bytes(stdCode, encoding = "utf8"))

    def hft_sub_order_queue(self, id:int, stdCode:str):
        """
        HFT策略订阅委托队列接口（回测引擎）
        
        订阅指定合约的委托队列数据。订阅后，当该合约有新的委托队列数据时，会触发策略的
        on_order_queue回调函数。委托队列数据包含买卖盘口的挂单信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串），要订阅的合约
        """
        # 调用C++接口函数，订阅委托队列
        self.api.hft_sub_order_queue(id, bytes(stdCode, encoding = "utf8"))

    def hft_sub_order_detail(self, id:int, stdCode:str):
        """
        HFT策略订阅逐笔委托接口（回测引擎）
        
        订阅指定合约的逐笔委托数据。订阅后，当该合约有新的逐笔委托数据时，会触发策略的
        on_order_detail回调函数。逐笔委托数据包含每一笔委托的详细信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串），要订阅的合约
        """
        # 调用C++接口函数，订阅逐笔委托
        self.api.hft_sub_order_detail(id, bytes(stdCode, encoding = "utf8"))

    def hft_sub_transaction(self, id:int, stdCode:str):
        """
        HFT策略订阅逐笔成交接口（回测引擎）
        
        订阅指定合约的逐笔成交数据。订阅后，当该合约有新的逐笔成交数据时，会触发策略的
        on_transaction回调函数。逐笔成交数据包含每一笔成交的详细信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串），要订阅的合约
        """
        # 调用C++接口函数，订阅逐笔成交
        self.api.hft_sub_transaction(id, bytes(stdCode, encoding = "utf8"))

    def hft_cancel(self, id:int, localid:int):
        """
        HFT策略撤销指定订单接口（回测引擎）
        
        撤销指定的订单。撤销操作会立即执行，撤销结果通过on_order回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param localid: 本地订单号（整数），下单时返回的订单标识
        @return: 是否撤销成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，撤销指定订单
        return self.api.hft_cancel(id, localid)

    def hft_cancel_all(self, id:int, stdCode:str, isBuy:bool):
        """
        HFT策略撤销全部订单接口（回测引擎）
        
        撤销指定合约的全部买入订单或卖出订单。撤销操作会立即执行，撤销结果通过
        on_order回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param isBuy: 是否买入订单（布尔值），True表示撤销买入订单，False表示撤销卖出订单
        @return: 撤销结果消息（字符串），包含撤销操作的详细信息
        """
        # 调用C++接口函数，撤销全部订单
        ret = self.api.hft_cancel_all(id, bytes(stdCode, encoding = "utf8"), isBuy)
        # 将返回的字节字符串解码为Python字符串
        return bytes.decode(ret)

    def hft_buy(self, id:int, stdCode:str, price:float, qty:float, userTag:str, flag:int):
        """
        HFT策略买入指令接口（回测引擎）
        
        提交买入订单。订单提交后，会立即返回本地订单号，订单状态变化通过on_order和
        on_trade回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param price: 买入价格（浮点数），0表示市价单
        @param qty: 买入数量（浮点数）
        @param userTag: 用户标记（字符串，需要编码为UTF-8字节字符串），用于标识订单
        @param flag: 订单标志（整数），用于控制订单行为
        @return: 本地订单号（字符串），用于标识订单，后续可以通过此订单号撤销订单
        """
        # 调用C++接口函数，提交买入订单
        ret = self.api.hft_buy(id, bytes(stdCode, encoding = "utf8"), price, qty, bytes(userTag, encoding = "utf8"), flag)
        # 将返回的字节字符串解码为Python字符串
        return bytes.decode(ret)

    def hft_sell(self, id:int, stdCode:str, price:float, qty:float, userTag:str, flag:int):
        """
        HFT策略卖出指令接口（回测引擎）
        
        提交卖出订单。订单提交后，会立即返回本地订单号，订单状态变化通过on_order和
        on_trade回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param price: 卖出价格（浮点数），0表示市价单
        @param qty: 卖出数量（浮点数）
        @param userTag: 用户标记（字符串，需要编码为UTF-8字节字符串），用于标识订单
        @param flag: 订单标志（整数），用于控制订单行为
        @return: 本地订单号（字符串），用于标识订单，后续可以通过此订单号撤销订单
        """
        # 调用C++接口函数，提交卖出订单
        ret = self.api.hft_sell(id, bytes(stdCode, encoding = "utf8"), price, qty, bytes(userTag, encoding = "utf8"), flag)
        # 将返回的字节字符串解码为Python字符串
        return bytes.decode(ret)

    def hft_step(self, id:int):
        """
        HFT策略单步执行接口（回测引擎）
        
        单步执行策略。此函数用于控制回测引擎的执行节奏，每次调用会处理一个时间点的数据。
        主要用于调试和精确控制回测过程。
        
        @param id: 策略ID，唯一标识一个策略实例
        """
        # 调用C++接口函数，单步执行策略
        self.api.hft_step(id)


    # ========== 本地撮合接口（回测引擎） ==========
    def init_cta_mocker(self, name:str, slippage:int = 0, hook:bool = False, persistData:bool = True, incremental:bool = False, isRatioSlp:bool = False) -> int:
        """
        初始化CTA策略本地撮合器接口（回测引擎）
        
        创建CTA策略的回测环境。本地撮合器用于模拟交易撮合过程，包括滑点模拟、
        数据持久化等功能。此函数会创建一个策略实例并返回策略ID。
        
        @param name: 策略名称（字符串，需要编码为UTF-8字节字符串），用于标识策略
        @param slippage: 滑点大小（整数，默认0），用于模拟交易时的价格滑点
        @param hook: 是否安装钩子（布尔值，默认False），主要用于单步控制重算，用于调试
        @param persistData: 回测生成的数据是否落地（布尔值，默认True），True表示保存回测数据到文件
        @param incremental: 是否增量回测（布尔值，默认False），True表示增量回测模式
        @param isRatioSlp: 滑点是否是比例（布尔值，默认False），True表示slippage为万分比，False表示绝对价格
        @return: 系统内策略ID（整数），用于后续操作该策略实例
        """
        # 调用C++接口函数，初始化CTA策略本地撮合器
        return self.api.init_cta_mocker(bytes(name, encoding = "utf8"), slippage, hook, persistData, incremental, isRatioSlp)

    def init_hft_mocker(self, name:str, hook:bool = False) -> int:
        """
        初始化HFT策略本地撮合器接口（回测引擎）
        
        创建HFT策略的回测环境。本地撮合器用于模拟高频交易的撮合过程。
        此函数会创建一个策略实例并返回策略ID。
        
        @param name: 策略名称（字符串，需要编码为UTF-8字节字符串），用于标识策略
        @param hook: 是否安装钩子（布尔值，默认False），主要用于单步控制重算，用于调试
        @return: 系统内策略ID（整数），用于后续操作该策略实例
        """
        # 调用C++接口函数，初始化HFT策略本地撮合器
        return self.api.init_hft_mocker(bytes(name, encoding = "utf8"), hook)

    def init_sel_mocker(self, name:str, date:int, time:int, period:str, trdtpl:str = "CHINA", session:str = "TRADING", slippage:int = 0, isRatioSlp:bool = False) -> int:
        """
        初始化SEL策略本地撮合器接口（回测引擎）
        
        创建SEL策略的回测环境。本地撮合器用于模拟选股策略的交易撮合过程。
        此函数会创建一个策略实例并返回策略ID。
        
        @param name: 策略名称（字符串，需要编码为UTF-8字节字符串），用于标识策略
        @param date: 起始日期（整数），格式如20190726（YYYYMMDD）
        @param time: 起始时间（整数），格式如93200（HHMMSS）
        @param period: K线周期（字符串，需要编码为UTF-8字节字符串），如"m5"表示5分钟K线
        @param trdtpl: 交易模板（字符串，默认"CHINA"，需要编码为UTF-8字节字符串），用于定义交易规则
        @param session: 交易时段（字符串，默认"TRADING"，需要编码为UTF-8字节字符串），用于定义交易时间段
        @param slippage: 滑点大小（整数，默认0），用于模拟交易时的价格滑点
        @param isRatioSlp: 滑点是否是比例（布尔值，默认False），True表示slippage为万分比，False表示绝对价格
        @return: 系统内策略ID（整数），用于后续操作该策略实例
        """
        # 调用C++接口函数，初始化SEL策略本地撮合器
        return self.api.init_sel_mocker(bytes(name, encoding = "utf8"), date, time, 
            bytes(period, encoding = "utf8"), bytes(trdtpl, encoding = "utf8"), bytes(session, encoding = "utf8"), slippage, isRatioSlp)
