"""
实盘交易引擎模块

本模块定义了WtEngine类，这是wtpy框架的核心实盘交易引擎。
引擎负责管理策略、配置、数据加载、交易执行等核心功能。

主要功能：
1. 引擎初始化：根据引擎类型（CTA/HFT/SEL）初始化对应的底层引擎
2. 策略管理：添加和管理CTA、HFT、SEL策略
3. 配置管理：加载和管理引擎配置、品种信息、合约信息、交易时段等
4. 数据管理：管理历史数据加载器、行情解析器、执行器等扩展模块
5. 运行控制：启动和停止引擎，处理引擎事件回调

设计模式：
- 使用单例模式，确保整个应用只有一个引擎实例
- 通过Wrapper与C++底层交互，封装底层接口调用
"""

# 导入底层包装器，用于与C++底层交互
from wtpy.wrapper import WtWrapper
# 导入策略上下文类
from wtpy.CtaContext import CtaContext
from wtpy.SelContext import SelContext
from wtpy.HftContext import HftContext
# 导入策略基类
from wtpy.StrategyDefs import BaseCtaStrategy, BaseSelStrategy, BaseHftStrategy
# 导入扩展工具基类
from wtpy.ExtToolDefs import BaseIndexWriter, BaseDataReporter
# 导入引擎类型枚举
from wtpy.WtCoreDefs import EngineType
# 导入扩展模块基类
from wtpy.ExtModuleDefs import BaseExtParser, BaseExtExecuter, BaseExtDataLoader
# 导入单例装饰器
from wtpy.WtUtilDefs import singleton

# 导入管理器类
from .ProductMgr import ProductMgr, ProductInfo
from .SessionMgr import SessionMgr, SessionInfo
from .ContractMgr import ContractMgr, ContractInfo
# 导入代码辅助类
from .CodeHelper import CodeHelper

# 导入标准库模块
import json  # JSON格式处理
import yaml  # YAML格式处理
import chardet  # 字符编码检测
import os  # 操作系统接口

