"""
主力合约选择器模块 (WtHotPicker)

本模块用于自动识别和切换期货主力合约，支持从交易所官网或本地快照文件获取行情数据，
根据成交量、持仓量等指标自动确定主力合约和次主力合约，并生成换月规则。

主要功能：
1. 从交易所官网（CFFEX、SHFE、DCE、CZCE、INE）拉取当日行情快照
2. 从本地快照文件读取行情数据
3. 根据成交量、持仓量等指标自动识别主力合约和次主力合约
4. 生成主力合约切换规则，支持全量重构和增量更新
5. 支持邮件通知主力合约切换事件

设计逻辑：
- 使用缓存机制避免重复拉取数据
- 支持多种数据源（交易所官网、本地快照文件）
- 针对不同交易所采用不同的主力合约识别算法
- 支持邮件通知功能，及时通知主力合约切换
"""

# 导入标准库模块
import datetime  # 日期时间处理
import time      # 时间相关操作
import json      # JSON数据处理
import os        # 操作系统接口
import logging   # 日志记录

# 导入网络请求相关模块
import urllib.request  # HTTP请求
import io             # 输入输出流
import gzip           # GZIP压缩解压
import xml.dom.minidom  # XML解析
from pyquery import PyQuery as pq  # HTML解析
import re  # 正则表达式

class DayData:
    '''
    每日行情数据类
    
    用于存储单个合约在某个交易日的行情快照数据，包括合约代码、收盘价、成交量、持仓量等信息。
    这些数据用于判断主力合约和次主力合约。
    '''

    def __init__(self):
        """
        初始化每日行情数据对象
        
        初始化所有字段为空值或0，后续通过数据拉取填充。
        """
        self.pid = ''      # 品种代码（如IF、IH、IC等）
        self.month = 0     # 合约月份（如2103表示2021年3月）
        self.code = ''     # 完整合约代码（如IF2103）
        self.close = 0     # 收盘价
        self.volume = 0    # 成交量（单位：手）
        self.hold = 0      # 持仓量（总持仓量，单位：手）

def extractPID(code):
    """
    从合约代码中提取品种代码
    
    合约代码通常由品种代码和月份组成，如"IF2103"中"IF"是品种代码，"2103"是月份。
    本函数通过查找第一个数字字符的位置来分离品种代码和月份。
    
    @param code: 合约代码字符串，如"IF2103"
    @return: 品种代码字符串，如"IF"
    """
    # 遍历合约代码，找到第一个数字字符的位置
    for idx in range(0, len(code)):
        c = code[idx]
        # 如果当前字符是数字，则停止遍历
        if '0' <= c and c <= '9': 
            break
    
    # 返回数字字符之前的部分，即品种代码
    return code[:idx]

def readFileContent(filename):
    """
    读取文件内容
    
    安全地读取文件内容，如果文件不存在则返回空字符串。
    
    @param filename: 文件路径
    @return: 文件内容字符串，如果文件不存在则返回空字符串
    """
    # 检查文件是否存在
    if not os.path.exists(filename):
        return ""
    # 打开文件并读取内容
    f = open(filename, 'r')
    content = f.read()
    f.close()
    return content

def cmp_alg_01(left:DayData, right:DayData):
    """
    主力合约比较算法（算法1）
    
    用于中金所（CFFEX）的主力合约识别，综合考虑月份、持仓量和成交量。
    比较逻辑：
    1. 如果左边合约月份大于右边，且持仓量和成交量都满足条件，则左边优先
    2. 否则右边优先
    
    @param left: 左侧合约的每日行情数据
    @param right: 右侧合约的每日行情数据
    @return: 1表示left优先，-1表示right优先
    """
    # 如果左边合约月份大于右边
    if left.month > right.month:
        # 如果左边持仓量大于右边，且左边成交量大于右边成交量的1/3，则左边优先
        if left.hold > right.hold and left.volume > right.volume/3:
            return 1
        else:
            return -1
    else:
        # 如果左边持仓量小于等于右边，或左边成交量小于等于右边成交量的1/3，则右边优先
        if left.hold <= right.hold or left.volume <= right.volume/3:
            return -1
        else:
            return 1

def countFridays(curDate:datetime.datetime):
    """
    计算截止到当周的周五的天数
    
    用于判断当前日期是当月的第几个周五，这对于中金所（CFFEX）的换月规则很重要。
    中金所股指期货通常在当月第三个周五进行交割，需要根据周五数量判断是否到了换月时间。
    
    @param curDate: 当前日期
    @return: 截止到当周的周五数量（包括当前周）
    """
    # 获取当前日期是星期几（0=周一，4=周五）
    wd = curDate.weekday()
    # 从当月1日开始检查
    checkDate = datetime.datetime(year=curDate.year, month=curDate.month, day=1)
    count = 0
    # 遍历从1日到当前日期的所有日期
    while checkDate < curDate:
        # 如果是周五（weekday()==4），计数加1
        if checkDate.weekday() == 4:
            count += 1
        
        checkDate += datetime.timedelta(days=1)

    # 如果当前日期还没到周五，但本周还没结束，则加上本周的周五
    if wd < 4:
        count += 1

    return count

