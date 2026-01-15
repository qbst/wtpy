"""
Baostock数据辅助工具模块

本模块提供了从Baostock（证券宝）获取股票数据的接口。
Baostock是一个免费、开源的证券数据平台，提供A股历史行情数据。

主要功能：
1. 获取A股股票代码列表
2. 获取日线和5分钟K线数据
3. 获取复权因子数据
4. 支持将数据导出到文件或数据库

数据源：http://baostock.com/
"""

# 导入数据辅助工具基类
from wtpy.apps.datahelper.DHDefs import BaseDataHelper, DBHelper
# 导入wtpy核心定义
from wtpy.WtCoreDefs import WTSBarStruct
# 导入Baostock库
import baostock as bs
# 导入标准库模块
from datetime import datetime, timedelta  # 日期时间处理
import json                                # JSON数据处理
import os                                  # 操作系统接口
import logging                             # 日志记录

def transCodes(codes:list) -> list:
    ret = list()
    for code in codes:
        items = code.split(".")
        exchg = items[0]
        if exchg == "SSE":
            ret.append("sh."+items[1])
        else:
            ret.append("sz."+items[1])

    return ret

def to_float(v:str, defVal:float = 0) -> float:
    v = v.strip()
    if len(v) == 0:
        return defVal

    try:
        return float(v)
    except:
        return defVal

