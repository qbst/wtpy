"""
回测引擎模块

本模块定义了WtBtEngine类，这是wtpy框架的回测引擎。
回测引擎用于在历史数据上测试策略的表现，支持CTA、HFT、SEL三种类型的策略。

主要功能：
1. 引擎初始化：根据引擎类型（CTA/HFT/SEL）初始化对应的回测引擎
2. 策略管理：添加和管理CTA、HFT、SEL策略
3. 配置管理：加载和管理回测配置、品种信息、合约信息、交易时段等
4. 数据管理：管理历史数据加载器，支持从CSV或WTP格式加载数据
5. 回测控制：启动和停止回测，支持单步执行（用于强化学习训练）

设计模式：
- 使用单例模式，确保整个应用只有一个回测引擎实例
- 通过WtBtWrapper与C++底层交互，封装底层接口调用
- 支持增量回测，可以基于之前的回测结果继续回测
"""

# 导入回测底层包装器，用于与C++底层交互
from wtpy.wrapper import WtBtWrapper
# 导入策略上下文类
from wtpy.CtaContext import CtaContext
from wtpy.SelContext import SelContext
from wtpy.HftContext import HftContext
# 导入策略基类
from wtpy.StrategyDefs import BaseCtaStrategy, BaseSelStrategy, BaseHftStrategy
# 导入扩展工具基类
from wtpy.ExtToolDefs import BaseIndexWriter
# 导入引擎类型枚举
from wtpy.WtCoreDefs import EngineType
# 导入单例装饰器
from wtpy.WtUtilDefs import singleton
# 导入扩展模块基类
from wtpy.ExtModuleDefs import BaseExtDataLoader

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
class WtBtEngine:
    """
    回测引擎类（单例模式）
    
    负责管理回测策略、配置、数据加载、回测执行等核心功能。
    支持CTA、HFT、SEL三种类型的策略回测。
    支持单步执行模式，用于强化学习训练场景。
    """

    def __init__(self, eType:EngineType = EngineType.ET_CTA, logCfg:str = "logcfgbt.yaml", isFile:bool = True, bDumpCfg:bool = False, outDir:str = "./outputs_bt"):
        """
        构造函数
        
        初始化回测引擎，根据引擎类型初始化对应的底层回测引擎。
        
        @eType: 引擎类型，EngineType.ET_CTA（CTA引擎）、EngineType.ET_HFT（HFT引擎）、EngineType.ET_SEL（SEL引擎），默认为ET_CTA
        @logCfg: 日志模块配置文件路径或配置内容字符串，默认为"logcfgbt.yaml"
        @isFile: 是否文件，如果是文件，则将logCfg当做文件路径处理，如果不是文件，则直接当成json格式的字符串进行解析，默认为True
        @bDumpCfg: 回测的实际配置文件是否落地，默认为False
        @outDir: 回测数据输出目录，默认为"./outputs_bt"
        """
        # 是否为回测模式标志，回测引擎为True
        self.is_backtest = True

        # 底层API接口转换器，用于调用C++底层接口
        self.__wrapper__ = WtBtWrapper(self)
        # 策略上下文对象，回测引擎只支持单个策略
        self.__context__ = None
        # 框架配置字典，存储所有配置项
        self.__config__ = dict()
        # 配置是否已提交标志，防止重复提交
        self.__cfg_commited__ = False

        # 指标输出模块，用于输出策略计算的指标数据
        self.__idx_writer__ = None

        # 是否保存最终配置标志
        self.__dump_config__ = bDumpCfg
        # 配置文件是否为YAML格式标志，默认为False（JSON格式）
        self.__is_cfg_yaml__ = False
        
        # 当前交易日，格式yyyymmdd
        self.trading_day = 0

        # 扩展历史数据加载器，用于从外部数据源加载历史数据
        self.__ext_data_loader__:BaseExtDataLoader = None

        # 根据引擎类型初始化对应的底层回测引擎
        if eType == eType.ET_CTA:
            # 初始化CTA回测环境
            self.__wrapper__.initialize_cta(logCfg, isFile, outDir)
        elif eType == eType.ET_HFT:
            # 初始化HFT回测环境
            self.__wrapper__.initialize_hft(logCfg, isFile, outDir)
        elif eType == eType.ET_SEL:
            # 初始化SEL回测环境
            self.__wrapper__.initialize_sel(logCfg, isFile, outDir)

    def __check_config__(self):
        """
        检查设置项
        
        检查配置字典，补充一些默认设置项，确保配置完整。
        如果配置中缺少必要的字段，会自动添加默认值。
        """
        # 如果配置中没有"replayer"字段，添加默认回放器配置
        if "replayer" not in self.__config__:
            self.__config__["replayer"] = dict()
            self.__config__["replayer"]["basefiles"] = dict()

            # 设置回放模式为"csv"（从CSV文件读取数据）
            self.__config__["replayer"]["mode"] = "csv"
            # 设置数据存储路径
            self.__config__["replayer"]["store"] = {
                "path":"./storage/"
            }

        # 如果回放器配置中没有"basefiles"字段，添加默认基础文件配置
        if "basefiles" not in self.__config__["replayer"]:
            self.__config__["replayer"]["basefiles"] = {
                "commodity": None,  # 品种文件路径
                "contract": None,   # 合约文件路径
                "holiday": None,    # 节假日文件路径
                "hot": None,        # 主力合约文件路径
                "session": None     # 交易时段文件路径
            }

        # 如果配置中没有"env"字段，添加默认环境配置
        if "env" not in self.__config__:
            self.__config__["env"] = dict()
            # 设置模拟器名称为"cta"
            self.__config__["env"]["mocker"] = "cta"

    def set_writer(self, writer:BaseIndexWriter):
        """
        设置指标输出模块
        
        设置用于输出策略计算的指标数据的输出模块。
        
        @writer: BaseIndexWriter实例，用于输出指标数据
        """
        # 保存指标输出模块引用
        self.__idx_writer__ = writer

    def write_indicator(self, id:str, tag:str, time:int, data:dict):
        """
        写入指标数据
        
        将策略计算的指标数据写入到输出模块。
        
        @id: 指标ID，标识指标数据的来源策略
        @tag: 标签，主要用于区分指标对应的周期，如m5、d等
        @time: 时间，格式如yyyymmddHHMM
        @data: 指标值字典，包含指标的具体数值
        """
        # 如果指标输出模块已设置，则调用其写入方法
        if self.__idx_writer__ is not None:
            self.__idx_writer__.write_indicator(id, tag, time, data)

    def init_with_config(self, folder:str, 
        config:dict, 
        commfile:str = None, 
        contractfile:str = None,
        sessionfile:str = None,
        holidayfile:str= None,
        hotfile:str = None,
        secondfile:str = None):
        """
        使用配置字典初始化引擎
        
        使用传入的配置字典初始化引擎，加载品种、合约、交易时段等信息。
        
        @folder: 基础数据文件目录
        @config: 配置字典，包含回测的所有配置项
        @commfile: 品种文件路径，如果为None则使用配置文件中的路径
        @contractfile: 合约文件路径，如果为None则使用配置文件中的路径
        @sessionfile: 交易时段文件路径，如果为None则使用配置文件中的路径
        @holidayfile: 节假日文件路径，如果为None则使用配置文件中的路径
        @hotfile: 主力合约配置文件路径，如果为None则使用配置文件中的路径
        @secondfile: 秒线配置文件路径，如果为None则使用配置文件中的路径
        """
        # 复制配置字典（避免修改原始配置）
        self.__config__ = config.copy()

        # 检查并补充默认配置项
        self.__check_config__()

        # 如果提供了合约文件路径，则更新配置
        if contractfile is not None:
            self.__config__["replayer"]["basefiles"]["contract"] = os.path.join(folder, contractfile)
        
        # 如果提供了交易时段文件路径，则更新配置
        if sessionfile is not None:
            self.__config__["replayer"]["basefiles"]["session"] = os.path.join(folder, sessionfile)

        # 如果提供了品种文件路径，则更新配置
        if commfile is not None:
            self.__config__["replayer"]["basefiles"]["commodity"] = os.path.join(folder, commfile)

        # 如果提供了节假日文件路径，则更新配置
        if holidayfile is not None:
            self.__config__["replayer"]["basefiles"]["holiday"] = os.path.join(folder, holidayfile)

        # 如果提供了主力合约配置文件路径，则更新配置
        if hotfile is not None:
            self.__config__["replayer"]["basefiles"]["hot"] = os.path.join(folder, hotfile)

        # 如果提供了秒线配置文件路径，则更新配置
        if secondfile is not None:
            self.__config__["replayer"]["basefiles"]["second"] = os.path.join(folder, secondfile)

        # 创建品种管理器实例
        self.productMgr = ProductMgr()
        # 如果配置中包含品种文件路径
        if self.__config__["replayer"]["basefiles"]["commodity"] is not None:
            # 如果品种文件路径是字符串（单个文件）
            if type(self.__config__["replayer"]["basefiles"]["commodity"]) == str:
                # 加载单个品种文件
                self.productMgr.load(self.__config__["replayer"]["basefiles"]["commodity"])
            # 如果品种文件路径是列表（多个文件）
            elif type(self.__config__["replayer"]["basefiles"]["commodity"]) == list:
                # 遍历列表，加载每个品种文件
                for fname in self.__config__["replayer"]["basefiles"]["commodity"]:
                    self.productMgr.load(fname)

        # 创建合约管理器实例，传入品种管理器引用
        self.contractMgr = ContractMgr(self.productMgr)
        # 如果合约文件路径是字符串（单个文件）
        if type(self.__config__["replayer"]["basefiles"]["contract"]) == str:
            # 加载单个合约文件
            self.contractMgr.load(self.__config__["replayer"]["basefiles"]["contract"])
        # 如果合约文件路径是列表（多个文件）
        elif type(self.__config__["replayer"]["basefiles"]["contract"]) == list:
            # 遍历列表，加载每个合约文件
            for fname in self.__config__["replayer"]["basefiles"]["contract"]:
                self.contractMgr.load(fname)

        # 创建交易时段管理器实例
        self.sessionMgr = SessionMgr()
        # 加载交易时段文件
        self.sessionMgr.load(self.__config__["replayer"]["basefiles"]["session"])

    def init(self, folder:str, 
        cfgfile:str = "configbt.yaml", 
        commfile:str = None, 
        contractfile:str = None,
        sessionfile:str = None,
        holidayfile:str= None,
        hotfile:str = None,
        secondfile:str = None):
        """
        初始化引擎
        
        从配置文件加载配置，初始化品种管理器、合约管理器、交易时段管理器等。
        
        @folder: 基础数据文件目录，以\\结尾
        @cfgfile: 配置文件路径，支持JSON和YAML格式，默认为"configbt.yaml"
        @commfile: 品种定义文件路径，JSON/YAML格式，如果为None则使用配置文件中的路径
        @contractfile: 合约定义文件路径，JSON/YAML格式，如果为None则使用配置文件中的路径
        @sessionfile: 交易时段文件路径，如果为None则使用配置文件中的路径
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
            # 如果是JSON文件，使用json模块解析并调用init_with_config
            self.init_with_config(folder, json.loads(content), commfile, contractfile, sessionfile, holidayfile, hotfile, secondfile)
            # 设置配置文件格式标志为False（非YAML）
            self.__is_cfg_yaml__ = False
        else:
            # 如果是YAML文件，使用yaml模块解析并调用init_with_config
            self.init_with_config(folder, yaml.full_load(content), commfile, contractfile, sessionfile, holidayfile, hotfile, secondfile)
            # 设置配置文件格式标志为True（YAML）
            self.__is_cfg_yaml__ = True   

    def configMocker(self, name:str):
        """
        设置模拟器
        
        设置回测使用的模拟器名称。
        
        @name: 模拟器名称，例如"cta"、"hft"等
        """
        # 设置环境配置中的模拟器名称
        self.__config__["env"]["mocker"] = name

    def configBacktest(self, stime:int, etime:int):
        """
        配置回测设置项
        
        设置回测的开始时间和结束时间。
        
        @stime: 开始时间，格式yyyymmdd或yyyymmddHHMM
        @etime: 结束时间，格式yyyymmdd或yyyymmddHHMM
        """
        # 设置回放器配置中的开始时间
        self.__config__["replayer"]["stime"] = int(stime)
        # 设置回放器配置中的结束时间
        self.__config__["replayer"]["etime"] = int(etime)

    def configBTStorage(self, mode:str, path:str = None, storage:dict = None):
        """
        配置数据存储
        
        配置历史数据的存储模式和存储路径。
        
        @mode: 存储模式，"csv"表示从csv直接读取（一般回测使用），"wtp"表示使用wt框架自带数据存储
        @path: 数据存储路径，如果为None则不设置路径
        @storage: 存储配置字典，如果提供则使用此字典作为存储配置
        """
        # 设置回放器配置中的存储模式
        self.__config__["replayer"]["mode"] = mode
        # 如果提供了路径参数
        if path is not None:
            # 设置存储配置为包含路径的字典
            self.__config__["replayer"]["store"] = {
                "path":path
            }

        # 如果提供了存储配置字典
        if storage is not None:
            # 使用提供的存储配置字典
            self.__config__["replayer"]["store"] = storage

    def configIncrementalBt(self, incrementBtBase:str):
        """
        设置增量回测
        
        设置增量回测的基础目录，用于基于之前的回测结果继续回测。
        
        @incrementBtBase: 增量回测基础目录路径
        """
        # 设置环境配置中的增量回测基础目录
        self.__config__["env"]["incremental_backtest_base"] = incrementBtBase
        
    def registerCustomRule(self, ruleTag:str, filename:str):
        """
        注册自定义连续合约规则
        
        注册自定义的连续合约规则，用于生成连续合约代码。
        
        @ruleTag: 规则标签，例如ruleTag为"THIS"，对应的连续合约代码为"CFFEX.IF.THIS"
        @filename: 规则定义文件名，格式和hots.json一样
        """
        # 如果配置中没有"rules"字段，添加空字典
        if "rules" not in self.__config__["replayer"]["basefiles"]:
            self.__config__["replayer"]["basefiles"]["rules"] = dict()

        # 将规则标签和文件名添加到配置中
        self.__config__["replayer"]["basefiles"]["rules"][ruleTag] = filename

    def setExternalCtaStrategy(self, id:str, module:str, typeName:str, params:dict):
        """
        添加C++的CTA策略
        
        添加C++实现的CTA策略，策略定义在动态链接库中。
        
        @id: 策略ID，唯一标识一个策略
        @module: 策略模块文件名，包含后缀，例如："WzCtaFact.dll"
        @typeName: 模块内的策略类名
        @params: 策略参数字典，包含策略的配置信息
        """
        # 如果配置中没有"cta"字段，添加空字典
        if "cta" not in self.__config__:
            self.__config__["cta"] = dict()

        # 设置CTA策略模块文件名
        self.__config__["cta"]["module"] = module

        # 如果CTA配置中没有"strategy"字段，添加空字典
        if "strategy" not in self.__config__["cta"]:
            self.__config__["cta"]["strategy"] = dict()

        # 设置策略ID
        self.__config__["cta"]["strategy"]["id"] = id
        # 设置策略类名
        self.__config__["cta"]["strategy"]["name"] = typeName
        # 设置策略参数
        self.__config__["cta"]["strategy"]["params"] = params
        

    def setExternalHftStrategy(self, id:str, module:str, typeName:str, params:dict):
        """
        添加C++的HFT策略
        
        添加C++实现的HFT策略，策略定义在动态链接库中。
        
        @id: 策略ID，唯一标识一个策略
        @module: 策略模块文件名，包含后缀，例如："WzHftFact.dll"
        @typeName: 模块内的策略类名
        @params: 策略参数字典，包含策略的配置信息
        """
        # 如果配置中没有"hft"字段，添加空字典
        if "hft" not in self.__config__:
            self.__config__["hft"] = dict()

        # 设置HFT策略模块文件名
        self.__config__["hft"]["module"] = module

        # 如果HFT配置中没有"strategy"字段，添加空字典
        if "strategy" not in self.__config__["hft"]:
            self.__config__["hft"]["strategy"] = dict()

        # 设置策略ID
        self.__config__["hft"]["strategy"]["id"] = id
        # 设置策略类名
        self.__config__["hft"]["strategy"]["name"] = typeName
        # 设置策略参数
        self.__config__["hft"]["strategy"]["params"] = params

    def set_extended_data_loader(self, loader:BaseExtDataLoader, bAutoTrans:bool = True):
        """
        设置扩展数据加载器
        
        设置用于从外部数据源加载历史数据的扩展加载器。
        
        @loader: 数据加载器模块，BaseExtDataLoader实例
        @bAutoTrans: 是否自动转储，如果是的话底层就转成dsb文件，默认为True
        """
        # 保存扩展数据加载器引用
        self.__ext_data_loader__ = loader
        # 向底层注册扩展数据加载器
        self.__wrapper__.register_extended_data_loader(bAutoTrans)

    def get_extended_data_loader(self) -> BaseExtDataLoader:
        """
        获取扩展的数据加载器
        
        返回当前设置的扩展历史数据加载器。
        
        @return: BaseExtDataLoader实例，如果未设置则返回None
        """
        return self.__ext_data_loader__

    def commitBTConfig(self):
        """
        提交配置
        
        将配置提交给底层回测引擎，只有第一次调用会生效，不可重复调用。
        如果执行run_backtest之前没有调用，run_backtest会自动调用该方法。
        """
        # 如果配置已提交，直接返回
        if self.__cfg_commited__:
            return

        # 将配置字典转换为格式化的JSON字符串
        cfgfile = json.dumps(self.__config__, indent=4, sort_keys=True)
        # 调用底层接口提交回测配置（第二个参数False表示传入的是字符串而非文件路径）
        self.__wrapper__.config_backtest(cfgfile, False)
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

    def getSessionByCode(self, code:str) -> SessionInfo:
        """
        通过合约代码获取交易时间模板
        
        根据合约代码获取对应的交易时段信息。
        
        @code: 合约代码，格式如SHFE.rb.HOT
        @return: SessionInfo对象，如果找不到则返回None
        """
        # 将标准代码转换为标准品种ID
        pid = CodeHelper.stdCodeToStdCommID(code)

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

    def getProductInfo(self, code:str) -> ProductInfo:
        """
        获取品种信息
        
        根据合约代码或品种代码获取品种信息。
        
        @code: 合约代码或品种代码，格式如SHFE.rb.HOT或SHFE.rb
        @return: ProductInfo对象，如果找不到则返回None
        """
        # 调用品种管理器获取品种信息
        return self.productMgr.getProductInfo(code)

    def getContractInfo(self, code:str) -> ContractInfo:
        """
        获取合约信息
        
        根据合约代码获取合约信息。
        
        @code: 合约代码，格式如SHFE.rb.HOT
        @return: ContractInfo对象，如果找不到或不在有效期内则返回None
        """
        # 调用合约管理器获取合约信息，传入当前交易日
        return self.contractMgr.getContractInfo(code, self.trading_day)

    def getAllCodes(self) -> list:
        """
        获取全部合约代码
        
        获取所有可用的合约代码列表。
        
        @return: 合约代码列表
        """
        # 调用合约管理器获取全部合约代码，传入当前交易日
        return self.contractMgr.getTotalCodes(self.trading_day)

    def getRawStdCode(self, stdCode:str):
        """
        根据连续合约代码获取原始合约代码
        
        根据连续合约代码（如SHFE.rb.HOT）获取当前对应的分月合约代码（如SHFE.rb.2305）。
        
        @stdCode: 连续合约代码，格式如SHFE.rb.HOT
        @return: 分月合约代码，格式如SHFE.rb.2305，如果不存在则返回空字符串
        """
        # 调用底层接口获取原始合约代码
        return self.__wrapper__.get_raw_stdcode(stdCode)
    
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

    def set_time_range(self, beginTime:int, endTime:int):
        """
        设置回测时间范围
        
        设置回测的开始时间和结束时间。
        一般用于一个进程中多次回测的时候，启动下一轮回测之前重设时间范围。
        
        @beginTime: 开始时间，格式如yyyymmddHHMM
        @endTime: 结束时间，格式如yyyymmddHHMM
        """
        # 调用底层接口设置回测时间范围
        self.__wrapper__.set_time_range(beginTime, endTime)

    def set_cta_strategy(self, strategy:BaseCtaStrategy, slippage:int = 0, hook:bool = False, persistData:bool = True, incremental:bool = False, isRatioSlp:bool = False):
        """
        添加CTA策略
        
        添加一个CTA策略到回测引擎中，创建策略上下文并注册到底层。
        
        @strategy: 策略对象，继承自BaseCtaStrategy的策略实例
        @slippage: 滑点大小，用于模拟交易时的滑点，默认为0
        @hook: 是否安装钩子，主要用于单步控制重算（强化学习训练），默认为False
        @persistData: 回测生成的数据是否落地，默认为True
        @incremental: 是否增量回测，默认为False，如果为True，则会自动根据策略ID到output_bt目录下加载对应的数据
        @isRatioSlp: 滑点是否是比例，默认为False，如果为True，则slippage为万分比
        """
        # 调用底层接口初始化CTA模拟器，返回上下文ID
        ctxid = self.__wrapper__.init_cta_mocker(strategy.name(), slippage, hook, persistData, incremental, isRatioSlp)
        # 创建CTA策略上下文对象
        self.__context__ = CtaContext(ctxid, strategy, self.__wrapper__, self)

    def set_hft_strategy(self, strategy:BaseHftStrategy, hook:bool = False):
        """
        添加HFT策略
        
        添加一个HFT策略到回测引擎中，创建策略上下文并注册到底层。
        
        @strategy: 策略对象，继承自BaseHftStrategy的策略实例
        @hook: 是否安装钩子，主要用于单步控制重算（强化学习训练），默认为False
        """
        # 调用底层接口初始化HFT模拟器，返回上下文ID
        ctxid = self.__wrapper__.init_hft_mocker(strategy.name(), hook)
        # 创建HFT策略上下文对象
        self.__context__ = HftContext(ctxid, strategy, self.__wrapper__, self)

    def set_sel_strategy(self, strategy:BaseSelStrategy, date:int=0, time:int=0, period:str="d", trdtpl:str="CHINA", session:str="TRADING", slippage:int = 0, isRatioSlp:bool = False):
        """
        添加SEL策略
        
        添加一个SEL策略到回测引擎中，创建策略上下文并注册到底层。
        
        @strategy: SEL策略对象，继承自BaseSelStrategy的策略实例
        @date: 日期，根据周期变化：每日为0，每周为0~6（对应周日到周六），每月为1~31，每年为0101~1231，默认为0
        @time: 时间，精确到分钟，格式HHMM，默认为0
        @period: 时间周期，可以是分钟min、天d、周w、月m、年y，默认为"d"
        @trdtpl: 交易日历模板，默认为"CHINA"
        @session: 交易时间模板，默认为"TRADING"
        @slippage: 滑点大小，用于模拟交易时的滑点，默认为0
        @isRatioSlp: 滑点是否是比例，默认为False，如果为True，则slippage为万分比
        """
        # 调用底层接口初始化SEL模拟器，返回上下文ID
        ctxid = self.__wrapper__.init_sel_mocker(strategy.name(), date, time, period, trdtpl, session, slippage, isRatioSlp)
        # 创建SEL策略上下文对象
        self.__context__ = SelContext(ctxid, strategy, self.__wrapper__, self)

    def get_context(self, id:int):
        """
        根据ID获取策略上下文
        
        根据策略ID获取对应的策略上下文对象。
        注意：回测引擎只支持单个策略，所以id参数实际上被忽略。
        
        @id: 上下文ID，一般添加策略的时候会自动生成一个唯一的上下文ID
        @return: 策略上下文对象（CtaContext、HftContext或SelContext）
        """
        # 返回当前策略上下文（回测引擎只支持单个策略）
        return self.__context__

    def run_backtest(self, bAsync:bool = False, bNeedDump:bool = True):
        """
        运行回测框架
        
        启动回测引擎，开始执行回测。
        
        @bAsync: 是否异步运行，默认为False。如果不启动异步模式，则强化学习的训练环境也不能生效，即使策略下了钩子
        @bNeedDump: 是否需要转储数据，默认为True
        """
        # 如果配置没有提交，则自动提交一下
        if not self.__cfg_commited__:
            self.commitBTConfig()

        # 调用底层接口运行回测
        self.__wrapper__.run_backtest(bNeedDump = bNeedDump, bAsync = bAsync)

    def cta_step(self, remark:str = "") -> bool:
        """
        CTA策略单步执行
        
        执行CTA策略的单步回测，用于强化学习训练场景。
        只有在安装了钩子（hook=True）的情况下才能使用。
        
        @remark: 单步备注信息，没有实际作用，主要用于外部调用区分步骤，默认为空字符串
        @return: 是否执行成功，True表示成功，False表示失败或回测已结束
        """
        # 调用底层接口执行CTA策略单步
        return self.__wrapper__.cta_step(self.__context__.id)

    def hft_step(self):
        """
        HFT策略单步执行
        
        执行HFT策略的单步回测，用于强化学习训练场景。
        只有在安装了钩子（hook=True）的情况下才能使用。
        """
        # 调用底层接口执行HFT策略单步
        self.__wrapper__.hft_step(self.__context__.id)

    def stop_backtest(self):
        """
        手动停止回测
        
        手动停止正在运行的回测，用于中断回测过程。
        """
        # 调用底层接口停止回测
        self.__wrapper__.stop_backtest()

    def release_backtest(self):
        """
        释放框架
        
        释放回测引擎资源，清理回测相关的数据。
        """
        # 调用底层接口释放回测引擎
        self.__wrapper__.release_backtest()

    def on_init(self):
        """
        引擎初始化回调函数（由底层调用）
        
        在引擎初始化时调用，用于执行初始化相关的操作。
        """
        return

    def on_schedule(self, date:int, time:int, taskid:int = 0):
        """
        引擎调度回调函数（由底层调用）
        
        在引擎定时调度时调用，用于执行定时任务。
        
        @date: 日期，格式yyyymmdd
        @time: 时间，格式HHMM
        @taskid: 任务ID，默认为0
        """
        return

    def on_session_begin(self, date:int):
        """
        交易日开始回调函数（由底层调用）
        
        在每个交易日开始时调用，用于执行交易日开始时的操作。
        
        @date: 交易日，格式yyyymmdd
        """
        # 更新当前交易日
        self.trading_day = date
        return

    def on_session_end(self, date:int):
        """
        交易日结束回调函数（由底层调用）
        
        在每个交易日结束时调用，用于执行交易日结束时的操作。
        
        @date: 交易日，格式yyyymmdd
        """
        return

    def on_backtest_end(self):
        """
        回测结束回调函数（由底层调用）
        
        在回测结束时调用，用于执行回测结束时的操作。
        会调用策略的on_backtest_end回调函数。
        """
        # 如果策略上下文不存在，直接返回
        if self.__context__ is None:
            return

        # 调用策略上下文的回测结束回调
        self.__context__.on_backtest_end()

    def clear_cache(self):
        """
        清除缓存的数据
        
        清除已经加载到内存中的数据，释放内存。
        即把已经加载到内存中的数据全部清除。
        """
        # 调用底层接口清除缓存
        self.__wrapper__.clear_cache()