def httpGet(url, encoding='utf-8'):
    """
    发送HTTP GET请求并返回响应内容
    
    支持gzip压缩内容的自动解压，用于从交易所官网拉取行情数据。
    
    @param url: 请求的URL地址
    @param encoding: 响应内容的编码格式，默认为utf-8
    @return: 响应内容的字符串，如果请求失败则返回空字符串
    """
    # 创建HTTP请求对象
    request = urllib.request.Request(url)
    # 添加请求头，支持gzip压缩
    request.add_header('Accept-encoding', 'gzip')
    # 添加User-Agent，模拟浏览器请求
    request.add_header(
        'User-Agent', 'Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)')
    try:
        # 发送请求
        f = urllib.request.urlopen(request)
        # 检查响应是否使用了gzip压缩
        ec = f.headers.get('Content-Encoding')
        if ec == 'gzip':
            # 读取压缩内容
            cd = f.read()
            # 创建字节流对象
            cs = io.BytesIO(cd)
            # 使用gzip解压
            f = gzip.GzipFile(fileobj=cs)

        # 读取并解码响应内容
        return f.read().decode(encoding)
    except:
        # 如果请求失败，返回空字符串
        return ""

def httpPost(url, datas, encoding='utf-8'):
    """
    发送HTTP POST请求并返回响应内容
    
    支持gzip压缩内容的自动解压，用于向交易所官网提交表单数据并获取响应。
    
    @param url: 请求的URL地址
    @param datas: POST请求的数据字典
    @param encoding: 响应内容的编码格式，默认为utf-8
    @return: 响应内容的字符串，如果请求失败则返回空字符串
    """
    # 设置请求头
    headers = {
        'User-Agent': 'Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)',  # 模拟浏览器
        'Accept-encoding': 'gzip'  # 支持gzip压缩
    }
    # 将数据字典编码为URL格式的字节串
    data = urllib.parse.urlencode(datas).encode('utf-8')
    # 创建POST请求对象
    request = urllib.request.Request(url, data, headers)
    try:
        # 发送请求
        f = urllib.request.urlopen(request)
        # 检查响应是否使用了gzip压缩
        ec = f.headers.get('Content-Encoding')
        if ec == 'gzip':
            # 读取压缩内容
            cd = f.read()
            # 创建字节流对象
            cs = io.BytesIO(cd)
            # 使用gzip解压
            f = gzip.GzipFile(fileobj=cs)

        # 读取并解码响应内容
        return f.read().decode(encoding)
    except:
        # 如果请求失败，返回空字符串
        return ""

class WtCacheMon:
    """
    缓存管理器基类
    
    用于缓存每日行情数据，避免重复拉取。子类需要实现get_cache方法来获取指定交易所和日期的行情数据。
    采用字典结构缓存数据，key为日期字符串（格式：YYYYMMDD），value为交易所代码到行情数据的映射。
    """
    def __init__(self):
        """
        初始化缓存管理器
        
        创建空的缓存字典，用于存储每日行情数据。
        """
        # 每日行情数据缓存，结构：{日期字符串: {交易所代码: {合约代码: DayData对象}}}
        self.day_cache = dict()

    def get_cache(self, exchg, curDT:datetime.datetime):
        """
        获取指定交易所和日期的行情缓存数据（抽象方法）
        
        子类必须实现此方法，用于获取指定交易所和日期的行情数据。
        
        @param exchg: 交易所代码（如CFFEX、SHFE等）
        @param curDT: 指定日期
        @return: 返回该交易所该日期的所有合约行情数据字典，格式：{合约代码: DayData对象}
        """
        pass

