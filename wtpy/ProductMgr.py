"""
品种信息管理模块

本模块负责管理交易品种的基本信息，包括品种代码、名称、交易时段、价格变动单位等。
品种信息通常从JSON或YAML配置文件中加载，支持多交易所、多品种的管理。

主要功能：
1. ProductInfo：品种信息数据类，存储单个品种的所有属性
2. ProductMgr：品种信息管理器，负责加载、存储和查询品种信息
"""

# 导入JSON处理模块
import json
# 导入YAML处理模块
import yaml
# 导入操作系统接口模块
import os
# 导入字符编码检测模块
import chardet

class ProductInfo:
    """
    品种信息数据类
    
    存储单个交易品种的所有属性信息，包括交易所、品种代码、名称、
    交易时段、价格变动单位、数量乘数等。
    """

    def __init__(self):
        """
        构造函数
        
        初始化品种信息的所有属性为默认值。
        """
        # 交易所代码，例如：SHFE、CFFEX、CZCE等
        self.exchg = ''
        # 品种代码，例如：rb、ag、IF等
        self.product = ''
        # 品种名称，中文名称，例如：螺纹钢、白银等
        self.name = ''
        # 交易时段名称，对应SessionMgr中定义的时段模板
        self.session = ''
        # 价格变动单位（最小变动价位），例如：1.0表示1元
        self.pricetick = 0
        # 数量乘数，用于计算合约价值，例如：10表示每手10吨
        self.volscale = 1
        # 最小交易数量（手数），通常为1
        self.minlots = 1
        # 交易数量变动单位，例如：1表示每次只能变动1手
        self.lotstick = 1

class ProductMgr:
    """
    品种信息管理器类
    
    负责加载、存储和管理所有交易品种的信息。
    支持从JSON或YAML格式的配置文件中加载品种信息。
    """
    
    def __init__(self):
        """
        构造函数
        
        初始化品种信息管理器，创建空的品种信息字典。
        """
        # 存储所有品种信息的字典，键为标准品种ID（格式：交易所.品种），值为ProductInfo对象
        self.__products__ = dict()
        return

    def load(self, fname:str):
        """
        从文件加载品种信息
        
        支持JSON和YAML两种格式的配置文件。
        文件格式应为：{交易所: {品种代码: {name: 名称, session: 时段, ...}}}
        
        @fname: 配置文件路径，支持.json和.yaml格式
        """
        # 检查文件是否存在，如果不存在则直接返回
        if not os.path.exists(fname):
            return
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
            # 获取该交易所下的所有品种
            exchgObj = exchgMap[exchg]
            # 遍历该交易所下的所有品种
            for pid in exchgObj:
                # 获取品种配置对象
                pObj = exchgObj[pid]
                # 创建品种信息对象
                pInfo = ProductInfo()
                # 设置交易所代码
                pInfo.exchg = exchg
                # 设置品种代码
                pInfo.product = pid
                # 设置品种名称
                pInfo.name = pObj["name"]
                # 设置交易时段名称
                pInfo.session = pObj["session"]
                # 设置价格精度（保留小数位数）
                pInfo.precision = int(pObj["precision"])
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

                # 构造标准品种ID（格式：交易所.品种）
                key = "%s.%s" % (exchg, pid)
                # 将品种信息存储到字典中
                self.__products__[key] = pInfo
    
    def addProductInfo(self, key:str, pInfo:ProductInfo):
        """
        手动添加品种信息
        
        允许通过代码方式添加品种信息，而不必从文件加载。
        
        @key: 标准品种ID（格式：交易所.品种）
        @pInfo: 品种信息对象
        """
        # 将品种信息添加到字典中
        self.__products__[key] = pInfo

    def getProductInfo(self, pid:str) -> ProductInfo:
        """
        获取品种信息
        
        根据品种ID获取对应的品种信息对象。
        支持的输入格式：
        - 标准品种ID：SHFE.rb
        - 标准合约代码：SHFE.rb.HOT（连续合约）
        - 标准合约代码：SHFE.rb.1912（具体月份合约）
        
        @pid: 品种ID或合约代码
        @return: 返回ProductInfo对象，如果不存在则返回None
        """
        # pid形式可能为SHFE.ag.HOT，或者SHFE.ag.1912，或者SHFE.ag
        # 按点号分割
        items = pid.split(".")
        # 提取前两部分作为标准品种ID（交易所.品种）
        key = items[0] + "." + items[1]
        # 检查品种ID是否存在
        if key not in self.__products__:
            return None

        # 返回对应的品种信息对象
        return self.__products__[key]
