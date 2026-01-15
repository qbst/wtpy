"""
WonderTrader回测监控模块

该模块提供了回测任务的管理和监控功能，用于管理用户策略的回测任务。
支持创建、启动、监控回测任务，并接收回测过程中的事件（启动、结束、状态更新、资金变化等）。

主要功能：
1. 回测任务管理：创建、启动、监控回测任务
2. 策略管理：管理用户的策略列表和回测历史
3. 任务监控：监控回测任务的运行状态，接收回测事件
4. 数据持久化：将策略和回测信息保存到文件系统
5. 回测结果查询：查询回测任务的执行结果和统计信息

设计模式：
- 使用观察者模式，通过BtTaskSink接口实现回测事件回调
- 使用文件系统存储用户数据和回测结果
- 使用消息队列接收回测任务的事件通知
"""

import os
import json
import subprocess
import platform
import sys
import psutil
import hashlib
import datetime
import shutil
import json
import threading
import time

from wtpy import WtDtServo
from .WtLogger import WtLogger
from .EventReceiver import BtEventReceiver, BtEventSink

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

def md5_str(v:str) -> str:
    """
    计算字符串的MD5哈希值
    
    将字符串编码为UTF-8后计算MD5哈希值，并返回十六进制字符串。
    
    @param v: 要计算哈希值的字符串
    @return: MD5哈希值的十六进制字符串（32位）
    """
    return hashlib.md5(v.encode()).hexdigest()

def gen_btid(user:str, straid:str) -> str:
    """
    生成回测任务ID
    
    根据用户名、策略ID和当前时间戳生成唯一的回测任务ID。
    使用MD5哈希确保ID的唯一性和固定长度。
    
    @param user: 用户名（字符串）
    @param straid: 策略ID（字符串）
    @return: 回测任务ID（字符串，32位MD5哈希值）
    """
    # 获取当前时间
    now = datetime.datetime.now()
    # 拼接字符串：用户名_策略ID_时间戳
    s = user + "_" + straid + "_" + str(now.timestamp())
    # 计算MD5哈希值并返回
    return md5_str(s)

def gen_straid(user:str) -> str:
    """
    生成策略ID
    
    根据用户名和当前时间戳生成唯一的策略ID。
    使用MD5哈希确保ID的唯一性和固定长度。
    
    @param user: 用户名（字符串）
    @return: 策略ID（字符串，32位MD5哈希值）
    """
    # 获取当前时间
    now = datetime.datetime.now()
    # 拼接字符串：用户名_时间戳
    s = user + "_" + str(now.timestamp())
    # 计算MD5哈希值并返回
    return md5_str(s)

class BtTaskSink:
    """
    回测任务事件回调接口类
    
    定义了回测任务过程中各种事件的回调接口。
    用户需要继承此类并实现相应的方法来处理回测事件。
    
    使用示例：
        class MyBtTaskSink(BtTaskSink):
            def on_start(self, user, straid, btid):
                print(f"回测任务{btid}已启动")
    """

    def __init__(self):
        """
        初始化回测任务事件回调接口
        
        基类构造函数，子类可以重写此方法进行初始化。
        """
        pass

    def on_start(self, user:str, straid:str, btid:str):
        """
        回测任务启动事件回调函数
        
        当回测任务启动时，会调用此函数。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        """
        pass

    def on_stop(self, user:str, straid:str, btid:str):
        """
        回测任务停止事件回调函数
        
        当回测任务停止时，会调用此函数。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        """
        pass

    def on_state(self, user:str, straid:str, btid:str, statInfo:dict):
        """
        回测任务状态更新事件回调函数
        
        当回测任务状态更新时，会调用此函数。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @param statInfo: 状态信息字典，包含回测的当前状态（进度、当前日期等）
        """
        pass

    def on_fund(self, user:str, straid:str, btid:str, fundInfo:dict):
        """
        回测任务资金变化事件回调函数
        
        当回测任务资金发生变化时，会调用此函数。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @param fundInfo: 资金信息字典，包含资金变化的详细信息（日期、权益、盈亏等）
        """
        pass