class WtCacheMonExchg(WtCacheMon):
    """
    交易所行情缓存器
    
    通过访问交易所官网拉取当日的行情快照，并缓存当日行情数据。
    支持从CFFEX（中金所）、SHFE（上期所）、DCE（大商所）、CZCE（郑商所）、INE（上海国际能源交易中心）
    等交易所官网获取行情数据。
    """

    @staticmethod
    def getCffexData(curDT:datetime.datetime) -> dict:
        """
        读取CFFEX（中金所）指定日期的行情快照
        
        从中国金融期货交易所官网拉取指定日期的所有合约行情数据，包括IF、IH、IC、T、TF、TS等品种。
        数据格式为XML，需要解析XML获取各合约的收盘价、成交量、持仓量等信息。
        
        @param curDT: 指定的日期
        @return: 返回该日期所有合约的行情数据字典，格式：{合约代码: DayData对象}，如果获取失败则返回None
        """
        # 将日期格式化为YYYYMMDD格式的字符串
        dtStr = curDT.strftime('%Y%m%d')
        # 将日期字符串转换为整数
        dtNum = int(dtStr)
        # 构建CFFEX官网的XML数据URL路径，格式：http://www.cffex.com.cn/fzjy/mrhq/YYYY/MM/index.xml
        path = "http://www.cffex.com.cn/fzjy/mrhq/%d/%02d/index.xml" % (dtNum/100, dtNum % 100)
        # 发送HTTP GET请求获取XML内容
        content = httpGet(path)
        # 如果获取失败（内容为空），返回None
        if len(content) == 0:
            return None

        try:
            # 解析XML内容
            dom = xml.dom.minidom.parseString(content)
        except:
            # 如果解析失败，记录日志并返回None
            logging.info("[CFFEX]%s无数据，跳过" % (dtStr))
            return None

        # 获取XML根节点
        root = dom.documentElement
        
        # 存储所有合约的行情数据
        items = {}
        # 获取所有dailydata节点（每个节点代表一个合约的日行情数据）
        days = root.getElementsByTagName("dailydata")
        for day in days:
            # 获取品种代码（如IF、IH、IC等）
            pid = day.getElementsByTagName(
                "productid")[0].firstChild.data.strip()

            # 只处理指定的品种：IF（沪深300）、IH（上证50）、IC（中证500）、T（10年期国债）、TF（5年期国债）、TS（2年期国债）
            if pid not in ["IF","IH","IC","T",'TF','TS']:
                continue

            # 创建每日行情数据对象
            item = DayData()
            # 获取合约代码（如IF2103）
            item.code = day.getElementsByTagName("instrumentid")[
                0].firstChild.data.strip()
            # 设置品种代码
            item.pid = pid
            # 获取持仓量（总持仓量）
            item.hold = float(day.getElementsByTagName(
                "openinterest")[0].firstChild.data)
            # 获取收盘价
            item.close = float(day.getElementsByTagName(
                "closeprice")[0].firstChild.data)
            # 获取成交量
            item.volume = int(day.getElementsByTagName(
                "volume")[0].firstChild.data)

            # 从合约代码中提取月份（去掉品种代码部分）
            item.month = item.code[len(item.pid):]

            # 将合约行情数据存入字典，以合约代码为key
            items[item.code] = item
        return items

    @staticmethod
    def getShfeData(curDT:datetime.datetime) -> dict:
        '''
        读取SHFE指定日期的行情快照

        @curDT  指定的日期
        '''

        dtStr = curDT.strftime('%Y%m%d')
        content = httpGet("http://www.shfe.com.cn/data/dailydata/kx/kx%s.dat" % (dtStr))
        if len(content) == 0:
            return None
        
        items = {}
        root = json.loads(content)
        for day in root['o_curinstrument']:
            pid = day['PRODUCTID'].strip().rstrip('_f')
            dm = day['DELIVERYMONTH']
            if len(str(day['CLOSEPRICE']).strip()) == 0:
                continue

            code = pid + dm

            item = DayData()
            item.pid = pid
            item.code = code
            if day['OPENINTEREST'] != '':
                item.hold = int(day['OPENINTEREST'])
            else:
                item.hold = 0

            if day['VOLUME'] != '':
                item.volume = int(day['VOLUME'])
            item.close = float(day["CLOSEPRICE"])
            item.month = item.code[len(item.pid):]
            items[code] = item
        return items

    @staticmethod
    def getCzceData(curDT:datetime.datetime) -> dict:
        '''
        读取CZCE指定日期的行情快照

        @curDT  指定的日期
        '''

        dtStr = curDT.strftime('%Y%m%d')
        url = 'http://www.czce.com.cn/cn/DFSStaticFiles/Future/%s/%s/FutureDataDaily.htm' % (dtStr[0:4], dtStr)
        try:
            html = httpGet(url).strip()
        except urllib.error.HTTPError as httperror:
            print(httperror)
            return None

        if len(html) == 0:
            return None

        dataitems = {}
        doc = pq(html)
        # print(doc(#senfe .table  table))
        items = doc('#tab1')
        # 去掉第一行标题
        items.remove('tr.tr0')
        # 获取tr   items.find('tr')
        lis = items('tbody>tr')
        # print(lis)
        # tr行数
        trcount = len(lis)
        # 遍历行
        for tr in range(0, trcount-1):
            item = DayData()
            tdlis = doc(lis[tr])('td')

            item.code = doc(tdlis[0]).text()
            ay = re.compile('[A-Za-z]+').findall(item.code)
            if len(ay) == 0:
                continue

            item.pid = ay[0]    

            close = doc(tdlis[5]).text()
            if close != '':
                item.close = float(close.replace(",",""))

            volume = doc(tdlis[9]).text()
            if volume != '':
                item.volume = int(volume.replace(",",""))

            hold = doc(tdlis[10]).text()
            if hold != '':
                item.hold = int(hold.replace(",",""))

            item.month = item.code[len(item.pid):]
            # 这个逻辑是有点问题的，但是没好的办法
            # 因为郑商所只有3位数字，必须自动补全，不然后面处理会有问题
            # By Wesley @ 2021.12.15
            if int(item.month[0]) < 5:
                item.month = "2" + item.month
            else:
                item.month = "1" + item.month

            dataitems[item.code] = item
        # print(dataitems)
        return dataitems

    @staticmethod
    def getDceData(curDT:datetime.datetime) -> dict:
        '''
        读取DCE指定日期的行情快照

        @curDT  指定的日期
        '''

        pname_map = {
            "聚乙烯": "l",
            "鸡蛋": "jd",
            "焦煤": "jm",
            "豆二": "b",
            "胶合板": "bb",
            "玉米": "c",
            "豆粕": "m",
            "棕榈油": "p",
            "玉米淀粉": "cs",
            "纤维板": "fb",
            "铁矿石": "i",
            "焦炭": "j",
            "豆一": "a",
            "聚丙烯": "pp",
            "聚氯乙烯": "v",
            "豆油": "y",
            "乙二醇":"eg",
            "粳米":"rr",
            "苯乙烯":"eb",
            "液化石油气":"pg",
            "生猪":"lh"
        }

        url = 'http://www.dce.com.cn/publicweb/quotesdata/dayQuotesCh.html'
        try:
            data = {}
            data['dayQuotes.variety'] = 'all'
            data['dayQuotes.trade_type'] = 0
            data['year'] = curDT.year
            data['month'] = curDT.month - 1
            data['day'] = curDT.day
            html = httpPost(url, data)
        except urllib.error.HTTPError as httperror:
            print(httperror)
            return None

        dataitems = {}
        doc = pq(html)
        items = doc('.dataArea')  # doc('#printData')
        # # 获取tr   items.find('tr')
        lis = items('tr')
        trcount = len(lis)
        # 遍历行
        for tr in range(1, trcount):

            tdlis = doc(lis[tr])('td')
            # 商品名称
            pzname = doc(tdlis[0]).text()
            if pzname not in pname_map:
                if "小计" not in pzname and "总计" not in pzname:
                    logging.error("未知品种:" + pzname)
                continue

            # 交割月份
            item = DayData()
            item.pid = pname_map[pzname]
            if item.pid in doc(tdlis[1]).text():
                item.code = doc(tdlis[1]).text()
            else:
                item.code = item.pid + doc(tdlis[1]).text()
            # 收盘价
            spj = doc(tdlis[5]).text()
            item.close = float(spj if spj != '' else 0)
            # 成交量
            item.volume = int(doc(tdlis[10]).text())
            # 持仓量
            item.hold = int(doc(tdlis[11]).text())
            item.month = item.code[len(item.pid):]
            dataitems[item.code] = item

        return dataitems

    @staticmethod
    def getIneData(curDT:datetime.datetime) -> dict:
        '''
        读取INE指定日期的行情快照

        @curDT  指定的日期
        '''
        dtStr = curDT.strftime('%Y%m%d')
        content = httpGet("http://www.ine.cn/data/dailydata/kx/kx%s.dat" % (dtStr))
        if len(content) == 0:
            return None

        items = {}
        root = json.loads(content)
        for day in root['o_curinstrument']:
            pid = day['PRODUCTID'].strip().rstrip('_f')
            dm = day['DELIVERYMONTH']
            if pid != 'sc' or dm == '' or dm == '小计':
                continue
            item = DayData()
            item.pid = pid
            item.code = pid + dm
            item.hold = int(day['OPENINTEREST'])
            item.close = float(day['CLOSEPRICE'])
            item.volume = int(day['VOLUME']) if day['VOLUME']!='' else 0
            item.month = item.code[len(item.pid):]
            items[item.code] = item
        return items


    def cache_by_date(self, exchg:str, curDT:datetime.datetime):
        '''
        缓存指定日期指定交易所的行数据

        @exchg  交易所代码
        @curDT  指定日期
        '''
        dtStr = curDT.strftime('%Y%m%d')

        if dtStr not in self.day_cache:
            self.day_cache[dtStr] = dict()

        cacheItem = self.day_cache[dtStr]
        if exchg == 'CFFEX':
            cacheItem[exchg] = WtCacheMonExchg.getCffexData(curDT)
        elif exchg  == 'SHFE':
            cacheItem[exchg] = WtCacheMonExchg.getShfeData(curDT)
        elif exchg  == 'DCE':
            cacheItem[exchg] = WtCacheMonExchg.getDceData(curDT)
        elif exchg  == 'CZCE':
            cacheItem[exchg] = WtCacheMonExchg.getCzceData(curDT)
        elif exchg  == 'INE':
            cacheItem[exchg] = WtCacheMonExchg.getIneData(curDT)
        else:
            raise Exception("未知交易所代码" + exchg)

    def get_cache(self, exchg:str, curDT:datetime.datetime):
        '''
        获取指定日期的某个交易所合约的快照数据

        @exchg  交易所代码
        @curDT  指定日期
        '''
        dtStr = curDT.strftime('%Y%m%d')
        if dtStr not in self.day_cache or exchg not in self.day_cache[dtStr]:
            self.cache_by_date(exchg, curDT)

        if dtStr not in self.day_cache:
            return None

        if exchg not in self.day_cache[dtStr]:
            return None
        return self.day_cache[dtStr][exchg]

