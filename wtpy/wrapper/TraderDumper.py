"""
交易数据导出器模块

本模块提供WonderTrader交易数据导出功能的Python接口封装。交易数据导出器用于从交易接口
导出交易相关的数据，包括：
1. 账户信息（资金、持仓、盈亏等）
2. 订单信息（委托单状态、成交情况等）
3. 成交信息（成交记录）
4. 持仓信息（持仓明细）

主要功能：
1. 初始化导出器
2. 配置交易接口连接
3. 注册数据回调函数
4. 运行导出器导出数据
5. 释放资源

数据通过回调函数返回，用户需要实现DumperSink接口来处理接收到的数据。
"""

# 导入平台辅助工具，用于获取动态库路径
from .PlatformHelper import PlatformHelper as ph
# 导入ctypes库，用于调用C++动态库
from ctypes import cdll,CFUNCTYPE,c_void_p,c_char_p,c_uint32,c_double,c_bool,c_uint64

# 导入操作系统模块
import os
# 导入字符编码检测模块，用于自动检测配置文件编码
import chardet
# 导入YAML和JSON处理模块，用于解析配置文件
import yaml
import json

# 定义账户信息回调函数类型：通道ID、交易日、货币、上日余额、当前余额、动态权益、平仓盈亏、浮动盈亏、手续费、保证金、入金、出金、是否最后一条
CB_ACCOUNT = CFUNCTYPE(c_void_p, c_char_p, c_uint32, c_char_p, c_double, c_double, c_double, c_double, 
            c_double, c_double, c_double, c_double, c_double, c_bool)
# 定义订单信息回调函数类型：通道ID、交易所、合约代码、交易日、订单ID、买卖方向、开平标志、委托数量、剩余数量、成交数量、委托价格、订单类型、价格类型、委托时间、订单状态、状态消息、是否最后一条
CB_ORDER = CFUNCTYPE(c_void_p, c_char_p, c_char_p, c_char_p, c_uint32, c_char_p, c_uint32, c_uint32, 
            c_double, c_double, c_double, c_double, c_uint32, c_uint32, c_uint64, c_uint32, c_char_p, c_bool)
# 定义成交信息回调函数类型：通道ID、交易所、合约代码、交易日、成交ID、订单ID、买卖方向、开平标志、成交数量、成交价格、成交金额、订单类型、成交类型、成交时间、是否最后一条
CB_TRADE = CFUNCTYPE(c_void_p, c_char_p, c_char_p, c_char_p, c_uint32, c_char_p, c_char_p, c_uint32, 
            c_uint32, c_double, c_double, c_double, c_uint32, c_uint32, c_uint64, c_bool)
# 定义持仓信息回调函数类型：通道ID、交易所、合约代码、交易日、买卖方向、持仓数量、持仓成本、占用保证金、持仓均价、浮动盈亏、数量乘数、是否最后一条
CB_POSITION = CFUNCTYPE(c_void_p, c_char_p, c_char_p, c_char_p, c_uint32, c_uint32, c_double, c_double, 
            c_double, c_double, c_double, c_uint32, c_bool)