@singleton
class WtEngine:
    """
    实盘交易引擎类（单例模式）
    
    负责管理策略、配置、数据加载、交易执行等核心功能。
    支持CTA、HFT、SEL三种类型的策略引擎。
    """

    def __init__(self, eType:EngineType, logCfg:str = "logcfg.yaml", genDir:str = "generated", bDumpCfg:bool = False):
        """
        构造函数
        
        初始化实盘交易引擎，根据引擎类型初始化对应的底层引擎。
        
        @eType: 引擎类型，EngineType.ET_CTA（CTA引擎）、EngineType.ET_HFT（HFT引擎）、EngineType.ET_SEL（SEL引擎）
        @logCfg: 日志配置文件路径，默认为"logcfg.yaml"
        @genDir: 数据输出目录，默认为"generated"
        @bDumpCfg: 是否保存最终配置文件，默认为False
        """
        # 是否为回测模式标志，实盘引擎为False
        self.is_backtest = False

        # 底层API接口转换器，用于调用C++底层接口
        self.__wrapper__:WtWrapper = WtWrapper(self)
        # CTA策略上下文映射表，键为策略ID，值为CtaContext对象
        self.__cta_ctxs__ = dict()
        # SEL策略上下文映射表，键为策略ID，值为SelContext对象
        self.__sel_ctxs__ = dict()
        # HFT策略上下文映射表，键为策略ID，值为HftContext对象
        self.__hft_ctxs__ = dict()
        # 框架配置字典，存储所有配置项
        self.__config__ = dict()
        # 配置是否已提交标志，防止重复提交
        self.__cfg_commited__ = False

        # 指标输出模块，用于输出策略计算的指标数据
        self.__writer__:BaseIndexWriter = None
        # 数据报告器，用于报告实时数据、结算数据等
        self.__reporter__:BaseDataReporter = None

        # 扩展历史数据加载器，用于从外部数据源加载历史数据
        self.__ext_data_loader__:BaseExtDataLoader = None

        # 外接的行情接入模块字典，键为解析器ID，值为BaseExtParser对象
        self.__ext_parsers__ = dict()
        # 外接的执行器字典，键为执行器ID，值为BaseExtExecuter对象
        self.__ext_executers__ = dict()

        # 是否保存最终配置标志
        self.__dump_config__ = bDumpCfg
        # 配置文件是否为YAML格式标志
        self.__is_cfg_yaml__ = True

        # 当前交易日，格式yyyymmdd
        self.trading_day = 0

        # 引擎类型，保存传入的引擎类型参数
        self.__engine_type:EngineType = eType
        # 根据引擎类型初始化对应的底层引擎
        if eType == EngineType.ET_CTA:
            # 初始化CTA引擎
            self.__wrapper__.initialize_cta(logCfg=logCfg, isFile=True, genDir=genDir)
        elif eType == EngineType.ET_HFT:
            # 初始化HFT引擎
            self.__wrapper__.initialize_hft(logCfg=logCfg, isFile=True, genDir=genDir)
        elif eType == EngineType.ET_SEL:
            # 初始化SEL引擎
            self.__wrapper__.initialize_sel(logCfg=logCfg, isFile=True, genDir=genDir)

    def __check_config__(self):
        """
        检查设置项
        
        检查配置字典，补充一些默认设置项，确保配置完整。
        如果配置中缺少必要的字段，会自动添加默认值。
        """
        # 如果配置中没有"basefiles"字段，添加空字典
        if "basefiles" not in self.__config__:
            self.__config__["basefiles"] = dict()

        # 如果配置中没有"env"字段，添加默认环境配置
        if "env" not in self.__config__:
            self.__config__["env"] = dict()
            # 设置环境名称为"cta"
            self.__config__["env"]["name"] = "cta"
            # 设置运行模式为"product"（产品模式）
            self.__config__["env"]["mode"] = "product"
            # 设置产品配置，默认交易时段为"TRADING"
            self.__config__["env"]["product"] = {
                "session":"TRADING"
            }
    
    def get_engine_type(self) -> EngineType:
        """
        获取引擎类型
        
        返回当前引擎的类型。
        
        @return: 引擎类型枚举值
        """
        return self.__engine_type

    def set_extended_data_loader(self, loader:BaseExtDataLoader):
        """
        设置扩展历史数据加载器
        
        设置用于从外部数据源加载历史数据的扩展加载器。
        
        @loader: BaseExtDataLoader实例，用于加载历史数据
        """
        # 保存扩展数据加载器引用
        self.__ext_data_loader__ = loader
        # 向底层注册扩展数据加载器
        self.__wrapper__.register_extended_data_loader()

    def get_extended_data_loader(self) -> BaseExtDataLoader:
        """
        获取扩展历史数据加载器
        
        返回当前设置的扩展历史数据加载器。
        
        @return: BaseExtDataLoader实例，如果未设置则返回None
        """
        return self.__ext_data_loader__

    def add_exetended_parser(self, parser:BaseExtParser):
        """
        添加扩展行情解析器
        
        添加用于接入外部行情数据源的扩展解析器。
        
        @parser: BaseExtParser实例，用于解析外部行情数据
        """
        # 获取解析器ID
        id = parser.id()
        # 如果解析器ID不存在，则创建并添加
        if id not in self.__ext_parsers__:
            # 调用底层接口创建扩展解析器
            if self.__wrapper__.create_extended_parser(id):
                # 如果创建成功，保存解析器引用
                self.__ext_parsers__[id] = parser

    def add_exetended_executer(self, executer:BaseExtExecuter):
        """
        添加扩展执行器
        
        添加用于实现自定义订单执行逻辑的扩展执行器。
        
        @executer: BaseExtExecuter实例，用于执行订单
        """
        # 获取执行器ID
        id = executer.id()
        # 如果执行器ID不存在，则创建并添加
        if id not in self.__ext_executers__:
            # 调用底层接口创建扩展执行器
            if self.__wrapper__.create_extended_executer(id):
                # 如果创建成功，保存执行器引用
                self.__ext_executers__[id] = executer

    def get_extended_parser(self, id:str)->BaseExtParser:
        """
        根据ID获取扩展行情解析器
        
        根据解析器ID获取对应的扩展行情解析器。
        
        @id: 解析器ID
        @return: BaseExtParser实例，如果不存在则返回None
        """
        # 如果解析器ID不存在，返回None
        if id not in self.__ext_parsers__:
            return None
        # 返回对应的解析器实例
        return self.__ext_parsers__[id]

    def get_extended_executer(self, id:str)->BaseExtExecuter:
        """
        根据ID获取扩展执行器
        
        根据执行器ID获取对应的扩展执行器。
        
        @id: 执行器ID
        @return: BaseExtExecuter实例，如果不存在则返回None
        """
        # 如果执行器ID不存在，返回None
        if id not in self.__ext_executers__:
            return None
        # 返回对应的执行器实例
        return self.__ext_executers__[id]

    def push_quote_from_extended_parser(self, id:str, newTick, uProcFlag:int):
        """
        向底层推送Tick数据
        
        从扩展行情解析器向底层推送Tick数据。
        用于扩展解析器将解析到的行情数据传递给底层引擎。
        
        @id: 解析器ID，标识数据来源
        @newTick: Tick数据指针，POINTER(WTSTickStruct)类型
        @uProcFlag: 预处理标记，0-不处理，1-切片，2-累加
        """
        # 调用底层接口推送Tick数据
        self.__wrapper__.push_quote_from_exetended_parser(id, newTick, uProcFlag)

    def set_writer(self, writer:BaseIndexWriter):
        """
        设置指标输出模块
        
        设置用于输出策略计算的指标数据的输出模块。
        
        @writer: BaseIndexWriter实例，用于输出指标数据
        """
        # 保存指标输出模块引用
        self.__writer__ = writer

    def write_indicator(self, id:str, tag:str, time:int, data:dict):
        """
        写入指标数据
        
        将策略计算的指标数据写入到输出模块。
        
        @id: 策略ID，标识指标数据的来源策略
        @tag: 指标标签，用于区分不同的指标，例如：m5、d等
        @time: 指标时间，格式如yyyymmddHHMM
        @data: 指标数据字典，包含指标的具体数值
        """
        # 如果指标输出模块已设置，则调用其写入方法
        if self.__writer__ is not None:
            self.__writer__.write_indicator(id, tag, time, data)

    def set_data_reporter(self, reporter:BaseDataReporter):
        """
        设置数据报告器
        
        设置用于报告实时数据、结算数据等的数据报告器。
        
        @reporter: BaseDataReporter实例，用于报告数据
        """
        # 保存数据报告器引用
        self.__reporter__ = reporter

    def init(self, folder:str, 
        cfgfile:str = "config.yaml", 
        contractfile:str = None,
        sessionfile:str = None,
        commfile:str = None, 
        holidayfile:str = None,
        hotfile:str = None,
        secondfile:str = None):
        """
        初始化引擎
        
        加载配置文件，初始化品种管理器、合约管理器、交易时段管理器等。
        
        @folder: 基础数据文件目录，以\\结尾
        @cfgfile: 配置文件路径，支持JSON和YAML格式，默认为"config.yaml"
        @contractfile: 合约文件路径，如果为None则使用配置文件中的路径
        @sessionfile: 交易时段文件路径，如果为None则使用配置文件中的路径
        @commfile: 品种文件路径，如果为None则使用配置文件中的路径
        @holidayfile: 节假日文件路径，如果为None则使用配置文件中的路径
        @hotfile: 主力合约配置文件路径，如果为None则使用配置文件中的路径
        @secondfile: 秒线配置文件路径，如果为None则使用配置文件中的路径
        """
        # 以二进制模式打开配置文件
        f = open(cfgfile, "rb")
        # 读取文件内容
        content = f.read()
        # 关闭文件
        f.close()
        # 检测文件编码（检测前500字节）
        encoding = chardet.detect(content[:500])["encoding"]
        # 使用检测到的编码解码文件内容
        content = content.decode(encoding)

        # 根据文件扩展名判断文件格式
        if cfgfile.lower().endswith(".json"):
            # 如果是JSON文件，使用json模块解析
            self.__config__ = json.loads(content)
            # 设置配置文件格式标志为False（非YAML）
            self.__is_cfg_yaml__ = False
        else:
            # 如果是YAML文件，使用yaml模块解析
            self.__config__ = yaml.full_load(content)
            # 设置配置文件格式标志为True（YAML）
            self.__is_cfg_yaml__ = True

        # 检查并补充默认配置项
        self.__check_config__()

        # 如果提供了合约文件路径，则更新配置
        if contractfile is not None:        
            self.__config__["basefiles"]["contract"] = os.path.join(folder, contractfile)
        
        # 如果提供了交易时段文件路径，则更新配置
        if sessionfile is not None:
            self.__config__["basefiles"]["session"] = os.path.join(folder, sessionfile)

        # 如果提供了品种文件路径，则更新配置
        if commfile is not None:
            self.__config__["basefiles"]["commodity"] = os.path.join(folder, commfile)

        # 如果提供了节假日文件路径，则更新配置
        if holidayfile is not None:
            self.__config__["basefiles"]["holiday"] = os.path.join(folder, holidayfile)

        # 如果提供了主力合约配置文件路径，则更新配置
        if hotfile is not None:
            self.__config__["basefiles"]["hot"] = os.path.join(folder, hotfile)

        # 如果提供了秒线配置文件路径，则更新配置
        if secondfile is not None:
            self.__config__["basefiles"]["second"] = os.path.join(folder, secondfile)

        # 创建品种管理器实例
        self.productMgr = ProductMgr()
        # 如果配置中包含品种文件路径
        if "commodity" in self.__config__["basefiles"] and self.__config__["basefiles"]["commodity"] is not None:
            # 如果品种文件路径是字符串（单个文件）
            if type(self.__config__["basefiles"]["commodity"]) == str:
                # 加载单个品种文件
                self.productMgr.load(self.__config__["basefiles"]["commodity"])
            # 如果品种文件路径是列表（多个文件）
            elif type(self.__config__["basefiles"]["commodity"]) == list:
                # 遍历列表，加载每个品种文件
                for fname in self.__config__["basefiles"]["commodity"]:
                    self.productMgr.load(fname)

        # 创建合约管理器实例，传入品种管理器引用
        self.contractMgr = ContractMgr(self.productMgr)
        # 如果合约文件路径是字符串（单个文件）
        if type(self.__config__["basefiles"]["contract"]) == str:
            # 加载单个合约文件
            self.contractMgr.load(self.__config__["basefiles"]["contract"])
        # 如果合约文件路径是列表（多个文件）
        elif type(self.__config__["basefiles"]["contract"]) == list:
            # 遍历列表，加载每个合约文件
            for fname in self.__config__["basefiles"]["contract"]:
                self.contractMgr.load(fname)

        # 创建交易时段管理器实例
        self.sessionMgr = SessionMgr()
        # 加载交易时段文件
        self.sessionMgr.load(self.__config__["basefiles"]["session"])

    def configEngine(self, name:str, mode:str = "product"):
        """
        设置引擎和运行模式
        
        配置引擎名称和运行模式。
        
        @name: 引擎名称，用于标识引擎实例
        @mode: 运行模式，默认为"product"（产品模式），还可以是其他模式
        """
        # 设置环境名称
        self.__config__["env"]["name"] = name
        # 设置运行模式
        self.__config__["env"]["mode"] = mode

    def addExternalCtaStrategy(self, id:str, params:dict):
        """
        添加外部的CTA策略
        
        通过配置方式添加CTA策略，策略定义在外部配置文件中。
        
        @id: 策略ID，唯一标识一个策略
        @params: 策略参数字典，包含策略的配置信息
        """
        # 如果配置中没有"strategies"字段，添加空字典
        if "strategies" not in self.__config__:
            self.__config__["strategies"] = dict()

        # 如果配置中没有"cta"字段，添加空列表
        if "cta" not in self.__config__["strategies"]:
            self.__config__["strategies"]["cta"] = list()

        # 在参数字典中添加策略ID
        params["id"] = id
        # 将策略参数添加到CTA策略列表
        self.__config__["strategies"]["cta"].append(params)

    def addExternalHftStrategy(self, id:str, params:dict):
        """
        添加外部的HFT策略
        
        通过配置方式添加HFT策略，策略定义在外部配置文件中。
        
        @id: 策略ID，唯一标识一个策略
        @params: 策略参数字典，包含策略的配置信息
        """
        # 如果配置中没有"strategies"字段，添加空字典
        if "strategies" not in self.__config__:
            self.__config__["strategies"] = dict()

        # 如果配置中没有"hft"字段，添加空列表
        if "hft" not in self.__config__["strategies"]:
            self.__config__["strategies"]["hft"] = list()

        # 在参数字典中添加策略ID
        params["id"] = id
        # 将策略参数添加到HFT策略列表
        self.__config__["strategies"]["hft"].append(params)

    def configStorage(self, path:str, module:str=""):
        """
        配置数据存储
        
        配置历史数据的存储路径和存储模块。
        
        @path: 数据存储路径
        @module: 存储模式，空字符串表示使用wt框架自带数据存储，"csv"表示从csv直接读取（一般回测使用），"wtp"表示使用wt框架自带数据存储
        """
        # 设置存储模块
        self.__config__["data"]["store"]["module"] = module
        # 设置存储路径
        self.__config__["data"]["store"]["path"] = path

    def registerCustomRule(self, ruleTag:str, filename:str):
        """
        注册自定义连续合约规则
        
        注册自定义的连续合约规则，用于生成连续合约代码。
        
        @ruleTag: 规则标签，例如ruleTag为"THIS"，对应的连续合约代码为"CFFEX.IF.THIS"
        @filename: 规则定义文件名，格式和hots.json一样
        """
        # 如果配置中没有"rules"字段，添加空字典
        if "rules" not in self.__config__["basefiles"]:
            self.__config__["basefiles"]["rules"] = dict()

        # 将规则标签和文件名添加到配置中
        self.__config__["basefiles"]["rules"][ruleTag] = filename

    def commitConfig(self):
        """
        提交配置
        
        将配置提交给底层引擎，只有第一次调用会生效，不可重复调用。
        如果执行run之前没有调用，run会自动调用该方法。
        """
        # 如果配置已提交，直接返回
        if self.__cfg_commited__:
            return

        # 将配置字典转换为格式化的JSON字符串
        cfgfile = json.dumps(self.__config__, indent=4, sort_keys=True)
        # 调用底层接口提交配置（第二个参数False表示传入的是字符串而非文件路径）
        self.__wrapper__.config(cfgfile, False)
        # 标记配置已提交
        self.__cfg_commited__ = True

        # 如果需要保存最终配置
        if self.__dump_config__:
            # 如果是YAML格式
            if self.__is_cfg_yaml__:
                # 打开文件准备写入
                f = open("config_run.yaml", 'w')
                # 将配置字典转换为YAML格式并写入文件
                f.write(yaml.dump_all(self.__config__, indent=4, allow_unicode=True))
                # 关闭文件
                f.close()
            else:
                # 如果是JSON格式
                # 打开文件准备写入
                f = open("config_run.json", 'w')
                # 写入JSON字符串
                f.write(cfgfile)
                # 关闭文件
                f.close()

    def regCtaStraFactories(self, factFolder:str):
        """
        向底层模块注册CTA工厂模块目录
        
        注册CTA策略工厂模块所在的目录，CTA策略只会被CTA引擎加载。
        
        @factFolder: 工厂模块所在的目录路径
        @return: 注册是否成功
        """
        # 调用底层接口注册CTA工厂模块目录
        return self.__wrapper__.reg_cta_factories(factFolder)

    def regHftStraFactories(self, factFolder:str):
        """
        向底层模块注册HFT工厂模块目录
        
        注册HFT策略工厂模块所在的目录，HFT策略只会被HFT引擎加载。
        
        @factFolder: 工厂模块所在的目录路径
        @return: 注册是否成功
        """
        # 调用底层接口注册HFT工厂模块目录
        return self.__wrapper__.reg_hft_factories(factFolder)

    def regExecuterFactories(self, factFolder:str):
        """
        向底层模块注册执行器模块目录
        
        注册执行器工厂模块所在的目录，执行器只在CTA引擎有效。
        
        @factFolder: 工厂模块所在的目录路径
        @return: 注册是否成功
        """
        # 调用底层接口注册执行器工厂模块目录
        return self.__wrapper__.reg_exe_factories(factFolder)

    def addExecuter(self, id:str, trader:str, policies:dict, scale:int = 1):
        """
        添加执行器
        
        添加订单执行器，用于执行策略的订单。
        
        @id: 执行器ID，唯一标识一个执行器
        @trader: 交易接口ID，指定使用哪个交易接口
        @policies: 执行策略字典，包含执行策略的配置
        @scale: 数量放大倍数，用于调整交易数量，默认为1
        """
        # 如果配置中没有"executers"字段，添加空列表
        if "executers" not in self.__config__:
            self.__config__["executers"] = list()

        # 创建执行器配置项
        exeItem = {
            "active":True,      # 是否激活
            "id": id,           # 执行器ID
            "scale": scale,      # 数量放大倍数
            "policy": policies,  # 执行策略
            "trader":trader     # 交易接口ID
        }

        # 将执行器配置添加到列表
        self.__config__["executers"].append(exeItem)

    def addTrader(self, id:str, params:dict):
        """
        添加交易接口
        
        添加交易接口配置，用于连接交易服务器。
        
        @id: 交易接口ID，唯一标识一个交易接口
        @params: 交易接口参数字典，包含连接信息等配置
        """
        # 如果配置中没有"traders"字段，添加空列表
        if "traders" not in self.__config__:
            self.__config__["traders"] = list()

        # 创建交易接口配置项
        tItem = params
        # 设置交易接口为激活状态
        tItem["active"] = True
        # 设置交易接口ID
        tItem["id"] = id

        # 将交易接口配置添加到列表
        self.__config__["traders"].append(tItem)

    def getSessionByCode(self, stdCode:str) -> SessionInfo:
        """
        通过合约代码获取交易时间模板
        
        根据合约代码获取对应的交易时段信息。
        
        @stdCode: 合约代码，格式如SHFE.rb.HOT
        @return: SessionInfo对象，如果找不到则返回None
        """
        # 将标准代码转换为标准品种ID
        pid = CodeHelper.stdCodeToStdCommID(stdCode)
        # 获取品种信息
        pInfo = self.productMgr.getProductInfo(pid)
        # 如果品种信息不存在，返回None
        if pInfo is None:
            return None

        # 根据品种信息中的交易时段名称获取交易时段信息
        return self.sessionMgr.getSession(pInfo.session)

    def getSessionByName(self, sname:str) -> SessionInfo:
        """
        通过模板名获取交易时间模板
        
        根据交易时段名称获取对应的交易时段信息。
        
        @sname: 交易时段模板名称，例如"TRADING"
        @return: SessionInfo对象，如果找不到则返回None
        """
        # 根据交易时段名称获取交易时段信息
        return self.sessionMgr.getSession(sname)

    def getProductInfo(self, stdCode:str) -> ProductInfo:
        """
        获取品种信息
        
        根据合约代码或品种代码获取品种信息。
        
        @stdCode: 合约代码或品种代码，格式如SHFE.rb.HOT或SHFE.rb
        @return: ProductInfo对象，如果找不到则返回None
        """
        # 调用品种管理器获取品种信息
        return self.productMgr.getProductInfo(stdCode)

    def getContractInfo(self, stdCode:str) -> ContractInfo:
        """
        获取合约信息
        
        根据合约代码获取合约信息。
        
        @stdCode: 合约代码，格式如SHFE.rb.HOT
        @return: ContractInfo对象，如果找不到或不在有效期内则返回None
        """
        # 调用合约管理器获取合约信息，传入当前交易日
        return self.contractMgr.getContractInfo(stdCode, self.trading_day)

    def getAllCodes(self) -> list:
        """
        获取全部合约代码
        
        获取所有可用的合约代码列表。
        
        @return: 合约代码列表
        """
        # 调用合约管理器获取全部合约代码，传入当前交易日
        return self.contractMgr.getTotalCodes(self.trading_day)
    
    def getCodesByProduct(self, stdPID:str) -> list:
        """
        根据品种ID获取对应合约代码
        
        根据品种代码获取该品种下的所有合约代码列表。
        
        @stdPID: 品种代码，格式如SHFE.rb
        @return: 合约代码列表
        """
        # 调用合约管理器根据品种代码获取合约列表，传入当前交易日
        return self.contractMgr.getCodesByProduct(stdPID, self.trading_day)
    
    def getCodesByUnderlying(self, underlying:str) -> list:
        """
        根据标的资产获取对应合约代码（期权专用）
        
        根据标的资产代码获取该标的资产下的所有期权合约代码列表。
        
        @underlying: 标的资产代码，格式如CFFEX.IM2304
        @return: 合约代码列表
        """
        # 调用合约管理器根据标的资产获取合约列表，传入当前交易日
        return self.contractMgr.getCodesByUnderlying(underlying, self.trading_day)

    def getRawStdCode(self, stdCode:str):
        """
        根据连续合约代码获取原始合约代码
        
        根据连续合约代码（如SHFE.rb.HOT）获取当前对应的分月合约代码（如SHFE.rb.2305）。
        
        @stdCode: 连续合约代码，格式如SHFE.rb.HOT
        @return: 分月合约代码，格式如SHFE.rb.2305，如果不存在则返回空字符串
        """
        # 调用底层接口获取原始合约代码
        return self.__wrapper__.get_raw_stdcode(stdCode)

    def add_cta_strategy(self, strategy:BaseCtaStrategy, slippage:int = 0):
        """
        添加CTA策略
        
        添加一个CTA策略到引擎中，创建策略上下文并注册到底层。
        
        @strategy: 策略对象，继承自BaseCtaStrategy的策略实例
        @slippage: 滑点大小，用于模拟交易时的滑点，默认为0
        """
        # 调用底层接口创建CTA策略上下文，返回策略ID
        id = self.__wrapper__.create_cta_context(strategy.name(), slippage)
        # 创建CTA策略上下文对象，并保存到映射表中
        self.__cta_ctxs__[id] = CtaContext(id, strategy, self.__wrapper__, self)

    def add_hft_strategy(self, strategy:BaseHftStrategy, trader:str, agent:bool = True, slippage:int = 0):
        """
        添加HFT策略
        
        添加一个HFT策略到引擎中，创建策略上下文并注册到底层。
        
        @strategy: 策略对象，继承自BaseHftStrategy的策略实例
        @trader: 交易接口ID，指定使用哪个交易接口
        @agent: 是否使用代理模式，默认为True
        @slippage: 滑点大小，用于模拟交易时的滑点，默认为0
        """
        # 调用底层接口创建HFT策略上下文，返回策略ID
        id = self.__wrapper__.create_hft_context(strategy.name(), trader, agent, slippage)
        # 创建HFT策略上下文对象，并保存到映射表中
        self.__hft_ctxs__[id] = HftContext(id, strategy, self.__wrapper__, self)

    def add_sel_strategy(self, strategy:BaseSelStrategy, date:int, time:int, period:str, trdtpl:str="CHINA", session:str="TRADING", slippage:int = 0):
        """
        添加SEL策略
        
        添加一个SEL策略到引擎中，创建策略上下文并注册到底层。
        
        @strategy: SEL策略对象，继承自BaseSelStrategy的策略实例
        @date: 日期，根据周期变化：每日为0，每周为0~6（对应周日到周六），每月为1~31，每年为0101~1231
        @time: 时间，精确到分钟，格式HHMM
        @period: 时间周期，可以是分钟min、天d、周w、月m、年y
        @trdtpl: 交易日历模板，默认为"CHINA"
        @session: 交易时段名称，默认为"TRADING"
        @slippage: 滑点大小，用于模拟交易时的滑点，默认为0
        """
        # 调用底层接口创建SEL策略上下文，返回策略ID
        id = self.__wrapper__.create_sel_context(name=strategy.name(), date=date, time=time, period=period, trdtpl=trdtpl, session=session, slippage=slippage)
        # 创建SEL策略上下文对象，并保存到映射表中
        self.__sel_ctxs__[id] = SelContext(id, strategy, self.__wrapper__, self)

    def get_context(self, id:int):
        """
        根据ID获取策略上下文
        
        根据策略ID获取对应的策略上下文对象。
        
        @id: 上下文ID，一般添加策略的时候会自动生成一个唯一的上下文ID
        @return: 策略上下文对象（CtaContext、HftContext或SelContext），如果不存在则返回None
        """
        # 根据引擎类型查找对应的上下文
        if self.__engine_type == EngineType.ET_CTA:
            # 如果是CTA引擎，从CTA上下文映射表中查找
            if id not in self.__cta_ctxs__:
                return None

            return self.__cta_ctxs__[id]
        elif self.__engine_type == EngineType.ET_HFT:
            # 如果是HFT引擎，从HFT上下文映射表中查找
            if id not in self.__hft_ctxs__:
                return None

            return self.__hft_ctxs__[id]
        elif self.__engine_type == EngineType.ET_SEL:
            # 如果是SEL引擎，从SEL上下文映射表中查找
            if id not in self.__sel_ctxs__:
                return None

            return self.__sel_ctxs__[id]

    def run(self, bAsync:bool = True):
        """
        运行框架
        
        启动引擎，开始运行策略。
        
        @bAsync: 是否异步运行，默认为True（异步运行，立即返回），False为同步运行（阻塞直到引擎停止）
        """
        # 如果配置没有提交，则自动提交一下
        if not self.__cfg_commited__:
            self.commitConfig()

        # 调用底层接口运行引擎
        self.__wrapper__.run(bAsync)

    def release(self):
        """
        释放框架
        
        释放引擎资源，停止引擎运行。
        """
        # 调用底层接口释放引擎
        self.__wrapper__.release()

    def on_init(self):
        """
        引擎初始化回调函数（由底层调用）
        
        在引擎初始化时调用，用于执行初始化相关的操作。
        """
        # 如果数据报告器已设置，报告初始化数据
        if self.__reporter__ is not None:
            self.__reporter__.report_init_data()
        return

    def on_schedule(self, date:int, time:int, taskid:int = 0):
        """
        引擎调度回调函数（由底层调用）
        
        在引擎定时调度时调用，用于执行定时任务。
        
        @date: 日期，格式yyyymmdd
        @time: 时间，格式HHMM
        @taskid: 任务ID，默认为0
        """
        # print("engine scheduled")
        # 如果数据报告器已设置，报告实时数据
        if self.__reporter__ is not None:
            self.__reporter__.report_rt_data()

    def on_session_begin(self, date:int):
        """
        交易日开始回调函数（由底层调用）
        
        在每个交易日开始时调用，用于执行交易日开始时的操作。
        
        @date: 交易日，格式yyyymmdd
        """
        # print("session begin")
        # 更新当前交易日
        self.trading_day = date
        return

    def on_session_end(self, date:int):
        """
        交易日结束回调函数（由底层调用）
        
        在每个交易日结束时调用，用于执行交易日结束时的操作。
        
        @date: 交易日，格式yyyymmdd
        """
        # 如果数据报告器已设置，报告结算数据
        if self.__reporter__ is not None:
            self.__reporter__.report_settle_data()
        return
