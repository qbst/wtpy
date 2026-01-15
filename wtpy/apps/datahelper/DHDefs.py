"""
数据辅助工具定义模块

本模块定义了数据辅助工具的基础类和接口，包括数据库辅助类和数据辅助基类。
所有具体的数据辅助工具类都需要继承这些基类。

主要类：
1. DBHelper - 数据库辅助类基类，用于将数据存储到数据库
2. BaseDataHelper - 数据辅助工具基类，定义了数据获取的标准接口
"""

# 导入标准库模块
from datetime import datetime  # 日期时间处理

class DBHelper:
    """
    数据库辅助类基类
    
    用于将K线数据和复权因子数据存储到数据库中。
    子类需要实现具体的数据库操作方法。
    """

    def __init__(self):
        pass

    def initDB(self):
        '''
        初始化数据库，主要是建表等工作
        '''
        pass

    def writeBars(self, bars:list, period="day"):
        '''
        将K线存储到数据库中
        @bars   K线序列
        @period K线周期
        '''
        pass

    def writeFactors(self, factors:dict):
        '''
        将复权因子存储到数据库中
        @factors   复权因子
        '''
        pass


class BaseDataHelper:
    """
    数据辅助工具基类
    
    定义了从各种数据源获取金融数据的标准接口。
    所有具体的数据辅助工具类都需要继承此类并实现相应的方法。
    
    支持的功能：
    1. 获取股票/期货代码列表
    2. 获取K线数据（支持日线、分钟线等）
    3. 获取复权因子数据
    4. 支持将数据导出到文件或数据库
    """

    def __init__(self):
        self.isAuthed = False
        pass

    def __check__(self):
        if not self.isAuthed:
            raise Exception("This module has not authorized yet!")

    def auth(self, **kwargs):
        '''
        模块认证
        '''
        pass

    def dmpCodeListToFile(self, filename:str, hasIndex:bool=True, hasStock:bool=True):
        '''
        将代码列表导出到文件
        @filename   要输出的文件名，json格式
        @hasIndex   是否包含指数
        @hasStock   是否包含股票
        '''
        pass

    def dmpAdjFactorsToFile(self, codes:list, filename:str):
        '''
        将除权因子导出到文件
        @codes  股票列表，格式如["SSE.600000","SZSE.000001"]
        @filename   要输出的文件名，json格式
        '''
        pass

    def dmpBarsToFile(self, folder:str, codes:list, start_date:datetime=None, end_date:datetime=None, period="day"):
        '''
        将K线导出到指定的目录下的csv文件，文件名格式如SSE.600000_d.csv
        @folder 要输出的文件夹
        @codes  股票列表，格式如["SSE.600000","SZSE.000001"]
        @start_date 开始日期，datetime类型，传None则自动设置为1990-01-01
        @end_date   结束日期，datetime类型，传None则自动设置为当前日期
        @period K线周期，支持day、min1、min5
        '''
        pass

    def dmpAdjFactorsToDB(self, dbHelper:DBHelper, codes:list):
        '''
        将除权因子导出到数据库
        @codes  股票列表，格式如["SSE.600000","SZSE.000001"]
        @dbHelper   数据库辅助模块
        '''
        pass

    def dmpBarsToDB(self, dbHelper:DBHelper, codes:list, start_date:datetime=None, end_date:datetime=None, period:str="day"):
        '''
        将K线导出到数据库
        @dbHelper 数据库辅助模块
        @codes  股票列表，格式如["SSE.600000","SZSE.000001"]
        @start_date 开始日期，datetime类型，传None则自动设置为1990-01-01
        @end_date   结束日期，datetime类型，传None则自动设置为当前日期
        @period K线周期，支持day、min1、min5
        '''
        pass


    def dmpBars(self, codes:list, cb, start_date:datetime=None, end_date:datetime=None, period:str="day"):
        '''
        将K线导出到指定的目录下的csv文件，文件名格式如SSE.600000_d.csv
        @cb     回调函数，格式如cb(exchg:str, code:str, firstBar:POINTER(WTSBarStruct), count:int, period:str)
        @codes  股票列表，格式如["SSE.600000","SZSE.000001"]
        @start_date 开始日期，datetime类型，传None则自动设置为1990-01-01
        @end_date   结束日期，datetime类型，传None则自动设置为当前日期
        @period K线周期，支持day、min1、min5
        '''
        pass