class DumperSink:
    """
    数据导出接收器基类
    
    用户需要继承此类并实现相应的方法来处理导出的数据。
    当导出器接收到数据时，会调用对应的回调方法。
    """
    
    def on_account(self, channelid, curTDate:int, currency, prebalance:float, balance:float, dynbalance:float, 
	        closeprofit:float, dynprofit:float, fee:float, margin:float, deposit:float, withdraw:float, isLast:bool):
        """
        账户信息回调方法
        
        当导出账户信息时调用此方法。
        
        @param channelid: 通道ID（字节串）
        @param curTDate: 当前交易日（整数，格式yyyymmdd）
        @param currency: 货币类型（字节串）
        @param prebalance: 上日余额（浮点数）
        @param balance: 当前余额（浮点数）
        @param dynbalance: 动态权益（浮点数）
        @param closeprofit: 平仓盈亏（浮点数）
        @param dynprofit: 浮动盈亏（浮点数）
        @param fee: 手续费（浮点数）
        @param margin: 占用保证金（浮点数）
        @param deposit: 入金（浮点数）
        @param withdraw: 出金（浮点数）
        @param isLast: 是否最后一条数据（布尔）
        """
        pass

    def on_order(self, channelid, exchg, code, curTDate:int, orderid, direct:int, offset:int, 
            volume:float, leftover:float, traded:float, price:float, ordertype:int, pricetype:int, ordertime:int, state:int, statemsg, isLast:bool):
        """
        订单信息回调方法
        
        当导出订单信息时调用此方法。
        
        @param channelid: 通道ID（字节串）
        @param exchg: 交易所代码（字节串）
        @param code: 合约代码（字节串）
        @param curTDate: 当前交易日（整数，格式yyyymmdd）
        @param orderid: 订单ID（字节串）
        @param direct: 买卖方向（整数，0-买入，1-卖出）
        @param offset: 开平标志（整数，0-开仓，1-平仓）
        @param volume: 委托数量（浮点数）
        @param leftover: 剩余数量（浮点数）
        @param traded: 成交数量（浮点数）
        @param price: 委托价格（浮点数）
        @param ordertype: 订单类型（整数）
        @param pricetype: 价格类型（整数）
        @param ordertime: 委托时间（整数，格式HHMMSS）
        @param state: 订单状态（整数）
        @param statemsg: 状态消息（字节串）
        @param isLast: 是否最后一条数据（布尔）
        """
        pass

    def on_trade(self, channelid, exchg, code, curTDate:int, tradeid, orderid, direct:int, 
            offset:int, volume:float, price:float, amount:float, ordertype:int, tradetype:int, tradetime:int, isLast:bool):
        """
        成交信息回调方法
        
        当导出成交信息时调用此方法。
        
        @param channelid: 通道ID（字节串）
        @param exchg: 交易所代码（字节串）
        @param code: 合约代码（字节串）
        @param curTDate: 当前交易日（整数，格式yyyymmdd）
        @param tradeid: 成交ID（字节串）
        @param orderid: 订单ID（字节串）
        @param direct: 买卖方向（整数，0-买入，1-卖出）
        @param offset: 开平标志（整数，0-开仓，1-平仓）
        @param volume: 成交数量（浮点数）
        @param price: 成交价格（浮点数）
        @param amount: 成交金额（浮点数）
        @param ordertype: 订单类型（整数）
        @param tradetype: 成交类型（整数）
        @param tradetime: 成交时间（整数，格式HHMMSS）
        @param isLast: 是否最后一条数据（布尔）
        """
        pass

    def on_position(self, channelid, exchg, code, curTDate:int, direct:int, volume:float, 
            cost:float, margin:float, avgpx:float, dynprofit:float, volscale:int, isLast:bool):
        """
        持仓信息回调方法
        
        当导出持仓信息时调用此方法。
        
        @param channelid: 通道ID（字节串）
        @param exchg: 交易所代码（字节串）
        @param code: 合约代码（字节串）
        @param curTDate: 当前交易日（整数，格式yyyymmdd）
        @param direct: 买卖方向（整数，0-多头，1-空头）
        @param volume: 持仓数量（浮点数）
        @param cost: 持仓成本（浮点数）
        @param margin: 占用保证金（浮点数）
        @param avgpx: 持仓均价（浮点数）
        @param dynprofit: 浮动盈亏（浮点数）
        @param volscale: 数量乘数（整数）
        @param isLast: 是否最后一条数据（布尔）
        """
        pass