class DHBaostock(BaseDataHelper):
    """
    Baostock数据辅助工具类
    
    用于从Baostock（证券宝）获取A股股票数据，包括代码列表、K线数据、复权因子等。
    继承自BaseDataHelper，实现了所有必需的数据获取方法。
    """

    def __init__(self):
        BaseDataHelper.__init__(self)
        logging.info("Baostock helper has been created.")
        return

    def auth(self, **kwargs):
        if self.isAuthed:
            return

        bs.login()
        self.isAuthed = True
        logging.info("Baostock has been authorized.")

    def dmpCodeListToFile(self, filename:str, hasIndex:bool=True, hasStock:bool=True):
        stocks = {
            "SSE":{},
            "SZSE":{}
        }


        logging.info("Confirming latest tradingday...")
        rs = bs.query_trade_dates()
        dates = []
        while (rs.error_code == '0') & rs.next():
            row = rs.get_row_data()
            if row[1] == '1':
                dates.append(row[0])
        prevDate = dates[-2]
        
        logging.info(f"Feting all stocks of  latest tradingday: {prevDate}...")
        rs = bs.query_all_stock(day=prevDate)

        print(rs.fields)
        while (rs.error_code == '0') & rs.next():
            row = rs.get_row_data()
            code = row[0]
            name = row[2]
            state = row[1]
            if state != '1' or name=='':
                continue

            rss = bs.query_stock_basic(code)

            sInfo = dict()
            if code[:2] == "sh":
                sInfo["exchg"] = "SSE"
            else:
                sInfo["exchg"] = "SZSE"
            code = code[3:]
            sInfo["code"] = code
            sInfo["name"] = name

            if sInfo["exchg"] == 'SSE':
                if code[0] == '0':
                    sInfo["product"] = 'IDX'   
                elif code[0] == '5':
                    sInfo["product"] = 'ETF' 
                elif code[:4] == '1000':
                    sInfo["product"] = 'ETFO'
                else:
                    sInfo["product"] = 'STK'
            elif sInfo["exchg"] == 'SZSE':
                if code[:3] == '399':
                    sInfo["product"] = 'IDX'   
                elif code[:3] == '159':
                    sInfo["product"] = 'ETF'   
                elif code[:4] == '9000':
                    sInfo["product"] = 'ETFO'
                else:
                    sInfo["product"] = 'STK'
            
            stocks[sInfo["exchg"]][code] = sInfo

        logging.info("Writing code list into file %s..." % (filename))
        f = open(filename, 'w')
        f.write(json.dumps(stocks, sort_keys=True, indent=4, ensure_ascii=False))
        f.close()

    def dmpAdjFactorsToFile(self, codes:list, filename:str):
        codes = transCodes(codes)
        stocks = {
            "SSE":{},
            "SZSE":{}
        }
        count = 0
        length = len(codes)
        for code in codes:
            exchg = code[:2]
            if exchg == 'sh':
                exchg = 'SSE'
            else:
                exchg = 'SZSE'
            count += 1

            stocks[exchg][code[3:]] = list()
            logging.info("Fetching adjust factors of %s(%d/%s)..." % (code, count, length))
            rs = bs.query_adjust_factor(code=code, start_date="1990-01-01")

            if rs.error_code != '0':
                logging.error("Error occured: %s" % (rs.error_msg))
                continue
    
            while rs.next():
                items = rs.get_row_data()
                date = int(items[1].replace("-",""))
                factor = to_float(items[4], 1.0)
                stocks[exchg][code[3:]].append({
                    "date": date,
                    "factor": factor
                })
        
        logging.info("Writing adjust factors into file %s..." % (filename))
        f = open(filename, 'w+')
        f.write(json.dumps(stocks, sort_keys=True, indent=4, ensure_ascii=False))
        f.close()

    def dmpBarsToFile(self, folder:str, codes:list, start_date:datetime=None, end_date:datetime=None, period:str="day"):
        codes = transCodes(codes)

        if start_date is None:
            start_date = datetime(year=1990, month=1, day=1)
        
        if end_date is None:
            end_date = datetime.now()

        start_date = start_date.strftime("%Y-%m-%d")
        end_date = end_date.strftime("%Y-%m-%d")

        freq = ''
        isDay = False
        filetag = ''
        fields = ""
        if period == 'day':
            freq = 'd'
            isDay = True
            filetag = 'd'
            fields = "date,open,high,low,close,volume,amount"
        elif period == "min5":
            freq = '5'
            filetag = 'm5'
            fields = "date,time,open,high,low,close,volume,amount"
        else:
            raise Exception("Baostock has only bars of frequency day and min5")

        count = 0
        length = len(codes)
        for code in codes:
            exchg = code[:2]
            if exchg == 'sh':
                exchg = 'SSE'
            else:
                exchg = 'SZSE'
            count += 1
            
            logging.info("Fetching %s bars of %s(%d/%s)..." % (period, code, count, length))
            rs = bs.query_history_k_data_plus(code=code, fields=fields, start_date=start_date, end_date=end_date, frequency=freq)
            content = "date,time,open,high,low,close,volume,turnover\n"
            if rs.error_code != '0':
                logging.error("Error occured: %s" % (rs.error_msg))
                continue

            while rs.next():
                items = rs.get_row_data().copy()
                if isDay:
                    items.insert(1, "0")
                else:
                    time = items[1][-9:-3]
                    items[1] = time[:2]+":"+time[2:4]+":"+time[4:]
                content += ",".join(items) + "\n"

            filename = "%s.%s_%s.csv" % (exchg, code[3:], filetag)
            filepath = os.path.join(folder, filename)
            logging.info("Writing bars into file %s..." % (filepath))
            f = open(filepath, "w", encoding="utf-8")
            f.write(content)
            f.close()

    def dmpAdjFactorsToDB(self, dbHelper:DBHelper, codes:list):
        codes = transCodes(codes)
        stocks = {
            "SSE":{},
            "SZSE":{}
        }

        count = 0
        length = len(codes)
        for code in codes:
            exchg = code[:2]
            if exchg == 'sh':
                exchg = 'SSE'
            else:
                exchg = 'SZSE'
            count += 1
            
            logging.info("Fetching adjust factors of %s(%d/%s)..." % (code, count, length))
            stocks[exchg][code[3:]] = list()
            rs = bs.query_adjust_factor(code=code, start_date="1990-01-01")

            if rs.error_code != '0':
                logging.info("Error occured: %s" % (rs.error_msg))
                continue
    
            while rs.next():
                items = rs.get_row_data()
                date = int(items[1].replace("-",""))
                factor = to_float(items[4], 1.0)
                stocks[exchg][code[3:]].append({
                    "date": date,
                    "factor": factor
                })
        
        logging.info("Writing adjust factors into database...")
        dbHelper.writeFactors(stocks)

    def dmpBarsToDB(self, dbHelper:DBHelper, codes:list, start_date:datetime=None, end_date:datetime=None, period:str="day"):
        codes = transCodes(codes)

        if start_date is None:
            start_date = datetime(year=1990, month=1, day=1)
        
        if end_date is None:
            end_date = datetime.now()

        start_date = start_date.strftime("%Y-%m-%d")
        end_date = end_date.strftime("%Y-%m-%d")

        freq = ''
        isDay = False
        fields = ""
        if period == 'day':
            freq = 'd'
            isDay = True
            fields = "date,open,high,low,close,volume,amount"
        elif period == "min5":
            freq = '5'
            fields = "date,time,open,high,low,close,volume,amount"
        else:
            raise Exception("Baostock has only bars of frequency day and min5")

        count = 0
        length = len(codes)
        for code in codes:
            exchg = code[:2]
            if exchg == 'sh':
                exchg = 'SSE'
            else:
                exchg = 'SZSE'
            count += 1
            
            logging.info("Fetching %s bars of %s(%d/%s)..." % (period, code, count, length))
            rs = bs.query_history_k_data_plus(code=code, fields=fields, start_date=start_date, end_date=end_date, frequency=freq)
            bars = []
            while (rs.error_code == '0') & rs.next():
                items = rs.get_row_data()
                if isDay:
                    bars.append({
                        "exchange":exchg,
                        "code":code[3:],
                        "date": int(items[0].replace("-","")),
                        "time": 0,
                        "open": to_float(items[1]),
                        "high": to_float(items[2]),
                        "low": to_float(items[3]),
                        "close": to_float(items[4]),
                        "volume": to_float(items[5]),
                        "turnover": to_float(items[6])
                    })
                else:
                    time = int(items[1][-9:-5])
                    bars.append({
                        "exchange":exchg,
                        "code":code[3:],
                        "date": int(items[0].replace("-","")),
                        "time": time,
                        "open": to_float(items[2]),
                        "high": to_float(items[3]),
                        "low": to_float(items[4]),
                        "close": to_float(items[5]),
                        "volume": to_float(items[6]),
                        "turnover": to_float(items[7])
                    })

            logging.info("Writing bars into database...")
            dbHelper.writeBars(bars, period)

    def dmpBars(self, codes:list, cb, start_date:datetime=None, end_date:datetime=None, period:str="day"):
        codes = transCodes(codes)

        if start_date is None:
            start_date = datetime(year=1990, month=1, day=1)
        
        if end_date is None:
            end_date = datetime.now()

        start_date = start_date.strftime("%Y-%m-%d")
        end_date = end_date.strftime("%Y-%m-%d")

        freq = ''
        isDay = False
        fields = ""
        if period == 'day':
            freq = 'd'
            isDay = True
            fields = "date,open,high,low,close,volume,amount"
        elif period == "min5":
            freq = '5'
            fields = "date,time,open,high,low,close,volume,amount"
        else:
            raise Exception("Baostock has only bars of frequency day and min5")

        count = 0
        length = len(codes)
        for code in codes:
            exchg = code[:2]
            if exchg == 'sh':
                exchg = 'SSE'
            else:
                exchg = 'SZSE'
            count += 1
            
            logging.info("Fetching %s bars of %s(%d/%s)..." % (period, code, count, length))
            rs = bs.query_history_k_data_plus(code=code, fields=fields, start_date=start_date, end_date=end_date, frequency=freq)
            bastList = []
            if rs.error_code != '0':
                logging.error("Error occured: %s" % (rs.error_msg))
                continue

            while rs.next():
                items = rs.get_row_data().copy()
                curBar = WTSBarStruct()
                curBar.date = int(items[0].replace("-",""))
                if isDay:
                    curBar.time = 0
                    curBar.open = to_float(items[1])
                    curBar.high = to_float(items[2])
                    curBar.low = to_float(items[3])
                    curBar.close = to_float(items[4])
                    curBar.vol = to_float(items[5].strip())
                    curBar.money = to_float(items[6])
                else:
                    curBar.time = int(items[1][-9:-5]) + (curBar.date-19900000)*10000
                    curBar.open = to_float(items[2])
                    curBar.high = to_float(items[3])
                    curBar.low = to_float(items[4])
                    curBar.close = to_float(items[5])
                    curBar.vol = to_float(items[6])
                    curBar.money = to_float(items[7])
                bastList.append(curBar)
            
            from ctypes import addressof
            BUFFER = WTSBarStruct*len(bastList)
            buffer = BUFFER()
            for i in range(len(bastList)):
                curBar = buffer[i]
                srcBar = bastList[i]
                curBar.date = srcBar.date
                curBar.time = srcBar.time
                curBar.open = srcBar.open
                curBar.high = srcBar.high
                curBar.low = srcBar.low
                curBar.close = srcBar.close
                curBar.vol = srcBar.vol
                curBar.money = srcBar.money
            cb(exchg, code[3:], buffer, len(bastList), period)
                