class WtCacheMonSS(WtCacheMon):
    '''
    快照缓存管理器
    通过读取wtpy的datakit当日生成的快照文件，缓存当日行情数据
    一般目录为"数据存储目录/his/snapshots/xxxxxxx.csv"
    '''

    def __init__(self, snapshot_path:str):
        WtCacheMon.__init__(self)
        self.snapshot_path = snapshot_path

    def cache_snapshot(self, curDT:datetime):
        '''
        缓存指定日期的快照数据

        @curDT  指定的日期
        '''
        dtStr = curDT.strftime('%Y%m%d')

        filename = "%s%s.csv" % (self.snapshot_path, dtStr)
        content = readFileContent(filename)
        lines = content.split("\n")

        if dtStr not in self.day_cache:
            self.day_cache[dtStr] = dict()

        cacheItem = self.day_cache[dtStr]
        for idx in range(1, len(lines)):
            line = lines[idx]
            if len(line) == 0:
                break
            items = line.split(",")
            
            exchg = items[1]
            if exchg not in cacheItem:
                cacheItem[exchg] = dict()

            day = DayData()
            day.pid = extractPID(items[2])
            day.code = items[2]
            # 收盘价
            day.close = float(items[6])
            # 成交量
            day.volume = float(items[8])
            # 持仓量
            day.hold = float(items[10])
            day.month = day.code[len(day.pid):]
            if len(day.month) == 3:
                if day.month[0] >= '0' and day.month[0] <= '5':
                    day.month = "2" + day.month
                else:
                    day.month = "1" + day.month
            cacheItem[exchg][day.code] = day

    def get_cache(self, exchg, curDT:datetime):
        '''
        获取指定日期的某个交易所合约的快照数据

        @exchg  交易所代码
        @curDT  指定日期
        '''

        dtStr = curDT.strftime('%Y%m%d')
        if dtStr not in self.day_cache:
            self.cache_snapshot(curDT)

        if dtStr not in self.day_cache:
            return None

        if exchg not in self.day_cache[dtStr]:
            return None
        return self.day_cache[dtStr][exchg]

