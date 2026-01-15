"""
扩展模块定义模块

本模块定义了扩展模块的基础类，用于扩展框架的功能。
主要包括扩展行情解析器、扩展执行器、扩展数据加载器和扩展数据导出器四类扩展模块。

主要功能：
1. BaseExtParser：扩展行情解析器基类，用于接入外部行情数据源
2. BaseExtExecuter：扩展执行器基类，用于自定义订单执行逻辑
3. BaseExtDataLoader：扩展数据加载器基类，用于从外部数据源加载历史数据
4. BaseExtDataDumper：扩展数据导出器基类，用于将数据导出到外部存储
"""


class BaseExtParser:
    """
    扩展行情解析器基类
    
    所有扩展行情解析器的基类，用于接入外部行情数据源（如第三方行情接口、数据文件等）。
    子类需要实现连接、订阅、数据接收等方法，将外部行情数据转换为框架标准格式并推送。
    """
    
    def __init__(self, id:str):
        """
        构造函数
        
        初始化扩展行情解析器，设置解析器ID。
        
        @id: 解析器ID，用于唯一标识该解析器
        """
        # 保存解析器ID
        self.__id__ = id
        return

    def id(self) -> str:
        """
        获取解析器ID
        
        @return: 返回解析器ID字符串
        """
        return self.__id__

    def init(self, engine):
        """
        初始化解析器
        
        在解析器创建后调用，用于保存引擎引用，以便后续调用引擎接口。
        
        @engine: 引擎对象引用，用于调用引擎的接口
        """
        # 保存引擎引用
        self.__engine__ = engine
        return

    def connect(self):
        """
        开始连接（抽象方法）
        
        子类需要实现此方法，建立与外部行情数据源的连接。
        """
        return

    def disconnect(self):
        """
        断开连接（抽象方法）
        
        子类需要实现此方法，断开与外部行情数据源的连接。
        """
        return

    def release(self):
        """
        释放资源（抽象方法）
        
        子类需要实现此方法，释放解析器占用的资源。
        一般在进程退出时调用。
        """
        return

    def subscribe(self, fullCode:str):
        """
        订阅实时行情（抽象方法）
        
        子类需要实现此方法，向外部行情数据源订阅指定合约的实时行情。
        
        @fullCode: 合约代码，格式如CFFEX.IF2106
        """
        return

    def unsubscribe(self, fullCode:str):
        """
        退订实时行情（抽象方法）
        
        子类需要实现此方法，取消对指定合约的实时行情订阅。
        
        @fullCode: 合约代码，格式如CFFEX.IF2106
        """
        return


class BaseExtExecuter:
    """
    扩展执行器基类
    
    所有扩展执行器的基类，用于自定义订单执行逻辑。
    执行器接收策略的目标仓位，然后根据自定义逻辑执行订单，实现更精细的订单管理。
    """
    
    def __init__(self, id:str, scale:float):
        """
        构造函数
        
        初始化扩展执行器，设置执行器ID和数量放大倍数。
        
        @id: 执行器ID，用于唯一标识该执行器
        @scale: 数量放大倍数，用于调整目标仓位的大小
        """
        # 保存执行器ID
        self.__id__ = id
        # 保存数量放大倍数
        self.__scale__ = scale
        # 存储目标仓位的字典，键为合约代码，值为目标仓位
        self.__targets__ = dict()
        return

    def id(self):
        """
        获取执行器ID
        
        @return: 返回执行器ID字符串
        """
        return self.__id__
    
    def init(self):
        """
        初始化执行器（抽象方法）
        
        子类可以重写此方法，在执行器创建后执行初始化操作。
        """
        return

    def set_position(self, stdCode:str, targetPos:float):
        """
        设置目标仓位
        
        接收策略的目标仓位设置，子类可以重写此方法实现自定义的执行逻辑。
        
        @stdCode: 合约代码，期货格式为CFFEX.IF.2106
        @targetPos: 目标仓位，浮点数，正数表示多头，负数表示空头
        """
        # 确定原来的目标仓位
        oldPos = 0
        if stdCode in self.__targets__:
            oldPos = self.__targets__[stdCode]

        # 修改最新的目标仓位
        self.__targets__[stdCode] = targetPos
        return

