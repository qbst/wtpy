"""
合约代码辅助工具模块

本模块提供合约代码相关的辅助函数，主要用于处理标准化的合约代码格式转换和识别。
支持期货、期权等不同类型的合约代码解析，特别是对中国期货期权代码格式的特殊处理。

主要功能：
1. 识别中国期货期权标准代码格式
2. 将标准合约代码转换为标准品种ID
"""

# 导入正则表达式模块，用于模式匹配
import re

class CodeHelper:
    """
    合约代码辅助工具类
    
    提供静态方法用于处理合约代码的格式转换和识别。
    所有方法都是静态方法，可以直接通过类名调用，无需实例化。
    """
    
    @staticmethod
    def isStdChnFutOptCode(stdCode:str) -> bool:
        """
        判断是否为标准的中国期货期权代码
        
        中国期货期权代码格式：交易所.品种年月.(C|P).行权价
        例如：CFFEX.IO2304.C.5000 表示中金所IO2304看涨期权，行权价5000
        
        @stdCode: 标准合约代码字符串
        @return: 如果是标准中国期货期权代码返回True，否则返回False
        """
        # 定义正则表达式模式，匹配标准中国期货期权代码格式
        # 格式：交易所(大写字母).品种(字母+4位数字).(C或P).行权价(数字)
        pattern = re.compile("^[A-Z]+.[A-z]+\\d{4}.(C|P).\\d+$")
        # 使用正则表达式匹配，如果匹配成功则返回True
        if re.match(pattern, stdCode) is not None:
            return True

        # 匹配失败返回False
        return False

    @staticmethod
    def stdCodeToStdCommID(stdCode:str) -> str:
        """
        将标准合约代码转换为标准品种ID
        
        标准合约代码格式：交易所.品种.合约月份/连续合约标识
        标准品种ID格式：交易所.品种
        
        对于期权合约，不同交易所的处理方式不同：
        - CZCE（郑商所）：品种ID包含期权标识
        - CFFEX（中金所）：品种ID不包含期权标识
        - 其他交易所：品种ID添加'_o'后缀表示期权
        
        @stdCode: 标准合约代码，例如：SHFE.rb.2305 或 CFFEX.IO2304.C.5000
        @return: 标准品种ID，例如：SHFE.rb 或 CFFEX.IO
        """
        # 将标准代码按点号分割成数组
        ay = stdCode.split(".")
        # 如果不是标准中国期货期权代码，直接返回前两部分（交易所.品种）
        if not CodeHelper.isStdChnFutOptCode(stdCode):
            return ay[0] + "." + ay[1]
        else:
            # 对于期权代码，需要特殊处理
            # 提取交易所代码
            exchg = ay[0]
            # 提取品种代码，去掉后4位年月数字
            pid = ay[1][:-4]
            # 提取期权类型标识（C或P）
            flag = ay[2]
            # 根据交易所类型返回不同的品种ID格式
            if exchg == 'CZCE':
                # 郑商所：品种ID包含期权标识
                return exchg + "." + pid + flag
            elif exchg == 'CFFEX':
                # 中金所：品种ID不包含期权标识
                return exchg + "." + pid
            else:
                # 其他交易所：品种ID添加'_o'后缀表示期权
                return exchg + "." + pid + '_o'
