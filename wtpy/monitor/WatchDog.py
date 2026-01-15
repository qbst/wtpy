"""
WonderTrader看门狗（WatchDog）模块

该模块提供了应用进程监控和自动调度功能，用于监控交易应用的运行状态，
并在应用异常退出时自动重启，同时支持定时调度功能。

主要功能：
1. 进程监控：定期检查应用进程是否运行，检测进程异常退出
2. 自动重启：当应用异常退出时，自动重启应用（如果启用了守护模式）
3. 定时调度：支持按周、按时间点自动启动、停止或重启应用
4. 事件接收：接收应用通过消息队列发送的事件（订单、成交、通知、日志等）
5. 状态管理：管理应用的状态（不存在、未运行、运行中、关闭中、已关闭）

设计模式：
- 使用观察者模式，通过WatcherSink接口实现事件回调
- 使用守护进程模式，持续监控应用状态
- 使用定时调度模式，支持按时间表自动操作应用
"""

import threading
import time
import subprocess
import os
import datetime
import json
import copy
import platform
import psutil

from .EventReceiver import EventReceiver, EventSink
from .WtLogger import WtLogger

from enum import Enum

def isWindows():
    """
    判断当前操作系统是否为Windows
    
    通过检查platform.system()的返回值来判断操作系统类型。
    
    @return: 如果是Windows系统返回True，否则返回False
    """
    # 将系统名称转换为小写后检查是否包含"windows"
    if "windows" in platform.system().lower():
        return True

    return False

class WatcherSink:
    """
    看门狗事件回调接口类
    
    定义了看门狗监控过程中各种事件的回调接口。
    用户需要继承此类并实现相应的方法来处理监控事件。
    
    使用示例：
        class MyWatcherSink(WatcherSink):
            def on_start(self, appid):
                print(f"应用{appid}已启动")
    """

    def __init__(self):
        """
        初始化看门狗事件回调接口
        
        基类构造函数，子类可以重写此方法进行初始化。
        """
        pass

    def on_start(self, appid:str):
        """
        应用启动事件回调函数
        
        当应用启动时，会调用此函数。
        
        @param appid: 应用ID（字符串），标识启动的应用
        """
        pass

    def on_stop(self, appid:str, isErr:bool = False):
        """
        应用停止事件回调函数
        
        当应用停止时，会调用此函数。
        
        @param appid: 应用ID（字符串），标识停止的应用
        @param isErr: 是否异常停止（布尔值，默认False），True表示异常退出，False表示正常停止
        """
        pass

    def on_output(self, appid:str, tag:str, time:int, message:str):
        """
        应用输出事件回调函数
        
        当应用输出日志或消息时，会调用此函数。
        
        @param appid: 应用ID（字符串），标识输出来源的应用
        @param tag: 输出标签（字符串），用于标识输出类型
        @param time: 输出时间（整数），时间戳格式
        @param message: 输出消息内容（字符串）
        """
        pass

    def on_order(self, appid:str, chnl:str, ordInfo:dict):
        """
        订单事件回调函数
        
        当应用产生订单事件时，会调用此函数。
        
        @param appid: 应用ID（字符串），标识订单来源的应用
        @param chnl: 交易通道名称（字符串），标识订单来源的交易接口
        @param ordInfo: 订单信息字典，包含订单的详细信息
        """
        pass

    def on_trade(self, appid:str, chnl:str, trdInfo:dict):
        """
        成交事件回调函数
        
        当应用产生成交事件时，会调用此函数。
        
        @param appid: 应用ID（字符串），标识成交来源的应用
        @param chnl: 交易通道名称（字符串），标识成交来源的交易接口
        @param trdInfo: 成交信息字典，包含成交的详细信息
        """
        pass
    
    def on_notify(self, appid:str, chnl:str, message:str):
        """
        通知事件回调函数
        
        当应用产生通知事件时，会调用此函数。
        
        @param appid: 应用ID（字符串），标识通知来源的应用
        @param chnl: 交易通道名称（字符串），标识通知来源的交易接口
        @param message: 通知消息内容（字符串）
        """
        pass

    def on_timeout(self, appid:str):
        """
        超时事件回调函数
        
        当应用消息接收超时时，会调用此函数。
        
        @param appid: 应用ID（字符串），标识超时的应用
        """
        pass


class ActionType(Enum):
    """
    操作类型枚举类
    
    定义了定时调度中可以执行的操作类型。
    """
    # 启动操作，启动应用
    AT_START    = 0
    # 停止操作，停止应用
    AT_STOP     = 1
    # 重启操作，重启应用
    AT_RESTART  = 2

class AppState(Enum):
    """
    应用状态枚举类
    
    定义了应用可能处于的各种状态。
    """
    # 应用不存在，应用路径或文件不存在
    AS_NotExist     = 901
    # 应用未运行，应用存在但未启动
    AS_NotRunning   = 902
    # 应用运行中，应用正在运行
    AS_Running      = 903
    # 应用已关闭，应用已停止
    AS_Closed       = 904
    # 应用关闭中，应用正在关闭过程中
    AS_Closing      = 905

