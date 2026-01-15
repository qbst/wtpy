"""
交易时段管理模块

本模块负责管理交易时段（Session）信息，包括交易时间段的定义、时间转换等功能。
交易时段定义了合约的交易时间，包括集合竞价时间和多个交易时间段。
支持时间偏移（offset）功能，可以处理跨日交易等特殊情况。

主要功能：
1. SectionInfo：交易时间段信息类，存储单个时间段的开始和结束时间
2. SessionInfo：交易时段信息类，存储完整的交易时段配置，包括集合竞价和多个交易时间段
3. SessionMgr：交易时段管理器，负责加载和管理所有交易时段配置
"""

# 导入数学计算模块
import math
# 导入JSON处理模块
import json
# 导入YAML处理模块
import yaml
# 导入字符编码检测模块
import chardet

class SectionInfo:
    """
    交易时间段信息类
    
    存储单个交易时间段的开始和结束时间。
    一个交易时段（Session）可以包含多个交易时间段（Section），例如：上午段、下午段。
    """

    def __init__(self):
        """
        构造函数
        
        初始化交易时间段信息，设置开始和结束时间。
        """
        # 开始时间，格式：HHMM，例如：900表示9:00
        self.stime = 0
        # 结束时间，格式：HHMM，例如：1130表示11:30
        self.etime = 0