class WtBtTask(BtEventSink):
    """
    回测任务类
    
    管理单个回测任务的执行和监控。继承自BtEventSink，用于接收回测事件。
    
    主要功能：
    1. 启动回测任务进程
    2. 监控回测任务进程状态
    3. 接收回测事件（启动、结束、状态、资金变化）
    4. 将回测事件转发给上层回调接口
    """
    
    def __init__(self, user:str, straid:str, btid:str, folder:str, logger:WtLogger = None, sink:BtTaskSink = None):
        """
        初始化回测任务
        
        创建回测任务实例，设置任务的基本信息和回调接口。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @param folder: 回测任务文件夹路径（字符串），包含回测脚本和结果
        @param logger: 日志记录器（WtLogger，默认None），用于记录日志
        @param sink: 回测任务事件回调接口（BtTaskSink，默认None），用于处理回测事件
        """
        # 保存用户名
        self.user = user
        # 保存策略ID
        self.straid = straid
        # 保存回测任务ID
        self.btid = btid
        # 保存日志记录器引用
        self.logger = logger
        # 保存回测任务文件夹路径
        self.folder = folder
        # 保存回测任务事件回调接口
        self.sink = sink
        
        # 命令行字符串缓存，首次使用时生成
        self._cmd_line = None
        # 消息队列URL，使用IPC协议，路径基于回测任务ID
        self._mq_url = "ipc:///wtpy/bt_%s.ipc" % (btid)
        # 计时器计数，用于记录检查次数
        self._ticks = 0
        # 任务状态，0表示未启动，1表示已启动
        self._state = 0
        # 回测任务进程ID，None表示未启动或进程已退出
        self._procid = None
        # 事件接收器引用，用于接收回测事件
        self._evt_receiver = None

    def __check__(self):
        """
        进程检查方法（私有方法）
        
        后台线程函数，持续检查回测任务进程是否还在运行。
        当进程退出时，触发停止回调。
        """
        # 持续运行，直到进程退出
        while True:
            # 等待1秒，避免CPU占用过高
            time.sleep(1)
            # 获取所有进程ID列表（实际上这里不需要，因为已经有进程ID了）
            pids = psutil.pids()
            # 如果进程还存在，继续检查
            if psutil.pid_exists(self._procid):
                continue
            else:
                # 如果进程已退出，打印日志
                print("%s process %d finished" % (self.btid, self._procid))
                # 如果事件回调接口存在，调用停止回调
                if self.sink is not None:
                    self.sink.on_stop(self.user, self.straid, self.btid)
                # 退出循环
                break

    def run(self):
        """
        启动回测任务
        
        创建事件接收器，启动回测进程，并启动进程监控线程。
        如果任务已经启动，则直接返回。
        """
        # 如果任务已经启动，直接返回
        if self._state != 0:
            return

        # 创建回测事件接收器，用于接收回测事件
        self._evt_receiver = BtEventReceiver(url=self._mq_url, logger=self.logger, sink=self)
        # 启动事件接收器
        self._evt_receiver.run()
        # 记录事件接收器启动日志
        self.logger.info("回测%s开始接收%s的通知信息" % (self.btid, self._mq_url))

        try:
            # 构建回测脚本的完整路径
            fullPath = os.path.join(self.folder, "runBT.py")
            # 根据操作系统类型启动回测进程
            if isWindows():
                # Windows系统：使用CREATE_NEW_CONSOLE标志创建新控制台窗口
                self._procid = subprocess.Popen([sys.executable, fullPath],  # 需要执行的文件路径
                                cwd=self.folder, creationflags=subprocess.CREATE_NEW_CONSOLE).pid
            else:
                # Linux/Unix系统：直接启动进程
                self._procid = subprocess.Popen([sys.executable, fullPath],  # 需要执行的文件路径
                                cwd=self.folder).pid

            # 更新命令行字符串缓存
            self._cmd_line = sys.executable + " " + fullPath
        except:
            # 如果启动失败，记录异常日志
            self.logger.info("回测%s启动异常" % (self.btid))

        # 更新任务状态为已启动
        self._state = 1

        # 记录启动成功日志
        self.logger.info("回测%s的已启动，进程ID: %d" % (self.btid, self._procid))

        # 创建进程监控线程，用于监控回测进程状态
        self.watcher = threading.Thread(target=self.__check__, name=self.btid, daemon=True)
        # 启动监控线程
        self.watcher.start()

    @property
    def cmd_line(self) -> str:
        """
        获取回测任务命令行字符串（属性方法）
        
        根据Python解释器路径和回测脚本路径生成完整的命令行字符串。
        使用缓存机制，首次调用时生成并缓存，后续直接返回缓存值。
        
        @return: 完整的命令行字符串
        """
        # 构建回测脚本的完整路径
        fullPath = os.path.join(self.folder, "runBT.py")
        # 如果命令行字符串未缓存，生成并缓存
        if self._cmd_line is None:
            # 拼接Python解释器路径和脚本路径
            self._cmd_line = sys.executable + " " + fullPath
        # 返回命令行字符串
        return self._cmd_line

    def is_running(self, pids) -> bool:
        """
        检查回测任务是否正在运行
        
        通过检查进程ID是否存在，或遍历所有进程查找匹配的命令行来判断任务是否运行。
        如果找到匹配的进程，会更新进程ID并创建事件接收器。
        
        @param pids: 所有进程ID列表，用于查找匹配的进程
        @return: 如果任务正在运行返回True，否则返回False
        """
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
                        # 记录挂载成功日志
                        self.logger.info("回测%s挂载成功，进程ID: %d" % (self.btid, self._procid))

                        # 如果消息队列URL不为空，创建事件接收器
                        if self._mq_url != '':
                            # 创建回测事件接收器
                            self._evt_receiver = BtEventReceiver(url=self._mq_url, logger=self.logger, sink=self)
                            self._evt_receiver.run()
                            self.logger.info("回测%s开始接收%s的通知信息" % (self.btid, self._mq_url))

                        # 创建进程监控线程
                        self.watcher = threading.Thread(target=self.__check__, name=self.btid, daemon=True)
                        # 启动监控线程（注意：这里应该用start()而不是run()）
                        self.watcher.run()
                except:
                    # 如果获取进程信息失败，继续查找下一个进程
                    pass
            return False

        return True

    # ========== BtEventSink接口实现 ==========
    def on_begin(self):
        """
        回测开始事件回调函数（实现BtEventSink接口）
        
        当回测开始时，会调用此函数。
        将回测开始事件转发给回测任务事件回调接口。
        """
        if self.sink is not None:
            self.sink.on_start(self.user, self.straid, self.btid)

    def on_finish(self):
        """
        回测结束事件回调函数（实现BtEventSink接口）
        
        当回测结束时，会调用此函数。
        当前实现为空，可以根据需要添加处理逻辑。
        """
        pass

    def on_state(self, statInfo:dict):
        """
        回测状态更新事件回调函数（实现BtEventSink接口）
        
        当回测状态更新时，会调用此函数。
        将回测状态更新事件转发给回测任务事件回调接口。
        
        @param statInfo: 状态信息字典，包含回测的当前状态（进度、当前日期等）
        """
        if self.sink is not None:
            self.sink.on_state(self.user, self.straid, self.btid, statInfo)
        # 打印状态信息（用于调试）
        print(statInfo)

    def on_fund(self, fundInfo:dict):
        """
        回测资金变化事件回调函数（实现BtEventSink接口）
        
        当回测资金发生变化时，会调用此函数。
        将回测资金变化事件转发给回测任务事件回调接口。
        
        @param fundInfo: 资金信息字典，包含资金变化的详细信息（日期、权益、盈亏等）
        """
        if self.sink is not None:
            self.sink.on_fund(self.user, self.straid, self.btid, fundInfo)
        # 打印资金信息（用于调试）
        print(fundInfo)