class AppInfo(EventSink):
    """
    应用信息管理类
    
    管理单个应用的配置、状态和生命周期。
    继承自EventSink，用于接收应用通过消息队列发送的事件。
    
    主要功能：
    1. 管理应用的配置信息（路径、参数、调度设置等）
    2. 监控应用的运行状态
    3. 控制应用的启动、停止和重启
    4. 接收应用的事件（订单、成交、通知、日志等）
    5. 定时调度功能，按时间表自动操作应用
    """
    
    def __init__(self, appConf:dict, sink:WatcherSink = None, logger:WtLogger=None):
        """
        初始化应用信息
        
        根据应用配置创建应用信息实例，初始化各种状态和参数。
        
        @param appConf: 应用配置字典，包含应用的路径、参数、调度设置等信息
        @param sink: 看门狗事件回调接口（WatcherSink，默认None），用于处理应用事件
        @param logger: 日志记录器（WtLogger，默认None），用于记录日志
        """
        # 保存应用配置信息（私有变量，使用双下划线前缀）
        self.__info__ = appConf

        # 命令行字符串缓存，首次使用时生成
        self._cmd_line = None

        # 日志记录器引用
        self.__logger__ = logger

        # 线程锁，用于保护配置信息的线程安全访问
        self._lock = threading.Lock()
        # 应用ID，唯一标识一个应用
        self._id = appConf["id"]
        # 检查间隔（秒），每隔多少秒检查一次应用状态
        self._check_span = appConf["span"]
        # 守护标志，是否在应用异常退出时自动重启
        self._guard = appConf["guard"]
        # 重定向标志，是否重定向应用的输出
        self._redirect = appConf["redirect"]
        # 消息队列URL，用于接收应用的事件
        if "mqurl" in appConf:
            self._mq_url = appConf["mqurl"].strip()
        else:
            self._mq_url = ""
        # 调度激活标志，是否启用定时调度
        self._schedule = appConf["schedule"]["active"]
        # 周标志字符串，7位字符串，每位表示一周中的某一天是否启用调度（1启用，0禁用）
        self._weekflag = appConf["schedule"]["weekflag"]

        # 计时器计数，用于记录检查次数
        self._ticks = 0
        # 应用当前状态，初始化为未运行状态
        self._state = AppState.AS_NotRunning
        # 应用进程ID，None表示未启动或进程已退出
        self._procid = None
        # 看门狗事件回调接口
        self._sink = sink
        # 应用内存使用量（字节）
        self._mem = 0

        # 事件接收器引用，用于接收应用通过消息队列发送的事件
        self._evt_receiver = None

        # 检查应用路径和文件夹是否存在，如果不存在则设置状态为不存在
        if not os.path.exists(appConf["folder"]) or not os.path.exists(appConf["path"]):
            self._state == AppState.AS_NotExist

    def applyConf(self, appConf:dict):
        """
        应用配置更新方法
        
        更新应用的配置信息，如果消息队列URL发生变化，会重新创建事件接收器。
        
        @param appConf: 新的应用配置字典，包含要更新的配置信息
        """
        # 获取线程锁，保护配置信息的线程安全访问
        self._lock.acquire()
        # 更新应用配置信息
        self.__info__ = appConf
        # 更新检查间隔
        self._check_span = appConf["span"]
        # 更新守护标志
        self._guard = appConf["guard"]
        # 保存旧的消息队列URL，用于判断是否需要重新创建事件接收器
        old_mqurl = self._mq_url
        # 更新消息队列URL
        self._mq_url = appConf["mqurl"]
        # 更新重定向标志
        self._redirect = appConf["redirect"]
        # 更新调度激活标志
        self._schedule = appConf["schedule"]["active"]
        # 更新周标志字符串
        self._weekflag = appConf["schedule"]["weekflag"]
        # 重置计时器计数
        self._ticks = 0
        # 释放线程锁
        self._lock.release()
        # 记录配置更新日志
        self.__logger__.info("应用%s的调度设置已更新" % (self._id))

        # 如果消息队列URL发生变化
        if self._mq_url != old_mqurl:
            # 如果事件接收器存在，先释放旧的接收器
            if self._evt_receiver is not None:
                self._evt_receiver.release()

            # 如果新的消息队列URL不为空，创建新的事件接收器
            if self._mq_url != '':
                self._evt_receiver = EventReceiver(url=self._mq_url, logger=self.__logger__)
                self._evt_receiver.run()
                self.__logger__.info("应用%s开始接收%s的通知信息" % (self._id, self._mq_url))

    def getConf(self):
        """
        获取应用配置信息
        
        返回应用配置信息的副本，确保线程安全。
        
        @return: 应用配置字典的副本
        """
        # 获取线程锁，保护配置信息的线程安全访问
        self._lock.acquire()
        # 复制配置信息，避免外部修改影响内部状态
        ret = copy.copy(self.__info__)
        # 释放线程锁
        self._lock.release()
        # 返回配置信息副本
        return ret

    @property
    def cmd_line(self) -> str:
        """
        获取应用命令行字符串（属性方法）
        
        根据应用路径和参数生成完整的命令行字符串。
        使用缓存机制，首次调用时生成并缓存，后续直接返回缓存值。
        
        @return: 完整的命令行字符串
        """
        # 获取应用参数
        fullPath = self.__info__["param"]
        # 如果命令行字符串未缓存，生成并缓存
        if self._cmd_line is None:
            # 如果有参数，拼接路径和参数；否则只使用路径
            self._cmd_line = (self.__info__["path"] + " " + fullPath) if fullPath != "" else self.__info__["path"]
        # 返回命令行字符串
        return self._cmd_line

    def is_running(self, pids) -> bool:
        """
        检查应用是否正在运行
        
        通过检查进程ID是否存在，或遍历所有进程查找匹配的命令行来判断应用是否运行。
        如果找到匹配的进程，会更新进程ID和内存使用量，并创建事件接收器。
        
        @param pids: 所有进程ID列表，用于查找匹配的进程
        @return: 如果应用正在运行返回True，否则返回False
        """
        # 如果应用状态为关闭中，返回True（表示正在运行）
        if self._state == AppState.AS_Closing:
            return True

        # 如果应用状态为已关闭，返回False（表示未运行）
        if self._state == AppState.AS_Closed:
            return False
            
        # 判断是否需要检查进程：进程ID为空或进程不存在
        bNeedCheck = (self._procid is None) or (not psutil.pid_exists(self._procid))
        # 如果需要检查，遍历所有进程查找匹配的进程
        if bNeedCheck:
            for pid in pids:
                try:
                    # 获取进程信息
                    pInfo = psutil.Process(pid)
                    # 获取进程命令行参数列表
                    cmdLine = pInfo.cmdline()
                    # 如果命令行为空，跳过
                    if len(cmdLine) == 0:
                        continue
                    # 将命令行参数列表拼接为字符串
                    cmdLine = ' '.join(cmdLine)
                    # 比较命令行是否匹配（不区分大小写）
                    if self.cmd_line.upper() == cmdLine.upper():
                        # 找到匹配的进程，更新进程ID
                        self._procid = pid
                        # 更新内存使用量（RSS：实际物理内存使用量）
                        self._mem = pInfo.memory_info().rss
                        # 记录挂载成功日志
                        self.__logger__.info("应用%s挂载成功，进程ID: %d" % (self._id, self._procid))
     
                        # 如果消息队列URL不为空，创建事件接收器
                        if self._mq_url != '':
                            # 如果事件接收器为空或者URL发生了改变，则需要重新创建
                            bNeedCreate = self._evt_receiver is None or self._evt_receiver.url != self._mq_url
                            if bNeedCreate:
                                # 如果事件接收器存在，先释放旧的接收器
                                if self._evt_receiver is not None:
                                    self._evt_receiver.release()
                                # 创建新的事件接收器
                                self._evt_receiver = EventReceiver(url=self._mq_url, logger=self.__logger__, sink=self)
                                self._evt_receiver.run()
                                self.__logger__.info("应用%s开始接收%s的通知信息" % (self._id, self._mq_url))
                        return True
                except:
                    # 如果获取进程信息失败，继续查找下一个进程
                    pass
            return False
        else:
            # 如果不需要检查，直接获取进程信息并更新内存使用量
            pInfo = psutil.Process(self._procid)
            self._mem = pInfo.memory_info().rss

        return True

    def run(self):
        """
        启动应用
        
        创建子进程启动应用，并创建事件接收器接收应用的事件。
        如果应用已经在运行，则直接返回。
        """
        # 如果应用已经在运行，直接返回
        if self._state == AppState.AS_Running:
            return

        # 如果消息队列URL不为空，创建事件接收器
        if self._mq_url != '':
            # 每次启动都重新创建接收器，确保连接正常
            if self._evt_receiver is not None:
                self.__logger__.info("应用%s正在释放原有事件接收器..." % (self._id))
                self._evt_receiver.release()
            # 创建新的事件接收器
            self._evt_receiver = EventReceiver(url=self._mq_url, logger=self.__logger__, sink=self)
            self._evt_receiver.run()
            self.__logger__.info("应用%s开始接收%s的通知信息" % (self._id, self._mq_url))

        try:
            # 解析应用参数，如果参数不为空则按空格分割，否则为空列表
            args = self.__info__["param"].split(" ") if self.__info__["param"] != "" else []
            # 将应用路径插入到参数列表的第一位
            args.insert(0, self.__info__["path"])

            # 根据操作系统类型启动进程
            if isWindows():
                # Windows系统：使用CREATE_NEW_CONSOLE标志创建新控制台窗口
                self._procid = subprocess.Popen(args,
                                cwd=self.__info__["folder"], creationflags=subprocess.CREATE_NEW_CONSOLE).pid
            else:
                # Linux/Unix系统：直接启动进程
                self._procid = subprocess.Popen(args, 
                                cwd=self.__info__["folder"]).pid
            
            # 更新命令行字符串缓存
            self._cmd_line = (self.__info__["path"] + " " + self.__info__["param"]) if self.__info__["param"] != "" else self.__info__["path"]
            # 记录启动日志，包含命令行和工作目录
            self.__logger__.info(f"cmdline: {self._cmd_line}, cwd:{self.__info__['folder']}")
        except:
            # 如果启动失败，记录异常日志
            self.__logger__.info("应用%s启动异常" % (self._id))

        # 更新应用状态为运行中
        self._state = AppState.AS_Running

        # 记录启动成功日志
        self.__logger__.info("应用%s的已启动，进程ID: %d" % (self._id, self._procid))
        # 如果事件回调接口存在，调用启动回调
        if self._sink is not None:
            self._sink.on_start(self._id)

    def stop(self):
        """
        停止应用
        
        强制终止应用进程。如果应用未在运行，则直接返回。
        """
        # 如果应用未在运行，直接返回
        if self._state != AppState.AS_Running:
            return

        # 更新应用状态为关闭中
        self._state = AppState.AS_Closing
        try:
            # 根据操作系统类型终止进程
            if isWindows():
                # Windows系统：使用taskkill命令强制终止进程
                os.system("taskkill /f /pid " + str(self._procid))
            else:
                # Linux/Unix系统：使用kill -9命令强制终止进程
                os.system("kill -9 " + str(self._procid))
        except SystemError as e:
            # 如果终止进程失败，记录错误日志
            self.__logger__.error("关闭异常: {}" % (e))
            pass

        # 更新应用状态为已关闭
        self._state = AppState.AS_Closed
        # 记录停止日志
        self.__logger__.info("应用%s的已停止，进程ID: %d" % (self._id, self._procid))
        # 如果事件回调接口存在，调用停止回调（isErr=False表示正常停止）
        if self._sink is not None:
            self._sink.on_stop(self._id, False)
        # 清空进程ID
        self._procid = None

    def restart(self):
        """
        重启应用
        
        先停止应用（如果正在运行），然后启动应用。
        """
        # 如果进程ID不为空，先停止应用
        if self._procid is not None:
            self.stop()
        
        # 启动应用
        self.run()

    def update_state(self, pids):
        """
        更新应用状态
        
        检查应用是否运行，并更新应用状态。
        如果应用从运行状态变为未运行状态，会触发停止回调。
        
        @param pids: 所有进程ID列表，用于检查应用是否运行
        """
        # 检查应用是否运行
        if self.is_running(pids):
            # 如果运行，更新状态为运行中
            self._state = AppState.AS_Running
        # 如果应用之前是运行状态，但现在未运行
        elif self._state == AppState.AS_Running:
            # 更新状态为未运行
            self._state = AppState.AS_NotRunning
            # 记录停止日志
            self.__logger__.info("应用%s的已停止" % (self._id))
            # 清空进程ID
            self._procid = None
            # 清空内存使用量
            self._mem = 0
            # 如果事件回调接口存在，调用停止回调（isErr=True表示异常退出）
            if self._sink is not None:
                self._sink.on_stop(self._id, True)

    def tick(self, pids):
        """
        定时检查方法
        
        每次调用时增加计数器，当计数器达到检查间隔时，更新应用状态。
        如果启用了守护模式且应用未运行，会自动重启应用。
        如果启用了定时调度，会执行定时调度逻辑。
        
        @param pids: 所有进程ID列表，用于检查应用是否运行
        """
        # 增加计时器计数
        self._ticks += 1

        # 如果计时器计数达到检查间隔
        if self._ticks == self._check_span:
            # 更新应用状态
            self.update_state(pids)
            # 如果应用未运行且启用了守护模式，自动重启应用
            if self._state == AppState.AS_NotRunning and self._guard:
                self.__logger__.info("应用%s未启动，正在自动重启" % (self._id))
                # 在后台线程中启动应用，避免阻塞
                thrd = threading.Thread(target=self.run, daemon=True)
                thrd.start()
            # 如果启用了定时调度，执行定时调度逻辑
            elif self._schedule:
                self.__schedule__()

            # 重置计时器计数
            self._ticks = 0
    
    def __schedule__(self):
        """
        定时调度方法（私有方法）
        
        根据当前时间和调度配置，自动执行启动、停止或重启操作。
        支持按周、按时间点进行调度，避免重复执行。
        """
        # 获取周标志字符串
        weekflag = self._weekflag

        # 获取当前时间
        now = datetime.datetime.now()
        # Python中weekday()返回：周一是0，周天是6
        # 但是web端沿用了C++里的规则，周日是0，周六是6，所以做一个变换
        wd = now.weekday() + 1
        # 如果变换后是7，则改为0（周日）
        if wd == 7:
            wd = 0
        # 如果当前日期不在调度范围内，直接返回
        if weekflag[wd] != "1":
            return

        # 获取应用ID
        appid = self.__info__["id"]

        # 获取当前时间（时分，格式如0930表示9点30分）
        curMin = int(now.strftime("%H%M"))
        # 获取当前日期（年月日，格式如230101表示2023年1月1日）
        curDt = int(now.strftime("%y%m%d"))
        # 获取线程锁，保护调度任务的线程安全访问
        self._lock.acquire()
        # 遍历所有调度任务
        for tInfo in self.__info__["schedule"]["tasks"]:
            # 如果任务未激活，跳过
            if not tInfo["active"]:
                continue
            
            # 获取上次执行日期，如果不存在则默认为0
            if "lastDate" in tInfo:
                lastDate = tInfo["lastDate"]
            else:
                lastDate = 0

            # 获取上次执行时间，如果不存在则默认为0
            if "lastTime" in tInfo:
                lastTime = tInfo["lastTime"]
            else:
                lastTime = 0
            # 获取目标执行时间
            targetTm = tInfo["time"]
            # 获取操作类型（启动、停止或重启）
            action = tInfo["action"]

            # 如果当前时间匹配目标时间，且与上次执行时间或日期不同（避免重复执行）
            if curMin == targetTm and (curMin != lastTime or curDt != lastDate):
                # 如果是启动操作
                if action == ActionType.AT_START.value:
                    # 如果应用状态不是不存在或运行中，则启动应用
                    if self._state not in [AppState.AS_NotExist, AppState.AS_Running]:
                        self.__logger__.info("自动启动应用%s" % (appid))
                        self.run()
                # 如果是停止操作
                elif action == ActionType.AT_STOP.value:
                    # 如果应用正在运行，则停止应用
                    if self._state == AppState.AS_Running:
                        self.__logger__.info("自动停止应用%s" % (appid))
                        self.stop()
                # 如果是重启操作
                elif action == ActionType.AT_RESTART.value:
                    self.__logger__.info("自动重启应用%s" % (appid))
                    self.restart()

                # 更新上次执行日期和时间，避免重复执行
                tInfo["lastDate"] = curDt
                tInfo["lastTime"] = curMin
        # 释放线程锁
        self._lock.release()

    def isRunning(self):
        """
        检查应用是否正在运行
        
        @return: 如果应用正在运行返回True，否则返回False
        """
        return self._state == AppState.AS_Running

    @property
    def memory(self):
        """
        获取应用内存使用量（属性方法）
        
        @return: 应用内存使用量（整数，单位：字节）
        """
        return self._mem

    # ========== EventSink接口实现 ==========
    def on_timeout(self):
        """
        超时事件回调函数（实现EventSink接口）
        
        当应用消息接收超时时，会调用此函数。
        将超时事件转发给看门狗事件回调接口。
        """
        if self._sink is not None:
            self._sink.on_timeout(self._id)

    def on_order(self, chnl:str, ordInfo:dict):
        """
        订单事件回调函数（实现EventSink接口）
        
        当应用产生订单事件时，会调用此函数。
        将订单事件转发给看门狗事件回调接口。
        
        @param chnl: 交易通道名称（字符串），标识订单来源的交易接口
        @param ordInfo: 订单信息字典，包含订单的详细信息
        """
        if self._sink is not None:
            self._sink.on_order(self._id, chnl, ordInfo)

    def on_trade(self, chnl:str, trdInfo:dict):
        """
        成交事件回调函数（实现EventSink接口）
        
        当应用产生成交事件时，会调用此函数。
        将成交事件转发给看门狗事件回调接口。
        
        @param chnl: 交易通道名称（字符串），标识成交来源的交易接口
        @param trdInfo: 成交信息字典，包含成交的详细信息
        """
        if self._sink is not None:
            self._sink.on_trade(self._id, chnl, trdInfo)
    
    def on_notify(self, chnl:str, message:str):
        """
        通知事件回调函数（实现EventSink接口）
        
        当应用产生通知事件时，会调用此函数。
        将通知事件转发给看门狗事件回调接口。
        
        @param chnl: 交易通道名称（字符串），标识通知来源的交易接口
        @param message: 通知消息内容（字符串）
        """
        if self._sink is not None:
            self._sink.on_notify(self._id, chnl, message)

    def on_log(self, tag:str, time:int, message:str):
        """
        日志事件回调函数（实现EventSink接口）
        
        当应用产生日志事件时，会调用此函数。
        将日志事件转发给看门狗事件回调接口（作为输出事件）。
        
        @param tag: 日志标签（字符串），用于标识日志来源
        @param time: 日志时间（整数），时间戳格式
        @param message: 日志消息内容（字符串）
        """
        if self._sink is not None:
            self._sink.on_output(self._id, tag, time, message)
        pass