class SessionInfo:
    """
    交易时段信息类
    
    存储完整的交易时段配置，包括时段ID、名称、集合竞价时间、多个交易时间段等。
    支持时间偏移（offset）功能，可以处理跨日交易等特殊情况。
    """

    def __init__(self):
        """
        构造函数
        
        初始化交易时段信息，设置所有属性为默认值。
        """
        # 时段ID，用于唯一标识该交易时段
        self.id = ""
        # 时段名称，例如：TRADING、NIGHT等
        self.name = ""
        # 集合竞价时间段信息
        self.auction = SectionInfo()
        # 交易时间段列表，每个元素是一个SectionInfo对象
        self.sections = list()
        # 时间偏移量（分钟），用于处理跨日交易等情况
        self.offset = 0
        # 总交易分钟数，缓存值，避免重复计算
        self.totalMins = 0

    def toString(self):
        """
        将SessionInfo转换成JSON字符串
        
        将交易时段信息序列化为JSON格式的字符串，便于保存或传输。
        
        @return: 返回JSON格式的字符串
        """
        # 创建字典对象存储时段信息
        obj = dict()
        # 设置时段名称
        obj["name"] = self.name
        # 设置时间偏移量
        obj["offset"] = self.offset
        # 设置集合竞价时间段，转换为原始时间格式
        obj["auction"] = {
            "from": self.originalTime(self.auction.stime),
            "to": self.originalTime(self.auction.etime)
        }

        # 设置交易时间段列表
        obj["sections"] = list()
        # 遍历所有交易时间段
        for secInfo in self.sections:
            # 将每个时间段转换为原始时间格式并添加到列表
            obj["sections"].append({
                "from": self.originalTime(secInfo.stime),
                "to": self.originalTime(secInfo.etime)
            })

        # 将字典转换为JSON字符串并返回
        return json.dumps(obj, ensure_ascii=True)


    def offsetTime(self, rawTime:int):
        """
        将原始时间转换为偏移后的时间
        
        根据时间偏移量（offset）调整时间，用于处理跨日交易等情况。
        例如：如果offset为-60（向前偏移60分钟），则900会变成800。
        
        @rawTime: 原始时间，格式：HHMM，例如：900表示9:00
        @return: 偏移后的时间，格式：HHMM
        """
        # 将时间转换为分钟数：小时*60 + 分钟
        curMinute = math.floor(rawTime/100)*60 + rawTime%100
        # 加上偏移量
        curMinute += self.offset
        # 处理跨日情况：如果超过1440分钟（24小时），则减去1440
        if curMinute >= 1440:
            curMinute -= 1440
        # 处理跨日情况：如果小于0，则加上1440
        elif curMinute < 0:
            curMinute += 1440
        
        # 将分钟数转换回HHMM格式
        return math.floor(curMinute/60)*100 + curMinute%60

    def originalTime(self, offTime:int):
        """
        将偏移后的时间转换回原始时间
        
        根据时间偏移量（offset）反向调整时间，恢复为原始时间。
        这是offsetTime的逆操作。
        
        @offTime: 偏移后的时间，格式：HHMM
        @return: 原始时间，格式：HHMM
        """
        # 将时间转换为分钟数：小时*60 + 分钟
        curMinute = math.floor(offTime/100)*60 + offTime%100
        # 减去偏移量（反向操作）
        curMinute -= self.offset
        # 处理跨日情况：如果超过1440分钟（24小时），则减去1440
        if curMinute >= 1440:
            curMinute -= 1440
        # 处理跨日情况：如果小于0，则加上1440
        elif curMinute < 0:
            curMinute += 1440
        
        # 将分钟数转换回HHMM格式
        return math.floor(curMinute/60)*100 + curMinute%60

    def getOpenTime(self, bOffset:bool = False):
        """
        获取开盘时间
        
        返回第一个交易时间段的开始时间。
        
        @bOffset: 是否返回偏移后的时间，False返回原始时间，True返回偏移后的时间
        @return: 开盘时间，格式：HHMM，如果没有交易时间段则返回0
        """
        # 如果没有交易时间段，返回0
        if len(self.sections) == 0:
            return 0

        # 获取第一个时间段的开始时间
        opentm = self.sections[0].stime
        # 根据参数决定返回原始时间还是偏移后的时间
        if not bOffset:
            return self.originalTime(opentm)
        else:
            return opentm

    def getCloseTime(self, bOffset:bool = False):
        """
        获取收盘时间
        
        返回最后一个交易时间段的结束时间。
        
        @bOffset: 是否返回偏移后的时间，False返回原始时间，True返回偏移后的时间
        @return: 收盘时间，格式：HHMM，如果没有交易时间段则返回0
        """
        # 如果没有交易时间段，返回0
        if len(self.sections) == 0:
            return 0

        # 获取最后一个时间段的结束时间
        closetm = self.sections[-1].etime
        # 根据参数决定返回原始时间还是偏移后的时间
        if not bOffset:
            return self.originalTime(closetm)
        else:
            return closetm

    def getTradingMins(self):
        """
        获取总交易分钟数
        
        计算所有交易时间段的总交易分钟数，结果会被缓存以避免重复计算。
        
        @return: 总交易分钟数，如果没有交易时间段则返回0
        """
        # 如果没有交易时间段，返回0
        if len(self.sections) == 0:
            return 0
        
        # 如果已经计算过，直接返回缓存值
        if self.totalMins == 0:
            # 遍历所有交易时间段
            for sec in self.sections:
                # 获取时间段的开始和结束时间
                s = sec.stime
                e = sec.etime
                # 计算小时差
                h = math.floor(e / 100) - math.floor(s / 100)
                # 计算分钟差
                m = (e%100) - (s%100)
                # 累加总分钟数
                self.totalMins += (h*60 + m)
        # 返回总交易分钟数
        return self.totalMins

    def getTradingSecs(self):
        """
        获取总交易秒数
        
        将总交易分钟数转换为秒数。
        
        @return: 总交易秒数
        """
        return self.getTradingMins()*60

    def getSectionIndex(self, rawTime:int) -> int:
        """
        获取指定时间所在的时间段索引
        
        根据给定的时间，查找它属于哪个交易时间段。
        
        @rawTime: 原始时间，格式：HHMM
        @return: 时间段索引（从0开始），如果不在任何时间段内则返回-1
        """
        # 将原始时间转换为偏移后的时间
        offTime = self.offsetTime(rawTime)

        # 遍历所有交易时间段
        for idx in range(len(self.sections)):
            # 获取当前时间段
            sec = self.sections[idx]
            # 检查时间是否在当前时间段内
            if sec.stime <= offTime and offTime <= sec.etime:
                # 返回时间段索引
                return idx
        
        # 如果不在任何时间段内，返回-1
        return -1

    def isLastOfSection(self, rawTime:int):
        """
        判断是否为时间段的最后一分钟
        
        检查给定时间是否是某个交易时间段的结束时间。
        
        @rawTime: 原始时间，格式：HHMM
        @return: 如果是时间段的最后一分钟返回True，否则返回False
        """
        # 将原始时间转换为偏移后的时间
        offTime = self.offsetTime(rawTime)

        # 遍历所有交易时间段
        for sec in self.sections:
            # 检查是否是时间段的结束时间
            if sec.etime == offTime:
                return True
        
        # 如果不是任何时间段的结束时间，返回False
        return False

    def	isInTradingTime(self, rawTime:int, bStrict:bool = False):
        """
        判断是否在交易时间内
        
        检查给定时间是否在交易时间段内。
        
        @rawTime: 原始时间，格式：HHMM
        @bStrict: 是否严格模式，如果为True则时间段最后一分钟不算交易时间
        @return: 如果在交易时间内返回True，否则返回False
        """
        # 将时间转换为分钟数
        mins = self.timeToMinutes(rawTime)
        # 如果转换失败（不在交易时间内），返回False
        if mins == -1:
            return False

        # 如果严格模式且是时间段最后一分钟，返回False
        if bStrict and self.isLastOfSection(rawTime):
            return False
            
        # 其他情况返回True
        return True

    def isFirstOfSection(self, rawTime:int):
        """
        判断是否为时间段的第一分钟
        
        检查给定时间是否是某个交易时间段的开始时间。
        
        @rawTime: 原始时间，格式：HHMM
        @return: 如果是时间段的第一分钟返回True，否则返回False
        """
        # 将原始时间转换为偏移后的时间
        offTime = self.offsetTime(rawTime)

        # 遍历所有交易时间段
        for sec in self.sections:
            # 检查是否是时间段的开始时间
            if sec.stime == offTime:
                return True
        
        # 如果不是任何时间段的开始时间，返回False
        return False

    def timeToMinutes(self, rawTime:int):
        """
        将时间转换为从开盘开始的分钟数
        
        计算给定时间距离开盘时间的总分钟数，包括之前所有时间段的时长。
        
        @rawTime: 原始时间，格式：HHMM
        @return: 从开盘开始的分钟数，如果不在交易时间内则返回-1
        """
        # 如果没有交易时间段，返回-1
        if len(self.sections) == 0:
            return -1

        # 将原始时间转换为偏移后的时间
        offTime = self.offsetTime(rawTime)

        # 是否找到对应的时间段
        bFound = False
        # 累计的分钟数
        offset = 0
        # 遍历所有交易时间段
        for sec in self.sections:
            # 检查时间是否在当前时间段内
            if sec.stime <= offTime and offTime <= sec.etime:
                # 计算在当前时间段内的分钟数
                hour = math.floor(offTime / 100) - math.floor(sec.stime / 100)
                minute = offTime % 100 - sec.stime % 100
                offset += hour*60 + minute
                # 标记已找到
                bFound = True
                break
            else:
                # 如果不在当前时间段内，累加该时间段的时长
                hour = math.floor(sec.etime / 100) - math.floor(sec.stime / 100)
                minute = sec.etime % 100 - sec.stime % 100
                offset += hour*60 + minute

        # 如果未找到对应的时间段，返回-1
        if not bFound:
            return -1

        # 返回累计的分钟数
        return offset

    def minutesToTime(self, minutes:int, bHeadFirst:bool = False):
        """
        将分钟数转换为时间
        
        根据从开盘开始的分钟数，计算对应的实际时间。
        
        @minutes: 从开盘开始的分钟数
        @bHeadFirst: 是否优先使用时间段开始时间，如果为True则优先返回时间段开始时间
        @return: 对应的时间，格式：HHMM，如果无法转换则返回-1或收盘时间
        """
        # 如果没有交易时间段，返回-1
        if len(self.sections) == 0:
            return -1

        # 剩余的分钟数
        offset = minutes
        # 遍历所有交易时间段
        for sec in self.sections:
            # 计算时间段的开始和结束分钟数
            startMin = math.floor(sec.stime / 100)*60 + sec.stime % 100
            stopMin = math.floor(sec.etime / 100)*60 + sec.etime % 100

            # 如果不是优先使用开始时间
            if not bHeadFirst:
                # 如果剩余分钟数大于等于当前时间段的时长
                if startMin + offset >= stopMin:
                    # 减去当前时间段的时长
                    offset -= (stopMin - startMin)
                    # 如果剩余分钟数为0，返回时间段的结束时间
                    if offset == 0:
                        return self.originalTime(math.floor(stopMin / 60) * 100 + stopMin % 60)
                else:
                    # 计算目标分钟数
                    desMin = startMin + offset
                    # 处理跨日情况
                    if desMin > 1440:
                        desMin -= 1440

                    # 返回对应的时间
                    return self.originalTime(math.floor(desMin / 60) * 100 + desMin % 60)
            else:
                # 如果优先使用开始时间
                if startMin + offset >= stopMin:
                    # 减去当前时间段的时长
                    offset -= (stopMin - startMin)
                else:
                    # 计算目标分钟数
                    desMin = startMin + offset
                    # 处理跨日情况
                    if desMin > 1440:
                        desMin -= 1440

                    # 返回对应的时间
                    return self.originalTime(math.floor(desMin / 60) * 100 + desMin % 60)

        # 如果所有时间段都无法容纳，返回收盘时间
        return self.getCloseTime()

