"""
合约信息管理模块

本模块负责管理交易合约的详细信息，包括合约代码、名称、上市日期、到期日、
保证金率等。支持期货合约和期权合约的管理，可以根据品种、标的资产等条件查询合约。

主要功能：
1. ContractInfo：合约信息数据类，存储单个合约的所有属性
2. ContractMgr：合约信息管理器，负责加载、存储和查询合约信息
"""

# 导入JSON处理模块
import json
# 导入YAML处理模块
import yaml
# 导入字符编码检测模块
import chardet

# 导入品种管理器和品种信息类
from .ProductMgr import ProductMgr, ProductInfo

class ContractInfo:
    """
    合约信息数据类
    
    存储单个交易合约的所有属性信息，包括合约代码、名称、上市日期、
    到期日、保证金率等。支持期货合约和期权合约。
    """

    def __init__(self):
        """
        构造函数
        
        初始化合约信息的所有属性为默认值。
        """
        # 交易所代码，例如：SHFE、CFFEX、CZCE等
        self.exchg:str = ''
        # 合约代码，例如：rb2305、ag2312等
        self.code:str = ''
        # 合约名称，中文名称，例如：螺纹钢2305、白银2312等
        self.name:str = ''
        # 品种代码，例如：rb、ag等
        self.product:str = ''
        # 标准合约代码，格式：交易所.品种.月份，例如：SHFE.rb.2305
        self.stdCode:str = ''

        # 是否期权合约标志
        self.isOption:bool = False
        # 标的资产代码（期权专用），例如：IM2304
        self.underlying:str = ''
        # 行权价（期权专用）
        self.strikePrice:float = 0
        # 标的资产放大倍数（期权专用）
        self.underlyingScale:float = 0
        # 是否看涨期权（期权专用），True为看涨，False为看跌
        self.isCall:bool = True

        # 上市日期，格式：yyyymmdd，例如：20230101
        self.openDate:int = 19000101
        # 到期日，格式：yyyymmdd，例如：20231231
        self.expireDate:int = 20991231

        # 多头保证金率，用于计算保证金
        self.longMarginRatio:float = 0
        # 空头保证金率，用于计算保证金
        self.shortMarginRatio:float = 0