class WatchDog:
    """
    看门狗主类
    
    管理多个应用的监控和调度。从数据库加载应用配置，定期检查所有应用的状态，
    并在应用异常退出时自动重启（如果启用了守护模式）。
    
    主要功能：
    1. 从数据库加载应用配置
    2. 管理多个应用的AppInfo实例
    3. 定期检查所有应用的状态
    4. 提供应用启动、停止、重启等操作的接口
    5. 支持应用配置的增删改查
    """

    def __init__(self, db, sink:WatcherSink = None, logger:WtLogger=None):
        """
        初始化看门狗
        
        创建看门狗实例，从数据库加载应用配置，并创建对应的AppInfo实例。
        
        @param db: 数据库连接对象，用于加载和保存应用配置
        @param sink: 看门狗事件回调接口（WatcherSink，默认None），用于处理应用事件
        @param logger: 日志记录器（WtLogger，默认None），用于记录日志
        """
        # 数据库连接对象（私有变量）
        self.__db_conn__ = db
        # 应用信息字典，key为应用ID，value为AppInfo实例
        self.__apps__ = dict()
        # 应用配置字典，key为应用ID，value为应用配置字典
        self.__app_conf__ = dict()
        # 停止标志，用于控制监控线程的运行
        self.__stopped__ = False
        # 监控工作线程引用
        self.__worker__ = None
        # 看门狗事件回调接口
        self.__sinks__ = sink
        # 日志记录器引用
        self.__logger__ = logger

        # ========== 从数据库加载调度列表 ==========
        # 获取数据库游标
        cur = self.__db_conn__.cursor()
        # 查询所有调度配置
        for row in cur.execute("SELECT * FROM schedules;"):
            # 创建应用配置字典
            appConf = dict()
            # 应用ID（第2列，索引1）
            appConf["id"] = row[1]
            # 应用路径（第3列，索引2）
            appConf["path"] = row[2]
            # 工作目录（第4列，索引3）
            appConf["folder"] = row[3]
            # 应用参数（第5列，索引4）
            appConf["param"] = row[4]
            # 应用类型（第6列，索引5）
            appConf["type"] = row[5]
            # 检查间隔（第7列，索引6）
            appConf["span"] = row[6]
            # 守护标志（第8列，索引7），字符串'true'转换为布尔值True
            appConf["guard"] = row[7]=='true'
            # 重定向标志（第9列，索引8），字符串'true'转换为布尔值True
            appConf["redirect"] = row[8]=='true'
            # 消息队列URL（第12列，索引11）
            appConf["mqurl"] = row[11]
            # 调度配置字典
            appConf["schedule"] = dict()
            # 调度激活标志（第10列，索引9），字符串'true'转换为布尔值True
            appConf["schedule"]["active"] = row[9]=='true'
            # 周标志字符串（第11列，索引10），7位字符串，每位表示一周中的某一天是否启用调度
            appConf["schedule"]["weekflag"] = row[10]
            # 调度任务列表，包含6个调度任务
            appConf["schedule"]["tasks"] = list()
            # 从数据库加载6个调度任务（第13-18列，索引12-17），每个任务都是JSON字符串
            appConf["schedule"]["tasks"].append(json.loads(row[12]))
            appConf["schedule"]["tasks"].append(json.loads(row[13]))
            appConf["schedule"]["tasks"].append(json.loads(row[14]))
            appConf["schedule"]["tasks"].append(json.loads(row[15]))
            appConf["schedule"]["tasks"].append(json.loads(row[16]))
            appConf["schedule"]["tasks"].append(json.loads(row[17]))
            # 将应用配置保存到配置字典
            self.__app_conf__[appConf["id"]] = appConf
            # 创建AppInfo实例并保存到应用字典
            self.__apps__[appConf["id"]] = AppInfo(appConf, sink, self.__logger__)


    def __watch_impl__(self):
        """
        监控实现方法（私有方法）
        
        后台线程函数，持续监控所有应用的状态。
        每秒检查一次所有应用的运行状态，并触发相应的处理逻辑。
        """
        # 持续运行，直到停止标志为True
        while not self.__stopped__:
            # 等待1秒，避免CPU占用过高
            time.sleep(1)
            # 获取所有进程ID列表
            pids = psutil.pids()
            # 遍历所有应用
            for appid in self.__apps__:
                # 获取应用信息实例
                appInfo = self.__apps__[appid]

                # 调用应用的tick方法，检查状态并执行调度逻辑
                appInfo.tick(pids)

    def get_apps(self):
        """
        获取所有应用信息
        
        返回所有应用的配置信息和运行状态。
        
        @return: 应用信息字典，key为应用ID，value为包含配置和状态的字典
        """
        # 创建返回字典
        ret = {}
        # 遍历所有应用配置
        for appid in self.__app_conf__:
            # 检查应用是否正在运行
            bRunning = self.__apps__[appid].isRunning()
            # 复制应用配置，避免修改原始配置
            conf = copy.copy(self.__app_conf__[appid])
            # 添加运行状态
            conf["running"] = bRunning
            # 添加内存使用量
            conf["memory"] = self.__apps__[appid].memory
            # 将应用信息添加到返回字典
            ret[appid] = conf
        return ret

    def run(self):
        """
        启动看门狗监控服务
        
        启动后台监控线程，开始监控所有应用的状态。
        如果监控线程已经启动，则直接返回。
        """
        # 如果监控线程未启动，创建并启动监控线程
        if self.__worker__ is None:
            # 创建监控线程，设置为守护线程，线程名为"WatchDog"
            self.__worker__ = threading.Thread(target=self.__watch_impl__, name="WatchDog", daemon=True)
            # 启动监控线程
            self.__worker__.start()
            # 记录启动日志
            self.__logger__.info("自动调度服务已启动")

    def start(self, appid:str):
        """
        手动启动指定应用
        
        启动指定ID的应用。如果应用不存在，则直接返回。
        
        @param appid: 应用ID（字符串），要启动的应用标识
        """
        # 如果应用不存在，直接返回
        if appid not in self.__apps__:
            return

        # 记录手动启动日志
        self.__logger__.info("手动启动%s" % (appid))
        # 获取应用信息实例
        appInfo = self.__apps__[appid]
        # 直接调用应用的run方法启动应用（同步执行）
        appInfo.run()

    def stop(self, appid:str):
        """
        手动停止指定应用
        
        停止指定ID的应用。如果应用不存在，则直接返回。
        
        @param appid: 应用ID（字符串），要停止的应用标识
        """
        # 如果应用不存在，直接返回
        if appid not in self.__apps__:
            return

        # 记录手动停止日志
        self.__logger__.info("手动停止%s" % (appid))
        # 获取应用信息实例
        appInfo = self.__apps__[appid]
        # 直接调用应用的stop方法停止应用（同步执行）
        appInfo.stop()

    def has_app(self, appid:str):
        """
        检查应用是否存在
        
        @param appid: 应用ID（字符串），要检查的应用标识
        @return: 如果应用存在返回True，否则返回False
        """
        return appid in self.__apps__

    def restart(self, appid:str):
        """
        手动重启指定应用
        
        重启指定ID的应用。如果应用不存在，则直接返回。
        
        @param appid: 应用ID（字符串），要重启的应用标识
        """
        # 如果应用不存在，直接返回
        if appid not in self.__apps__:
            return

        # 获取应用信息实例
        appInfo = self.__apps__[appid]
        # 直接调用应用的restart方法重启应用（同步执行）
        appInfo.restart()
    
    def isRunning(self, appid:str):
        """
        检查指定应用是否正在运行
        
        @param appid: 应用ID（字符串），要检查的应用标识
        @return: 如果应用正在运行返回True，否则返回False
        """
        # 如果应用不存在，返回False
        if appid not in self.__apps__:
            return False

        # 获取应用信息实例并检查是否运行
        appInfo = self.__apps__[appid]
        return appInfo.isRunning()

    def getAppConf(self, appid:str):
        """
        获取指定应用的配置信息
        
        @param appid: 应用ID（字符串），要获取配置的应用标识
        @return: 应用配置字典，如果应用不存在则返回None
        """
        # 如果应用不存在，返回None
        if appid not in self.__apps__:
            return None
        
        # 获取应用信息实例并返回配置信息
        appInfo = self.__apps__[appid]
        return appInfo.getConf()

    def delApp(self, appid:str):
        """
        删除指定应用
        
        从内存和数据库中删除指定应用。如果应用不存在，则直接返回。
        
        @param appid: 应用ID（字符串），要删除的应用标识
        """
        # 如果应用不存在，直接返回
        if appid not in self.__apps__:
            return

        # 从应用字典中移除应用
        self.__apps__.pop(appid)
        # 从配置字典中移除应用配置
        self.__app_conf__.pop(appid)
        # 获取数据库游标
        cur = self.__db_conn__.cursor()
        # 从数据库中删除应用配置
        cur.execute("DELETE FROM schedules WHERE appid='%s';" % (appid))
        # 提交数据库事务
        self.__db_conn__.commit()
        # 记录删除日志
        self.__logger__.info("应用%s自动调度已删除" % (appid))

    def updateMQURL(self, appid:str, mqurl:str):
        """
        更新指定应用的消息队列URL
        
        更新应用的消息队列URL，并同步更新数据库。
        如果应用不存在，则直接返回。
        
        @param appid: 应用ID（字符串），要更新的应用标识
        @param mqurl: 新的消息队列URL（字符串）
        """
        # 如果应用不存在，直接返回
        if appid not in self.__apps__:
            return

        # 更新配置字典中的消息队列URL
        self.__app_conf__[appid]["mqurl"] = mqurl
        # 获取应用配置
        appConf = self.__app_conf__[appid]
        # 获取应用信息实例
        appInst = self.__apps__[appid]
        # 应用新配置，这会重新创建事件接收器
        appInst.applyConf(appConf)
        
        # 获取数据库游标
        cur = self.__db_conn__.cursor()
        # 构建更新SQL语句，更新消息队列URL和修改时间
        sql = "UPDATE schedules SET mqurl='%s',modifytime=datetime('now','localtime') WHERE appid='%s';" % (mqurl, appid)
        print(sql)
        # 执行SQL语句
        cur.execute(sql)
        # 提交数据库事务
        self.__db_conn__.commit()

    def applyAppConf(self, appConf:dict, isGroup:bool = False):
        """
        应用应用配置
        
        更新或创建应用配置。如果应用不存在则创建新应用，否则更新现有应用配置。
        配置会同步保存到数据库。
        
        @param appConf: 应用配置字典，包含应用的完整配置信息
        @param isGroup: 是否为分组应用（布尔值，默认False），True表示分组应用，False表示普通应用
        """
        # 获取应用ID
        appid = appConf["id"]
        # 更新或添加应用配置到配置字典
        self.__app_conf__[appid] = appConf
        # 判断是否为新应用
        isNewApp = False
        # 如果应用不存在，创建新应用
        if appid not in self.__apps__:
            isNewApp = True
            # 创建新的AppInfo实例
            self.__apps__[appid] = AppInfo(appConf, self.__sinks__, self.__logger__)
        else:
            # 如果应用已存在，更新应用配置
            appInst = self.__apps__[appid]
            appInst.applyConf(appConf)

        # 将布尔值转换为字符串，用于数据库存储
        guard = 'true' if appConf["guard"] else 'false'
        redirect = 'true' if appConf["redirect"] else 'false'
        # 注意：这里应该是appConf["schedule"]["active"]，但代码中写的是appConf["schedule"]
        schedule = 'true' if appConf["schedule"] else 'false'

        # 根据是否为分组应用设置类型（1表示分组，0表示普通）
        stype = 1 if isGroup else 0

        # 获取消息队列URL，如果不存在则默认为空字符串
        mqurl = ''
        if "mqurl" in appConf:
            mqurl = appConf['mqurl']

        # 获取数据库游标
        cur = self.__db_conn__.cursor()
        sql = ''
        # 如果是新应用，执行插入操作
        if isNewApp:
            # 构建插入SQL语句，插入所有配置信息
            sql = "INSERT INTO schedules(appid,path,folder,param,type,span,guard,redirect,schedule,weekflag,task1,task2,task3,task4,task5,task6,mqurl) \
                    VALUES('%s','%s','%s','%s',%d, %d,'%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s');" % (
                    appid, appConf["path"], appConf["folder"], appConf["param"], stype, appConf["span"], guard, redirect, schedule, appConf["schedule"]["weekflag"],
                    json.dumps(appConf["schedule"]["tasks"][0]),json.dumps(appConf["schedule"]["tasks"][1]),json.dumps(appConf["schedule"]["tasks"][2]),
                    json.dumps(appConf["schedule"]["tasks"][3]),json.dumps(appConf["schedule"]["tasks"][4]),json.dumps(appConf["schedule"]["tasks"][5]),
                    mqurl)
        else:
            # 如果是现有应用，执行更新操作
            sql = "UPDATE schedules SET path='%s',folder='%s',param='%s',type=%d,span='%s',guard='%s',redirect='%s',schedule='%s',weekflag='%s',task1='%s',task2='%s',\
                    task3='%s',task4='%s',task5='%s',task6='%s',mqurl='%s',modifytime=datetime('now','localtime') WHERE appid='%s';" % (
                    appConf["path"], appConf["folder"], appConf["param"], stype, appConf["span"], guard, redirect, schedule, appConf["schedule"]["weekflag"],
                    json.dumps(appConf["schedule"]["tasks"][0]),json.dumps(appConf["schedule"]["tasks"][1]),json.dumps(appConf["schedule"]["tasks"][2]),
                    json.dumps(appConf["schedule"]["tasks"][3]),json.dumps(appConf["schedule"]["tasks"][4]),json.dumps(appConf["schedule"]["tasks"][5]), 
                    mqurl, appid)
        # 执行SQL语句
        cur.execute(sql)
        # 提交数据库事务
        self.__db_conn__.commit()
