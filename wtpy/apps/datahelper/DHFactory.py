"""
数据辅助工具工厂模块

本模块提供了创建各种数据辅助工具的工厂方法，根据名称创建对应的数据辅助工具实例。
支持的数据源包括Tushare、Baostock、RQData、TqSdk等。

设计模式：工厂模式
通过统一的工厂方法创建不同的数据辅助工具，隐藏具体实现细节。
"""

# 导入数据辅助工具基类
from wtpy.apps.datahelper.DHDefs import BaseDataHelper

class DHFactory:
    """
    数据辅助工具工厂类
    
    用于创建各种数据辅助工具实例，根据名称返回对应的数据辅助工具对象。
    """
    
    @staticmethod
    def createHelper(name:str) -> BaseDataHelper:
        """
        创建数据辅助工具实例
        
        根据数据源名称创建对应的数据辅助工具实例。
        支持的数据源：tushare、baostock、rqdata、tqsdk
        
        @param name: 数据源名称（不区分大小写）
        @return: 数据辅助工具实例
        @raise Exception: 如果数据源名称不支持，抛出异常
        """
        name = name.lower()
        if name == "baostock":
            from wtpy.apps.datahelper.DHBaostock import DHBaostock
            return DHBaostock()
        elif name == "tushare":
            from wtpy.apps.datahelper.DHTushare import DHTushare
            return DHTushare()
        elif name == "rqdata":
            from wtpy.apps.datahelper.DHRqData import DHRqData
            return DHRqData()
        elif name == "tqsdk":
            from wtpy.apps.datahelper.DHTqSdk import DHTqSdk
            return DHTqSdk()
        else:
            raise Exception("Cannot recognize helper with name %s" % (name))