class WtMailNotifier:
    '''
    邮件通知器
    '''
    def __init__(self, user:str, pwd:str, sender:str=None, host:str="smtp.exmail.qq.com", port=465, isSSL:bool = True):
        self.user = user
        self.pwd = pwd
        self.sender = sender if sender is not None else "WtHotNotifier<%s>" % (user)
        self.receivers = list()

        self.mail_host = host
        self.mail_port = port
        self.mail_ssl = isSSL

    def add_receiver(self, name:str, addr:str):
        '''
        添加收件人

        @name   收件人姓名
        @addr   收件人邮箱地址
        '''
        self.receivers.append({
            "name":name,
            "addr":addr
        })

    def notify(self, hot_changes:dict, sec_changes:dict, nextDT:datetime.datetime, hotFile:str, hotMap:str, secFile:str, secMap:str):
        '''
        通知主力切换事件

        @hot_changes    当日主力切换的规则列表
        @sec_changes    当日次主力切换的规则列表
        @nextDT         生效日期
        @hotFile        主力规则文件
        @hotMap         主力映射文件
        '''
        dtStr = nextDT.strftime('%Y.%m.%d')
    
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.mime.application import MIMEApplication
        from email.header import Header

        sender = self.sender
        receivers = self.receivers

        content = ''
        for exchg in hot_changes:
            for pid in hot_changes[exchg]:
                item = hot_changes[exchg][pid][-1]
                content +=  '品种%s.%s的主力合约已切换,下个交易日(%s)生效, %s -> %s\n' % (exchg, pid, dtStr, item["from"], item["to"])

        content += '\n'
        for exchg in sec_changes:
            for pid in sec_changes[exchg]:
                item = sec_changes[exchg][pid][-1]
                content +=  '品种%s.%s的次主力合约已切换,下个交易日(%s)生效, %s -> %s\n' % (exchg, pid, dtStr, item["from"], item["to"])

        msg_mp = MIMEMultipart()
        msg_mp['From'] = sender  # 发送者          
        
        subject = '主力合约换月邮件<%s>' % (dtStr)
        msg_mp['Subject'] = Header(subject, 'utf-8')

        content = MIMEText(content, 'plain', 'utf-8')
        msg_mp.attach(content)

        xlspart = MIMEApplication(open(hotFile,'rb').read())
        xlspart["Content-Type"] = 'application/octet-stream'
        xlspart.add_header('Content-Disposition','attachment', filename=os.path.basename(hotFile))
        msg_mp.attach(xlspart)

        xlspart = MIMEApplication(open(hotMap,'rb').read())
        xlspart["Content-Type"] = 'application/octet-stream'
        xlspart.add_header('Content-Disposition','attachment', filename=os.path.basename(hotMap))
        msg_mp.attach(xlspart)

        xlspart = MIMEApplication(open(secFile,'rb').read())
        xlspart["Content-Type"] = 'application/octet-stream'
        xlspart.add_header('Content-Disposition','attachment', filename=os.path.basename(secFile))
        msg_mp.attach(xlspart)

        xlspart = MIMEApplication(open(secMap,'rb').read())
        xlspart["Content-Type"] = 'application/octet-stream'
        xlspart.add_header('Content-Disposition','attachment', filename=os.path.basename(secMap))
        msg_mp.attach(xlspart)

        if self.mail_ssl:
            smtpObj = smtplib.SMTP_SSL(self.mail_host, self.mail_port)
        else:
            smtpObj = smtplib.SMTP(self.mail_host, self.mail_port)

        try:
            smtpObj.ehlo()
            smtpObj.login(self.user, self.pwd) 
            logging.info("%s 登录成功 %s:%d", self.user, self.mail_host, self.mail_port)
        except smtplib.SMTPException as ex:
            logging.error("邮箱初始化失败：{}".format(ex))

        for item in receivers:
            to = "%s<%s>" % (item["name"], item["addr"])
            msg_mp['To'] =  Header(to, 'utf-8')    # 接收者
            try:
                smtpObj.sendmail(sender, item["addr"], msg_mp.as_string())
                logging.info("邮件发送失败，收件人: %s", to)
            except smtplib.SMTPException as ex:
                logging.error("邮件发送失败，收件人：{}, {}".format(to, ex))

