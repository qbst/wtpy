"""
实盘交易引擎包装器模块

本模块提供WonderTrader实盘交易引擎的Python接口封装。实盘交易引擎是wtpy框架的核心组件，
负责管理策略的执行、交易指令的下达、行情数据的接收和处理等。

主要功能：
1. 支持三种策略类型：CTA（商品交易顾问）、SEL（选股策略）、HFT（高频交易）
2. 策略生命周期管理：初始化、计算、行情推送、会话事件等
3. 交易指令接口：开多、开空、平多、平空、设置目标仓位等
4. 数据查询接口：获取K线、Tick、持仓、资金等信息
5. 扩展模块支持：扩展数据解析器、执行器、数据加载器等
6. 用户数据存储：保存和加载策略的用户自定义数据
7. 图表功能：支持K线图表、指标、标记等可视化功能

使用单例模式确保全局只有一个实盘交易引擎包装器实例。
"""

# 导入ctypes库，用于调用C++动态库
from ctypes import c_int32, cdll, c_char_p, c_bool, c_ulong, c_uint64, c_uint32, c_double, POINTER
# 导入执行器回调函数类型定义
from wtpy.WtCoreDefs import CB_EXECUTER_CMD, CB_EXECUTER_INIT, CB_PARSER_EVENT, CB_PARSER_SUBCMD
# 导入策略回调函数类型定义
from wtpy.WtCoreDefs import CB_STRATEGY_INIT, CB_STRATEGY_TICK, CB_STRATEGY_CALC, CB_STRATEGY_BAR, CB_STRATEGY_GET_BAR, CB_STRATEGY_GET_TICK, CB_STRATEGY_GET_POSITION, CB_STRATEGY_COND_TRIGGER
# 导入解析器事件类型定义
from wtpy.WtCoreDefs import EVENT_PARSER_CONNECT, EVENT_PARSER_DISCONNECT, EVENT_PARSER_INIT, EVENT_PARSER_RELEASE
# 导入HFT策略回调函数类型定义
from wtpy.WtCoreDefs import CB_HFTSTRA_CHNL_EVT, CB_HFTSTRA_ENTRUST, CB_HFTSTRA_ORD, CB_HFTSTRA_TRD, CB_SESSION_EVENT, CB_HFTSTRA_POSITION
# 导入HFT策略数据回调函数类型定义
from wtpy.WtCoreDefs import CB_HFTSTRA_ORDQUE, CB_HFTSTRA_ORDDTL, CB_HFTSTRA_TRANS, CB_HFTSTRA_GET_ORDQUE, CB_HFTSTRA_GET_ORDDTL, CB_HFTSTRA_GET_TRANS
# 导入通道事件和引擎事件类型定义
from wtpy.WtCoreDefs import CHNL_EVENT_READY, CHNL_EVENT_LOST, CB_ENGINE_EVENT
# 导入历史数据加载函数类型定义
from wtpy.WtCoreDefs import FUNC_LOAD_HISBARS, FUNC_LOAD_HISTICKS, FUNC_LOAD_ADJFACTS
# 导入引擎事件类型定义
from wtpy.WtCoreDefs import EVENT_ENGINE_INIT, EVENT_SESSION_BEGIN, EVENT_SESSION_END, EVENT_ENGINE_SCHDL
# 导入数据结构定义
from wtpy.WtCoreDefs import WTSTickStruct, WTSBarStruct, WTSOrdQueStruct, WTSOrdDtlStruct, WTSTransStruct
# 导入NumPy数组封装类
from wtpy.WtDataDefs import WtNpKline, WtNpOrdDetails, WtNpOrdQueues, WtNpTicks, WtNpTransactions
# 导入单例装饰器，确保全局唯一实例
from wtpy.WtUtilDefs import singleton
# 导入平台辅助工具，用于获取动态库路径和编码转换
from .PlatformHelper import PlatformHelper as ph
# 导入操作系统模块
import os