class BaseExtDataLoader:
    """
    扩展数据加载器基类
    
    所有扩展数据加载器的基类，用于从外部数据源加载历史数据。
    支持加载K线数据、Tick数据和复权因子数据，可以替代框架默认的数据加载方式。
    """
    
    def __init__(self):
        """
        构造函数
        
        初始化扩展数据加载器，基类中不做任何操作。
        """
        pass

    def load_final_his_bars(self, stdCode:str, period:str, feeder) -> bool:
        """
        加载最终历史K线数据（抽象方法）
        
        加载经过处理的历史K线数据，如复权数据、主力合约数据等。
        该接口一般用于加载外部处理好的数据。
        
        @stdCode: 合约代码，格式如CFFEX.IF.2106
        @period: 周期，例如：m1（1分钟）、m5（5分钟）、d1（日线）
        @feeder: 回调函数，用于接收数据，函数签名为feed_raw_bars(bars:POINTER(WTSBarStruct), count:int)
        @return: 如果成功加载数据返回True，否则返回False
        """
        # 基类中返回False，表示未实现
        return False

    def load_raw_his_bars(self, stdCode:str, period:str, feeder) -> bool:
        """
        加载原始历史K线数据（抽象方法）
        
        加载未经过处理的历史K线数据，如未复权数据和分月合约数据。
        该接口一般用于加载原始数据，由框架进行后续处理。
        
        @stdCode: 合约代码，格式如CFFEX.IF.2106
        @period: 周期，例如：m1（1分钟）、m5（5分钟）、d1（日线）
        @feeder: 回调函数，用于接收数据，函数签名为feed_raw_bars(bars:POINTER(WTSBarStruct), count:int)
        @return: 如果成功加载数据返回True，否则返回False
        """
        # 基类中返回False，表示未实现
        return False

    def load_his_ticks(self, stdCode:str, uDate:int, feeder) -> bool:
        """
        加载历史Tick数据（抽象方法）
        
        加载指定日期的历史Tick数据。
        注意：此接口只在回测时有效，实盘时只提供当日落地的数据。
        
        @stdCode: 合约代码，格式如CFFEX.IF.2106
        @uDate: 日期，格式如yyyymmdd，例如：20230101
        @feeder: 回调函数，用于接收数据，函数签名为feed_raw_bars(bars:POINTER(WTSTickStruct), count:int)
        @return: 如果成功加载数据返回True，否则返回False
        """
        # 基类中返回False，表示未实现
        return False

    def load_adj_factors(self, stdCode:str = "", feeder = None) -> bool:
        """
        加载复权因子数据（抽象方法）
        
        加载股票的复权因子数据，用于计算复权价格。
        如果stdCode为空，则加载全部除权数据；如果stdCode不为空，则按需加载。
        
        @stdCode: 合约代码，格式如CFFEX.IF.2106，如果为空则加载全部数据
        @feeder: 回调函数，用于接收数据，函数签名为feed_adj_factors(stdCode:str, dates:list, factors:list)
        @return: 如果成功加载数据返回True，否则返回False
        """
        # 基类中返回False，表示未实现
        return False

class BaseExtDataDumper:
    """
    扩展数据导出器基类
    
    所有扩展数据导出器的基类，用于将数据导出到外部存储系统。
    支持导出K线数据和Tick数据，可以替代框架默认的数据存储方式。
    """
    
    def __init__(self, id:str):
        """
        构造函数
        
        初始化扩展数据导出器，设置导出器ID。
        
        @id: 导出器ID，用于唯一标识该导出器
        """
        # 保存导出器ID
        self.__id__ = id

    def id(self):
        """
        获取导出器ID
        
        @return: 返回导出器ID字符串
        """
        return self.__id__

    def dump_his_bars(self, stdCode:str, period:str, bars, count:int) -> bool:
        """
        导出历史K线数据（抽象方法）
        
        将K线数据导出到外部存储系统。
        子类需要实现此方法，定义具体的导出逻辑。
        
        @stdCode: 合约代码，格式如CFFEX.IF.2106
        @period: 周期，例如：m1（1分钟）、m5（5分钟）、d1（日线）
        @bars: K线数据指针，类型为POINTER(WTSBarStruct)
        @count: 数据条数
        @return: 如果成功导出数据返回True，否则返回False
        """
        # 基类中返回True，表示默认成功（实际应由子类实现）
        return True

    def dump_his_ticks(self, stdCode:str, uDate:int, ticks, count:int) -> bool:
        """
        导出历史Tick数据（抽象方法）
        
        将Tick数据导出到外部存储系统。
        注意：此接口只在回测时有效，实盘时只提供当日落地的数据。
        
        @stdCode: 合约代码，格式如CFFEX.IF.2106
        @uDate: 日期，格式如yyyymmdd，例如：20230101
        @ticks: Tick数据指针，类型为POINTER(WTSTickStruct)
        @count: 数据条数
        @return: 如果成功导出数据返回True，否则返回False
        """
        # 基类中返回True，表示默认成功（实际应由子类实现）
        return True