class WtHotPicker:
    """
    主力合约选择器类
    
    用于自动识别和切换期货主力合约和次主力合约。支持从多个交易所获取行情数据，
    根据成交量、持仓量等指标自动确定主力合约，并生成换月规则文件。
    支持全量重构和增量更新两种模式。
    """
    def __init__(self, markerFile:str = "./marker.json", hotFile:str = "../Common/hots.json", secFile:str = None):
        """
        初始化主力合约选择器
        
        @param markerFile: 标记文件路径，用于记录上次更新的日期
        @param hotFile: 主力合约规则文件路径，存储主力合约切换规则
        @param secFile: 次主力合约规则文件路径，存储次主力合约切换规则，如果为None则不处理次主力
        """
        # 标记文件路径，记录上次更新的日期
        self.marker_file = markerFile
        # 主力合约规则文件路径
        self.hot_file = hotFile
        # 次主力合约规则文件路径
        self.sec_file = secFile

        # 邮件通知器，用于发送主力合约切换通知
        self.mail_notifier:WtMailNotifier = None
        # 行情数据缓存监控器，用于获取每日行情数据
        self.cache_monitor:WtCacheMon = None

        # 当前主力合约映射，格式：{交易所代码: {品种代码: 合约代码}}
        self.current_hots = None
        # 当前次主力合约映射，格式：{交易所代码: {品种代码: 合约代码}}
        self.current_secs = None

    def set_cacher(self, cacher:WtCacheMon):
        """
        设置日行情缓存器
        
        设置用于获取每日行情数据的缓存监控器，可以是WtCacheMonExchg（从交易所官网获取）
        或WtCacheMonSS（从本地快照文件获取）。
        
        @param cacher: 行情数据缓存监控器对象
        """
        self.cache_monitor = cacher
        
    def set_mail_notifier(self, notifier:WtMailNotifier):
        """
        设置邮件通知器
        
        设置用于发送主力合约切换通知的邮件通知器。
        
        @param notifier: 邮件通知器对象
        """
        self.mail_notifier = notifier

    def pick_exchg_hots(self, exchg:str, beginDT:datetime.datetime, endDT:datetime.datetime, alg:int = 0):
        '''
        确定指定市场的主力合约

        @exchg          交易所代码
        @beginDT        开始日期
        @endDT          截止日期
        @alg            切换规则算法，0-除中金所外，按成交量确定，1-中金所，按照成交量和总持共同确定
        '''

        cacheMon = self.cache_monitor
        current_hots = self.current_hots
        current_secs = self.current_secs

        if exchg not in current_hots:
            current_hots[exchg] = dict()

        if exchg not in current_secs:
            current_secs[exchg] = dict()

        lastHots = current_hots[exchg]
        lastSecs = current_secs[exchg]

        hot_switches = {}
        sec_switches = {}

        curDT = beginDT

        while curDT <= endDT:
            hots = {}
            seconds = {}
            logging.info("[%s]开始拉取%s数据" % (exchg, curDT.strftime('%Y%m%d')))
            items = cacheMon.get_cache(exchg, curDT)
            if items is not None:
                wd = curDT.weekday()
                fri_cnt = countFridays(curDT)
                cur_month = curDT.strftime('%Y%m')[2:]
                next_month = int(cur_month)+1
                if next_month % 100 == 13:
                    next_month = str(int(cur_month[:2])+1)+"01"
                else:
                    next_month = str(next_month)

                items_by_pid = dict()
                for code in items:
                    item = items[code]
                    pid = item.pid

                    if pid not in items_by_pid:
                        items_by_pid[pid] = list()

                    items_by_pid[pid].append(item)

                for pid in items_by_pid:
                    ay = items_by_pid[pid]
                    if alg == 1:
                        #ay.sort(key=functools.cmp_to_key(cmp_alg_01)) #按总持排序
                        ay.sort(key=lambda x : x.volume) #按成交量
                    elif alg == 0:
                        ay.sort(key=lambda x : x.hold) #按总持
                        
                    if len(ay) > 1:
                        hot = ay[-1]
                        sec = ay[-2]
                        #中金所算法，如果是当月第三个周三，并且主力合约月份小于次主力合约月份，
                        #说明没有根据数据自动换月，强制进行换月
                        if alg == 1 and wd == 2 and fri_cnt == 3 and hot.month==cur_month:
                            for item in ay:
                                if item.month == next_month:
                                    hot = item
                                    break

                        #如果主力合约月份大于等于次主力合约，则次主力递延一位
                        if hot.month >= sec.month and len(ay)>=3:
                            sec = ay[-3]
     
                        for i in range(-2,-len(ay),-1):
                            sec = ay[i]
                            #次主力合约月份大于等于次主力合约才可以
                            if hot.month < sec.month:
                                break
                        if sec is not None and hot.month < sec.month:
                            hots[pid] = hot.code
                            seconds[pid] = sec.code
                    else:
                        # 如果这一天只有一个合约的信息，就没办法实现同时跟换主次月，跳过这一天，否则会出现主力换月，次主力没有换月的情况，导致某一天的主力次主力是同一个合约
                        continue
                    
                # 生成换月表
                for key in hots.keys():
                    nextDT = curDT + datetime.timedelta(days=1)
                    if key not in lastHots:
                        item = {}
                        item["date"] = int(curDT.strftime('%Y%m%d'))
                        item["from"] = ""
                        item["to"] = hots[key]
                        item["oldclose"] = 0.0
                        item["newclose"] = items[hots[key]].close
                        hot_switches[key] = [item]
                        lastHots[key] = hots[key]
                        logging.info("[%s]品种%s主力确认, 确认日期: %s, %s", exchg,key, nextDT.strftime('%Y%m%d'), hots[key])
                    else:
                        oldcode = lastHots[key]
                        newcode = hots[key]
                        oldItem = None
                        if oldcode in items:
                            oldItem = items[oldcode]
                        newItem = items[newcode]
                        if oldItem is None or newItem.month > oldItem.month:
                            item = {}
                            item["date"] = int(nextDT.strftime('%Y%m%d'))
                            item["from"] = oldcode
                            item["to"] = newcode
                            if oldcode in items:
                                item["oldclose"] = items[oldcode].close
                            else:
                                item["oldclose"] = 0.0
                                item["date"] = int(curDT.strftime('%Y%m%d'))
                            item["newclose"] = items[newcode].close
                            if key not in hot_switches:
                                hot_switches[key] = list()
                            hot_switches[key].append(item)
                            logging.info("[%s]品种%s主力切换 切换日期: %s，%s -> %s", exchg, key, nextDT.strftime('%Y%m%d'), lastHots[key], hots[key])
                            lastHots[key] = hots[key]

                for key in seconds.keys():
                    nextDT = curDT + datetime.timedelta(days=1)
                    if key not in lastSecs:
                        item = {}
                        item["date"] = int(curDT.strftime('%Y%m%d'))
                        item["from"] = ""
                        item["to"] = seconds[key]
                        item["oldclose"] = 0.0
                        item["newclose"] = items[seconds[key]].close
                        sec_switches[key] = [item]
                        lastSecs[key] = seconds[key]
                        logging.info("[%s]品种%s次主力确认, 确认日期: %s, %s", exchg,key, nextDT.strftime('%Y%m%d'), seconds[key])
                    else:
                        oldcode = lastSecs[key]
                        newcode = seconds[key]
                        oldItem = None
                        if oldcode in items:
                            oldItem = items[oldcode]
                        newItem = items[newcode]
                        if oldItem is None or newItem.month > oldItem.month:
                            item = {}
                            item["date"] = int(nextDT.strftime('%Y%m%d'))
                            item["from"] = oldcode
                            item["to"] = newcode
                            if oldcode in items:
                                item["oldclose"] = items[oldcode].close
                            else:
                                item["oldclose"] = 0.0
                                item["date"] = int(curDT.strftime('%Y%m%d'))
                            item["newclose"] = items[newcode].close
                            if key not in sec_switches:
                                sec_switches[key] = list()
                            sec_switches[key].append(item)
                            logging.info("[%s]品种%s次主力切换 切换日期: %s，%s -> %s", exchg, key, nextDT.strftime('%Y%m%d'), lastSecs[key], seconds[key])
                            lastSecs[key] = seconds[key]
            # 日期递增
            curDT = curDT + datetime.timedelta(days=1)
        return hot_switches,sec_switches
    
    def merge_switch_list(self, total, exchg, switch_list):
        '''
        合并主力切换规则
        
        @total          已有的全部切换规则
        @exchg          交易所代码
        @switcg_list    新的切换规则
        '''
        if exchg not in total:
            total[exchg] = switch_list
            logging.info("[%s]全市场主力切换规则重构" % (exchg))
            return True, total
        
        bChanged = False
        for pid in switch_list:
            if pid not in total[exchg]:
                total[exchg][pid] = switch_list[pid]
                logging.info("[%s]品种%s主力切换规则重构" % (exchg, pid))
                bChanged = True
            else:
                total[exchg][pid].extend(switch_list[pid])
                logging.info("[%s]品种%s主力切换规则追加%d条" % (exchg, pid, len(switch_list[pid])))
                bChanged = True
        return bChanged, total

    def execute_rebuild(self, beginDate:datetime.datetime = None, endDate:datetime.datetime = None, exchanges = ["CFFEX", "SHFE", "CZCE", "DCE", "INE"], wait=False):
        '''
        重构全部的主力切换规则
        不依赖现有数据，全部重新确定主力合约的切换规则

        @beginDate  开始日期
        @endDate    截止日期
        @exchanges  要重构的交易所列表
        @wait       每个日期切换是否等待，等待时间1s，主要针对从交易所官网拉取，防止被拉黑名单
        '''
        if endDate is None:
            endDate = datetime.datetime.now()

        if beginDate is None:
            beginDate = datetime.datetime.strptime("2016-01-01", '%Y-%m-%d')
        
        total_hots = dict()
        total_secs = dict()

        self.current_hots = dict()
        self.current_secs = dict()

        for exchg in exchanges:
            self.current_hots[exchg] = dict()
            self.current_secs[exchg] = dict()
        
        hot_changes = dict()
        sec_changes = dict()
        curDate = beginDate
        while curDate <= endDate:
            if wait:
                time.sleep(1)
            for exchg in exchanges:
                alg = 1 if exchg=='CFFEX' else 0    # 中金所的换月算法和其他交易所不同
                hotRules,secRules = self.pick_exchg_hots(exchg, curDate, curDate, alg=alg)

                if len(hotRules.keys()) > 0:
                    hasChange,total_hots = self.merge_switch_list(total_hots, exchg, hotRules)

                    if exchg not in hot_changes:
                        hot_changes[exchg] = dict()
                    hot_changes[exchg].update(hotRules)

                if len(secRules.keys()) > 0:
                    hasChange,total_secs = self.merge_switch_list(total_secs, exchg, secRules)

                    if exchg not in sec_changes:
                        sec_changes[exchg] = dict()
                    sec_changes[exchg].update(secRules)

            curDate = curDate + datetime.timedelta(days=1)

        #日期标记要保存
        marker = dict()
        marker["date"] = int(endDate.strftime('%Y%m%d'))
        output = open(self.marker_file, 'w')
        output.write(json.dumps(marker, sort_keys=True, indent = 4))
        output.close()
        
        logging.info("主力切换规则已更新")

        output = open(self.hot_file, 'w')
        output.write(json.dumps(total_hots, sort_keys=True, indent = 4))
        output.close()

        if self.sec_file is not None:
            output = open(self.sec_file, 'w')
            output.write(json.dumps(total_secs, sort_keys=True, indent = 4))
            output.close()

        output = open("hotmap.json", 'w')
        output.write(json.dumps(self.current_hots, sort_keys=True, indent = 4))
        output.close()

        output = open("secmap.json", 'w')
        output.write(json.dumps(self.current_secs, sort_keys=True, indent = 4))
        output.close()

        if self.mail_notifier is not None:
            self.mail_notifier.notify(hot_changes, sec_changes, endDate, hotFile, "hotmap.json", secFile, "secmap.json")

        return total_hots,total_secs
  
    def execute_increment(self, endDate:datetime.datetime = None, exchanges = ["CFFEX", "SHFE", "CZCE", "DCE", "INE"]):
        '''
        增量更新主力切换规则
        会自动加载marker.json取得上次更新的日期，并读取hots.json确定当前的映射规则

        @endDate    截止日期
        @exchanges  要重构的交易所列表
        '''

        if endDate is None:
            endDate = datetime.datetime.now()

        markerFile = self.marker_file
        hotFile = self.hot_file
        secFile = self.sec_file

        marker = {"date":"0"}
        c = readFileContent(markerFile)
        if len(c) > 0:
            marker = json.loads(c)

        c = readFileContent(hotFile)
        total_hots = dict()
        if len(c) > 0:
            total_hots = json.loads(c)
        else:
            marker["date"] = "0"

        c = readFileContent(secFile)
        total_secs = dict()
        if len(c) > 0:
            total_secs = json.loads(c)
        else:
            marker["date"] = "0"

        lastDate = str(marker["date"])
        if lastDate >= endDate.strftime('%Y%m%d'):
            logging.info("上次更新日期%s大于结束日期%s，退出更新" % (lastDate, endDate.strftime('%Y%m%d')))
            exit()
        elif lastDate != "0":
            beginDT = datetime.datetime.strptime(lastDate, "%Y%m%d") + datetime.timedelta(days=1)
        else:
            beginDT = datetime.datetime.strptime("2016-01-01", '%Y-%m-%d')
        
        self.current_hots = dict()
        self.current_secs = dict()

        for exchg in total_hots:
            if exchg not in self.current_hots:
                self.current_hots[exchg] = dict()

            for pid in total_hots[exchg]:
                ay = total_hots[exchg][pid]
                self.current_hots[exchg][pid] = ay[-1]["to"]

        for exchg in total_secs:
            if exchg not in self.current_secs:
                self.current_secs[exchg] = dict()

            for pid in total_secs[exchg]:
                ay = total_secs[exchg][pid]
                self.current_secs[exchg][pid] = ay[-1]["to"]
        
        bChanged = False
        hot_changes = dict()
        sec_changes = dict()
        for exchg in exchanges:
            logging.info("[%s]开始分析主力换月数据" % exchg)
            alg = 1 if exchg=='CFFEX' else 0    # 中金所的换月算法和其他交易所不同
            hotRules,secRules = self.pick_exchg_hots(exchg, beginDT, endDate, alg=alg)

            if len(hotRules.keys()) > 0:
                hasChange,total_hots = self.merge_switch_list(total_hots, exchg, hotRules)
                bChanged  = bChanged or hasChange
                hot_changes[exchg] = hotRules

            if len(secRules.keys()) > 0:
                hasChange,total_secs = self.merge_switch_list(total_secs, exchg, secRules)
                bChanged  = bChanged or hasChange
                sec_changes[exchg] = secRules


        #日期标记要保存
        marker = dict()
        marker["date"] = int(endDate.strftime('%Y%m%d'))
        output = open(markerFile, 'w')
        output.write(json.dumps(marker, sort_keys=True, indent = 4))
        output.close()
        
        if bChanged:
            logging.info("主力切换规则已更新")

            output = open(hotFile, 'w')
            output.write(json.dumps(total_hots, sort_keys=True, indent = 4))
            output.close()

            output = open(secFile, 'w')
            output.write(json.dumps(total_secs, sort_keys=True, indent = 4))
            output.close()

            output = open("hotmap.json", 'w')
            output.write(json.dumps(self.current_hots, sort_keys=True, indent = 4))
            output.close()

            output = open("secmap.json", 'w')
            output.write(json.dumps(self.current_secs, sort_keys=True, indent = 4))
            output.close()

            if self.mail_notifier is not None:
                self.mail_notifier.notify(hot_changes, sec_changes, endDate, hotFile, "hotmap.json", secFile, "secmap.json")
        else:
            logging.info("主力切换规则未更新，不保存数据")