class SessionMgr:
    """
    交易时段管理器类
    
    负责加载和管理所有交易时段配置。
    支持从JSON或YAML格式的配置文件中加载交易时段信息。
    """

    def __init__(self):
        """
        构造函数
        
        初始化交易时段管理器，创建空的时段字典。
        """
        # 存储所有交易时段的字典，键为时段ID，值为SessionInfo对象
        self.__sessions__ = dict()
        return


    def load(self, fname:str):
        """
        从文件加载交易时段配置
        
        支持JSON和YAML两种格式的配置文件。
        文件格式应为：{时段ID: {name: 名称, offset: 偏移量, sections: [...], ...}}
        
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
            sessions_dict = yaml.full_load(content)
        else:
            # JSON格式文件，使用json模块解析
            sessions_dict = json.loads(content)
        # 遍历所有时段配置
        for sid in sessions_dict:
            # 如果时段已存在，跳过（避免重复加载）
            if sid in self.__sessions__:
                continue

            # 获取时段配置对象
            sObj = sessions_dict[sid]
            # 创建时段信息对象
            sInfo = SessionInfo()
            # 设置时段ID
            sInfo.id = sid
            # 设置时间偏移量
            sInfo.offset = sObj["offset"]
            # 设置时段名称
            sInfo.name = sObj["name"]

            # 如果配置中包含集合竞价时间段
            if "auction" in sObj:
                # 设置集合竞价开始时间（转换为偏移后的时间）
                sInfo.auction.stime = sInfo.offsetTime(sObj["auction"]["from"])
                # 设置集合竞价结束时间（转换为偏移后的时间）
                sInfo.auction.etime = sInfo.offsetTime(sObj["auction"]["to"])

            # 遍历所有交易时间段配置
            for secObj in sObj["sections"]:
                # 创建时间段信息对象
                secInfo = SectionInfo()
                # 设置时间段开始时间（转换为偏移后的时间）
                secInfo.stime = sInfo.offsetTime(secObj["from"])
                # 设置时间段结束时间（转换为偏移后的时间）
                secInfo.etime = sInfo.offsetTime(secObj["to"])
                # 将时间段添加到时段的时间段列表
                sInfo.sections.append(secInfo)

            # 将时段信息存储到字典中
            self.__sessions__[sid] = sInfo


    def getSession(self, sid:str) -> SessionInfo:
        """
        根据时段ID获取时段信息
        
        @sid: 时段ID，例如：TRADING、NIGHT等
        @return: 返回SessionInfo对象，如果不存在则返回None
        """
        # 检查时段是否存在
        if sid not in self.__sessions__:
            return None

        # 返回时段信息对象
        return self.__sessions__[sid]