class WtBtMon(BtTaskSink):
    """
    回测管理器类
    
    管理用户的策略和回测任务。继承自BtTaskSink，用于处理回测任务的事件。
    
    主要功能：
    1. 策略管理：添加、查询、删除用户的策略
    2. 回测任务管理：创建、启动、查询回测任务
    3. 数据持久化：将策略和回测信息保存到文件系统
    4. 回测结果查询：查询回测任务的执行结果和统计信息
    5. 任务监控：监控回测任务的运行状态
    """
    
    def __init__(self, deploy_folder:str, dtServo:WtDtServo = None, logger:WtLogger = None):
        """
        初始化回测管理器
        
        创建回测管理器实例，设置部署文件夹、数据服务器和日志记录器。
        
        @param deploy_folder: 部署文件夹路径（字符串），用于存储用户数据和回测结果
        @param dtServo: 数据服务器实例（WtDtServo，默认None），用于提供历史数据服务
        @param logger: 日志记录器（WtLogger，默认None），用于记录日志
        """
        # 保存部署文件夹路径
        self.path = deploy_folder
        # 用户策略字典，key为用户名，value为该用户的策略字典（key为策略ID，value为策略信息）
        self.user_stras = dict()
        # 用户回测字典，key为用户名，value为该用户的回测字典（key为回测ID，value为回测信息）
        self.user_bts = dict()
        # 保存日志记录器引用
        self.logger = logger
        # 保存数据服务器引用
        self.dt_servo = dtServo

        # 任务信息字典，key为回测任务ID，value为任务信息
        self.task_infos = dict()
        # 任务映射字典，key为回测任务ID，value为WtBtTask实例
        self.task_map = dict()

        # 加载所有任务
        self.__load_tasks__()

    def __load_user_data__(self, user:str):
        """
        加载用户数据（私有方法）
        
        从文件系统加载指定用户的策略和回测数据。
        如果用户文件夹或标记文件不存在，则返回False。
        
        @param user: 用户名（字符串），要加载数据的用户
        @return: 如果加载成功返回True，否则返回False
        """
        # 构建用户文件夹路径
        folder = os.path.join(self.path, user)
        # 如果用户文件夹不存在，创建文件夹
        if not os.path.exists(folder):
            os.mkdir(folder)

        # 构建标记文件路径（marker.json存储用户的策略和回测列表）
        filepath = os.path.join(folder, "marker.json")
        # 如果标记文件不存在，返回False
        if not os.path.exists(filepath):
            return False

        # 读取标记文件内容
        f = open(filepath, "r")
        content = f.read()
        f.close()

        # 解析JSON内容
        obj = json.loads(content)
        # 加载用户策略字典
        self.user_stras[user] = obj["strategies"]
        # 加载用户回测字典
        self.user_bts[user] = obj["backtests"]
        return True

    def __save_user_data__(self, user):
        """
        保存用户数据（私有方法）
        
        将指定用户的策略和回测数据保存到文件系统。
        
        @param user: 用户名（字符串），要保存数据的用户
        @return: 如果保存成功返回True
        """
        # 构建用户文件夹路径
        folder = os.path.join(self.path, user)
        # 如果用户文件夹不存在，创建文件夹
        if not os.path.exists(folder):
            os.mkdir(folder)

        # 创建数据对象
        obj = {
            "strategies":{},
            "backtests":{}
        }

        # 如果用户有策略数据，添加到对象中
        if user in self.user_stras:
            obj["strategies"] = self.user_stras[user]

        # 如果用户有回测数据，添加到对象中
        if user in self.user_bts:
            obj["backtests"] = self.user_bts[user]

        # 构建标记文件路径
        filepath = os.path.join(folder, "marker.json")
        # 打开文件并写入JSON数据
        f = open(filepath, "w")
        f.write(json.dumps(obj, indent=4, ensure_ascii=False))
        f.close()
        return True

    def get_strategies(self, user:str) -> list:
        """
        获取用户的所有策略
        
        返回指定用户的所有策略列表。如果用户数据未加载，会先加载用户数据。
        
        @param user: 用户名（字符串），要查询策略的用户
        @return: 策略信息列表，如果用户不存在则返回None
        """
        # 如果用户策略数据未加载，先加载用户数据
        if user not in self.user_stras:
            bSucc = self.__load_user_data__(user)
        
            # 如果加载失败，返回None
            if not bSucc:
                return None

        # 创建策略列表
        ay = list()
        # 遍历用户的所有策略，添加到列表
        for straid in self.user_stras[user]:
            ay.append(self.user_stras[user][straid])
        return ay

    def add_strategy(self, user:str, name:str) -> dict:
        """
        添加策略
        
        为用户添加一个新策略，生成唯一的策略ID，并初始化策略信息。
        
        @param user: 用户名（字符串），要添加策略的用户
        @param name: 策略名称（字符串），策略的显示名称
        @return: 策略信息字典，包含策略ID、名称和性能指标
        """
        # 如果用户策略数据未加载，先加载用户数据
        if user not in self.user_stras:
            self.__load_user_data__(user)

        # 如果用户策略字典不存在，创建空字典
        if user not in self.user_stras:
            self.user_stras[user] = dict()

        # 生成唯一的策略ID
        straid = gen_straid(user)
        # 创建策略信息字典，包含策略ID、名称和性能指标
        self.user_stras[user][straid] = {
            "id":straid,
            "name":name,
            "perform":{
                "days": 0,
                "total_return": 0,
                "annual_return": 0,
                "win_rate": 0,
                "max_falldown": 0,  # 最大回撤
                "max_profratio": 0,  # 最大盈利比例
                "std": 0,  # 标准差
                "down_std": 0,  # 下行标准差
                "sharpe_ratio": 0,  # 夏普比率
                "sortino_ratio": 0,  # 索提诺比率
                "calmar_ratio": 0  # 卡玛比率
            }
        }

        # 构建策略文件夹路径
        folder = os.path.join(self.path, user, straid)
        # 如果策略文件夹不存在，创建文件夹
        if not os.path.exists(folder):
            os.mkdir(folder)

        # 构建策略代码文件路径
        fname = os.path.join(folder, "MyStrategy.py")
        # 构建模板文件路径
        srcfname = os.path.join(self.path, "template/MyStrategy.py")
        # 从模板文件复制策略代码文件
        shutil.copyfile(srcfname, fname)

        # 保存用户数据
        self.__save_user_data__(user)

        # 返回策略信息字典
        return self.user_stras[user][straid]

    def del_strategy(self, user:str, straid:str):
        """
        删除策略
        
        删除指定用户的策略。策略文件夹会被移动到删除文件夹（.del），而不是直接删除。
        如果策略不存在，则直接返回True。
        
        @param user: 用户名（字符串），要删除策略的用户
        @param straid: 策略ID（字符串），要删除的策略标识
        @return: 如果删除成功返回True，否则返回False
        """
        # 如果用户回测数据未加载，先加载用户数据（注意：这里应该是user_stras而不是user_bts）
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回False
            if not bSucc:
                return False

        # 如果策略不存在，返回True（表示删除成功，因为目标不存在）
        if straid not in self.user_stras[user]:
            return True

        # 构建策略文件夹路径
        folder = os.path.join(self.path, user, straid)
        # 如果策略文件夹不存在，返回True（表示删除成功）
        if not os.path.exists(folder):
            return True

        # 构建删除文件夹路径（.del文件夹用于存放已删除的策略）
        delFolder = os.path.join(self.path, user, ".del")
        # 如果删除文件夹不存在，创建文件夹
        if not os.path.exists(delFolder):
            os.mkdir(delFolder)
        # 将策略文件夹移动到删除文件夹
        shutil.move(folder, delFolder)
        # 从策略字典中移除策略
        self.user_stras[user].pop(straid)
        # 保存用户数据
        self.__save_user_data__(user)
        return True
    
    def has_strategy(self, user:str, straid:str, btid:str = None) -> bool:
        """
        检查策略或回测是否存在
        
        检查指定用户的策略或回测是否存在。
        如果btid为None，则检查策略；否则检查回测。
        
        @param user: 用户名（字符串），要检查的用户
        @param straid: 策略ID（字符串），要检查的策略标识
        @param btid: 回测任务ID（字符串，默认None），如果提供则检查回测，否则检查策略
        @return: 如果存在返回True，否则返回False
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回False
            if not bSucc:
                return False

        # 如果btid为None，检查策略是否存在
        if btid is None:
            return straid in self.user_stras[user]
        else:
            # 否则检查回测是否存在
            return btid in self.user_bts[user]

    def get_strategy_code(self, user:str, straid:str, btid:str = None) -> str:
        """
        获取策略代码
        
        读取策略的Python代码文件内容。
        如果btid为None，则读取策略代码；否则读取回测任务的策略代码。
        
        @param user: 用户名（字符串），策略所属的用户
        @param straid: 策略ID（字符串），策略标识
        @param btid: 回测任务ID（字符串，默认None），如果提供则读取回测任务的策略代码
        @return: 策略代码内容（字符串），如果文件不存在则返回None
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回None
            if not bSucc:
                return None

        # 如果btid为None，读取策略代码
        if btid is None:
            # 构建策略代码文件路径
            path = os.path.join(self.path, user, straid, "MyStrategy.py")
            # 如果文件不存在，返回None
            if not os.path.exists(path):
                return None

            # 读取文件内容（使用UTF-8编码）
            f = open(path, "r", encoding="UTF-8")
            content = f.read()
            f.close()
            return content
        else:
            # 如果btid不为None，读取回测任务的策略代码
            # 获取用户的回测字典
            thisBts = self.user_bts[user]
            # 如果回测不存在，返回None
            if btid not in thisBts:
                return None

            # 构建回测任务的策略代码文件路径
            bt_path = os.path.join(self.path, "%s/%s/backtests/%s/runBT.py" % (user, straid, btid))
            # 读取文件内容
            f = open(bt_path, "r")
            content = f.read()
            f.close()
            return content

    def set_strategy_code(self, user:str, straid:str, content:str) -> bool:
        """
        设置策略代码
        
        将策略的Python代码保存到文件。
        
        @param user: 用户名（字符串），策略所属的用户
        @param straid: 策略ID（字符串），策略标识
        @param content: 策略代码内容（字符串），要保存的代码
        @return: 如果保存成功返回True，如果文件不存在则返回None
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回False
            if not bSucc:
                return False

        # 构建策略代码文件路径
        path = os.path.join(self.path, user, straid, "MyStrategy.py")
        # 如果文件不存在，返回None
        if not os.path.exists(path):
            return None

        # 写入文件内容（使用UTF-8编码）
        f = open(path, "w", encoding="UTF-8")
        f.write(content)
        f.close()
        return True

    def get_backtests(self, user:str, straid:str) -> list:
        """
        获取用户的所有回测
        
        返回指定用户的所有回测列表。如果用户数据未加载，会先加载用户数据。
        
        @param user: 用户名（字符串），要查询回测的用户
        @param straid: 策略ID（字符串），策略标识（此参数在当前实现中未使用）
        @return: 回测信息列表，如果用户不存在则返回None
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回None
            if not bSucc:
                return None

        # 如果用户回测字典不存在，返回None
        if user not in self.user_bts:
            return None

        # 创建回测列表
        ay = list()
        # 遍历用户的所有回测，添加到列表
        for btid in self.user_bts[user]:
            ay.append(self.user_bts[user][btid])

        return ay

    def del_backtest(self, user:str, btid:str):
        """
        删除回测
        
        删除指定用户的回测记录。只从内存和标记文件中删除，不回删除回测结果文件。
        
        @param user: 用户名（字符串），要删除回测的用户
        @param btid: 回测任务ID（字符串），要删除的回测标识
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，直接返回
            if not bSucc:
                return

        # 如果用户回测字典不存在，直接返回
        if user not in self.user_bts:
            return

        # 如果回测存在，从字典中移除
        if btid in self.user_bts[user]:
            self.user_bts[user].pop(btid)
            # 记录删除日志
            self.logger.info("Backtest %s of %s deleted" % (btid, user))

            # 保存用户数据
            self.__save_user_data__(user)

    def get_bt_funds(self, user:str, straid:str, btid:str) -> list:
        """
        获取回测资金曲线数据
        
        读取回测任务的资金曲线CSV文件，解析为字典列表。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @return: 资金曲线数据列表，每个元素包含日期、平仓盈亏、浮动盈亏、动态权益、手续费等信息
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回None
            if not bSucc:
                return None

        # 获取用户的回测字典
        thisBts = self.user_bts[user]
        # 如果回测不存在，返回None
        if btid not in thisBts:
            return None

        # 构建资金曲线CSV文件路径
        filename = "%s/%s/backtests/%s/outputs_bt/%s/funds.csv" % (user, straid, btid, btid)
        filename = os.path.join(self.path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取文件内容
        f = open(filename, "r")
        lines = f.readlines()
        f.close()
        # 跳过第一行（表头）
        lines = lines[1:]

        # 创建资金数据列表
        funds = list()
        # 遍历所有行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")
            # 如果单元格数量超过10个，跳过（可能是格式错误）
            if len(cells) > 10:
                continue

            # 创建资金数据项
            tItem = {
                "date": int(cells[0]),  # 日期
                "closeprofit": float(cells[1]),  # 平仓盈亏
                "dynprofit": float(cells[2]),  # 浮动盈亏
                "dynbalance": float(cells[3]),  # 动态权益
                "fee": 0  # 手续费，默认为0
            }

            # 如果单元格数量大于4，读取手续费
            if len(cells) > 4:
                tItem["fee"] = float(cells[4])

            # 添加到资金数据列表
            funds.append(tItem)
        
        return funds

    def get_bt_trades(self, user:str, straid:str, btid:str) -> list:
        """
        获取回测交易记录数据
        
        读取回测任务的交易记录CSV文件，解析为字典列表。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @return: 交易记录数据列表，每个元素包含合约代码、时间、方向、开平、价格、数量、标记、手续费等信息
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回None
            if not bSucc:
                return None

        # 获取用户的回测字典
        thisBts = self.user_bts[user]
        # 如果回测不存在，返回None
        if btid not in thisBts:
            return None

        # 构建交易记录CSV文件路径
        filename = "%s/%s/backtests/%s/outputs_bt/%s/trades.csv" % (user, straid, btid, btid)
        filename = os.path.join(self.path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取文件内容
        f = open(filename, "r")
        lines = f.readlines()
        f.close()
        # 跳过第一行（表头）
        lines = lines[1:]

        # 创建交易记录列表
        items = list()
        # 遍历所有行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")
            # 如果单元格数量超过10个，跳过（可能是格式错误）
            if len(cells) > 10:
                continue

            # 创建交易记录项
            item = {
                "code": cells[0],  # 合约代码
                "time": int(cells[1]),  # 交易时间
                "direction": cells[2],  # 交易方向（买入/卖出）
                "offset": cells[3],  # 开平标志（开仓/平仓）
                "price": float(cells[4]),  # 成交价格
                "volume": float(cells[5]),  # 成交数量
                "tag": cells[6],  # 用户标记
                "fee": 0  # 手续费，默认为0
            }

            # 如果单元格数量大于7，读取手续费
            if len(cells) > 7:
                item["fee"] = float(cells[7])

            # 注意：这里代码有重复，如果单元格数量大于4也会设置手续费，但应该只设置一次
            if len(cells) > 4:
                item["fee"] = float(cells[4])

            # 添加到交易记录列表
            items.append(item)
        
        return items

    def get_bt_rounds(self, user:str, straid:str, btid:str) -> list:
        """
        获取回测交易回合数据
        
        读取回测任务的交易回合CSV文件，解析为字典列表。
        交易回合表示一次完整的开仓到平仓过程。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @return: 交易回合数据列表，每个元素包含合约代码、方向、开仓时间、开仓价、平仓时间、平仓价、数量、盈亏等信息
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回None
            if not bSucc:
                return None

        # 获取用户的回测字典
        thisBts = self.user_bts[user]
        # 如果回测不存在，返回None
        if btid not in thisBts:
            return None

        # 构建交易回合CSV文件路径
        filename = "%s/%s/backtests/%s/outputs_bt/%s/closes.csv" % (user, straid, btid, btid)
        filename = os.path.join(self.path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取文件内容
        f = open(filename, "r")
        lines = f.readlines()
        f.close()
        # 跳过第一行（表头）
        lines = lines[1:]

        # 创建交易回合列表
        items = list()
        # 遍历所有行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")

            # 创建交易回合项
            item = {
                "code": cells[0],  # 合约代码
                "direct": cells[1],  # 交易方向（多/空）
                "opentime": int(cells[2]),  # 开仓时间
                "openprice": float(cells[3]),  # 开仓价格
                "closetime": int(cells[4]),  # 平仓时间
                "closeprice": float(cells[5]),  # 平仓价格
                "qty": float(cells[6]),  # 交易数量
                "profit": float(cells[7]),  # 盈亏
                "maxprofit": float(cells[8]),  # 最大盈利
                "maxloss": float(cells[9]),  # 最大亏损
                "entertag": cells[11],  # 进场标记
                "exittag": cells[12]  # 出场标记
            }

            # 添加到交易回合列表
            items.append(item)
        
        return items

    def get_bt_signals(self, user:str, straid:str, btid:str) -> list:
        """
        获取回测信号数据
        
        读取回测任务的信号CSV文件，解析为字典列表。
        信号表示策略产生的交易信号（如条件单触发等）。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @return: 信号数据列表，每个元素包含合约代码、目标价格、信号价格、生成时间、标记等信息
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回None
            if not bSucc:
                return None

        # 获取用户的回测字典
        thisBts = self.user_bts[user]
        # 如果回测不存在，返回None
        if btid not in thisBts:
            return None

        # 构建信号CSV文件路径
        filename = "%s/%s/backtests/%s/outputs_bt/%s/signals.csv" % (user, straid, btid, btid)
        filename = os.path.join(self.path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取文件内容
        f = open(filename, "r")
        lines = f.readlines()
        f.close()
        # 跳过第一行（表头）
        lines = lines[1:]

        # 创建信号列表
        items = list()
        # 遍历所有行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")
            # 如果单元格数量超过10个，跳过（可能是格式错误）
            if len(cells) > 10:
                continue

            # 创建信号项
            item = {
                "code": cells[0],  # 合约代码
                "target": float(cells[1]),  # 目标价格
                "sigprice": float(cells[2]),  # 信号价格
                "gentime": cells[3],  # 生成时间
                "tag": cells[4]  # 用户标记
            }

            # 添加到信号列表
            items.append(item)
        
        return items

    def get_bt_summary(self, user:str, straid:str, btid:str) -> list:
        """
        获取回测摘要数据
        
        读取回测任务的摘要JSON文件，包含回测的统计信息（收益率、胜率、最大回撤等）。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @return: 回测摘要字典，包含各种性能指标，如果文件不存在则返回None
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回None
            if not bSucc:
                return None

        # 获取用户的回测字典
        thisBts = self.user_bts[user]
        # 如果回测不存在，返回None
        if btid not in thisBts:
            return None

        # 构建摘要JSON文件路径
        filename = "%s/%s/backtests/%s/outputs_bt/%s/summary.json" % (user, straid, btid, btid)
        filename = os.path.join(self.path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取文件内容
        f = open(filename, "r")
        content = f.read()
        f.close()

        # 解析JSON内容
        obj = json.loads(content)
        return obj

    def get_bt_state(self, user:str, straid:str, btid:str) -> dict:
        """
        获取回测状态数据
        
        读取回测任务的状态JSON文件，包含回测的当前状态（进度、当前日期等）。
        如果状态已缓存，直接返回缓存的状态。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @return: 回测状态字典，包含回测的当前状态信息，如果文件不存在则返回None
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回None
            if not bSucc:
                return None

        # 获取用户的回测字典
        thisBts = self.user_bts[user]
        # 如果回测不存在，返回None
        if btid not in thisBts:
            return None

        # 构建状态JSON文件路径
        filename = "%s/%s/backtests/%s/outputs_bt/%s/btenv.json" % (user, straid, btid, btid)
        filename = os.path.join(self.path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取文件内容
        f = open(filename, "r")
        content = f.read()
        f.close()

        # 解析JSON内容并更新回测字典中的状态
        thisBts[btid]["state"] = json.loads(content)

        # 返回状态字典
        return thisBts[btid]["state"]

    def update_bt_state(self, user:str, straid:str, btid:str, stateObj:dict):
        """
        更新回测状态数据
        
        更新回测任务的状态信息。只更新内存中的状态，不保存到文件。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @param stateObj: 状态对象字典，包含要更新的状态信息
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回None
            if not bSucc:
                return None

        # 获取用户的回测字典
        thisBts = self.user_bts[user]
        # 如果回测不存在，返回None
        if btid not in thisBts:
            return None

        # 更新回测状态
        thisBts[btid]["state"] = stateObj

    def get_bt_kline(self, user:str, straid:str, btid:str) -> list:
        """
        获取回测K线数据
        
        从数据服务器获取回测任务使用的K线数据。
        如果K线数据已缓存，直接返回缓存的数据；否则从数据服务器加载并缓存。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @return: K线数据列表，每个元素包含时间、开盘价、最高价、最低价、收盘价、成交量等信息
        """
        # 如果数据服务器未设置，返回None
        if self.dt_servo is None:
            return None

        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            bSucc = self.__load_user_data__(user)

            # 如果加载失败，返回None
            if not bSucc:
                return None
        
        # 获取回测状态
        btState = self.get_bt_state(user, straid, btid)
        # 如果状态不存在，返回None
        if btState is None:
            return None

        # 获取用户的回测字典
        thisBts = self.user_bts[user]
        # 如果K线数据未缓存，从数据服务器加载
        if "kline" not in thisBts[btid]:
            # 从状态中获取K线参数
            code = btState["code"]  # 合约代码
            period = btState["period"]  # K线周期
            stime = btState["stime"]  # 开始时间
            etime = btState["etime"]  # 结束时间
            # 从数据服务器获取K线数据
            barList = self.dt_servo.get_bars(stdCode=code, period=period, fromTime=stime, endTime=etime)
            # 如果获取失败，返回None
            if barList is None:
                return None

            # 创建K线数据列表
            bars = list()
            # 遍历所有K线，转换为字典格式
            for realBar in barList:
                bar = dict()
                # 如果是日线周期，使用日期作为时间
                if period[0] == 'd':
                    bar["time"] = realBar.date
                else:
                    # 否则使用时间戳格式（1990年作为基准年份）
                    bar["time"] = 1990*100000000 + realBar.time
                    bar["bartime"] = bar["time"]
                    bar["open"] = realBar.open  # 开盘价
                    bar["high"] = realBar.high  # 最高价
                    bar["low"] = realBar.low  # 最低价
                    bar["close"] = realBar.close  # 收盘价
                    bar["volume"] = realBar.vol  # 成交量
                bars.append(bar)
            # 缓存K线数据
            thisBts[btid]["kline"] = bars

        # 返回K线数据
        return thisBts[btid]["kline"]

    def run_backtest(self, user:str, straid:str, fromTime:int, endTime:int, capital:float, slippage:int=0) -> dict:
        """
        运行回测任务
        
        创建并启动一个新的回测任务。会创建回测目录，复制策略文件和配置文件，
        生成回测脚本，并启动回测进程。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），要回测的策略标识
        @param fromTime: 回测开始时间（整数），时间戳格式
        @param endTime: 回测结束时间（整数），时间戳格式
        @param capital: 初始资金（浮点数），回测的初始资金
        @param slippage: 滑点（整数，默认0），交易滑点，单位为最小价格变动单位
        @return: 回测信息字典，包含回测ID、资金、运行时间、状态、性能指标等
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            self.__load_user_data__(user)

        # 如果用户回测字典不存在，创建空字典
        if user not in self.user_bts:
            self.user_bts[user] = dict()
            
        # 生成唯一的回测任务ID
        btid = gen_btid(user, straid)

        # ========== 创建回测目录 ==========
        # 构建回测目录路径
        folder = os.path.join(self.path, user, straid, "backtests")
        # 如果回测目录不存在，创建目录
        if not os.path.exists(folder):
            os.mkdir(folder)
        
        # 构建回测任务目录路径
        folder = os.path.join(folder, btid)
        # 创建回测任务目录
        os.mkdir(folder)

        # ========== 复制策略文件 ==========
        # 构建源策略文件路径
        old_path = os.path.join(self.path, user, straid, "MyStrategy.py")
        # 构建目标策略文件路径
        new_path = os.path.join(folder, "MyStrategy.py")
        # 复制策略文件到回测目录
        shutil.copyfile(old_path, new_path)

        # ========== 初始化配置文件 ==========
        # 复制回测配置文件，并替换回测任务ID
        old_path = os.path.join(self.path, "template/configbt.json")
        new_path = os.path.join(folder, "configbt.json")
        # 读取模板文件内容
        f = open(old_path, "r", encoding="UTF-8")
        content = f.read()
        f.close()
        # 替换回测任务ID占位符
        content = content.replace("$BTID$", btid)
        # 写入配置文件
        f = open(new_path, "w", encoding="UTF-8")
        f.write(content)
        f.close()

        # 复制日志配置文件
        old_path = os.path.join(self.path, "template/logcfgbt.json")
        new_path = os.path.join(folder, "logcfgbt.json")
        shutil.copyfile(old_path, new_path)

        # 复制手续费配置文件
        old_path = os.path.join(self.path, "template/fees.json")
        new_path = os.path.join(folder, "fees.json")
        shutil.copyfile(old_path, new_path)

        # ========== 生成回测脚本 ==========
        # 复制回测脚本模板
        old_path = os.path.join(self.path, "template/runBT.py")
        new_path = os.path.join(folder, "runBT.py")

        # 读取模板文件内容
        f = open(old_path, "r", encoding="UTF-8")
        content = f.read()
        f.close()
        # 替换模板中的占位符
        content = content.replace("$FROMTIME$", str(fromTime))  # 开始时间
        content = content.replace("$ENDTIME$", str(endTime))  # 结束时间
        content = content.replace("$STRAID$", btid)  # 策略ID（实际是回测任务ID）
        content = content.replace("$CAPITAL$", str(capital))  # 初始资金
        content = content.replace("$SLIPPAGE$", str(slippage))  # 滑点
        # 写入回测脚本
        f = open(new_path, "w", encoding="UTF-8")
        f.write(content)
        f.close()

        # ========== 创建回测信息 ==========
        # 创建回测信息字典
        btInfo = {
            "id":btid,  # 回测任务ID
            "capital":capital,  # 初始资金
            "runtime":datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S"),  # 运行时间
            "state":{
                "code": "",  # 合约代码（初始为空）
                "period": "",  # K线周期（初始为空）
                "stime": fromTime,  # 开始时间
                "etime": endTime,  # 结束时间
                "progress": 0,  # 回测进度（初始为0）
                "elapse": 0  # 已用时间（初始为0）
            },
            "perform":{
                "days": 0,  # 回测天数
                "total_return": 0,  # 总收益率
                "annual_return": 0,  # 年化收益率
                "win_rate": 0,  # 胜率
                "max_falldown": 0,  # 最大回撤
                "max_profratio": 0,  # 最大盈利比例
                "std": 0,  # 标准差
                "down_std": 0,  # 下行标准差
                "sharpe_ratio": 0,  # 夏普比率
                "sortino_ratio": 0,  # 索提诺比率
                "calmar_ratio": 0  # 卡玛比率
            }
        }

        # 将回测信息添加到用户回测字典
        self.user_bts[user][btid] = btInfo

        # 保存用户数据
        self.__save_user_data__(user)

        # ========== 启动回测任务 ==========
        # 创建回测任务实例
        btTask = WtBtTask(user, straid, btid, folder, self.logger, sink=self)
        # 启动回测任务
        btTask.run()

        # 将回测任务添加到任务映射字典
        self.task_map[btid] = btTask

        # ========== 保存任务信息 ==========
        # 创建任务信息字典（用于持久化，重启后可以恢复任务）
        taskInfo = {
            "user":user,  # 用户名
            "straid":straid,  # 策略ID
            "btid":btid,  # 回测任务ID
            "folder":folder  # 回测目录路径
        }
        # 将任务信息添加到任务信息字典
        self.task_infos[btid]= taskInfo
        # 保存任务信息到文件
        self.__save_tasks__()

        # 返回回测信息
        return btInfo

    def __update_bt_result__(self, user:str, straid:str, btid:str):
        """
        更新回测结果（私有方法）
        
        更新回测任务的状态和性能指标，并同步更新策略的性能指标。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        """
        # 如果用户回测数据未加载，先加载用户数据
        if user not in self.user_bts:
            self.__load_user_data__(user)

        # 如果用户回测字典不存在，创建空字典
        if user not in self.user_bts:
            self.user_bts[user] = dict()

        # 更新回测状态
        stateObj = self.get_bt_state(user, straid, btid)
        self.user_bts[user][btid]["state"] = stateObj

        # 更新回测结果摘要
        summaryObj = self.get_bt_summary(user, straid, btid)
        # 更新回测任务的性能指标
        self.user_bts[user][btid]["perform"] = summaryObj
        # 同步更新策略的性能指标
        self.user_stras[user][straid]["perform"] = summaryObj

        # 保存用户数据
        self.__save_user_data__(user)
    
    def __save_tasks__(self):
        """
        保存任务信息（私有方法）
        
        将任务信息字典保存到文件系统，用于持久化。
        重启后可以通过__load_tasks__方法恢复任务。
        """
        # 获取任务信息字典
        obj = self.task_infos

        # 构建任务信息文件路径
        filename = os.path.join(self.path, "tasks.json")
        # 打开文件并写入JSON数据
        f = open(filename, "w")
        f.write(json.dumps(obj, indent=4))
        f.close()

    def __load_tasks__(self):
        """
        加载任务信息（私有方法）
        
        从文件系统加载任务信息，恢复之前运行的回测任务。
        如果任务文件不存在，则直接返回。
        """
        # 构建任务信息文件路径
        filename = os.path.join(self.path, "tasks.json")
        # 如果任务文件不存在，直接返回
        if not os.path.exists(filename):
            return

        # 读取任务文件内容
        f = open(filename, "r")
        content = f.read()
        f.close()

        # 解析JSON内容
        task_infos = json.loads(content)
        # 获取所有进程ID列表
        pids = psutil.pids()
        # 遍历所有任务信息
        for btid in task_infos:
            # 复制任务信息字典
            tInfo = task_infos[btid].copy()
            # 添加日志记录器到任务信息
            tInfo["logger"] = self.logger
            # 创建回测任务实例（使用关键字参数展开）
            btTask = WtBtTask(**tInfo)

            # 检查任务是否正在运行
            if btTask.is_running(pids):
                # 如果任务正在运行，恢复任务映射
                self.task_map[btid] = btTask
                self.task_infos[btid] = task_infos[btid]
                # 记录任务恢复日志
                self.logger.info("回测任务%s已恢复" % (btid))
            else:
                # 如果任务未运行，说明任务已执行完成，更新回测结果
                self.__update_bt_result__(tInfo["user"], tInfo["straid"], btid)
        
        # 保存任务信息（移除已完成的任务）
        self.__save_tasks__()
            

    # ========== BtTaskSink接口实现 ==========
    def on_start(self, user:str, straid:str, btid:str):
        """
        回测任务启动事件回调函数（实现BtTaskSink接口）
        
        当回测任务启动时，会调用此函数。
        当前实现为空，可以根据需要添加处理逻辑。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        """
        pass

    def on_stop(self, user:str, straid:str, btid:str):
        """
        回测任务停止事件回调函数（实现BtTaskSink接口）
        
        当回测任务停止时，会调用此函数。
        更新回测结果，包括状态和性能指标。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        """
        # 更新回测结果（状态和性能指标）
        self.__update_bt_result__(user, straid, btid)

    def on_state(self, user:str, straid:str, btid:str, statInfo:dict):
        """
        回测任务状态更新事件回调函数（实现BtTaskSink接口）
        
        当回测任务状态更新时，会调用此函数。
        更新回测任务的状态信息。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @param statInfo: 状态信息字典，包含回测的当前状态（进度、当前日期等）
        """
        # 更新回测任务的状态
        self.user_bts[user][btid]["state"] = statInfo

    def on_fund(self, user:str, straid:str, btid:str, fundInfo:dict):
        """
        回测任务资金变化事件回调函数（实现BtTaskSink接口）
        
        当回测任务资金发生变化时，会调用此函数。
        当前实现为空，可以根据需要添加处理逻辑（如实时更新资金曲线等）。
        
        @param user: 用户名（字符串），回测任务的用户
        @param straid: 策略ID（字符串），回测的策略标识
        @param btid: 回测任务ID（字符串），回测任务的唯一标识
        @param fundInfo: 资金信息字典，包含资金变化的详细信息（日期、权益、盈亏等）
        """
        pass