class ContractMgr:
    """
    合约信息管理器类
    
    负责加载、存储和管理所有交易合约的信息。
    支持从JSON或YAML格式的配置文件中加载合约信息。
    提供按品种、按标的资产等条件查询合约的功能。
    """

    def __init__(self, prodMgr:ProductMgr = None):
        """
        构造函数
        
        初始化合约信息管理器，创建空的合约信息字典和索引字典。
        
        @prodMgr: 可选的品种管理器对象，用于关联品种信息
        """
        # 存储所有合约信息的字典，键为标准合约代码，值为ContractInfo对象
        self.__contracts__ = dict()
        # 按标的资产索引的字典（期权专用），键为标的资产标准代码，值为合约代码列表
        self.__underlyings__ = dict()
        # 按品种索引的字典，键为标准品种ID，值为合约代码列表
        self.__products__ = dict()
        # 保存品种管理器引用，用于关联品种信息
        self.__prod_mgr__ = prodMgr

    def load(self, fname:str):
        """
        从文件加载合约信息
        
        支持JSON和YAML两种格式的配置文件。
        文件格式应为：{交易所: {合约代码: {name: 名称, product: 品种, ...}}}
        
        @fname: 配置文件路径，支持.json和.yaml格式
        """
        # 以二进制模式打开文件
        f = open(fname, 'rb')
        # 读取文件内容
        content = f.read()
        # 关闭文件
        f.close()
        # 检测文件编码（检测前500字节）
        encoding = chardet.detect(content[:500])["encoding"]
        # 将文件内容解码为字符串
        content = content.decode(encoding)

        # 根据文件扩展名选择解析方式
        if fname.lower().endswith(".yaml"):
            # YAML格式文件，使用yaml模块解析
            exchgMap = yaml.full_load(content)
        else:
            # JSON格式文件，使用json模块解析
            exchgMap = json.loads(content)
        # 遍历所有交易所
        for exchg in exchgMap:
            # 获取该交易所下的所有合约
            exchgObj = exchgMap[exchg]

            # 遍历该交易所下的所有合约
            for code in exchgObj:
                # 获取合约配置对象
                cObj = exchgObj[code]
                # 创建合约信息对象
                cInfo = ContractInfo()
                # 设置交易所代码
                cInfo.exchg = exchg
                # 设置合约代码
                cInfo.code = code
                # 设置合约名称
                cInfo.name = cObj["name"]

                # By Wesley @ 2021-03-31 
                # 增加了对合约的上市日期和到期日的读取
                # 增加了对合约的保证金率的读取
                # 如果配置中包含上市日期，则设置
                if "opendate" in cObj:
                    cInfo.openDate = int(cObj["opendate"])
                # 如果配置中包含到期日，则设置
                if "expiredate" in cObj:
                    cInfo.expireDate = int(cObj["expiredate"])
                # 如果配置中包含多头保证金率，则设置
                if "longmarginratio" in cObj:
                    cInfo.longMarginRatio = float(cObj["longmarginratio"])
                # 如果配置中包含空头保证金率，则设置
                if "shortmarginratio" in cObj:
                    cInfo.shortMarginRatio = float(cObj["shortmarginratio"])

                # 如果配置中包含品种信息
                if "product" in cObj:
                    # 设置品种代码
                    cInfo.product = cObj["product"]
                    # 股票标准代码为SSE.000001，期货标准代码为SHFE.rb.2010
                    # 判断合约代码是否以品种代码开头
                    if cInfo.code[:len(cInfo.product)] == cInfo.product:
                        # 提取月份部分（合约代码去掉品种代码后的部分）
                        month = cInfo.code[len(cInfo.product):]
                        # 如果月份长度小于4位，在前面补2（表示20xx年）
                        if len(month) < 4:
                            month = "2" + month
                        # 构造标准合约代码：交易所.品种.月份
                        cInfo.stdCode = exchg + "." + cInfo.product + "." + month
                    else:
                        # 如果合约代码不以品种代码开头，则使用完整合约代码
                        cInfo.stdCode = exchg + "." + cInfo.product + "." + cInfo.code

                    # 构造标准品种ID
                    stdPID = exchg + "." + cInfo.product
                    # 如果该品种还没有索引，则创建索引列表
                    if stdPID not in self.__products__:
                        self.__products__[stdPID] = list()

                    # 将合约代码添加到品种索引中
                    self.__products__[stdPID].append(cInfo.stdCode)
                else:
                    # 如果没有品种信息，则合约代码就是品种代码
                    cInfo.product = cInfo.code
                    # 标准合约代码就是交易所.合约代码
                    cInfo.stdCode = exchg + "." + cInfo.code
                    # 如果配置中包含rules字段，说明这是内嵌的品种定义
                    if "rules" in cObj:
                        # 获取品种规则配置
                        pObj = cObj["rules"]
                        # 创建品种信息对象
                        pInfo = ProductInfo()
                        # 设置交易所代码
                        pInfo.exchg = exchg
                        # 设置品种代码
                        pInfo.product = cInfo.code
                        # 设置品种名称
                        pInfo.name = cInfo.name
                        # 设置交易时段名称
                        pInfo.session = pObj["session"]
                        # 设置数量乘数
                        pInfo.volscale = int(pObj["volscale"])
                        # 设置价格变动单位
                        pInfo.pricetick = float(pObj["pricetick"])

                        # 如果配置中包含最小交易数量，则设置
                        if "minlots" in pObj:
                            pInfo.minlots = float(pObj["minlots"])
                        # 如果配置中包含交易数量变动单位，则设置
                        if "lotstick" in pObj:
                            pInfo.lotstick = float(pObj["lotstick"])

                # 如果配置中包含期权信息
                if "option" in cObj:
                    # 获取期权配置对象
                    oObj = cObj["option"]
                    # 标记为期权合约
                    cInfo.isOption = True
                    # 判断期权类型：49表示看涨期权（C），50表示看跌期权（P）
                    cInfo.isCall = (int(oObj["optiontype"])==49)
                    # 设置标的资产代码
                    cInfo.underlying = oObj["underlying"]
                    # 设置行权价
                    cInfo.strikePrice = float(oObj["strikeprice"])
                    # 设置标的资产放大倍数
                    cInfo.underlyingScale = float(oObj["underlyingscale"])

                # 将合约信息存储到字典中
                self.__contracts__[cInfo.stdCode] = cInfo
                # 如果是期权合约，需要建立标的资产索引
                if cInfo.isOption:
                    # 构造标的资产标准代码
                    stdUnderlying = f"{exchg}.{cInfo.underlying}"
                    # 如果该标的资产还没有索引，则创建索引列表
                    if stdUnderlying not in self.__underlyings__:
                        self.__underlyings__[stdUnderlying] = list()

                    # 将合约代码添加到标的资产索引中
                    self.__underlyings__[stdUnderlying].append(cInfo.stdCode)

    def getContractInfo(self, stdCode:str, uDate:int = 0) -> ContractInfo:
        """
        获取合约信息
        
        根据标准合约代码获取对应的合约信息对象。
        可以指定交易日，只返回在该交易日有效的合约。
        
        @stdCode: 标准合约代码，格式如SHFE.rb.2305
        @uDate: 交易日，格式如20210101，如果为0则不检查日期有效性
        @return: 返回ContractInfo对象，如果不存在或不在有效期内则返回None
        """
        # 检查合约代码是否存在
        if stdCode not in self.__contracts__:
            return None
            
        # 获取合约信息对象
        cInfo:ContractInfo = self.__contracts__[stdCode]
        # 如果指定了交易日，检查合约是否在该日期有效
        if uDate != 0 and (cInfo.openDate > uDate or cInfo.expireDate < uDate):
            return None
        
        # 返回合约信息对象
        return cInfo

    def getTotalCodes(self, uDate:int = 0) -> list:
        """
        获取全部合约代码列表
        
        返回所有合约的标准代码列表。
        可以指定交易日，只返回在该交易日有效的合约。
        
        @uDate: 交易日，格式如20210101，如果为0则返回所有合约
        @return: 返回合约代码列表
        """
        # 创建结果列表
        codes = list()
        # 遍历所有合约
        for code in self.__contracts__:
            # 获取合约信息对象
            cInfo:ContractInfo = self.__contracts__[code]
            # 如果未指定交易日，或者合约在该日期有效，则添加到结果列表
            if uDate == 0 or (cInfo.openDate <= uDate and cInfo.expireDate >= uDate):
                codes.append(self.__contracts__[code].stdCode)
        # 返回结果列表
        return codes
    
    def getCodesByUnderlying(self, underlying:str, uDate:int = 0) -> list:
        """
        根据标的资产获取合约列表（期权专用）
        
        返回指定标的资产的所有期权合约代码列表。
        可以指定交易日，只返回在该交易日有效的合约。
        
        @underlying: 标的资产标准代码，格式如CFFEX.IM2304
        @uDate: 交易日，格式如20210101，如果为0则返回所有合约
        @return: 返回合约代码列表
        """
        # 创建结果列表
        ret = list()
        # 检查标的资产是否存在索引
        if underlying in self.__underlyings__:
            # 获取该标的资产的所有合约代码
            codes = self.__underlyings__[underlying]
            # 遍历所有合约代码
            for code in codes:
                # 获取合约信息对象
                cInfo:ContractInfo = self.__contracts__[code]
                # 如果未指定交易日，或者合约在该日期有效，则添加到结果列表
                if uDate == 0 or (cInfo.openDate <= uDate and cInfo.expireDate >= uDate):
                    ret.append(self.__contracts__[code].stdCode)

        # 返回结果列表
        return ret
    
    def getCodesByProduct(self, stdPID:str, uDate:int = 0) -> list:
        """
        根据品种代码获取合约列表
        
        返回指定品种的所有合约代码列表。
        可以指定交易日，只返回在该交易日有效的合约。
        
        @stdPID: 品种标准代码，格式如SHFE.rb
        @uDate: 交易日，格式如20210101，如果为0则返回所有合约
        @return: 返回合约代码列表
        """
        # 创建结果列表
        ret = list()
        # 检查品种是否存在索引
        if stdPID in self.__products__:
            # 获取该品种的所有合约代码
            codes = self.__products__[stdPID]
            # 遍历所有合约代码
            for code in codes:
                # 获取合约信息对象
                cInfo:ContractInfo = self.__contracts__[code]
                # 如果未指定交易日，或者合约在该日期有效，则添加到结果列表
                if uDate == 0 or (cInfo.openDate <= uDate and cInfo.expireDate >= uDate):
                    ret.append(self.__contracts__[code].stdCode)
        # 返回结果列表
        return ret
        