class TraderDumper:
    """
    交易数据导出器类
    
    用于从交易接口导出交易相关数据，包括账户、订单、成交、持仓等信息。
    数据通过回调函数返回给用户实现的数据接收器。
    """

    def __init__(self, sink:DumperSink, logCfg:str = 'logCfg.yaml'):
        """
        初始化交易数据导出器
        
        @param sink: 数据接收器对象，需要实现DumperSink接口
        @param logCfg: 日志配置文件路径，默认为'logCfg.yaml'
        """
        # 获取当前文件所在目录
        paths = os.path.split(__file__)
        # 获取交易数据导出器动态库文件名（包含平台和架构信息）
        dllname = ph.getModule("TraderDumper")
        # 拼接路径
        a = (paths[:-1] + (dllname,))
        # 生成完整的动态库路径
        _path = os.path.join(*a)
        # 加载C++动态库
        self.api = cdll.LoadLibrary(_path)
        # 保存数据接收器引用
        self.sink:DumperSink = sink

        # 初始化配置字典
        self.__config__ = None

        # 调用C++库初始化导出器
        self.api.init(bytes(logCfg, encoding = "utf8"))

        #注册回调函数
        # 创建账户信息回调函数
        self.cb_account     = CB_ACCOUNT(self.sink.on_account)
        # 创建订单信息回调函数
        self.cb_order       = CB_ORDER(self.sink.on_order)
        # 创建成交信息回调函数
        self.cb_trade       = CB_TRADE(self.sink.on_trade)
        # 创建持仓信息回调函数
        self.cb_position    = CB_POSITION(self.sink.on_position)
        # 向C++库注册所有回调函数
        self.api.register_callbacks(self.cb_account, self.cb_order, self.cb_trade, self.cb_position)

    def __check_config__(self):
        """
        检查并初始化配置字典
        
        确保配置字典存在并包含必要的键。
        """
        # 如果配置字典不存在，创建空字典
        if self.__config__ is None:
            self.__config__ = dict()

        # 如果basefiles键不存在，创建空字典
        if "basefiles" not in self.__config__:
            self.__config__["basefiles"] = dict()

        # 如果traders键不存在，创建空列表
        if "traders" not in self.__config__:
            self.__config__["traders"] = list()

    def clear_traders(self):
        """
        清空交易接口列表
        
        清除配置中的所有交易接口配置。
        """
        # 将交易接口列表清空
        self.__config__['traders'] = []

    def add_trader(self, params:dict):
        """
        添加交易接口配置
        
        @param params: 交易接口参数字典，包含连接信息等
        """
        # 将交易接口参数添加到配置列表中
        self.__config__['traders'].append(params)

    def init(self, folder:str,
            cfgfile:str = 'config.yaml',
            commfile:str= None, 
            contractfile:str = None,
            sessionfile:str = None):
        """
        初始化导出器配置
        
        从配置文件加载配置，并设置基础文件路径。
        
        @param folder: 基础文件目录路径
        @param cfgfile: 配置文件路径，默认为'config.yaml'
        @param commfile: 商品信息文件名，默认为None
        @param contractfile: 合约信息文件名，默认为None
        @param sessionfile: 交易时段信息文件名，默认为None
        """
        # 如果配置文件存在，读取并解析
        if os.path.exists(cfgfile):
            # 以二进制模式打开文件
            f = open(cfgfile, "rb")
            # 读取文件内容
            content = f.read()
            # 关闭文件
            f.close()
            # 检测文件编码（只检测前500字节）
            encoding = chardet.detect(content[:500])["encoding"]
            # 使用检测到的编码解码文件内容
            content = content.decode(encoding)

            # 根据文件扩展名选择解析方式
            if cfgfile.lower().endswith(".json"):
                # JSON格式：使用JSON解析
                self.__config__ = json.loads(content)
                # 标记配置文件不是YAML格式
                self.__is_cfg_yaml__ = False
            else:
                # YAML格式：使用YAML解析
                self.__config__ = yaml.full_load(content)
                # 标记配置文件是YAML格式
                self.__is_cfg_yaml__ = True

        # 检查并初始化配置字典
        self.__check_config__()

        # 如果指定了合约信息文件，设置路径
        if contractfile is not None:
            self.__config__["replayer"]["basefiles"]["contract"] = folder + contractfile
        
        # 如果指定了交易时段信息文件，设置路径
        if sessionfile is not None:
            self.__config__["replayer"]["basefiles"]["session"] = folder + sessionfile

        # 如果指定了商品信息文件，设置路径
        if commfile is not None:
            self.__config__["replayer"]["basefiles"]["commodity"] = folder + commfile

    def __commit__(self):
        """
        提交配置到C++库
        
        将配置字典转换为JSON字符串并传递给C++库。
        """
        # 将配置字典转换为JSON字符串（缩进4个空格，便于阅读）
        content = json.dumps(self.__config__, indent=4)
        # 打开配置文件写入配置
        f = open("config.json", "w")
        # 写入配置内容
        f.write(content)
        # 关闭文件
        f.close()
        # 调用C++库配置导出器，第二个参数False表示传入的是配置内容而非文件路径
        self.api.config(bytes(content, encoding = "utf8"), False)

    def run(self, bOnce:bool = False):
        """
        运行导出器
        
        开始导出交易数据。数据会通过回调函数返回。
        
        @param bOnce: 是否只导出一次，True表示导出一次后停止，False表示持续导出，默认为False
        """
        # 提交配置到C++库
        self.__commit__()
        # 调用C++库运行导出器
        self.api.run(bOnce)

    def release(self):
        """
        释放导出器资源
        
        停止导出器并释放相关资源。
        """
        # 调用C++库释放导出器
        self.api.release()