# Python对接C接口的库
@singleton
class WtWrapper:
    """
    WonderTrader实盘交易引擎C接口底层对接模块
    
    提供实盘交易引擎功能的Python封装，支持CTA、SEL、HFT三种策略类型。
    负责管理策略的执行、交易指令的下达、行情数据的接收和处理等。
    使用单例模式，确保全局只有一个实例。
    """

    # api可以作为公共变量，存储C++动态库的接口
    api = None
    # 版本信息
    ver = "Unknown"
    
    # 构造函数，传入交易引擎对象
    def __init__(self, engine):
        """
        初始化实盘交易引擎包装器
        
        @param engine: 交易引擎对象，用于管理策略上下文
        """
        # 保存交易引擎引用
        self._engine = engine
        # 获取当前文件所在目录
        paths = os.path.split(__file__)
        # 获取实盘交易引擎动态库文件名（包含平台和架构信息）
        dllname = ph.getModule("WtPorter")
        # 拼接路径
        a = (paths[:-1] + (dllname,))
        # 生成完整的动态库路径
        _path = os.path.join(*a)
        # 加载C++动态库
        self.api = cdll.LoadLibrary(_path)
        
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
        # 设置sel_get_price函数的返回类型：最新价格（双精度浮点数）
        self.api.sel_get_price.restype = c_double
        # 设置sel_get_position_profit函数的返回类型：持仓盈亏（双精度浮点数）
        self.api.sel_get_position_profit.restype = c_double
        # 设置sel_get_position_avgpx函数的返回类型：持仓均价（双精度浮点数）
        self.api.sel_get_position_avgpx.restype = c_double
        # 设置sel_get_detail_cost函数的返回类型：指定标记持仓的开仓价（双精度浮点数）
        self.api.sel_get_detail_cost.restype = c_double
        # 设置sel_get_detail_profit函数的返回类型：指定标记持仓的盈亏（双精度浮点数）
        self.api.sel_get_detail_profit.restype = c_double
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
        self.api.hft_buy.argtypes = [c_ulong, c_char_p, c_double, c_double, c_char_p, c_int32]
        # 设置hft_sell函数的返回类型：本地订单号（字符指针）
        self.api.hft_sell.restype = c_char_p
        # 设置hft_sell函数的参数类型：策略ID、合约代码、价格、数量、用户标记、下单标志
        self.api.hft_sell.argtypes = [c_ulong, c_char_p, c_double, c_double, c_char_p, c_int32]
        # 设置hft_cancel_all函数的返回类型：撤销结果消息（字符指针）
        self.api.hft_cancel_all.restype = c_char_p

        # ========== 扩展模块接口函数签名设置 ==========
        # 设置create_ext_parser函数的返回类型：是否创建成功（布尔值）
        self.api.create_ext_parser.restype = c_bool
        # 设置create_ext_parser函数的参数类型：解析器ID（字符指针）
        self.api.create_ext_parser.argtypes = [c_char_p]

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

        # ========== 工具函数返回类型设置 ==========
        # 设置get_raw_stdcode函数的返回类型：原始标准化代码（字符指针）
        self.api.get_raw_stdcode.restype = c_char_p

    def on_engine_event(self, evtid:int, evtDate:int, evtTime:int):
        """
        引擎事件回调函数
        
        当引擎发生生命周期事件时（初始化、定时调度、会话开始、会话结束），C++库会调用此函数。
        
        @param evtid: 事件ID，标识事件类型
        @param evtDate: 事件日期（整数，格式yyyymmdd）
        @param evtTime: 事件时间（整数，格式HHMM）
        """
        # 获取交易引擎对象
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
        return

    # ========== 策略回调函数 ==========
    def on_stra_init(self, id:int):
        """
        策略初始化回调函数
        
        当策略需要初始化时，C++库会调用此函数。此函数由C++引擎在策略创建后自动调用，
        用于触发策略的初始化逻辑。
        
        @param id: 策略ID，唯一标识一个策略实例
        """
        # 获取交易引擎对象引用
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
        # 获取交易引擎对象引用
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
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，调用策略的计算方法，触发策略的on_calculate回调
        if ctx is not None:
            ctx.on_calculate()
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
        # 获取交易引擎对象引用
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
        # 获取交易引擎对象引用
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
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 将周期字符串从字节字符串解码为Python字符串
        period = bytes.decode(period)
        # 判断是否为日线周期（日线周期以'd'开头）
        isDay = period[0]=='d'

        # 创建NumPy封装的K线数据容器，使用零拷贝模式提高性能
        npBars = WtNpKline(isDay, forceCopy=False)
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
        # 获取交易引擎对象引用
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

    def on_stra_get_position(self, id:int, stdCode:str, qty:float, frozen:float):
        """
        获取持仓数据回调函数
        
        该回调函数由Python主动发起的持仓查询触发，需要同步执行，因此不走事件推送机制。
        当策略调用get_all_position接口查询所有持仓时，C++库会通过此回调函数返回每个合约的持仓数据。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param qty: 持仓数量，正数表示多仓，负数表示空仓
        @param frozen: 冻结数量，表示因挂单而冻结的持仓数量
        """
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 如果上下文存在，将持仓数据传递给策略，触发策略的on_getpositions回调
        if ctx is not None:
            ctx.on_getpositions(bytes.decode(stdCode), qty, frozen)

    def on_stra_cond_triggerd(self, id:int, stdCode:str, target:float, price:float, usertag:str):
        """
        条件单触发回调函数
        
        当条件单被触发时，C++库会调用此函数。条件单是一种特殊的订单类型，
        当市场价格达到预设条件时自动触发。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param target: 目标价格，条件单触发时的目标价格
        @param price: 触发价格，实际触发时的市场价格
        @param usertag: 用户标记（字节字符串，需要解码），用于标识条件单
        """
        # 获取交易引擎对象引用
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
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        
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
        @param localid: 本地订单号，策略下单时返回的订单标识
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param isBuy: 是否为买入订单，True表示买入，False表示卖出
        @param totalQty: 订单总数量
        @param leftQty: 剩余未成交数量
        @param price: 订单价格
        @param isCanceled: 是否已撤销，True表示订单已撤销
        @param userTag: 用户标记（字节字符串，需要解码），用于标识订单
        """
        # 将合约代码从字节字符串解码为Python字符串
        stdCode = bytes.decode(stdCode)
        # 将用户标记从字节字符串解码为Python字符串
        userTag = bytes.decode(userTag)
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 将订单回报信息传递给策略，触发策略的on_order回调
        ctx.on_order(localid, stdCode, isBuy, totalQty, leftQty, price, isCanceled, userTag)

    def on_hftstra_trade(self, id:int, localid:int, stdCode:str, isBuy:bool, qty:float, price:float, userTag:str):
        """
        HFT策略成交通知回调函数
        
        当订单成交时，C++库会调用此函数。成交通知包含成交的详细信息，包括成交价格、
        成交数量等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param localid: 本地订单号，策略下单时返回的订单标识
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param isBuy: 是否为买入成交，True表示买入，False表示卖出
        @param qty: 成交数量
        @param price: 成交价格
        @param userTag: 用户标记（字节字符串，需要解码），用于标识订单
        """
        # 将合约代码从字节字符串解码为Python字符串
        stdCode = bytes.decode(stdCode)
        # 将用户标记从字节字符串解码为Python字符串
        userTag = bytes.decode(userTag)
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 将成交通知信息传递给策略，触发策略的on_trade回调
        ctx.on_trade(localid, stdCode, isBuy, qty, price, userTag)

    def on_hftstra_entrust(self, id:int, localid:int, stdCode:str, bSucc:bool, message:str, userTag:str):
        """
        HFT策略委托回报回调函数
        
        当下单请求被交易所接受或拒绝时，C++库会调用此函数。委托回报表示订单是否
        成功提交到交易所。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param localid: 本地订单号，策略下单时返回的订单标识
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param bSucc: 是否成功，True表示委托成功，False表示委托失败
        @param message: 委托结果消息（字节字符串，GBK编码，需要解码），包含成功或失败的原因
        @param userTag: 用户标记（字节字符串，需要解码），用于标识订单
        """
        # 将合约代码从字节字符串解码为Python字符串
        stdCode = bytes.decode(stdCode)
        # 将消息从字节字符串解码为Python字符串（Windows使用GBK编码）
        message = bytes.decode(message, "gbk")
        # 将用户标记从字节字符串解码为Python字符串
        userTag = bytes.decode(userTag)
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 将委托回报信息传递给策略，触发策略的on_entrust回调
        ctx.on_entrust(localid, stdCode, bSucc, message, userTag)

    def on_hftstra_position(self, id:int, stdCode:str, isLong:bool, prevol:float, preavail:float, newvol:float, newavail:float):
        """
        HFT策略持仓变化回调函数
        
        当持仓发生变化时，C++库会调用此函数。持仓变化包括持仓数量和可用数量的变化。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param isLong: 是否为多仓，True表示多仓，False表示空仓
        @param prevol: 变化前的持仓数量
        @param preavail: 变化前的可用数量
        @param newvol: 变化后的持仓数量
        @param newavail: 变化后的可用数量
        """
        # 将合约代码从字节字符串解码为Python字符串
        stdCode = bytes.decode(stdCode)
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 将持仓变化信息传递给策略，触发策略的on_position回调
        ctx.on_position(stdCode, isLong, prevol, preavail, newvol, newavail)

    def on_hftstra_order_queue(self, id:int, stdCode:str, newOrdQue:POINTER(WTSOrdQueStruct)):
        """
        HFT策略委托队列数据回调函数
        
        当接收到委托队列数据时，C++库会调用此函数。委托队列数据包含买卖盘口的
        委托队列信息，用于分析市场深度。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param newOrdQue: 委托队列数据指针（指向WTSOrdQueStruct结构体）
        """
        # 将合约代码从字节字符串解码为Python字符串
        stdCode = bytes.decode(stdCode)
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 获取指针指向的结构体内容
        newOrdQue = newOrdQue.contents

        # 如果上下文存在，将委托队列数据传递给策略，触发策略的on_order_queue回调
        if ctx is not None:
            # 将结构体转换为元组格式传递给策略
            ctx.on_order_queue(stdCode, newOrdQue.to_tuple())

    def on_hftstra_get_order_queue(self, id:int, stdCode:str, newOrdQue:POINTER(WTSOrdQueStruct), count:int, isLast:bool):
        """
        HFT策略获取委托队列数据回调函数
        
        该回调函数由Python主动发起的数据查询触发，需要同步执行，因此不走事件推送机制。
        当策略调用get_order_queue接口查询委托队列数据时，C++库会通过此回调函数返回数据。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param newOrdQue: 委托队列数据数组指针（指向WTSOrdQueStruct结构体数组的起始位置）
        @param count: 委托队列数据条数
        @param isLast: 是否为最后一批数据，True表示数据已全部返回
        """
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 创建NumPy封装的委托队列数据容器，使用零拷贝模式提高性能
        npHftData = WtNpOrdQueues(forceCopy=False)
        # 将C++传递的委托队列数据数组设置到NumPy容器中
        npHftData.set_data(newOrdQue, count)

        # 如果上下文存在，将委托队列数据传递给策略，触发策略的on_get_order_queue回调
        if ctx is not None:
            ctx.on_get_order_queue(bytes.decode(stdCode), npHftData)

    def on_hftstra_order_detail(self, id:int, stdCode:str, newOrdDtl:POINTER(WTSOrdDtlStruct)):
        """
        HFT策略逐笔委托数据回调函数
        
        当接收到逐笔委托数据时，C++库会调用此函数。逐笔委托数据包含每一笔委托的
        详细信息，用于分析市场微观结构。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，不需要解码，因为已经是字符串类型）
        @param newOrdDtl: 逐笔委托数据指针（指向WTSOrdDtlStruct结构体）
        """
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 获取指针指向的结构体内容
        newOrdDtl = newOrdDtl.contents
        
        # 如果上下文存在，将逐笔委托数据传递给策略，触发策略的on_order_detail回调
        if ctx is not None:
            # 将结构体转换为元组格式传递给策略
            ctx.on_order_detail(stdCode, newOrdDtl.to_tuple())

    def on_hftstra_get_order_detail(self, id:int, stdCode:str, newOrdDtl:POINTER(WTSOrdDtlStruct), count:int, isLast:bool):
        """
        HFT策略获取逐笔委托数据回调函数
        
        该回调函数由Python主动发起的数据查询触发，需要同步执行，因此不走事件推送机制。
        当策略调用get_order_detail接口查询逐笔委托数据时，C++库会通过此回调函数返回数据。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param newOrdDtl: 逐笔委托数据数组指针（指向WTSOrdDtlStruct结构体数组的起始位置）
        @param count: 逐笔委托数据条数
        @param isLast: 是否为最后一批数据，True表示数据已全部返回
        """
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        
        # 创建NumPy封装的逐笔委托数据容器，使用零拷贝模式提高性能
        npHftData = WtNpOrdDetails(forceCopy=False)
        # 将C++传递的逐笔委托数据数组设置到NumPy容器中
        npHftData.set_data(newOrdDtl, count)
            
        # 如果上下文存在，将逐笔委托数据传递给策略，触发策略的on_get_order_detail回调
        if ctx is not None:
            ctx.on_get_order_detail(bytes.decode(stdCode), npHftData)

    def on_hftstra_transaction(self, id:int, stdCode:str, newTrans:POINTER(WTSTransStruct)):
        """
        HFT策略逐笔成交数据回调函数
        
        当接收到逐笔成交数据时，C++库会调用此函数。逐笔成交数据包含每一笔成交的
        详细信息，用于分析市场成交情况。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，不需要解码，因为已经是字符串类型）
        @param newTrans: 逐笔成交数据指针（指向WTSTransStruct结构体）
        """
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        # 获取指针指向的结构体内容
        newTrans = newTrans.contents
        
        # 如果上下文存在，将逐笔成交数据传递给策略，触发策略的on_transaction回调
        if ctx is not None:
            # 将结构体转换为元组格式传递给策略
            ctx.on_transaction(stdCode, newTrans.to_tuple())
        
    def on_hftstra_get_transaction(self, d:int, stdCode:str, newTrans:POINTER(WTSTransStruct), count:int, isLast:bool):
        """
        HFT策略获取逐笔成交数据回调函数
        
        该回调函数由Python主动发起的数据查询触发，需要同步执行，因此不走事件推送机制。
        当策略调用get_transaction接口查询逐笔成交数据时，C++库会通过此回调函数返回数据。
        
        注意：参数d应该是id，可能是代码中的笔误。
        
        @param d: 策略ID（应该是id，可能是代码中的笔误），唯一标识一个策略实例
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param newTrans: 逐笔成交数据数组指针（指向WTSTransStruct结构体数组的起始位置）
        @param count: 逐笔成交数据条数
        @param isLast: 是否为最后一批数据，True表示数据已全部返回
        """
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的策略上下文对象
        ctx = engine.get_context(id)
        
        # 创建NumPy封装的逐笔成交数据容器，使用零拷贝模式提高性能
        npHftData = WtNpTransactions(forceCopy=False)
        # 将C++传递的逐笔成交数据数组设置到NumPy容器中
        npHftData.set_data(newTrans, count)
            
        # 如果上下文存在，将逐笔成交数据传递给策略，触发策略的on_get_transaction回调
        if ctx is not None:
            ctx.on_get_transaction(bytes.decode(stdCode), npHftData)

    def on_parser_event(self, evtId:int, id:str):
        """
        扩展解析器事件回调函数
        
        当扩展解析器发生生命周期事件时，C++库会调用此函数。扩展解析器是用户自定义的
        行情数据解析器，用于处理特殊格式的行情数据。
        
        @param evtId: 事件ID，标识事件类型（初始化、连接、断开、释放等）
        @param id: 解析器ID（字节字符串，需要解码），唯一标识一个解析器实例
        """
        # 将解析器ID从字节字符串解码为Python字符串
        id = bytes.decode(id)
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的扩展解析器对象
        parser = engine.get_extended_parser(id)
        # 如果解析器不存在，直接返回
        if parser is None:
            return
        
        # 根据事件类型调用解析器的相应方法
        if evtId == EVENT_PARSER_INIT:
            # 解析器初始化事件：调用解析器的初始化方法
            parser.init(engine)
        elif evtId == EVENT_PARSER_CONNECT:
            # 解析器连接事件：调用解析器的连接方法，开始接收数据
            parser.connect()
        elif evtId == EVENT_PARSER_DISCONNECT:
            # 解析器断开事件：调用解析器的断开方法，停止接收数据
            parser.disconnect()
        elif evtId == EVENT_PARSER_RELEASE:
            # 解析器释放事件：调用解析器的释放方法，清理资源
            parser.release()

    def on_parser_sub(self, id:str, fullCode:str, isForSub:bool):
        """
        扩展解析器订阅命令回调函数
        
        当需要订阅或取消订阅合约时，C++库会调用此函数。订阅命令用于控制解析器
        接收哪些合约的行情数据。
        
        @param id: 解析器ID（字节字符串，需要解码），唯一标识一个解析器实例
        @param fullCode: 完整合约代码（字节字符串，需要解码），包含交易所信息
        @param isForSub: 是否为订阅操作，True表示订阅，False表示取消订阅
        """
        # 将解析器ID从字节字符串解码为Python字符串
        id = bytes.decode(id)
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的扩展解析器对象
        parser = engine.get_extended_parser(id)
        # 如果解析器不存在，直接返回
        if parser is None:
            return
        # 将合约代码从字节字符串解码为Python字符串
        fullCode = bytes.decode(fullCode)
        # 根据操作类型调用解析器的订阅或取消订阅方法
        if isForSub:
            # 订阅合约：调用解析器的订阅方法，开始接收该合约的行情数据
            parser.subscribe(fullCode)
        else:
            # 取消订阅：调用解析器的取消订阅方法，停止接收该合约的行情数据
            parser.unsubscribe(fullCode)

    def on_executer_init(self, id:str):
        """
        扩展执行器初始化回调函数
        
        当扩展执行器需要初始化时，C++库会调用此函数。扩展执行器是用户自定义的
        订单执行器，用于实现特殊的订单执行逻辑（如TWAP、VWAP等算法）。
        
        @param id: 执行器ID（字节字符串，需要解码），唯一标识一个执行器实例
        """
        # 将执行器ID从字节字符串解码为Python字符串
        id = bytes.decode(id)
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的扩展执行器对象
        executer = engine.get_extended_executer(id)
        # 如果执行器不存在，直接返回
        if executer is None:
            return

        # 调用执行器的初始化方法，完成执行器的初始化工作
        executer.init()

    def on_executer_cmd(self, id:str, stdCode:str, targetPos:float):
        """
        扩展执行器命令回调函数
        
        当需要执行目标仓位设置命令时，C++库会调用此函数。执行器命令用于将策略的
        目标仓位传递给执行器，由执行器负责实现具体的执行逻辑。
        
        @param id: 执行器ID（字节字符串，需要解码），唯一标识一个执行器实例
        @param stdCode: 合约代码（字节字符串，需要解码），目标合约
        @param targetPos: 目标仓位，正数表示多仓，负数表示空仓，0表示平仓
        """
        # 将执行器ID从字节字符串解码为Python字符串
        id = bytes.decode(id)
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取对应的扩展执行器对象
        executer = engine.get_extended_executer(id)
        # 如果执行器不存在，直接返回
        if executer is None:
            return

        # 调用执行器的设置仓位方法，将目标仓位传递给执行器
        executer.set_position(bytes.decode(stdCode), targetPos)

    def on_load_fnl_his_bars(self, stdCode:str, period:str):
        """
        加载最终K线历史数据回调函数
        
        当需要加载最终K线历史数据时，C++库会调用此函数。最终K线数据是经过复权处理
        的K线数据，用于回测和策略分析。此函数由扩展数据加载器负责实现数据加载逻辑。
        
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param period: K线周期（字节字符串，如"m5"表示5分钟K线，需要解码）
        @return: 是否加载成功，True表示成功，False表示失败
        """
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取扩展数据加载器对象
        loader = engine.get_extended_data_loader()
        # 如果数据加载器不存在，返回False
        if loader is None:
            return False

        # 调用数据加载器的加载最终K线数据方法
        # feed_raw_bars是C++接口函数，用于将K线数据传递给C++引擎
        # 函数签名：feed_raw_bars(WTSBarStruct* bars, WtUInt32 count);
        loader.load_final_his_bars(bytes.decode(stdCode), bytes.decode(period), self.api.feed_raw_bars)

    def on_load_raw_his_bars(self, stdCode:str, period:str):
        """
        加载原始K线历史数据回调函数
        
        当需要加载原始K线历史数据时，C++库会调用此函数。原始K线数据是未经复权处理
        的K线数据，用于数据分析和复权计算。此函数由扩展数据加载器负责实现数据加载逻辑。
        
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param period: K线周期（字节字符串，如"m5"表示5分钟K线，需要解码）
        @return: 是否加载成功，True表示成功，False表示失败
        """
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取扩展数据加载器对象
        loader = engine.get_extended_data_loader()
        # 如果数据加载器不存在，返回False
        if loader is None:
            return False

        # 调用数据加载器的加载原始K线数据方法
        # feed_raw_bars是C++接口函数，用于将K线数据传递给C++引擎
        # 函数签名：feed_raw_bars(WTSBarStruct* bars, WtUInt32 count);
        loader.load_raw_his_bars(bytes.decode(stdCode), bytes.decode(period), self.api.feed_raw_bars)

    def feed_adj_factors(self, stdCode:str, dates:list, factors:list):
        """
        传递复权因子数据给C++引擎
        
        此函数用于将复权因子数据传递给C++引擎。复权因子用于计算复权价格，
        确保K线数据的连续性。
        
        注意：此函数需要将Python列表转换为C数组，当前实现可能需要优化。
        
        @param stdCode: 合约代码（字符串，需要编码为字节字符串）
        @param dates: 复权日期列表（整数列表，格式如20230101）
        @param factors: 复权因子列表（浮点数列表）
        
        TODO: 这里类型要转一下! 底层接口是传数组的
        函数签名：feed_adj_factors(WtString stdCode, WtUInt32* dates, double* factors, WtUInt32 count)
        """
        # 将合约代码编码为UTF-8字节字符串
        stdCode = bytes(stdCode, encoding="utf8")
        # 调用C++接口函数，将复权因子数据传递给C++引擎
        # 注意：dates和factors需要转换为C数组类型，当前实现可能需要优化
        self.api.feed_adj_factors(stdCode, dates, factors, len(dates))

    def on_load_adj_factors(self, stdCode:str) -> bool:
        """
        加载复权因子数据回调函数
        
        当需要加载复权因子数据时，C++库会调用此函数。复权因子用于计算复权价格，
        确保K线数据的连续性。此函数由扩展数据加载器负责实现数据加载逻辑。
        
        @param stdCode: 合约代码（字节字符串，需要解码）
        @return: 是否加载成功，True表示成功，False表示失败
        """
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取扩展数据加载器对象
        loader = engine.get_extended_data_loader()
        # 如果数据加载器不存在，返回False
        if loader is None:
            return False

        # 将合约代码从字节字符串解码为Python字符串
        stdCode = bytes.decode(stdCode)
        # 调用数据加载器的加载复权因子方法，feed_adj_factors是回调函数，用于传递数据给C++引擎
        return loader.load_adj_factors(stdCode, self.feed_adj_factors)

    def on_load_his_ticks(self, stdCode:str, uDate:int):
        """
        加载Tick历史数据回调函数
        
        当需要加载Tick历史数据时，C++库会调用此函数。Tick历史数据用于回测和
        策略分析。此函数由扩展数据加载器负责实现数据加载逻辑。
        
        @param stdCode: 合约代码（字节字符串，需要解码）
        @param uDate: 交易日期（整数格式，如20230101）
        @return: 是否加载成功，True表示成功，False表示失败
        """
        # 获取交易引擎对象引用
        engine = self._engine
        # 从引擎获取扩展数据加载器对象
        loader = engine.get_extended_data_loader()
        # 如果数据加载器不存在，返回False
        if loader is None:
            return False

        # 调用数据加载器的加载Tick历史数据方法
        # feed_raw_ticks是C++接口函数，用于将Tick数据传递给C++引擎
        # 函数签名：feed_raw_ticks(WTSTickStruct* ticks, WtUInt32 count);
        loader.load_his_ticks(bytes.decode(stdCode), uDate, self.api.feed_raw_ticks)

    def write_log(self, level, message:str, catName:str = ""):
        """
        写入日志函数
        
        将日志消息写入日志系统。日志用于记录系统运行状态、错误信息等。
        
        @param level: 日志级别，数值越大表示日志级别越高
        @param message: 日志消息内容（字符串，需要编码为UTF-8字节字符串）
        @param catName: 日志分类名称（字符串，默认为空，需要编码为UTF-8字节字符串）
        """
        # 调用C++接口函数，将日志消息写入日志系统
        self.api.write_log(level, bytes(message, encoding = "utf8"), bytes(catName, encoding = "utf8"))

    # ========== 实盘引擎控制接口（与回测引擎有差异） ==========
    def run(self, bAsync:bool = True):
        """
        启动实盘交易引擎
        
        启动实盘交易引擎，开始接收行情数据和执行交易指令。
        
        @param bAsync: 是否异步运行，True表示异步运行（非阻塞），False表示同步运行（阻塞）
        """
        # 调用C++接口函数，启动实盘交易引擎
        self.api.run_porter(bAsync)

    def release(self):
        """
        释放实盘交易引擎资源
        
        释放实盘交易引擎占用的资源，包括关闭连接、清理内存等。
        在程序退出前应调用此函数以确保资源正确释放。
        """
        # 调用C++接口函数，释放实盘交易引擎资源
        self.api.release_porter()

    def config(self, cfgfile:str = 'config.yaml', isFile:bool = True):
        """
        配置实盘交易引擎
        
        加载配置文件，配置实盘交易引擎的参数，包括行情源、交易接口、策略等。
        
        @param cfgfile: 配置文件路径或配置内容（字符串，默认'config.yaml'）
        @param isFile: 是否为文件路径，True表示cfgfile是文件路径，False表示cfgfile是配置内容
        """
        # 调用C++接口函数，配置实盘交易引擎
        self.api.config_porter(bytes(cfgfile, encoding = "utf8"), isFile)

    def get_raw_stdcode(self, stdCode:str):
        """
        获取原始标准化代码
        
        将标准化代码转换为原始代码格式。标准化代码是wtpy内部使用的统一代码格式，
        原始代码是交易所使用的代码格式。
        
        @param stdCode: 标准化代码（字符串，需要编码为UTF-8字节字符串）
        @return: 原始代码（字符串，从字节字符串解码得到）
        """
        # 调用C++接口函数，获取原始代码，并解码为Python字符串
        return bytes.decode(self.api.get_raw_stdcode(bytes(stdCode, encoding = "utf8")))

    def create_extended_parser(self, id:str) -> bool:
        """
        创建扩展解析器
        
        在C++引擎中创建扩展解析器实例。扩展解析器是用户自定义的行情数据解析器，
        用于处理特殊格式的行情数据。
        
        @param id: 解析器ID（字符串，需要编码为UTF-8字节字符串）
        @return: 是否创建成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，创建扩展解析器
        return self.api.create_ext_parser(bytes(id, encoding = "utf8"))

    def create_extended_executer(self, id:str) -> bool:
        """
        创建扩展执行器
        
        在C++引擎中创建扩展执行器实例。扩展执行器是用户自定义的订单执行器，
        用于实现特殊的订单执行逻辑（如TWAP、VWAP等算法）。
        
        @param id: 执行器ID（字符串，需要编码为UTF-8字节字符串）
        @return: 是否创建成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，创建扩展执行器
        return self.api.create_ext_executer(bytes(id, encoding = "utf8"))

    def push_quote_from_exetended_parser(self, id:str, newTick:POINTER(WTSTickStruct), uProcFlag:int = 1):
        """
        从扩展解析器推送行情数据
        
        扩展解析器通过此函数将解析后的行情数据推送给C++引擎。此函数由扩展解析器
        在接收到行情数据后调用。
        
        @param id: 解析器ID（字符串，需要编码为UTF-8字节字符串）
        @param newTick: Tick数据指针（指向WTSTickStruct结构体）
        @param uProcFlag: 处理标志（整数，默认为1），控制数据的处理方式
        @return: 是否推送成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，将行情数据推送给C++引擎
        return self.api.parser_push_quote(bytes(id, encoding = "utf8"), newTick, uProcFlag)

    def register_extended_module_callbacks(self,):
        """
        注册扩展模块回调函数
        
        将扩展模块（解析器和执行器）的回调函数注册到C++引擎。注册后，C++引擎
        会在相应事件发生时调用这些回调函数。
        """
        # 创建解析器事件回调函数对象，用于接收解析器的生命周期事件
        self.cb_parser_event = CB_PARSER_EVENT(self.on_parser_event)
        # 创建解析器订阅命令回调函数对象，用于接收订阅/取消订阅命令
        self.cb_parser_subcmd = CB_PARSER_SUBCMD(self.on_parser_sub)
        # 创建执行器初始化回调函数对象，用于接收执行器的初始化事件
        self.cb_executer_init = CB_EXECUTER_INIT(self.on_executer_init)
        # 创建执行器命令回调函数对象，用于接收执行器的命令
        self.cb_executer_cmd = CB_EXECUTER_CMD(self.on_executer_cmd)

        # 将解析器回调函数注册到C++引擎
        self.api.register_parser_callbacks(self.cb_parser_event, self.cb_parser_subcmd)
        # 将执行器回调函数注册到C++引擎
        self.api.register_exec_callbacks(self.cb_executer_init, self.cb_executer_cmd)

    def register_extended_data_loader(self):
        """
        注册扩展历史数据加载器回调函数
        
        将扩展历史数据加载器的回调函数注册到C++引擎。注册后，C++引擎在需要加载
        历史数据时会调用这些回调函数，由Python端的扩展数据加载器负责实现数据加载逻辑。
        """
        # 创建加载最终K线数据回调函数对象
        self.cb_load_fnlbars = FUNC_LOAD_HISBARS(self.on_load_fnl_his_bars)
        # 创建加载原始K线数据回调函数对象
        self.cb_load_rawbars = FUNC_LOAD_HISBARS(self.on_load_raw_his_bars)
        # 创建加载Tick历史数据回调函数对象
        self.cb_load_histicks = FUNC_LOAD_HISTICKS(self.on_load_his_ticks)
        # 创建加载复权因子数据回调函数对象
        self.cb_load_adjfacts = FUNC_LOAD_ADJFACTS(self.on_load_adj_factors)
        # 将所有数据加载回调函数注册到C++引擎
        self.api.register_ext_data_loader(self.cb_load_fnlbars, self.cb_load_rawbars, self.cb_load_adjfacts, self.cb_load_histicks)

    # ========== 策略类型初始化接口（实盘引擎专用） ==========
    def initialize_cta(self, logCfg:str = "logcfg.yaml", isFile:bool = True, genDir:str = 'generated'):
        """
        初始化CTA策略引擎
        
        初始化CTA（商品交易顾问）策略引擎，注册所有CTA策略相关的回调函数，
        并启动C++引擎。此函数必须在添加策略之前调用。
        
        @param logCfg: 日志配置文件路径或配置内容（字符串，默认"logcfg.yaml"）
        @param isFile: 是否为文件路径，True表示logCfg是文件路径，False表示logCfg是配置内容
        @param genDir: 生成文件目录（字符串，默认'generated'），用于存储引擎生成的文件
        """
        # ========== 创建CTA策略回调函数对象 ==========
        # 创建策略初始化回调函数对象，用于接收策略初始化事件
        self.cb_stra_init = CB_STRATEGY_INIT(self.on_stra_init)
        # 创建Tick数据回调函数对象，用于接收Tick行情数据
        self.cb_stra_tick = CB_STRATEGY_TICK(self.on_stra_tick)
        # 创建策略计算回调函数对象，用于接收策略计算事件
        self.cb_stra_calc = CB_STRATEGY_CALC(self.on_stra_calc)
        # 创建K线闭合回调函数对象，用于接收K线闭合事件
        self.cb_stra_bar = CB_STRATEGY_BAR(self.on_stra_bar)
        # 创建会话事件回调函数对象，用于接收交易会话开始/结束事件
        self.cb_session_event = CB_SESSION_EVENT(self.on_session_event)
        # 创建条件单触发回调函数对象，用于接收条件单触发事件
        self.cb_stra_cond_trigger = CB_STRATEGY_COND_TRIGGER(self.on_stra_cond_triggerd)

        # ========== 创建引擎事件回调函数对象 ==========
        # 创建引擎事件回调函数对象，用于接收引擎生命周期事件
        self.cb_engine_event = CB_ENGINE_EVENT(self.on_engine_event)
        
        # ========== 注册回调函数并初始化引擎 ==========
        try:
            # 注册引擎事件回调函数到C++引擎
            self.api.register_evt_callback(self.cb_engine_event)
            # 注册CTA策略回调函数到C++引擎
            self.api.register_cta_callbacks(self.cb_stra_init, self.cb_stra_tick, self.cb_stra_calc, self.cb_stra_bar, self.cb_session_event, self.cb_stra_cond_trigger)
            # 初始化C++引擎，加载日志配置和生成目录
            self.api.init_porter(bytes(logCfg, encoding = "utf8"), isFile, bytes(genDir, encoding = "utf8"))
            # 注册扩展模块（解析器和执行器）的回调函数
            self.register_extended_module_callbacks()
        except OSError as oe:
            # 如果发生操作系统错误（如动态库加载失败），打印错误信息
            print(oe)

        # 写入初始化成功日志
        self.write_log(102, "WonderTrader CTA production framework initialzied, version: %s" % (self.ver))

    def initialize_hft(self, logCfg:str = "logcfg.yaml", isFile:bool = True, genDir:str = 'generated'):
        """
        初始化HFT策略引擎
        
        初始化HFT（高频交易）策略引擎，注册所有HFT策略相关的回调函数，
        并启动C++引擎。HFT策略支持更细粒度的行情数据和交易回报。
        此函数必须在添加策略之前调用。
        
        @param logCfg: 日志配置文件路径或配置内容（字符串，默认"logcfg.yaml"）
        @param isFile: 是否为文件路径，True表示logCfg是文件路径，False表示logCfg是配置内容
        @param genDir: 生成文件目录（字符串，默认'generated'），用于存储引擎生成的文件
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
        self.cb_hftstra_chnl_evt = CB_HFTSTRA_CHNL_EVT(self.on_hftstra_channel_evt)
        # 创建订单回报回调函数对象，用于接收订单状态变化事件
        self.cb_hftstra_order = CB_HFTSTRA_ORD(self.on_hftstra_order)
        # 创建成交通知回调函数对象，用于接收订单成交事件
        self.cb_hftstra_trade = CB_HFTSTRA_TRD(self.on_hftstra_trade)
        # 创建委托回报回调函数对象，用于接收委托提交结果事件
        self.cb_hftstra_entrust = CB_HFTSTRA_ENTRUST(self.on_hftstra_entrust)
        # 创建持仓变化回调函数对象，用于接收持仓变化事件
        self.cb_hftstra_position = CB_HFTSTRA_POSITION(self.on_hftstra_position)
        # 创建逐笔委托回调函数对象，用于接收逐笔委托数据
        self.cb_hftstra_orddtl = CB_HFTSTRA_ORDDTL(self.on_hftstra_order_detail)
        # 创建委托队列回调函数对象，用于接收委托队列数据
        self.cb_hftstra_ordque = CB_HFTSTRA_ORDQUE(self.on_hftstra_order_queue)
        # 创建逐笔成交回调函数对象，用于接收逐笔成交数据
        self.cb_hftstra_trans = CB_HFTSTRA_TRANS(self.on_hftstra_transaction)

        # ========== 创建引擎事件回调函数对象 ==========
        # 创建引擎事件回调函数对象，用于接收引擎生命周期事件
        self.cb_engine_event = CB_ENGINE_EVENT(self.on_engine_event)
        
        # ========== 注册回调函数并初始化引擎 ==========
        try:
            # 注册引擎事件回调函数到C++引擎
            self.api.register_evt_callback(self.cb_engine_event)
            # 注册HFT策略回调函数到C++引擎，包括基础回调和HFT专用回调
            self.api.register_hft_callbacks(self.cb_stra_init, self.cb_stra_tick, self.cb_stra_bar, 
                self.cb_hftstra_chnl_evt, self.cb_hftstra_order, self.cb_hftstra_trade, self.cb_hftstra_entrust,
                self.cb_hftstra_orddtl, self.cb_hftstra_ordque, self.cb_hftstra_trans, self.cb_session_event, self.cb_hftstra_position)
            # 初始化C++引擎，加载日志配置和生成目录
            self.api.init_porter(bytes(logCfg, encoding = "utf8"), isFile, bytes(genDir, encoding = "utf8"))
        except OSError as oe:
            # 如果发生操作系统错误（如动态库加载失败），打印错误信息
            print(oe)

        # 写入初始化成功日志
        self.write_log(102, "WonderTrader HFT production framework initialzied, version: %s" % (self.ver))

    def initialize_sel(self, logCfg:str = "logcfg.yaml", isFile:bool = True, genDir:str = 'generated'):
        """
        初始化SEL策略引擎
        
        初始化SEL（选股）策略引擎，注册所有SEL策略相关的回调函数，
        并启动C++引擎。SEL策略主要用于多标的选择和组合管理。
        此函数必须在添加策略之前调用。
        
        @param logCfg: 日志配置文件路径或配置内容（字符串，默认"logcfg.yaml"）
        @param isFile: 是否为文件路径，True表示logCfg是文件路径，False表示logCfg是配置内容
        @param genDir: 生成文件目录（字符串，默认'generated'），用于存储引擎生成的文件
        """
        # ========== 创建SEL策略回调函数对象 ==========
        # 创建策略初始化回调函数对象，用于接收策略初始化事件
        self.cb_stra_init = CB_STRATEGY_INIT(self.on_stra_init)
        # 创建Tick数据回调函数对象，用于接收Tick行情数据
        self.cb_stra_tick = CB_STRATEGY_TICK(self.on_stra_tick)
        # 创建策略计算回调函数对象，用于接收策略计算事件
        self.cb_stra_calc = CB_STRATEGY_CALC(self.on_stra_calc)
        # 创建K线闭合回调函数对象，用于接收K线闭合事件
        self.cb_stra_bar = CB_STRATEGY_BAR(self.on_stra_bar)
        # 创建会话事件回调函数对象，用于接收交易会话开始/结束事件
        self.cb_session_event = CB_SESSION_EVENT(self.on_session_event)

        # ========== 创建引擎事件回调函数对象 ==========
        # 创建引擎事件回调函数对象，用于接收引擎生命周期事件
        self.cb_engine_event = CB_ENGINE_EVENT(self.on_engine_event)

        # ========== 注册回调函数并初始化引擎 ==========
        try:
            # 注册引擎事件回调函数到C++引擎
            self.api.register_evt_callback(self.cb_engine_event)
            # 注册SEL策略回调函数到C++引擎
            self.api.register_sel_callbacks(self.cb_stra_init, self.cb_stra_tick, self.cb_stra_calc, self.cb_stra_bar, self.cb_session_event)
            # 初始化C++引擎，加载日志配置和生成目录
            self.api.init_porter(bytes(logCfg, encoding = "utf8"), isFile, bytes(genDir, encoding = "utf8"))
            # 注册扩展模块（解析器和执行器）的回调函数
            self.register_extended_module_callbacks()
        except OSError as oe:
            # 如果发生操作系统错误（如动态库加载失败），打印错误信息
            print(oe)

        # 写入初始化成功日志
        self.write_log(102, "WonderTrader SEL production framework initialzied, version: %s" % (self.ver))

    def cta_enter_long(self, id:int, stdCode:str, qty:float, usertag:str, limitprice:float = 0.0, stopprice:float = 0.0):
        """
        CTA策略开多仓接口
        
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
        CTA策略平多仓接口
        
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
        CTA策略开空仓接口
        
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
        CTA策略平空仓接口
        
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
        CTA策略获取K线数据接口
        
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
        CTA策略获取Tick数据接口
        
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
        CTA策略获取持仓浮动盈亏接口
        
        获取指定合约的持仓浮动盈亏。浮动盈亏是根据当前市场价格计算的未实现盈亏。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的持仓浮动盈亏（浮点数），正数表示盈利，负数表示亏损
        """
        # 调用C++接口函数，获取持仓浮动盈亏
        return self.api.cta_get_position_profit(id, bytes(stdCode, encoding = "utf8"))

    def cta_get_position_avgpx(self, id:int, stdCode:str):
        """
        CTA策略获取持仓均价接口
        
        获取指定合约的持仓均价。持仓均价是所有持仓的平均开仓价格。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的持仓均价（浮点数）
        """
        # 调用C++接口函数，获取持仓均价
        return self.api.cta_get_position_avgpx(id, bytes(stdCode, encoding = "utf8"))

    def cta_get_all_position(self, id:int):
        """
        CTA策略获取全部持仓接口
        
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
        CTA策略获取持仓接口
        
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
        CTA策略获取资金数据接口
        
        获取策略的资金数据，包括动态权益、盈亏、手续费等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param flag: 资金数据标志（整数），0-动态权益，1-总平仓盈亏，2-总浮动盈亏，3-总手续费
        @return: 资金数据（浮点数），根据flag返回相应的资金数据
        """
        # 调用C++接口函数，获取资金数据
        return self.api.cta_get_fund_data(id, flag)

    def cta_get_price(self, stdCode:str) -> float:
        """
        CTA策略获取最新价格接口
        
        获取指定合约的最新价格。最新价格是最近一笔成交的价格。
        
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的最新价格（浮点数）
        """
        # 调用C++接口函数，获取最新价格
        return self.api.cta_get_price(bytes(stdCode, encoding = "utf8"))

    def cta_get_day_price(self, stdCode:str, flag:int = 0) -> float:
        """
        CTA策略获取当日价格接口
        
        获取指定合约的当日价格，包括开盘价、最高价、最低价、最新价等。
        
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param flag: 价格标记（整数，默认0），0-开盘价，1-最高价，2-最低价，3-最新价
        @return: 指定合约的价格（浮点数），根据flag返回相应的价格
        """
        # 调用C++接口函数，获取当日价格
        return self.api.cta_get_day_price(bytes(stdCode, encoding = "utf8"), flag)

    def cta_set_position(self, id:int, stdCode:str, qty:float, usertag:str = "", limitprice:float = 0.0, stopprice:float = 0.0):
        """
        CTA策略设置目标仓位接口
        
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
        CTA策略获取当前交易日接口
        
        获取当前交易日。交易日是交易所规定的交易日期，可能与自然日不同。
        
        @return: 当前交易日（整数），格式如20230101
        """
        # 调用C++接口函数，获取当前交易日
        return self.api.cta_get_tdate()

    def cta_get_date(self) -> int:
        """
        CTA策略获取当前日期接口
        
        获取当前日期。当前日期是系统日期，可能与交易日不同。
        
        @return: 当前日期（整数），格式如20230101
        """
        # 调用C++接口函数，获取当前日期
        return self.api.cta_get_date()

    def cta_get_time(self) -> int:
        """
        CTA策略获取当前时间接口
        
        获取当前时间。当前时间是系统时间，格式为HHMMSS（时分秒）。
        
        @return: 当前时间（整数），格式如93000表示09:30:00
        """
        # 调用C++接口函数，获取当前时间
        return self.api.cta_get_time()

    def cta_get_first_entertime(self, id:int, stdCode:str) -> int:
        """
        CTA策略获取首次进场时间接口
        
        获取当前持仓的首次进场时间。首次进场时间是最早一笔持仓的开仓时间。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 首次进场时间（整数），格式如201907260932表示2019年7月26日09:32:00
        """
        # 调用C++接口函数，获取首次进场时间
        return self.api.cta_get_first_entertime(id, bytes(stdCode, encoding = "utf8"))

    def cta_get_last_entertag(self, id:int, stdCode:str) -> str:
        """
        CTA策略获取最后进场标记接口
        
        获取当前持仓的最后进场标记。最后进场标记是最近一笔持仓的用户标记。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 最后进场标记（字符串），从字节字符串解码得到
        """
        # 调用C++接口函数，获取最后进场标记，并解码为Python字符串
        return bytes.decode(self.api.cta_get_last_entertag(id, bytes(stdCode, encoding = "utf8")))

    def cta_get_last_entertime(self, id:int, stdCode:str) -> int:
        """
        CTA策略获取最后进场时间接口
        
        获取当前持仓的最后进场时间。最后进场时间是最近一笔持仓的开仓时间。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 最后进场时间（整数），格式如201907260932表示2019年7月26日09:32:00
        """
        # 调用C++接口函数，获取最后进场时间
        return self.api.cta_get_last_entertime(id, bytes(stdCode, encoding = "utf8"))

    def cta_get_last_exittime(self, id:int, stdCode:str) -> int:
        """
        CTA策略获取最后出场时间接口
        
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
        CTA策略日志输出接口
        
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
        CTA策略获取指定标记持仓的进场时间接口
        
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
        CTA策略获取指定标记持仓的开仓价接口
        
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
        CTA策略获取指定标记持仓的盈亏接口
        
        获取指定用户标记的持仓的盈亏信息。可以查询浮动盈亏、最大浮盈、最大亏损等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param usertag: 进场标记（字符串，需要编码为UTF-8字节字符串），用于标识特定的持仓
        @param flag: 盈亏记号（整数），0-浮动盈亏，1-最大浮盈，2-最大亏损（负数）
        @return: 盈亏（浮点数），根据flag返回相应的盈亏数据
        """
        # 调用C++接口函数，获取指定标记持仓的盈亏
        return self.api.cta_get_detail_profit(id, bytes(stdCode, encoding = "utf8"), bytes(usertag, encoding = "utf8"), flag) 

    def cta_save_user_data(self, id:int, key:str, val:str):
        """
        CTA策略保存用户数据接口
        
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
        CTA策略加载用户数据接口
        
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
        CTA策略订阅Tick行情接口
        
        订阅指定品种的Tick行情数据。订阅后，策略会收到该品种的所有Tick数据回调。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串），可以是具体合约或品种代码
        """
        # 调用C++接口函数，订阅Tick行情
        self.api.cta_sub_ticks(id, bytes(stdCode, encoding = "utf8"))

    def cta_sub_bar_events(self, id:int, stdCode:str, period:str):
        """
        CTA策略订阅K线事件接口
        
        订阅指定品种和周期的K线闭合事件。订阅后，当K线闭合时，策略会收到K线数据回调。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串），可以是具体合约或品种代码
        @param period: K线周期（字符串，需要编码为UTF-8字节字符串），如"m5"表示5分钟K线
        """
        # 调用C++接口函数，订阅K线事件
        self.api.cta_sub_bar_events(id, bytes(stdCode, encoding = "utf8"), bytes(period, encoding = "utf8"))

    def cta_set_chart_kline(self, id:int, stdCode:str, period:str):
        """
        CTA策略设置图表K线接口
        
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
        CTA策略添加图表标记接口
        
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
        CTA策略注册指标接口
        
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
        CTA策略注册指标线接口
        
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
        CTA策略添加指标基准线接口
        
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
        CTA策略设置指标值接口
        
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
  
    # ========== SEL策略接口 ==========
    def sel_get_bars(self, id:int, stdCode:str, period:str, count:int, isMain:bool):
        """
        SEL策略获取K线数据接口
        
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
        return self.api.sel_get_bars(id, bytes(stdCode, encoding = "utf8"), bytes(period, encoding = "utf8"), count, isMain, CB_STRATEGY_GET_BAR(self.on_stra_get_bar))
    
    def sel_get_ticks(self, id:int, stdCode:str, count:int):
        """
        SEL策略获取Tick数据接口
        
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
        SEL策略保存用户数据接口
        
        保存策略的用户自定义数据。用户数据可以用于存储策略的状态、参数等信息，
        数据会持久化保存，程序重启后可以加载。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param key: 数据键名（字符串，需要编码为UTF-8字节字符串），用于标识数据
        @param val: 数据值（字符串，需要编码为UTF-8字节字符串），要保存的数据内容
        """
        # 调用C++接口函数，保存用户数据
        self.api.sel_save_userdata(id, bytes(key, encoding = "utf8"), bytes(val, encoding = "utf8"))

    def sel_load_user_data(self, id:int, key:str, defVal:str  = ""):
        """
        SEL策略加载用户数据接口
        
        加载策略的用户自定义数据。如果数据不存在，则返回默认值。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param key: 数据键名（字符串，需要编码为UTF-8字节字符串），用于标识数据
        @param defVal: 默认值（字符串，默认空字符串，需要编码为UTF-8字节字符串），当数据不存在时返回此值
        @return: 用户数据（字符串），从字节字符串解码得到，如果数据不存在则返回默认值
        """
        # 调用C++接口函数，加载用户数据，并解码为Python字符串
        ret = self.api.sel_load_userdata(id, bytes(key, encoding = "utf8"), bytes(defVal, encoding = "utf8"))
        return bytes.decode(ret)

    def sel_get_all_position(self, id:int):
        """
        SEL策略获取全部持仓接口
        
        获取策略的所有持仓信息。持仓信息通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_stra_get_position回调函数返回。
        
        @param id: 策略ID，唯一标识一个策略实例
        @return: 是否查询成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，查询所有持仓
        # 持仓数据通过on_stra_get_position回调函数异步返回
        return self.api.sel_get_all_position(id, CB_STRATEGY_GET_POSITION(self.on_stra_get_position))

    def sel_get_position(self, id:int, stdCode:str, bonlyvalid:bool = False, usertag:str = ""):
        """
        SEL策略获取持仓接口
        
        获取指定合约的持仓数量。可以获取全部持仓或指定标记的持仓。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param bonlyvalid: 是否只读可用持仓（布尔值，默认False），True表示只返回可用持仓，False表示返回全部持仓
        @param usertag: 进场标记（字符串，默认空字符串，需要编码为UTF-8字节字符串），如果为空则获取该合约全部持仓，否则只获取指定标记的持仓
        @return: 指定合约的持仓手数（浮点数），正数表示多仓，负数表示空仓，0表示无持仓
        """
        # 调用C++接口函数，获取持仓数量
        return self.api.sel_get_position(id, bytes(stdCode, encoding = "utf8"), bonlyvalid, bytes(usertag, encoding = "utf8"))

    def sel_get_price(self, stdCode:str):
        """
        SEL策略获取最新价格接口
        
        获取指定合约的最新价格。最新价格是最近一笔成交的价格。
        
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的最新价格（浮点数）
        """
        # 调用C++接口函数，获取最新价格
        return self.api.sel_get_price(bytes(stdCode, encoding = "utf8"))

    def sel_set_position(self, id:int, stdCode:str, qty:float, usertag:str = ""):
        """
        SEL策略设置目标仓位接口
        
        设置指定合约的目标仓位。系统会自动计算需要开仓或平仓的数量，并执行相应的交易指令。
        如果目标仓位大于当前持仓，则开仓；如果目标仓位小于当前持仓，则平仓。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param qty: 目标仓位（浮点数），正数表示多仓，负数表示空仓，0表示平仓
        @param usertag: 用户标记（字符串，默认空字符串，需要编码为UTF-8字节字符串），用于标识此笔交易
        """
        # 调用C++接口函数，设置目标仓位
        self.api.sel_set_position(id, bytes(stdCode, encoding = "utf8"), qty, bytes(usertag, encoding = "utf8"))

    def sel_get_tdate(self) -> int:
        """
        SEL策略获取当前交易日接口
        
        获取当前交易日。交易日是交易所规定的交易日期，可能与自然日不同。
        
        @return: 当前交易日（整数），格式如20230101
        """
        # 调用C++接口函数，获取当前交易日
        return self.api.sel_get_tdate()
    
    def sel_get_date(self):
        """
        SEL策略获取当前日期接口
        
        获取当前日期。当前日期是系统日期，可能与交易日不同。
        
        @return: 当前日期（整数），格式如20230101
        """
        # 调用C++接口函数，获取当前日期
        return self.api.sel_get_date()

    def sel_get_time(self):
        """
        SEL策略获取当前时间接口
        
        获取当前时间。当前时间是系统时间，格式为HHMMSS（时分秒）。
        
        @return: 当前时间（整数），格式如93000表示09:30:00
        """
        # 调用C++接口函数，获取当前时间
        return self.api.sel_get_time()

    def sel_log_text(self, id:int, level:int, message:str):
        """
        SEL策略日志输出接口
        
        输出策略日志。日志用于记录策略运行状态、交易决策等信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param level: 日志级别（整数），数值越大表示日志级别越高
        @param message: 日志内容（字符串），需要根据平台自动编码（Windows使用GBK，Linux使用UTF-8）
        """
        # 调用C++接口函数，输出策略日志
        # 使用PlatformHelper自动处理编码（Windows→GBK，Linux→UTF-8）
        self.api.sel_log_text(id, level, ph.auto_encode(message))

    def sel_sub_ticks(self, id:int, stdCode:str):
        """
        SEL策略订阅Tick行情接口
        
        订阅指定品种的Tick行情数据。订阅后，策略会收到该品种的所有Tick数据回调。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串），可以是具体合约或品种代码
        """
        # 调用C++接口函数，订阅Tick行情
        self.api.sel_sub_ticks(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_day_price(self, stdCode:str, flag:int = 0) -> float:
        """
        SEL策略获取当日价格接口
        
        获取指定合约的当日价格，包括开盘价、最高价、最低价、最新价等。
        
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param flag: 价格标记（整数，默认0），0-开盘价，1-最高价，2-最低价，3-最新价
        @return: 指定合约的价格（浮点数），根据flag返回相应的价格
        """
        # 调用C++接口函数，获取当日价格
        return self.api.sel_get_day_price(bytes(stdCode, encoding = "utf8"), flag)

    def sel_get_fund_data(self, id:int, flag:int) -> float:
        """
        SEL策略获取资金数据接口
        
        获取策略的资金数据，包括动态权益、盈亏、手续费等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param flag: 资金数据标志（整数），0-动态权益，1-总平仓盈亏，2-总浮动盈亏，3-总手续费
        @return: 资金数据（浮点数），根据flag返回相应的资金数据
        """
        # 调用C++接口函数，获取资金数据
        return self.api.sel_get_fund_data(id, flag)

    def sel_get_position_profit(self, id:int, stdCode:str):
        """
        SEL策略获取持仓浮动盈亏接口
        
        获取指定合约的持仓浮动盈亏。浮动盈亏是根据当前市场价格计算的未实现盈亏。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的持仓浮动盈亏（浮点数），正数表示盈利，负数表示亏损
        """
        # 调用C++接口函数，获取持仓浮动盈亏
        return self.api.sel_get_position_profit(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_position_avgpx(self, id:int, stdCode:str):
        """
        SEL策略获取持仓均价接口
        
        获取指定合约的持仓均价。持仓均价是所有持仓的平均开仓价格。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的持仓均价（浮点数）
        """
        # 调用C++接口函数，获取持仓均价
        return self.api.sel_get_position_avgpx(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_first_entertime(self, id:int, stdCode:str) -> int:
        """
        SEL策略获取首次进场时间接口
        
        获取当前持仓的首次进场时间。首次进场时间是最早一笔持仓的开仓时间。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 首次进场时间（整数），格式如201907260932表示2019年7月26日09:32:00
        """
        # 调用C++接口函数，获取首次进场时间
        return self.api.sel_get_first_entertime(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_last_entertime(self, id:int, stdCode:str) -> int:
        """
        SEL策略获取最后进场时间接口
        
        获取当前持仓的最后进场时间。最后进场时间是最近一笔持仓的开仓时间。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 最后进场时间（整数），格式如201907260932表示2019年7月26日09:32:00
        """
        # 调用C++接口函数，获取最后进场时间
        return self.api.sel_get_last_entertime(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_last_entertag(self, id:int, stdCode:str) -> str:
        """
        SEL策略获取最后进场标记接口
        
        获取当前持仓的最后进场标记。最后进场标记是最近一笔持仓的用户标记。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 最后进场标记（字符串），从字节字符串解码得到
        """
        # 调用C++接口函数，获取最后进场标记，并解码为Python字符串
        return bytes.decode(self.api.sel_get_last_entertag(id, bytes(stdCode, encoding = "utf8")))

    def sel_get_last_exittime(self, id:int, stdCode:str) -> int:
        """
        SEL策略获取最后出场时间接口
        
        获取当前持仓的最后出场时间。最后出场时间是最近一笔平仓的时间。
        如果当前没有持仓，则返回0。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 最后出场时间（整数），格式如201907260932表示2019年7月26日09:32:00，0表示没有出场记录
        """
        # 调用C++接口函数，获取最后出场时间
        return self.api.sel_get_last_exittime(id, bytes(stdCode, encoding = "utf8"))

    def sel_get_detail_entertime(self, id:int, stdCode:str, usertag:str) -> int:
        """
        SEL策略获取指定标记持仓的进场时间接口
        
        获取指定用户标记的持仓的进场时间。用于查询特定交易的详细信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param usertag: 进场标记（字符串，需要编码为UTF-8字节字符串），用于标识特定的持仓
        @return: 进场时间（整数），格式如201907260932表示2019年7月26日09:32:00，0表示未找到
        """
        # 调用C++接口函数，获取指定标记持仓的进场时间
        return self.api.sel_get_detail_entertime(id, bytes(stdCode, encoding = "utf8"), bytes(usertag, encoding = "utf8")) 

    def sel_get_detail_cost(self, id:int, stdCode:str, usertag:str) -> float:
        """
        SEL策略获取指定标记持仓的开仓价接口
        
        获取指定用户标记的持仓的开仓价。用于查询特定交易的开仓成本。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param usertag: 进场标记（字符串，需要编码为UTF-8字节字符串），用于标识特定的持仓
        @return: 开仓价（浮点数），0表示未找到
        """
        # 调用C++接口函数，获取指定标记持仓的开仓价
        return self.api.sel_get_detail_cost(id, bytes(stdCode, encoding = "utf8"), bytes(usertag, encoding = "utf8")) 

    def sel_get_detail_profit(self, id:int, stdCode:str, usertag:str, flag:int):
        """
        SEL策略获取指定标记持仓的盈亏接口
        
        获取指定用户标记的持仓的盈亏信息。可以查询浮动盈亏、最大浮盈、最大亏损等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param usertag: 进场标记（字符串，需要编码为UTF-8字节字符串），用于标识特定的持仓
        @param flag: 盈亏记号（整数），0-浮动盈亏，1-最大浮盈，-1-最大亏损（负数），2-最大浮盈价格，-2-最大浮亏价格
        @return: 盈亏（浮点数），根据flag返回相应的盈亏数据
        """
        # 调用C++接口函数，获取指定标记持仓的盈亏
        return self.api.sel_get_detail_profit(id, bytes(stdCode, encoding = "utf8"), bytes(usertag, encoding = "utf8"), flag) 

    # ========== HFT策略接口 ==========
    def hft_get_bars(self, id:int, stdCode:str, period:str, count:int):
        """
        HFT策略获取K线数据接口
        
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
        HFT策略获取Tick数据接口
        
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
        HFT策略获取委托队列数据接口
        
        查询指定合约的委托队列历史数据。委托队列数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_hftstra_get_order_queue回调函数返回。
        
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
        HFT策略获取逐笔委托数据接口
        
        查询指定合约的逐笔委托历史数据。逐笔委托数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_hftstra_get_order_detail回调函数返回。
        
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
        HFT策略获取逐笔成交数据接口
        
        查询指定合约的逐笔成交历史数据。逐笔成交数据通过回调函数异步返回，因此此函数
        立即返回，实际数据通过on_hftstra_get_transaction回调函数返回。
        
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
        HFT策略保存用户数据接口
        
        保存策略的用户自定义数据。用户数据可以用于存储策略的状态、参数等信息，
        数据会持久化保存，程序重启后可以加载。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param key: 数据键名（字符串，需要编码为UTF-8字节字符串），用于标识数据
        @param val: 数据值（字符串，需要编码为UTF-8字节字符串），要保存的数据内容
        """
        # 调用C++接口函数，保存用户数据
        self.api.hft_save_userdata(id, bytes(key, encoding = "utf8"), bytes(val, encoding = "utf8"))

    def hft_load_user_data(self, id:int, key:str, defVal:str  = ""):
        """
        HFT策略加载用户数据接口
        
        加载策略的用户自定义数据。如果数据不存在，则返回默认值。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param key: 数据键名（字符串，需要编码为UTF-8字节字符串），用于标识数据
        @param defVal: 默认值（字符串，默认空字符串，需要编码为UTF-8字节字符串），当数据不存在时返回此值
        @return: 用户数据（字符串），从字节字符串解码得到，如果数据不存在则返回默认值
        """
        # 调用C++接口函数，加载用户数据，并解码为Python字符串
        ret = self.api.hft_load_userdata(id, bytes(key, encoding = "utf8"), bytes(defVal, encoding = "utf8"))
        return bytes.decode(ret)

    def hft_get_position(self, id:int, stdCode:str, bonlyvalid:bool = False):
        """
        HFT策略获取持仓接口
        
        获取指定合约的持仓数量。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @param bonlyvalid: 是否只读可用持仓（布尔值，默认False），True表示只返回可用持仓，False表示返回全部持仓
        @return: 指定合约的持仓手数（浮点数），正数表示多仓，负数表示空仓，0表示无持仓
        """
        # 调用C++接口函数，获取持仓数量
        return self.api.hft_get_position(id, bytes(stdCode, encoding = "utf8"), bonlyvalid)

    def hft_get_position_profit(self, id:int, stdCode:str):
        """
        HFT策略获取持仓盈亏接口
        
        获取指定合约的持仓浮动盈亏。浮动盈亏是根据当前市场价格计算的未实现盈亏。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定持仓的浮动盈亏（浮点数），正数表示盈利，负数表示亏损
        """
        # 调用C++接口函数，获取持仓浮动盈亏
        return self.api.hft_get_position_profit(id, bytes(stdCode, encoding = "utf8"))

    def hft_get_position_avgpx(self, id:int, stdCode:str):
        """
        HFT策略获取持仓均价接口
        
        获取指定合约的持仓均价。持仓均价是所有持仓的平均开仓价格。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定持仓的持仓均价（浮点数）
        """
        # 调用C++接口函数，获取持仓均价
        return self.api.hft_get_position_avgpx(id, bytes(stdCode, encoding = "utf8"))

    def hft_get_undone(self, id:int, stdCode:str):
        """
        HFT策略获取未完成订单数量接口
        
        获取指定合约的未完成订单数量。未完成订单包括已提交但未成交的订单。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的未完成订单数量（浮点数），正数表示多仓方向，负数表示空仓方向
        """
        # 调用C++接口函数，获取未完成订单数量
        return self.api.hft_get_undone(id, bytes(stdCode, encoding = "utf8"))

    def hft_get_price(self, stdCode:str):
        """
        HFT策略获取最新价格接口
        
        获取指定合约的最新价格。最新价格是最近一笔成交的价格。
        
        @param stdCode: 合约代码（字符串，需要编码为UTF-8字节字符串）
        @return: 指定合约的最新价格（浮点数）
        """
        # 调用C++接口函数，获取最新价格
        return self.api.hft_get_price(bytes(stdCode, encoding = "utf8"))

    def hft_get_date(self):
        """
        HFT策略获取当前日期接口
        
        获取当前日期。当前日期是系统日期，可能与交易日不同。
        
        @return: 当前日期（整数），格式如20230101
        """
        # 调用C++接口函数，获取当前日期
        return self.api.hft_get_date()

    def hft_get_time(self):
        """
        HFT策略获取当前时间接口
        
        获取当前时间。当前时间是系统时间，格式为HHMMSS（时分秒）。
        
        @return: 当前时间（整数），格式如93000表示09:30:00
        """
        # 调用C++接口函数，获取当前时间
        return self.api.hft_get_time()

    def hft_get_secs(self):
        """
        HFT策略获取当前秒数接口
        
        获取当前时间的秒数部分。用于获取更精确的时间信息。
        
        @return: 当前时间的秒数（整数），范围0-59
        """
        # 调用C++接口函数，获取当前秒数
        return self.api.hft_get_secs()

    def hft_log_text(self, id:int, level:int, message:str):
        """
        HFT策略日志输出接口
        
        输出策略日志。日志用于记录策略运行状态、交易决策等信息。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param level: 日志级别（整数），数值越大表示日志级别越高
        @param message: 日志内容（字符串），需要根据平台自动编码（Windows使用GBK，Linux使用UTF-8）
        """
        # 调用C++接口函数，输出策略日志
        # 使用PlatformHelper自动处理编码（Windows→GBK，Linux→UTF-8）
        self.api.hft_log_text(id, level, ph.auto_encode(message))

    def hft_sub_ticks(self, id:int, stdCode:str):
        """
        HFT策略订阅实时Tick行情数据接口
        
        订阅指定品种的Tick行情数据。订阅后，策略会收到该品种的所有Tick数据回调。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串），可以是具体合约或品种代码
        """
        # 调用C++接口函数，订阅Tick行情
        self.api.hft_sub_ticks(id, bytes(stdCode, encoding = "utf8"))

    def hft_sub_order_queue(self, id:int, stdCode:str):
        """
        HFT策略订阅实时委托队列数据接口
        
        订阅指定品种的委托队列数据。订阅后，策略会收到该品种的所有委托队列数据回调。
        委托队列数据包含买卖盘口的委托队列信息，用于分析市场深度。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串），可以是具体合约或品种代码
        """
        # 调用C++接口函数，订阅委托队列数据
        self.api.hft_sub_order_queue(id, bytes(stdCode, encoding = "utf8"))

    def hft_sub_order_detail(self, id:int, stdCode:str):
        """
        HFT策略订阅逐笔委托数据接口
        
        订阅指定品种的逐笔委托数据。订阅后，策略会收到该品种的所有逐笔委托数据回调。
        逐笔委托数据包含每一笔委托的详细信息，用于分析市场微观结构。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串），可以是具体合约或品种代码
        """
        # 调用C++接口函数，订阅逐笔委托数据
        self.api.hft_sub_order_detail(id, bytes(stdCode, encoding = "utf8"))

    def hft_sub_transaction(self, id:int, stdCode:str):
        """
        HFT策略订阅逐笔成交数据接口
        
        订阅指定品种的逐笔成交数据。订阅后，策略会收到该品种的所有逐笔成交数据回调。
        逐笔成交数据包含每一笔成交的详细信息，用于分析市场成交情况。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串），可以是具体合约或品种代码
        """
        # 调用C++接口函数，订阅逐笔成交数据
        self.api.hft_sub_transaction(id, bytes(stdCode, encoding = "utf8"))

    def hft_cancel(self, id:int, localid:int):
        """
        HFT策略撤销指定订单接口
        
        撤销指定的订单。订单通过本地订单号标识。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param localid: 本地订单号（整数），下单时返回的订单标识
        @return: 是否撤销成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，撤销指定订单
        return self.api.hft_cancel(id, localid)

    def hft_cancel_all(self, id:int, stdCode:str, isBuy:bool):
        """
        HFT策略撤销全部订单接口
        
        撤销指定品种的全部买入订单或卖出订单。用于批量撤单操作。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串）
        @param isBuy: 是否撤销买入订单（布尔值），True表示撤销买入订单，False表示撤销卖出订单
        @return: 撤销结果消息（字符串），从字节字符串解码得到，包含撤销结果信息
        """
        # 调用C++接口函数，撤销全部订单，并解码返回消息
        ret = self.api.hft_cancel_all(id, bytes(stdCode, encoding = "utf8"), isBuy)
        return bytes.decode(ret)

    def hft_buy(self, id:int, stdCode:str, price:float, qty:float, userTag:str, flag:int):
        """
        HFT策略买入指令接口
        
        下达买入订单。HFT策略支持多种订单类型，包括普通单、FAK、FOK等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串）
        @param price: 买入价格（浮点数），0表示市价单，非0表示限价单
        @param qty: 买入数量（浮点数）
        @param userTag: 用户标记（字符串，需要编码为UTF-8字节字符串），用于标识订单
        @param flag: 下单标志（整数），0-normal（普通单），1-fak（立即成交剩余撤销），2-fok（全部成交否则撤销）
        @return: 本地订单号（字符串），从字节字符串解码得到，用于后续撤单和查询
        """
        # 调用C++接口函数，下达买入订单，并解码返回的本地订单号
        ret = self.api.hft_buy(id, bytes(stdCode, encoding = "utf8"), price, qty, bytes(userTag, encoding = "utf8"), flag)
        return bytes.decode(ret)

    def hft_sell(self, id:int, stdCode:str, price:float, qty:float, userTag:str, flag:int):
        """
        HFT策略卖出指令接口
        
        下达卖出订单。HFT策略支持多种订单类型，包括普通单、FAK、FOK等。
        
        @param id: 策略ID，唯一标识一个策略实例
        @param stdCode: 品种代码（字符串，需要编码为UTF-8字节字符串）
        @param price: 卖出价格（浮点数），0表示市价单，非0表示限价单
        @param qty: 卖出数量（浮点数）
        @param userTag: 用户标记（字符串，需要编码为UTF-8字节字符串），用于标识订单
        @param flag: 下单标志（整数），0-normal（普通单），1-fak（立即成交剩余撤销），2-fok（全部成交否则撤销）
        @return: 本地订单号（字符串），从字节字符串解码得到，用于后续撤单和查询
        """
        # 调用C++接口函数，下达卖出订单，并解码返回的本地订单号
        ret = self.api.hft_sell(id, bytes(stdCode, encoding = "utf8"), price, qty, bytes(userTag, encoding = "utf8"), flag)
        return bytes.decode(ret)

    # ========== 策略上下文创建接口 ==========
    def create_cta_context(self, name:str, slippage:int = 0) -> int:
        """
        创建CTA策略上下文接口
        
        在C++引擎中创建一个CTA策略上下文。策略上下文是策略的运行环境，
        包含策略的状态、持仓、资金等信息。
        
        @param name: 策略名称（字符串，需要编码为UTF-8字节字符串），用于标识策略
        @param slippage: 滑点大小（整数，默认0），单位为最小价格变动单位，用于模拟交易成本
        @return: 系统内策略ID（整数），用于后续调用策略接口时标识策略
        """
        # 调用C++接口函数，创建CTA策略上下文
        return self.api.create_cta_context(bytes(name, encoding = "utf8"), slippage)

    def create_hft_context(self, name:str, trader:str, agent:bool, slippage:int = 0) -> int:
        """
        创建HFT策略上下文接口
        
        在C++引擎中创建一个HFT策略上下文。HFT策略上下文需要指定交易通道，
        用于连接交易接口。
        
        @param name: 策略名称（字符串，需要编码为UTF-8字节字符串），用于标识策略
        @param trader: 交易通道ID（字符串，需要编码为UTF-8字节字符串），标识使用的交易接口
        @param agent: 数据是否托管（布尔值），True表示数据由引擎管理，False表示策略自己管理
        @param slippage: 滑点大小（整数，默认0），单位为最小价格变动单位，用于模拟交易成本
        @return: 系统内策略ID（整数），用于后续调用策略接口时标识策略
        """
        # 调用C++接口函数，创建HFT策略上下文
        return self.api.create_hft_context(bytes(name, encoding = "utf8"), bytes(trader, encoding = "utf8"), agent, slippage)

    def create_sel_context(self, name:str, date:int, time:int, period:str, trdtpl:str = 'CHINA', session:str = "TRADING", slippage:int = 0) -> int:
        """
        创建SEL策略上下文接口
        
        在C++引擎中创建一个SEL策略上下文。SEL策略上下文需要指定执行周期和时间，
        用于定时执行选股逻辑。
        
        @param name: 策略名称（字符串，需要编码为UTF-8字节字符串），用于标识策略
        @param date: 日期参数（整数），根据周期变化：每日为0，每周为0~6（对应周日到周六），每月为1~31，每年为0101~1231
        @param time: 时间参数（整数），精确到分钟，格式如930表示09:30
        @param period: 时间周期（字符串，需要编码为UTF-8字节字符串），可以是分钟min、天d、周w、月m、年y
        @param trdtpl: 交易模板（字符串，默认'CHINA'，需要编码为UTF-8字节字符串），用于定义交易时间规则
        @param session: 交易时段（字符串，默认"TRADING"，需要编码为UTF-8字节字符串），用于定义交易时段
        @param slippage: 滑点大小（整数，默认0），单位为最小价格变动单位，用于模拟交易成本
        @return: 系统内策略ID（整数），用于后续调用策略接口时标识策略
        """
        # 调用C++接口函数，创建SEL策略上下文
        return self.api.create_sel_context(bytes(name, encoding = "utf8"), date, time, 
            bytes(period, encoding = "utf8"), bytes(trdtpl, encoding = "utf8"), bytes(session, encoding = "utf8"), slippage)

    def reg_cta_factories(self, factFolder:str):
        """
        注册CTA策略工厂接口
        
        注册CTA策略工厂目录。策略工厂用于动态加载CTA策略类。
        
        @param factFolder: 工厂目录路径（字符串，需要编码为UTF-8字节字符串），包含策略工厂文件的目录
        @return: 是否注册成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，注册CTA策略工厂
        return self.api.reg_cta_factories(bytes(factFolder, encoding = "utf8") )

    def reg_hft_factories(self, factFolder:str):
        """
        注册HFT策略工厂接口
        
        注册HFT策略工厂目录。策略工厂用于动态加载HFT策略类。
        
        @param factFolder: 工厂目录路径（字符串，需要编码为UTF-8字节字符串），包含策略工厂文件的目录
        @return: 是否注册成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，注册HFT策略工厂
        return self.api.reg_hft_factories(bytes(factFolder, encoding = "utf8") )

    def reg_sel_factories(self, factFolder:str):
        """
        注册SEL策略工厂接口
        
        注册SEL策略工厂目录。策略工厂用于动态加载SEL策略类。
        
        @param factFolder: 工厂目录路径（字符串，需要编码为UTF-8字节字符串），包含策略工厂文件的目录
        @return: 是否注册成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，注册SEL策略工厂
        return self.api.reg_sel_factories(bytes(factFolder, encoding = "utf8") )

    def reg_exe_factories(self, factFolder:str):
        """
        注册执行器工厂接口
        
        注册执行器工厂目录。执行器工厂用于动态加载执行器类。
        
        @param factFolder: 工厂目录路径（字符串，需要编码为UTF-8字节字符串），包含执行器工厂文件的目录
        @return: 是否注册成功，True表示成功，False表示失败
        """
        # 调用C++接口函数，注册执行器工厂
        return self.api.reg_exe_factories(bytes(factFolder, encoding = "utf8") )

    